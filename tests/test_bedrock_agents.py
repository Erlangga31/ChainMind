"""Tests for Bedrock Agent stream parsing and deterministic fallbacks."""

from typing import Any

import pytest

from chainmind.agents.logistics import LogisticsAgent
from chainmind.agents.procurement import ProcurementAgent
from chainmind.core.config import Settings
from chainmind.core.errors import IntegrationError
from chainmind.core.models import (
    DisruptionEvent,
    LogisticsResult,
    VendorEvaluation,
)
from chainmind.factory import create_llm_client, create_pipeline
from chainmind.integrations.llm.bedrock_agents import BedrockAgentsClient
from chainmind.integrations.sap.mock_ariba import MockAribaClient
from chainmind.integrations.sap.mock_s4hana import MockSAPS4HANAClient


class FakeAgentClient:
    """Return a fixed Bedrock Agent completion stream for contract tests."""

    def __init__(self, completion: list[dict[str, Any]]) -> None:
        self.completion = completion
        self.request: dict[str, Any] = {}

    def invoke_agent(self, **kwargs: Any) -> dict[str, Any]:
        self.request = kwargs
        return {"completion": iter(self.completion)}


def agent_client(text: str) -> tuple[BedrockAgentsClient, FakeAgentClient]:
    fake = FakeAgentClient(
        [
            {"trace": {"orchestrationTrace": {"modelInvocationInput": {"type": "AGENT"}}}},
            {"chunk": {"bytes": text.encode("utf-8")}},
        ]
    )
    client = BedrockAgentsClient("agent-id", "alias-id", "us-east-1", client=fake)
    return client, fake


def demo_inputs() -> tuple[
    DisruptionEvent,
    VendorEvaluation,
    list[VendorEvaluation],
    LogisticsResult,
]:
    """Build deterministic event, vendor evaluations, and logistics evidence."""

    event = DisruptionEvent(
        title="Weather delay",
        description="Weather delays the Microchip X shipment.",
        delay_days=5,
    )
    inventory = MockSAPS4HANAClient().get_inventory("microchip-x")
    logistics = LogisticsAgent().analyze(event, inventory)
    procurement = ProcurementAgent(MockAribaClient(), Settings()).compare(
        event,
        inventory,
        logistics,
    )
    selected = next(item for item in procurement.evaluations if item.vendor.vendor_id == "vendor-b")
    return event, selected, procurement.evaluations, logistics


def test_agent_stream_parser_captures_trace_and_reuses_run_id() -> None:
    client, fake = agent_client("Vendor B avoids the model choosing or changing the quote.")
    _, selected, alternatives, logistics = demo_inputs()
    explanation = client.explain_vendor_choice(
        selected=selected,
        alternatives=alternatives,
        cost_of_inaction=logistics.cost_of_inaction,
        run_id="demo-run-id",
    )

    assert explanation.text.startswith("Vendor B")
    assert explanation.trace[0].source == "Amazon Bedrock"
    assert fake.request["sessionId"] == "demo-run-id"
    assert fake.request["enableTrace"] is True


@pytest.mark.parametrize(
    "output",
    ['{"text": 42, "confidence": 0.99}', '{"text": "uncertain", "confidence": 0.2}'],
)
def test_invalid_or_low_confidence_output_uses_auditable_fallback(output: str) -> None:
    client, _ = agent_client(output)
    event, _, _, _ = demo_inputs()
    result = create_pipeline(llm_client=client).run(event)

    assert result.selected_vendor_id == "vendor-b"
    assert any(
        entry.output_summary == "A deterministic explanation fallback was used."
        for entry in result.audit_log
    )


def test_factory_requires_agent_ids_for_bedrock_agents() -> None:
    with pytest.raises(IntegrationError, match="Agent ID and alias ID"):
        create_llm_client(Settings(llm_backend="bedrock_agents"))


def test_mock_pipeline_emits_source_labeled_trace_and_keeps_deterministic_vendor() -> None:
    result = create_pipeline().run(
        DisruptionEvent(
            title="Weather delay",
            description="Weather delays the Microchip X shipment.",
            delay_days=5,
        )
    )

    assert result.selected_vendor_id == "vendor-b"
    assert {step.source for step in result.trace_steps} == {
        "SAP S/4HANA",
        "SAP Ariba",
        "Amazon Bedrock",
    }
