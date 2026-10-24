"""Template-level assertions for the AWS infrastructure stack."""

import json

from aws_cdk import App
from aws_cdk.assertions import Match, Template

from infra.chainmind_stack import ChainMindStack


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
