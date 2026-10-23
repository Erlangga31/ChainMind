"""Template-level assertions for the AWS infrastructure stack."""

from aws_cdk import App
from aws_cdk.assertions import Match, Template

from infra.chainmind_stack import ChainMindStack


def test_stack_contains_expected_workflow_and_agent_lambdas() -> None:
    template = Template.from_stack(ChainMindStack(App(), "TestChainMindStack"))

    template.resource_count_is("AWS::Lambda::Function", 8)
    template.resource_count_is("AWS::StepFunctions::StateMachine", 1)
    template.resource_count_is("AWS::Events::EventBus", 1)


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
