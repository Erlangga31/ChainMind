from __future__ import annotations

from typing import Any

from scripts.verify_aws_account import verify_account


class StubAwsClient:
    def __init__(self, service: str) -> None:
        self.service = service

    def get_caller_identity(self) -> dict[str, str]:
        return {"Account": "123456789012"}

    def list_foundation_models(self) -> dict[str, list[dict[str, str]]]:
        return {"modelSummaries": [{"modelId": "unit-test-model"}]}

    def get_agent(self, *, agentId: str) -> dict[str, dict[str, str]]:
        return {"agent": {"agentId": agentId}}

    def get_agent_alias(self, *, agentId: str, agentAliasId: str) -> dict[str, dict[str, str]]:
        return {"agentAlias": {"agentId": agentId, "agentAliasId": agentAliasId}}

    def describe_event_bus(self, *, Name: str) -> dict[str, str]:
        return {"Name": Name}

    def describe_state_machine(self, *, stateMachineArn: str) -> dict[str, str]:
        return {"stateMachineArn": stateMachineArn}


def test_aws_account_verifier_uses_read_only_checks() -> None:
    requested: list[tuple[str, dict[str, Any]]] = []

    def client_factory(service: str, **kwargs: Any) -> StubAwsClient:
        requested.append((service, kwargs))
        return StubAwsClient(service)

    results = verify_account(
        region="us-east-1",
        model_id="unit-test-model",
        event_bus_name="chainmind",
        agent_id="agent-123",
        agent_alias_id="alias-123",
        state_machine_arn="arn:aws:states:us-east-1:123456789012:stateMachine:chainmind",
        client_factory=client_factory,
    )

    assert {result.name: result.status for result in results} == {
        "AWS credentials": "PASS",
        "Bedrock model catalog": "PASS",
        "Bedrock agent configuration": "PASS",
        "EventBridge bus": "PASS",
        "EventBridge PutEvents dry run": "SKIP",
        "Step Functions state machine": "PASS",
    }
    assert [service for service, _ in requested] == [
        "sts",
        "bedrock",
        "bedrock-agent",
        "events",
        "stepfunctions",
    ]


def test_aws_account_verifier_skips_unconfigured_agent_and_state_machine() -> None:
    def client_factory(service: str, **kwargs: Any) -> StubAwsClient:
        return StubAwsClient(service)

    results = verify_account(
        region="us-east-1",
        model_id="unit-test-model",
        event_bus_name="chainmind",
        client_factory=client_factory,
    )

    statuses = {result.name: result.status for result in results}
    assert statuses["Bedrock agent configuration"] == "SKIP"
    assert statuses["Step Functions state machine"] == "SKIP"
