"""AWS infrastructure for ChainMind's disruption-response workflow."""

from pathlib import Path

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import (
    aws_apigateway as apigateway,
)
from aws_cdk import (
    aws_dynamodb as dynamodb,
)
from aws_cdk import (
    aws_events as events,
)
from aws_cdk import (
    aws_events_targets as event_targets,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_s3 as s3,
)
from aws_cdk import (
    aws_stepfunctions as sfn,
)
from aws_cdk import (
    aws_stepfunctions_tasks as tasks,
)
from constructs import Construct


class ChainMindStack(Stack):
    """Define the API, event bus, four-agent state machine, and audit storage."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)
        chainmind_mode = str(self.node.try_get_context("chainmindMode") or "mock")
        if chainmind_mode not in {"mock", "aws"}:
            raise ValueError("Set CDK context chainmindMode to 'mock' or 'aws'.")
        bedrock_model_id = str(
            self.node.try_get_context("bedrockModelId") or "anthropic.claude-3-haiku-20240307-v1:0"
        )
        project_root = Path(__file__).resolve().parents[1]
        source = lambda_.Code.from_asset(
            str(project_root / "src"),
            exclude=["**/__pycache__/**", "**/*.pyc"],
        )

        # Shared DynamoDB event store: run snapshots and approval callback tokens.
        event_store = dynamodb.Table(
            self,
            "ChainMindEventStore",
            table_name="chainmind-events",
            partition_key=dynamodb.Attribute(name="run_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Private S3 storage for decision rationale and audit artifacts.
        artifacts = s3.Bucket(
            self,
            "ChainMindAuditArtifacts",
            bucket_name=None,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        def make_function(
            logical_id: str,
            handler: str,
            description: str,
            *,
            environment: dict[str, str] | None = None,
        ) -> lambda_.Function:
            return lambda_.Function(
                self,
                logical_id,
                runtime=lambda_.Runtime.PYTHON_3_12,
                handler=handler,
                code=source,
                memory_size=512,
                timeout=Duration.seconds(30),
                description=description,
                environment={
                    "CHAINMIND_MODE": chainmind_mode,
                    "CHAINMIND_AWS_REGION": self.region,
                    "CHAINMIND_BEDROCK_MODEL_ID": bedrock_model_id,
                    "CHAINMIND_EVENT_TABLE_NAME": event_store.table_name,
                    "CHAINMIND_ARTIFACT_BUCKET": artifacts.bucket_name,
                    **(environment or {}),
                },
            )

        # Stage 1: monitoring agent Lambda.
        monitoring = make_function(
            "MonitoringAgent",
            "chainmind.handlers.stages.monitoring",
            "Classify disruption severity and load stock coverage.",
        )
        # Stage 2: logistics agent Lambda.
        logistics = make_function(
            "LogisticsAgent",
            "chainmind.handlers.stages.logistics",
            "Calculate inventory coverage and production-loss exposure.",
        )
        # Stage 3: procurement agent Lambda.
        procurement = make_function(
            "ProcurementAgent",
            "chainmind.handlers.stages.procurement",
            "Compare alternative SAP Ariba supplier quotes.",
        )
        # Stage 4: orchestrator Lambda, including a private S3 rationale artifact.
        orchestrator = make_function(
            "OrchestratorAgent",
            "chainmind.handlers.stages.orchestrator",
            "Select the economic option and draft an approval-gated purchase order.",
        )
        artifacts.grant_put(orchestrator, "runs/*")

        # Approval callback Lambda stores Step Functions task tokens for the API workflow.
        approval_callback = make_function(
            "ApprovalCallback",
            "chainmind.handlers.approval.store_task_token",
            "Persist a Step Functions callback token for a human approval decision.",
        )
        event_store.grant_write_data(approval_callback)

        # Called only after the human callback returns decision=approve.
        execute_order = make_function(
            "ExecuteApprovedPurchaseOrder",
            "chainmind.handlers.stages.execute_approved",
            "Execute a draft only after the explicit approval callback.",
        )

        # FastAPI transport. The role has only the run-table and artifact permissions it needs.
        api_handler = make_function(
            "ChainMindApi",
            "chainmind.handlers.api.handler",
            "FastAPI API Gateway entrypoint for disruption and approval routes.",
        )
        event_store.grant_read_write_data(api_handler)
        artifacts.grant_put(api_handler, "runs/*")

        # Least-privilege Bedrock access for AWS-mode use; mocks remain the deploy default.
        model_arn = (
            f"arn:{self.partition}:bedrock:{self.region}::foundation-model/{bedrock_model_id}"
        )
        orchestrator.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[model_arn],
            )
        )

        # Step Functions: four agent stages followed by a callback-token approval wait.
        monitoring_task = tasks.LambdaInvoke(
            self,
            "MonitoringStage",
            lambda_function=monitoring,
            payload=sfn.TaskInput.from_object({"event": sfn.JsonPath.object_at("$.event")}),
            payload_response_only=True,
            result_path="$.monitoring",
        )
        monitoring_task.add_retry(
            errors=["States.TaskFailed"],
            interval=Duration.seconds(2),
            backoff_rate=2,
            max_attempts=3,
        )
        logistics_task = tasks.LambdaInvoke(
            self,
            "LogisticsStage",
            lambda_function=logistics,
            payload=sfn.TaskInput.from_object(
                {
                    "event": sfn.JsonPath.object_at("$.event"),
                    "inventory": sfn.JsonPath.object_at("$.monitoring.inventory"),
                }
            ),
            payload_response_only=True,
            result_path="$.logistics",
        )
        logistics_task.add_retry(
            errors=["States.TaskFailed"],
            interval=Duration.seconds(2),
            backoff_rate=2,
            max_attempts=3,
        )
        procurement_task = tasks.LambdaInvoke(
            self,
            "ProcurementStage",
            lambda_function=procurement,
            payload=sfn.TaskInput.from_object(
                {
                    "event": sfn.JsonPath.object_at("$.event"),
                    "inventory": sfn.JsonPath.object_at("$.monitoring.inventory"),
                    "logistics": sfn.JsonPath.object_at("$.logistics"),
                }
            ),
            payload_response_only=True,
            result_path="$.procurement",
        )
        procurement_task.add_retry(
            errors=["States.TaskFailed"],
            interval=Duration.seconds(2),
            backoff_rate=2,
            max_attempts=3,
        )
        orchestrator_task = tasks.LambdaInvoke(
            self,
            "OrchestratorStage",
            lambda_function=orchestrator,
            payload=sfn.TaskInput.from_object(
                {
                    "event": sfn.JsonPath.object_at("$.event"),
                    "inventory": sfn.JsonPath.object_at("$.monitoring.inventory"),
                    "logistics": sfn.JsonPath.object_at("$.logistics"),
                    "procurement": sfn.JsonPath.object_at("$.procurement"),
                }
            ),
            payload_response_only=True,
            result_path="$.orchestration",
        )
        orchestrator_task.add_retry(
            errors=["States.TaskFailed"],
            interval=Duration.seconds(2),
            backoff_rate=2,
            max_attempts=3,
        )
        approval_task = tasks.LambdaInvoke(
            self,
            "WaitForHumanApproval",
            lambda_function=approval_callback,
            integration_pattern=sfn.IntegrationPattern.WAIT_FOR_TASK_TOKEN,
            payload=sfn.TaskInput.from_object(
                {
                    "run_id": sfn.JsonPath.string_at("$.event.event_id"),
                    "taskToken": sfn.JsonPath.task_token,
                    "run": sfn.JsonPath.entire_payload,
                }
            ),
            result_path="$.approval",
            task_timeout=sfn.Timeout.duration(Duration.days(7)),
        )
        execute_task = tasks.LambdaInvoke(
            self,
            "ExecutePurchaseOrderAfterApproval",
            lambda_function=execute_order,
            payload=sfn.TaskInput.from_json_path_at("$"),
            payload_response_only=True,
            result_path="$.execution",
        )
        completed = sfn.Succeed(self, "PurchaseOrderProcessed")
        rejected = sfn.Succeed(self, "PurchaseOrderRejected")
        decision = sfn.Choice(self, "HumanDecision")
        decision.when(
            sfn.Condition.string_equals("$.approval.decision", "approve"),
            execute_task.next(completed),
        ).otherwise(rejected)
        non_significant = sfn.Succeed(self, "DisruptionNotSignificant")
        monitoring_gate = sfn.Choice(self, "DisruptionIsSignificant")
        monitoring_gate.when(
            sfn.Condition.boolean_equals("$.monitoring.result.significant", True),
            logistics_task.next(procurement_task)
            .next(orchestrator_task)
            .next(approval_task)
            .next(decision),
        ).otherwise(non_significant)
        workflow = monitoring_task.next(monitoring_gate)
        state_machine = sfn.StateMachine(
            self,
            "DisruptionResolutionStateMachine",
            definition_body=sfn.DefinitionBody.from_chainable(workflow),
            timeout=Duration.days(7),
            tracing_enabled=True,
        )

        # EventBridge receives external disruption events and starts the four-agent workflow.
        event_bus = events.EventBus(self, "ChainMindDisruptionBus", event_bus_name="chainmind")
        events.Rule(
            self,
            "DisruptionEventRule",
            event_bus=event_bus,
            event_pattern=events.EventPattern(
                source=["chainmind.disruptions"],
                detail_type=["SupplyChainDisruption"],
            ),
            targets=[
                event_targets.SfnStateMachine(
                    state_machine,
                    input=events.RuleTargetInput.from_object(
                        {"event": events.EventField.from_path("$.detail")}
                    ),
                )
            ],
        )

        # API Gateway forwards the documented API surface to the FastAPI Lambda.
        api = apigateway.RestApi(
            self,
            "ChainMindRestApi",
            rest_api_name="ChainMind API",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["Content-Type"],
            ),
        )
        integration = apigateway.LambdaIntegration(api_handler)
        api.root.add_resource("health").add_method("GET", integration)
        api.root.add_resource("disruptions").add_method("POST", integration)
        runs = api.root.add_resource("runs")
        runs.add_method("GET", integration)
        run = runs.add_resource("{run_id}")
        run.add_method("GET", integration)
        run.add_resource("decision").add_method("POST", integration)

        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(self, "EventBusName", value=event_bus.event_bus_name)
        CfnOutput(self, "StateMachineArn", value=state_machine.state_machine_arn)
        CfnOutput(self, "EventStoreName", value=event_store.table_name)
        CfnOutput(self, "AuditArtifactsBucket", value=artifacts.bucket_name)
