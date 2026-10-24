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
    aws_bedrock as bedrock,
)
from aws_cdk import (
    aws_cloudtrail as cloudtrail,
)
from aws_cdk import (
    aws_cloudwatch as cloudwatch,
)
from aws_cdk import (
    aws_cognito as cognito,
)
from aws_cdk import (
    aws_dynamodb as dynamodb,
)
from aws_cdk import (
    aws_ec2 as ec2,
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
    aws_kms as kms,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_logs as logs,
)
from aws_cdk import (
    aws_s3 as s3,
)
from aws_cdk import (
    aws_secretsmanager as secretsmanager,
)
from aws_cdk import (
    aws_sqs as sqs,
)
from aws_cdk import (
    aws_stepfunctions as sfn,
)
from aws_cdk import (
    aws_stepfunctions_tasks as tasks,
)
from constructs import Construct

from chainmind.workflow.definition import WorkflowState, validate_transition


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
        configured_max_revisions = self.node.try_get_context("maxRevisions")
        max_revisions = int(3 if configured_max_revisions is None else configured_max_revisions)
        if not 0 <= max_revisions <= 10:
            raise ValueError("Set maxRevisions CDK context to a value between 0 and 10.")
        llm_backend = str(
            self.node.try_get_context("llmBackend")
            or ("mock" if chainmind_mode == "mock" else "bedrock_agents")
        )
        if llm_backend not in {"mock", "bedrock", "bedrock_agents"}:
            raise ValueError("Set CDK context llmBackend to mock, bedrock, or bedrock_agents.")
        model_arn = (
            f"arn:{self.partition}:bedrock:{self.region}::foundation-model/{bedrock_model_id}"
        )
        project_root = Path(__file__).resolve().parents[1]
        encryption_key = kms.Key(
            self,
            "ChainMindEncryptionKey",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN,
            description="Customer-managed encryption for ChainMind application data.",
        )
        vpc = ec2.Vpc(
            self,
            "ChainMindVpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                ),
                ec2.SubnetConfiguration(
                    name="private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                ),
            ],
        )
        private_subnets = ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        vpc.add_gateway_endpoint(
            "DynamoDBEndpoint",
            service=ec2.GatewayVpcEndpointAwsService.DYNAMODB,
            subnets=[private_subnets],
        )
        vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
            subnets=[private_subnets],
        )
        for endpoint_name, service in (
            ("BedrockRuntimeEndpoint", ec2.InterfaceVpcEndpointAwsService.BEDROCK_RUNTIME),
            ("SecretsManagerEndpoint", ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER),
            ("CloudWatchLogsEndpoint", ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS),
        ):
            vpc.add_interface_endpoint(
                endpoint_name,
                service=service,
                subnets=private_subnets,
                private_dns_enabled=True,
            )
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
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=encryption_key,
            removal_policy=RemovalPolicy.RETAIN,
        )
        workflow_dlq = sqs.Queue(
            self,
            "WorkflowDeadLetterQueue",
            queue_name="chainmind-workflow-dlq",
            encryption=sqs.QueueEncryption.KMS,
            encryption_master_key=encryption_key,
            retention_period=Duration.days(14),
        )

        # Private S3 storage for decision rationale and audit artifacts.
        artifacts = s3.Bucket(
            self,
            "ChainMindAuditArtifacts",
            bucket_name=None,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            encryption=s3.BucketEncryption.KMS,
            encryption_key=encryption_key,
            versioned=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    expiration=Duration.days(365),
                    noncurrent_version_expiration=Duration.days(90),
                )
            ],
            removal_policy=RemovalPolicy.RETAIN,
        )

        def make_function(
            logical_id: str,
            handler: str,
            description: str,
            *,
            environment: dict[str, str] | None = None,
        ) -> lambda_.Function:
            function_log_group = logs.LogGroup(
                self,
                f"{logical_id}LogGroup",
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=RemovalPolicy.RETAIN,
            )
            return lambda_.Function(
                self,
                logical_id,
                runtime=lambda_.Runtime.PYTHON_3_12,
                handler=handler,
                code=source,
                memory_size=512,
                timeout=Duration.seconds(30),
                log_group=function_log_group,
                vpc=vpc,
                vpc_subnets=private_subnets,
                description=description,
                environment={
                    "CHAINMIND_MODE": chainmind_mode,
                    "CHAINMIND_LLM_BACKEND": llm_backend,
                    "CHAINMIND_AWS_REGION": self.region,
                    "CHAINMIND_BEDROCK_MODEL_ID": bedrock_model_id,
                    "CHAINMIND_EVENT_TABLE_NAME": event_store.table_name,
                    "CHAINMIND_ARTIFACT_BUCKET": artifacts.bucket_name,
                    "CHAINMIND_MAX_REVISIONS": str(max_revisions),
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
        track_execution = make_function(
            "TrackExecutedPurchaseOrder",
            "chainmind.handlers.stages.track_execution",
            "Reconcile Ariba confirmation, shipment ETA, and stock projection.",
        )
        event_store.grant_read_write_data(track_execution)

        # FastAPI transport. The role has only the run-table and artifact permissions it needs.
        api_handler = make_function(
            "ChainMindApi",
            "chainmind.handlers.api.handler",
            "FastAPI API Gateway entrypoint for disruption and approval routes.",
        )
        event_store.grant_read_write_data(api_handler)
        artifacts.grant_put(api_handler, "runs/*")
        api_handler.add_to_role_policy(
            iam.PolicyStatement(
                actions=["states:SendTaskSuccess", "states:SendTaskFailure"],
                # Callback APIs authorize by opaque task token, not state-machine ARN.
                resources=["*"],
            )
        )

        bridge_secret = secretsmanager.Secret(
            self,
            "EventBridgeSharedSecret",
            secret_name="chainmind/event-bridge",
            description="HMAC shared secret for trusted Event Mesh event ingestion.",
            encryption_key=encryption_key,
            generate_secret_string=secretsmanager.SecretStringGenerator(
                password_length=48,
                exclude_punctuation=True,
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )
        notification_link_secret = secretsmanager.Secret(
            self,
            "NotificationLinkSigningSecret",
            secret_name="chainmind/notification-links",
            description="HMAC key used to sign expiring notification action links.",
            encryption_key=encryption_key,
            generate_secret_string=secretsmanager.SecretStringGenerator(
                password_length=48,
                exclude_punctuation=True,
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )
        for notification_function in (approval_callback, track_execution, api_handler):
            notification_link_secret.grant_read(notification_function)
            notification_function.add_environment(
                "CHAINMIND_NOTIFICATION_LINK_SECRET_ID",
                notification_link_secret.secret_arn,
            )
        overdue_notifier = make_function(
            "ApprovalOverdueNotifier",
            "chainmind.handlers.notifications.approval_overdue",
            "Escalate approvals that remain pending beyond their configured age.",
        )
        event_store.grant_read_write_data(overdue_notifier)
        for artifact_writer in (
            approval_callback,
            execute_order,
            track_execution,
            overdue_notifier,
        ):
            artifacts.grant_put(artifact_writer, "runs/*")
        notification_link_secret.grant_read(overdue_notifier)
        overdue_notifier.add_environment(
            "CHAINMIND_NOTIFICATION_LINK_SECRET_ID",
            notification_link_secret.secret_arn,
        )
        event_bridge_handler = make_function(
            "EventMeshBridge",
            "chainmind.handlers.event_bridge.handler",
            "Validate signed Event Mesh payloads and publish normalized events.",
            environment={
                "CHAINMIND_EVENT_BRIDGE_SECRET_SECRET_ID": bridge_secret.secret_arn,
                "CHAINMIND_EVENT_BUS_NAME": "chainmind",
            },
        )
        bridge_secret.grant_read(event_bridge_handler)
        event_store.grant_write_data(event_bridge_handler)
        external_poll = make_function(
            "ExternalDisruptionPoller",
            "chainmind.handlers.external_poll.handler",
            "Poll configured weather and logistics event sources on a schedule.",
            environment={
                "CHAINMIND_EVENT_BUS_NAME": "chainmind",
                "CHAINMIND_EXTERNAL_POLL_ENABLED": str(
                    self.node.try_get_context("externalPollEnabled") or "false"
                ).lower(),
                "CHAINMIND_EXTERNAL_WEATHER_ENABLED": str(
                    self.node.try_get_context("externalWeatherEnabled") or "false"
                ).lower(),
            },
        )
        event_store.grant_write_data(external_poll)
        external_poll.add_environment("CHAINMIND_EVENT_TABLE_NAME", event_store.table_name)

        # Phase 3 action-group Lambda calls the existing deterministic agent and SAP adapters.
        action_group_handler = make_function(
            "BedrockActionGroupHandler",
            "chainmind.handlers.action_groups.handler",
            "Validate and dispatch Bedrock Agent actions to deterministic ChainMind logic.",
        )

        # Bedrock Agents can invoke only the configured model through this service role.
        agent_role = iam.Role(
            self,
            "BedrockAgentServiceRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
        )
        agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=[model_arn],
            )
        )

        # Shared guardrail blocks personal identifiers and topics outside supply-chain work.
        guardrail = bedrock.CfnGuardrail(
            self,
            "ChainMindSupplyChainGuardrail",
            name="chainmind-supply-chain-guardrail",
            description="Protects manufacturing supply-chain agent interactions.",
            blocked_input_messaging="This request is outside the supported supply-chain scope.",
            blocked_outputs_messaging="This response is outside the supported supply-chain scope.",
            sensitive_information_policy_config=bedrock.CfnGuardrail.SensitiveInformationPolicyConfigProperty(
                pii_entities_config=[
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(
                        action="ANONYMIZE",
                        type=entity_type,
                    )
                    for entity_type in ("EMAIL", "PHONE", "NAME", "ADDRESS")
                ]
            ),
            topic_policy_config=bedrock.CfnGuardrail.TopicPolicyConfigProperty(
                topics_config=[
                    bedrock.CfnGuardrail.TopicConfigProperty(
                        name="Out-of-scope requests",
                        definition=(
                            "Requests unrelated to manufacturing operations, supply-chain "
                            "disruptions, inventory, logistics, procurement, or human approval."
                        ),
                        type="DENY",
                        examples=["Write a personal essay unrelated to supply chains."],
                    )
                ]
            ),
        )

        prompt_names = {
            "Monitoring": "monitoring",
            "Logistics": "logistics",
            "Procurement": "procurement",
            "Orchestrator": "orchestrator",
        }
        schema_by_agent = {
            "Monitoring": ["get_inventory", "compute_coverage"],
            "Logistics": ["get_inventory", "compute_coverage"],
            "Procurement": ["search_alternative_vendors", "compare_vendors"],
            "Orchestrator": ["create_draft_po"],
        }
        agent_aliases: dict[str, bedrock.CfnAgentAlias] = {}
        for stage_name, prompt_name in prompt_names.items():
            action_groups = []
            for action_name in schema_by_agent[stage_name]:
                schema = (project_root / "infra" / "schemas" / f"{action_name}.yaml").read_text(
                    encoding="utf-8"
                )
                action_groups.append(
                    bedrock.CfnAgent.AgentActionGroupProperty(
                        action_group_name=f"{action_name}-action",
                        description=f"Deterministic {action_name.replace('_', ' ')} operation.",
                        action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(
                            lambda_=action_group_handler.function_arn
                        ),
                        api_schema=bedrock.CfnAgent.APISchemaProperty(payload=schema),
                    )
                )
            agent = bedrock.CfnAgent(
                self,
                f"{stage_name}BedrockAgent",
                agent_name=f"chainmind-{stage_name.lower()}",
                description=f"ChainMind {stage_name.lower()} agent.",
                foundation_model=bedrock_model_id,
                instruction=(
                    project_root / "src" / "chainmind" / "prompts" / f"{prompt_name}.md"
                ).read_text(encoding="utf-8"),
                agent_resource_role_arn=agent_role.role_arn,
                action_groups=action_groups,
                guardrail_configuration=bedrock.CfnAgent.GuardrailConfigurationProperty(
                    guardrail_identifier=guardrail.attr_guardrail_id,
                    guardrail_version="DRAFT",
                ),
                auto_prepare=True,
            )
            alias = bedrock.CfnAgentAlias(
                self,
                f"{stage_name}BedrockAgentAlias",
                agent_id=agent.attr_agent_id,
                agent_alias_name="chainmind-live",
                description=f"Prepared alias for the ChainMind {stage_name.lower()} agent.",
            )
            agent_aliases[stage_name] = alias
            action_group_handler.add_permission(
                f"Allow{stage_name}BedrockAgentInvoke",
                principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
                source_account=self.account,
                source_arn=agent.attr_agent_arn,
            )

        # The orchestrator may invoke only its prepared alias, never select or price vendors.
        orchestrator.add_environment(
            "CHAINMIND_BEDROCK_AGENT_ID",
            agent_aliases["Orchestrator"].agent_id,
        )
        orchestrator.add_environment(
            "CHAINMIND_BEDROCK_AGENT_ALIAS_ID",
            agent_aliases["Orchestrator"].attr_agent_alias_id,
        )
        orchestrator.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeAgent"],
                resources=[agent_aliases["Orchestrator"].attr_agent_alias_arn],
            )
        )

        # Least-privilege Bedrock access for AWS-mode use; mocks remain the deploy default.
        orchestrator.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[model_arn],
            )
        )

        workflow_failure = sfn.Fail(
            self,
            "WorkflowFailed",
            error="WorkflowTaskFailed",
            cause="A workflow task failed after configured retries.",
        )
        failure_task = tasks.SqsSendMessage(
            self,
            "SendWorkflowFailureToDLQ",
            queue=workflow_dlq,
            message_body=sfn.TaskInput.from_json_path_at("$"),
            result_path=sfn.JsonPath.DISCARD,
        ).next(workflow_failure)

        # Step Functions: four agent stages followed by a callback-token approval wait.
        monitoring_task = tasks.LambdaInvoke(
            self,
            f"{WorkflowState.MONITORING.value.title()}Stage",
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
        monitoring_task.add_catch(failure_task, errors=["States.ALL"], result_path="$.error")
        logistics_task = tasks.LambdaInvoke(
            self,
            f"{WorkflowState.LOGISTICS.value.title()}Stage",
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
        logistics_task.add_catch(failure_task, errors=["States.ALL"], result_path="$.error")
        procurement_task = tasks.LambdaInvoke(
            self,
            f"{WorkflowState.PROCUREMENT.value.title()}Stage",
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
        procurement_task.add_catch(failure_task, errors=["States.ALL"], result_path="$.error")
        orchestrator_task = tasks.LambdaInvoke(
            self,
            f"{WorkflowState.ORCHESTRATOR.value.title()}Stage",
            lambda_function=orchestrator,
            payload=sfn.TaskInput.from_object(
                {
                    "event": sfn.JsonPath.object_at("$.event"),
                    "inventory": sfn.JsonPath.object_at("$.monitoring.inventory"),
                    "logistics": sfn.JsonPath.object_at("$.logistics"),
                    "procurement": sfn.JsonPath.object_at("$.procurement"),
                    "workflow": sfn.JsonPath.object_at("$.workflow"),
                    "approval": sfn.JsonPath.object_at("$.approval"),
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
        orchestrator_task.add_catch(failure_task, errors=["States.ALL"], result_path="$.error")
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
        approval_timeout_escalation = tasks.LambdaInvoke(
            self,
            "EscalateTimedOutApproval",
            lambda_function=overdue_notifier,
            payload=sfn.TaskInput.from_json_path_at("$"),
            payload_response_only=True,
            result_path="$.overdue_escalation",
        )
        approval_timeout_escalation.add_retry(
            errors=["States.TaskFailed"],
            interval=Duration.seconds(2),
            backoff_rate=2,
            max_attempts=3,
        )
        approval_timeout_escalation.add_catch(
            failure_task,
            errors=["States.ALL"],
            result_path="$.error",
        )
        approval_timeout_escalation.next(sfn.Succeed(self, "ApprovalTimedOutAfterEscalation"))
        approval_task.add_catch(
            approval_timeout_escalation,
            errors=["States.Timeout"],
            result_path="$.approval_timeout",
        )
        execute_task = tasks.LambdaInvoke(
            self,
            "ExecutePurchaseOrderAfterApproval",
            lambda_function=execute_order,
            payload=sfn.TaskInput.from_json_path_at("$"),
            payload_response_only=True,
            result_path="$.execution",
        )
        execute_task.add_retry(
            errors=["States.TaskFailed"],
            interval=Duration.seconds(2),
            backoff_rate=2,
            max_attempts=3,
        )
        execute_task.add_catch(failure_task, errors=["States.ALL"], result_path="$.error")
        tracking_task = tasks.LambdaInvoke(
            self,
            "TrackSupplierExecution",
            lambda_function=track_execution,
            payload=sfn.TaskInput.from_json_path_at("$"),
            payload_response_only=True,
            result_path="$.tracking",
        )
        tracking_task.add_retry(
            errors=["States.TaskFailed"],
            interval=Duration.seconds(2),
            backoff_rate=2,
            max_attempts=3,
        )
        tracking_task.add_catch(failure_task, errors=["States.ALL"], result_path="$.error")
        completed = sfn.Succeed(self, "PurchaseOrderProcessed")
        execute_success = execute_task.next(tracking_task).next(completed)
        rejected = sfn.Succeed(self, "PurchaseOrderRejected")
        revision_limit = sfn.Succeed(self, "RevisionLimitReached")
        invalid_decision = sfn.Fail(
            self,
            "InvalidApprovalDecision",
            error="InvalidApprovalDecision",
            cause="The approval callback returned an unsupported decision.",
        )
        decision_after_revision = revision_limit
        for revision_index in reversed(range(max_revisions + 1)):
            decision = sfn.Choice(
                self,
                f"{WorkflowState.HUMAN_APPROVAL.value.title()}Decision{revision_index}",
            )
            decision.when(
                sfn.Condition.string_equals("$.approval.decision", "approve"),
                execute_success,
            ).when(
                sfn.Condition.string_equals("$.approval.decision", "reject"),
                rejected,
            )
            if revision_index < max_revisions:
                revision_procurement_task = tasks.LambdaInvoke(
                    self,
                    f"RevisedProcurementStage{revision_index + 1}",
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
                revision_procurement_task.add_retry(
                    errors=["States.TaskFailed"],
                    interval=Duration.seconds(2),
                    backoff_rate=2,
                    max_attempts=3,
                )
                revision_procurement_task.add_catch(
                    failure_task,
                    errors=["States.ALL"],
                    result_path="$.error",
                )
                revision_orchestrator_task = tasks.LambdaInvoke(
                    self,
                    f"RevisedOrchestratorStage{revision_index + 1}",
                    lambda_function=orchestrator,
                    payload=sfn.TaskInput.from_object(
                        {
                            "event": sfn.JsonPath.object_at("$.event"),
                            "inventory": sfn.JsonPath.object_at("$.monitoring.inventory"),
                            "logistics": sfn.JsonPath.object_at("$.logistics"),
                            "procurement": sfn.JsonPath.object_at("$.procurement"),
                            "workflow": sfn.JsonPath.object_at("$.workflow"),
                            "approval": sfn.JsonPath.object_at("$.approval"),
                        }
                    ),
                    payload_response_only=True,
                    result_path="$.orchestration",
                )
                revision_orchestrator_task.add_retry(
                    errors=["States.TaskFailed"],
                    interval=Duration.seconds(2),
                    backoff_rate=2,
                    max_attempts=3,
                )
                revision_orchestrator_task.add_catch(
                    failure_task,
                    errors=["States.ALL"],
                    result_path="$.error",
                )
                update_revision_count = sfn.Pass(
                    self,
                    f"UpdateRevisionCount{revision_index + 1}",
                    parameters={
                        "revision_count": sfn.JsonPath.number_at("$.orchestration.revision_count")
                    },
                    result_path="$.workflow",
                )
                revised_approval_task = tasks.LambdaInvoke(
                    self,
                    f"WaitForRevisedApproval{revision_index + 1}",
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
                revised_approval_task.add_catch(
                    approval_timeout_escalation,
                    errors=["States.Timeout"],
                    result_path="$.approval_timeout",
                )
                revised_approval_task.add_catch(rejected, errors=["HumanRejected"])
                revised_approval_task.add_catch(
                    failure_task,
                    errors=["States.ALL"],
                    result_path="$.error",
                )
                decision.when(
                    sfn.Condition.string_equals("$.approval.decision", "revise"),
                    sfn.Choice(self, f"RevisionLimitCheck{revision_index + 1}")
                    .when(
                        sfn.Condition.number_less_than(
                            "$.workflow.revision_count",
                            max_revisions,
                        ),
                        revision_procurement_task.next(revision_orchestrator_task)
                        .next(update_revision_count)
                        .next(revised_approval_task)
                        .next(decision_after_revision),
                    )
                    .otherwise(revision_limit),
                )
            else:
                decision.when(
                    sfn.Condition.string_equals("$.approval.decision", "revise"),
                    revision_limit,
                )
            decision.otherwise(invalid_decision)
            decision_after_revision = decision
        approval_task.add_catch(rejected, errors=["HumanRejected"])
        approval_task.add_catch(failure_task, errors=["States.ALL"], result_path="$.error")
        initialize_workflow = sfn.Pass(
            self,
            "InitializeWorkflow",
            result=sfn.Result.from_object({"revision_count": 0}),
            result_path="$.workflow",
        )
        initialize_approval = sfn.Pass(
            self,
            "InitializeApprovalDecision",
            result=sfn.Result.from_object({"decision": ""}),
            result_path="$.approval",
        )
        non_significant = sfn.Succeed(self, "DisruptionNotSignificant")
        monitoring_gate = sfn.Choice(self, "DisruptionIsSignificant")
        monitoring_gate.when(
            sfn.Condition.boolean_equals("$.monitoring.result.significant", True),
            logistics_task.next(procurement_task)
            .next(orchestrator_task)
            .next(approval_task)
            .next(decision),
        ).otherwise(non_significant)
        for current, following in (
            (WorkflowState.INGESTED, WorkflowState.MONITORING),
            (WorkflowState.MONITORING, WorkflowState.LOGISTICS),
            (WorkflowState.MONITORING, WorkflowState.NOT_SIGNIFICANT),
            (WorkflowState.LOGISTICS, WorkflowState.PROCUREMENT),
            (WorkflowState.PROCUREMENT, WorkflowState.ORCHESTRATOR),
            (WorkflowState.ORCHESTRATOR, WorkflowState.HUMAN_APPROVAL),
            (WorkflowState.HUMAN_APPROVAL, WorkflowState.PROCUREMENT),
            (WorkflowState.HUMAN_APPROVAL, WorkflowState.EXECUTION),
            (WorkflowState.HUMAN_APPROVAL, WorkflowState.REJECTED),
            (WorkflowState.EXECUTION, WorkflowState.COMPLETED),
        ):
            validate_transition(current, following)
        workflow = initialize_workflow.next(
            initialize_approval.next(monitoring_task.next(monitoring_gate))
        )
        state_machine = sfn.StateMachine(
            self,
            "DisruptionResolutionStateMachine",
            definition_body=sfn.DefinitionBody.from_chainable(workflow),
            timeout=Duration.days(7),
            tracing_enabled=True,
        )

        # EventBridge receives external disruption events and starts the four-agent workflow.
        event_bus = events.EventBus(self, "ChainMindDisruptionBus", event_bus_name="chainmind")
        api_handler.add_to_role_policy(
            iam.PolicyStatement(
                actions=["events:PutEvents"],
                resources=[event_bus.event_bus_arn],
            )
        )
        for event_publisher in (event_bridge_handler, external_poll):
            event_publisher.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["events:PutEvents"],
                    resources=[event_bus.event_bus_arn],
                )
            )
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
        events.Rule(
            self,
            "ExternalDisruptionPollSchedule",
            schedule=events.Schedule.rate(Duration.minutes(15)),
            targets=[event_targets.LambdaFunction(external_poll)],
        )
        events.Rule(
            self,
            "ApprovalOverdueEscalationSchedule",
            schedule=events.Schedule.rate(Duration.minutes(15)),
            targets=[event_targets.LambdaFunction(overdue_notifier)],
        )

        user_pool = cognito.UserPool(
            self,
            "ChainMindUserPool",
            user_pool_name="chainmind-approvers",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_digits=True,
                require_lowercase=True,
                require_uppercase=True,
                require_symbols=True,
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )
        for role_name in ("viewer", "approver"):
            cognito.CfnUserPoolGroup(
                self,
                f"{role_name.title()}UserGroup",
                user_pool_id=user_pool.user_pool_id,
                group_name=role_name,
            )
        callback_url = str(
            self.node.try_get_context("dashboardCallbackUrl") or "http://localhost:5173/"
        )
        dashboard_client = user_pool.add_client(
            "DashboardSpaClient",
            user_pool_client_name="chainmind-dashboard",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_srp=True),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL],
                callback_urls=[callback_url],
                logout_urls=[callback_url],
            ),
        )
        user_pool.add_domain(
            "ChainMindHostedAuthDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"chainmind-{self.account}-{self.region}"
            ),
        )
        authorizer = apigateway.CognitoUserPoolsAuthorizer(
            self,
            "ChainMindCognitoAuthorizer",
            cognito_user_pools=[user_pool],
            authorizer_name="chainmind-cognito",
        )
        api_access_logs = logs.LogGroup(
            self,
            "ApiGatewayAccessLogs",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # API Gateway forwards the documented API surface to the FastAPI Lambda.
        api = apigateway.RestApi(
            self,
            "ChainMindRestApi",
            rest_api_name="ChainMind API",
            default_method_options=apigateway.MethodOptions(
                authorizer=authorizer,
                authorization_type=apigateway.AuthorizationType.COGNITO,
            ),
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["Authorization", "Content-Type", "X-ChainMind-Role"],
            ),
            deploy_options=apigateway.StageOptions(
                stage_name="v1",
                logging_level=apigateway.MethodLoggingLevel.INFO,
                data_trace_enabled=False,
                metrics_enabled=True,
                throttling_rate_limit=20,
                throttling_burst_limit=40,
                access_log_destination=apigateway.LogGroupLogDestination(api_access_logs),
                access_log_format=apigateway.AccessLogFormat.json_with_standard_fields(
                    caller=False,
                    http_method=True,
                    ip=True,
                    protocol=True,
                    request_time=True,
                    resource_path=True,
                    response_length=True,
                    status=True,
                    user=False,
                ),
            ),
        )
        integration = apigateway.LambdaIntegration(api_handler)
        api.root.add_resource("health").add_method(
            "GET",
            integration,
            authorization_type=apigateway.AuthorizationType.NONE,
        )
        api.root.add_resource("disruptions").add_method("POST", integration)
        api.root.add_resource("kpis").add_method("GET", integration)
        notification_links = api.root.add_resource("notifications").add_resource("links")
        notification_link = notification_links.add_resource("{token}")
        notification_link.add_method("GET", integration)
        notification_link.add_resource("approve").add_method("POST", integration)
        api.root.add_resource("event-bridge").add_method(
            "POST",
            apigateway.LambdaIntegration(event_bridge_handler),
            authorization_type=apigateway.AuthorizationType.NONE,
        )
        runs = api.root.add_resource("runs")
        runs.add_method("GET", integration)
        run = runs.add_resource("{run_id}")
        run.add_method("GET", integration)
        run.add_resource("decision").add_method("POST", integration)

        cloudtrail.Trail(
            self,
            "ChainMindCloudTrail",
            bucket=artifacts,
            encryption_key=encryption_key,
            enable_file_validation=True,
            include_global_service_events=False,
            is_multi_region_trail=True,
            send_to_cloud_watch_logs=True,
            cloud_watch_logs_retention=logs.RetentionDays.ONE_MONTH,
        )
        cloudwatch.Alarm(
            self,
            "FailedWorkflowAlarm",
            metric=state_machine.metric_failed(),
            threshold=1,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            alarm_description="At least one ChainMind workflow execution failed.",
        )
        cloudwatch.Alarm(
            self,
            "WorkflowDlqDepthAlarm",
            metric=workflow_dlq.metric_approximate_number_of_messages_visible(),
            threshold=1,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            alarm_description="A message is waiting in the ChainMind workflow DLQ.",
        )
        cloudwatch.Dashboard(
            self,
            "ChainMindOperationsDashboard",
            dashboard_name="ChainMind-Operations",
            widgets=[
                [
                    cloudwatch.GraphWidget(
                        title="Workflow executions",
                        left=[
                            state_machine.metric_succeeded(),
                            state_machine.metric_failed(),
                            state_machine.metric_timed_out(),
                        ],
                        width=12,
                    ),
                    cloudwatch.GraphWidget(
                        title="Workflow dead-letter queue",
                        left=[workflow_dlq.metric_approximate_number_of_messages_visible()],
                        width=12,
                    ),
                ]
            ],
        )

        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(self, "EventBusName", value=event_bus.event_bus_name)
        CfnOutput(self, "StateMachineArn", value=state_machine.state_machine_arn)
        CfnOutput(self, "EventStoreName", value=event_store.table_name)
        CfnOutput(self, "AuditArtifactsBucket", value=artifacts.bucket_name)
        CfnOutput(self, "CognitoUserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "CognitoDashboardClientId", value=dashboard_client.user_pool_client_id)
