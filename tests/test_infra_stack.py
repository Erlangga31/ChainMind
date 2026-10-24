"""Template-level assertions for the AWS infrastructure stack."""

import json
from pathlib import Path

import pytest
from aws_cdk import App
from aws_cdk.assertions import Match, Template

from infra.chainmind_stack import ChainMindStack
from infra.lambda_package import prepare_lambda_package


def test_lambda_package_contains_source_and_python_312_runtime_dependencies() -> None:
    project_root = Path(__file__).resolve().parents[1]
    package = prepare_lambda_package(project_root)

    for module in ("chainmind", "boto3", "fastapi", "httpx", "jwt", "pydantic", "pydantic_core"):
        assert (package / module).exists(), f"Lambda asset is missing {module}"
    assert (package / "chainmind" / "data" / "sample_disruption.json").is_file()
    assert list((package / "pydantic_core").glob("_pydantic_core.cpython-312-*.so"))


def test_stack_contains_expected_workflow_and_agent_lambdas() -> None:
    template = Template.from_stack(ChainMindStack(App(), "TestChainMindStack"))

    template.resource_count_is("AWS::Lambda::Function", 12)
    template.resource_count_is("AWS::StepFunctions::StateMachine", 1)
    template.resource_count_is("AWS::Events::EventBus", 1)
    template.resource_count_is("AWS::Events::Rule", 3)
    template.resource_count_is("AWS::SecretsManager::Secret", 2)
    template.resource_count_is("AWS::KMS::Key", 1)
    template.resource_count_is("AWS::EC2::VPC", 1)
    template.resource_count_is("AWS::EC2::VPCEndpoint", 5)
    template.resource_count_is("AWS::Cognito::UserPool", 1)
    template.resource_count_is("AWS::Cognito::UserPoolClient", 1)
    template.resource_count_is("AWS::Cognito::UserPoolGroup", 2)
    template.resource_count_is("AWS::ApiGateway::Authorizer", 1)
    template.resource_count_is("AWS::CloudTrail::Trail", 1)
    template.resource_count_is("AWS::CloudWatch::Alarm", 2)
    template.resource_count_is("AWS::CloudWatch::Dashboard", 1)
    template.has_resource_properties(
        "AWS::SecretsManager::Secret",
        {"Name": "chainmind/notification-links"},
    )
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {"SSESpecification": {"SSEEnabled": True, "SSEType": "KMS"}},
    )
    template.has_resource_properties(
        "AWS::ApiGateway::Stage",
        {"MethodSettings": Match.array_with([Match.object_like({"ThrottlingRateLimit": 20})])},
    )
    template.has_resource_properties(
        "AWS::ApiGateway::Method",
        {"AuthorizationType": "COGNITO_USER_POOLS"},
    )
    template.has_resource_properties(
        "AWS::Events::Rule",
        {"ScheduleExpression": "rate(15 minutes)"},
    )
    template.resource_count_is("AWS::SQS::Queue", 1)
    template.has_resource_properties(
        "AWS::ApiGateway::Resource",
        {"PathPart": "event-bridge"},
    )


def test_stack_defines_bedrock_agents_guardrail_and_action_groups() -> None:
    template = Template.from_stack(ChainMindStack(App(), "TestAgentStack"))

    template.resource_count_is("AWS::Bedrock::Agent", 4)
    template.resource_count_is("AWS::Bedrock::AgentAlias", 4)
    template.resource_count_is("AWS::Bedrock::Guardrail", 1)
    template.has_resource_properties(
        "AWS::Bedrock::Agent",
        {
            "FoundationModel": "anthropic.claude-3-haiku-20240307-v1:0",
            "Instruction": Match.string_like_regexp("You are the ChainMind Monitoring Agent.*"),
        },
    )


def test_state_machine_has_bounded_revision_and_callback_states() -> None:
    template = Template.from_stack(ChainMindStack(App(), "TestWorkflowStack"))
    serialized = json.dumps(template.to_json())

    assert "WaitForHumanApproval" in serialized
    assert "ApprovalTimedOutAfterEscalation" in serialized
    assert "TrackSupplierExecution" in serialized
    assert "WaitForRevisedApproval3" in serialized
    assert "RevisionLimitReached" in serialized
    assert "HumanRejected" in serialized
    assert "SendWorkflowFailureToDLQ" in serialized
    assert "TracingConfiguration" in serialized


def test_overdue_schedule_targets_escalation_and_signed_approval_route_is_protected() -> None:
    template = Template.from_stack(ChainMindStack(App(), "TestNotificationStack"))
    resources = template.find_resources("AWS::ApiGateway::Resource")
    logical_ids = {
        resource["Properties"]["PathPart"]: logical_id
        for logical_id, resource in resources.items()
        if resource.get("Properties", {}).get("PathPart")
        in {"notifications", "links", "{token}", "approve"}
    }
    approve_id = logical_ids["approve"]
    token_id = logical_ids["{token}"]
    assert resources[approve_id]["Properties"]["ParentId"] == {"Ref": token_id}

    template.has_resource_properties(
        "AWS::ApiGateway::Method",
        {
            "HttpMethod": "POST",
            "ResourceId": {"Ref": approve_id},
            "AuthorizationType": "COGNITO_USER_POOLS",
        },
    )
    scheduled_rules = [
        rule
        for rule in template.find_resources("AWS::Events::Rule").values()
        if rule.get("Properties", {}).get("ScheduleExpression") == "rate(15 minutes)"
        and "ApprovalOverdueNotifier" in json.dumps(rule.get("Properties", {}).get("Targets", []))
    ]
    assert len(scheduled_rules) == 1
    assert "ApprovalOverdueNotifier" in json.dumps(scheduled_rules[0]["Properties"]["Targets"])


def test_storage_resources_use_customer_managed_encryption_and_private_s3_controls() -> None:
    template = Template.from_stack(ChainMindStack(App(), "TestEncryptedResources"))

    template.resource_count_is("AWS::KMS::Key", 1)
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {"SSESpecification": {"SSEEnabled": True, "SSEType": "KMS"}},
    )
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "VersioningConfiguration": {"Status": "Enabled"},
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            },
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "ServerSideEncryptionByDefault": {
                                    "SSEAlgorithm": "aws:kms",
                                    "KMSMasterKeyID": Match.any_value(),
                                }
                            }
                        )
                    ]
                )
            },
        },
    )
    template.has_resource_properties(
        "AWS::SQS::Queue",
        {"KmsMasterKeyId": Match.any_value(), "SqsManagedSseEnabled": Match.absent()},
    )
    template.has_resource_properties(
        "AWS::SecretsManager::Secret",
        {"KmsKeyId": Match.any_value()},
    )


def test_lambda_iam_wildcards_are_limited_to_unscopable_workflow_and_xray_actions() -> None:
    template = Template.from_stack(ChainMindStack(App(), "TestLeastPrivilege"))
    resources = template.find_resources("AWS::IAM::Policy")
    wildcard_statements = [
        statement
        for resource in resources.values()
        for statement in resource["Properties"]["PolicyDocument"]["Statement"]
        if statement.get("Resource") == "*"
    ]

    assert {tuple(sorted(statement["Action"])) for statement in wildcard_statements} == {
        ("states:SendTaskFailure", "states:SendTaskSuccess"),
        (
            "xray:GetSamplingRules",
            "xray:GetSamplingTargets",
            "xray:PutTelemetryRecords",
            "xray:PutTraceSegments",
        ),
    }


def test_eventbridge_bedrock_and_operations_resources_are_present() -> None:
    template = Template.from_stack(ChainMindStack(App(), "TestMappedServices"))

    template.resource_count_is("AWS::Events::EventBus", 1)
    template.resource_count_is("AWS::Events::Rule", 3)
    template.resource_count_is("AWS::Bedrock::Agent", 4)
    template.resource_count_is("AWS::Bedrock::AgentAlias", 4)
    template.resource_count_is("AWS::Bedrock::Guardrail", 1)
    template.resource_count_is("AWS::CloudTrail::Trail", 1)
    template.resource_count_is("AWS::CloudWatch::Alarm", 2)
    template.resource_count_is("AWS::CloudWatch::Dashboard", 1)

    agents = template.find_resources("AWS::Bedrock::Agent")
    for agent in agents.values():
        assert len(agent["Properties"]["AgentResourceRoleArn"]["Fn::GetAtt"]) == 2
        assert agent["Properties"]["ActionGroups"]
        assert agent["Properties"]["GuardrailConfiguration"]


def test_monthly_budget_notifies_at_eighty_percent_and_resources_are_tagged() -> None:
    template = Template.from_stack(ChainMindStack(App(), "TestBudgetAndTags"))

    template.has_resource_properties(
        "AWS::Budgets::Budget",
        {
            "Budget": {
                "BudgetType": "COST",
                "TimeUnit": "MONTHLY",
                "BudgetLimit": {"Amount": 100, "Unit": "USD"},
                "CostFilters": {"TagKeyValue": ["user:Project$ChainMind"]},
            }
        },
    )
    template.has_resource_properties(
        "AWS::Budgets::Budget",
        {
            "NotificationsWithSubscribers": Match.array_with(
                [
                    Match.object_like(
                        {
                            "Notification": {
                                "ComparisonOperator": "GREATER_THAN",
                                "NotificationType": "ACTUAL",
                                "Threshold": 80,
                                "ThresholdType": "PERCENTAGE",
                            },
                            "Subscribers": Match.array_with(
                                [Match.object_like({"SubscriptionType": "SNS"})]
                            ),
                        }
                    )
                ]
            )
        },
    )
    template.has_resource_properties(
        "AWS::SNS::Topic",
        {
            "KmsMasterKeyId": Match.any_value(),
            "Tags": Match.array_with(
                [
                    {"Key": "Environment", "Value": "mock"},
                    {"Key": "ManagedBy", "Value": "AWS-CDK"},
                    {"Key": "Project", "Value": "ChainMind"},
                ]
            ),
        },
    )


def test_budget_threshold_and_email_recipient_are_configurable() -> None:
    app = App(
        context={
            "monthlyBudgetUsd": 250,
            "budgetNotificationEmail": "owner@example.com",
        }
    )
    template = Template.from_stack(ChainMindStack(app, "TestConfiguredBudget"))

    template.has_resource_properties(
        "AWS::Budgets::Budget",
        {"Budget": {"BudgetLimit": {"Amount": 250, "Unit": "USD"}}},
    )
    template.has_resource_properties(
        "AWS::SNS::Subscription",
        {"Protocol": "email", "Endpoint": "owner@example.com"},
    )


@pytest.mark.parametrize("amount", ["0", "NaN", "Infinity"])
def test_budget_rejects_nonpositive_or_nonfinite_threshold(amount: str) -> None:
    app = App(context={"monthlyBudgetUsd": amount})

    with pytest.raises(ValueError, match="monthlyBudgetUsd.*finite.*positive"):
        ChainMindStack(app, "TestInvalidBudget")
