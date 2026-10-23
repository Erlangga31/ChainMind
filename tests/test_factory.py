"""Configuration tests for independent integration backends."""

import pytest

from chainmind import factory
from chainmind.core.config import Settings
from chainmind.core.errors import IntegrationError
from chainmind.factory import create_llm_client, create_sap_clients
from chainmind.integrations.sap.mock_ariba import MockAribaClient
from chainmind.integrations.sap.mock_s4hana import MockSAPS4HANAClient
from chainmind.integrations.sap.real_clients import (
    InMemoryApprovalWorkflowClient,
    RealAribaClient,
    RealS4HANAClient,
    SandboxWorkflowClient,
)


def test_default_mock_preset_remains_offline() -> None:
    sap, ariba, workflow = create_sap_clients(Settings())

    assert isinstance(sap, MockSAPS4HANAClient)
    assert isinstance(ariba, MockAribaClient)
    assert isinstance(workflow, InMemoryApprovalWorkflowClient)
    assert sap.get_inventory("microchip-x").current_stock == 3000


def test_sap_backend_can_select_local_sandbox_independent_of_mode() -> None:
    sap, ariba, workflow = create_sap_clients(
        Settings(
            mode="mock",
            sap_backend="sandbox",
            sap_workflow_base_url="http://127.0.0.1:8100",
        )
    )

    assert isinstance(sap, RealS4HANAClient)
    assert isinstance(ariba, RealAribaClient)
    assert isinstance(workflow, SandboxWorkflowClient)


def test_real_sap_backend_requires_explicit_connection_configuration() -> None:
    with pytest.raises(IntegrationError, match="configuration is incomplete"):
        create_sap_clients(Settings(mode="mock", sap_backend="real"))


def test_legacy_aws_mode_resolves_to_real_sap_and_bedrock() -> None:
    settings = Settings(mode="aws")

    assert settings.resolved_sap_backend == "real"
    assert settings.resolved_llm_backend == "bedrock"


def test_explicit_backend_overrides_legacy_mode() -> None:
    settings = Settings(mode="aws", sap_backend="sandbox", llm_backend="mock")

    assert settings.resolved_sap_backend == "sandbox"
    assert settings.resolved_llm_backend == "mock"


def test_bedrock_agents_backend_uses_configured_agent_and_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[tuple[str, str, str]] = []

    class FakeAgentsClient:
        def __init__(self, agent_id: str, alias_id: str, region: str) -> None:
            requested.append((agent_id, alias_id, region))

    monkeypatch.setattr(factory, "BedrockAgentsClient", FakeAgentsClient)
    create_llm_client(
        Settings(
            llm_backend="bedrock_agents",
            bedrock_agent_id="agent-123",
            bedrock_agent_alias_id="alias-456",
            aws_region="us-west-2",
        )
    )
    assert requested == [("agent-123", "alias-456", "us-west-2")]
    assert requested == [("agent-123", "alias-456", "us-west-2")]
