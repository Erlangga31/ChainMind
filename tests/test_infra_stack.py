"""Template-level assertions for the AWS infrastructure stack."""

from aws_cdk import App
from aws_cdk.assertions import Template

from infra.chainmind_stack import ChainMindStack


def test_stack_contains_expected_workflow_and_agent_lambdas() -> None:
    template = Template.from_stack(ChainMindStack(App(), "TestChainMindStack"))

    template.resource_count_is("AWS::Lambda::Function", 7)
    template.resource_count_is("AWS::StepFunctions::StateMachine", 1)
    template.resource_count_is("AWS::Events::EventBus", 1)
