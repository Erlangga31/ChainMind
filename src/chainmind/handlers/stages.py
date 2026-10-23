"""Thin Lambda wrappers around individual framework-agnostic agent stages."""

import json
import os
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from chainmind.agents.logistics import LogisticsAgent
from chainmind.agents.monitoring import MonitoringAgent
from chainmind.agents.orchestrator import OrchestratorAgent
from chainmind.agents.procurement import ProcurementAgent
from chainmind.core.config import Settings
from chainmind.core.errors import IntegrationError
from chainmind.core.models import (
    DisruptionEvent,
    InventorySnapshot,
    LogisticsResult,
    ProcurementResult,
)
from chainmind.core.retry import retry_integration_call
from chainmind.factory import create_llm_client, create_sap_clients


def monitoring(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Run monitoring and return inventory required by the next state."""

    del context
    disruption = DisruptionEvent.model_validate(event["event"])
    settings = Settings()
    sap, _ = create_sap_clients(settings)
    inventory = retry_integration_call(
        lambda: sap.get_inventory(disruption.component_id),
        attempts=settings.retry_attempts,
        base_delay_seconds=settings.retry_base_delay_seconds,
    )
    coverage = inventory.current_stock / inventory.daily_consumption
    result = MonitoringAgent().analyze(disruption, coverage)
    return {
        "result": result.model_dump(mode="json"),
        "inventory": inventory.model_dump(mode="json"),
    }


def logistics(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Run the inventory impact and inaction cost calculation."""

    del context
    disruption = DisruptionEvent.model_validate(event["event"])
    inventory = InventorySnapshot.model_validate(event["inventory"])
    result = LogisticsAgent().analyze(disruption, inventory)
    return result.model_dump(mode="json")


def procurement(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Compare alternative supplier offers from the Ariba adapter."""

    del context
    disruption = DisruptionEvent.model_validate(event["event"])
    inventory = InventorySnapshot.model_validate(event["inventory"])
    logistics_result = LogisticsResult.model_validate(event["logistics"])
    settings = Settings()
    _, ariba = create_sap_clients(settings)
    result = retry_integration_call(
        lambda: ProcurementAgent(ariba, settings).compare(disruption, inventory, logistics_result),
        attempts=settings.retry_attempts,
        base_delay_seconds=settings.retry_base_delay_seconds,
    )
    return result.model_dump(mode="json")


def orchestrator(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Choose the best feasible quote and create a draft PO for approval."""

    del context
    inventory = InventorySnapshot.model_validate(event["inventory"])
    logistics_result = LogisticsResult.model_validate(event["logistics"])
    procurement_result = ProcurementResult.model_validate(event["procurement"])
    settings = Settings()
    agent = OrchestratorAgent(create_llm_client(settings))
    result = retry_integration_call(
        lambda: agent.choose(procurement_result, logistics_result),
        attempts=settings.retry_attempts,
        base_delay_seconds=settings.retry_base_delay_seconds,
    )
    sap, _ = create_sap_clients(settings)
    draft = retry_integration_call(
        lambda: sap.create_draft_purchase_order(
            agent.draft_purchase_order(result.selected_vendor, inventory)
        ),
        attempts=settings.retry_attempts,
        base_delay_seconds=settings.retry_base_delay_seconds,
    )
    artifact_bucket = os.environ.get("CHAINMIND_ARTIFACT_BUCKET")
    if artifact_bucket:
        disruption = DisruptionEvent.model_validate(event["event"])
        try:
            retry_integration_call(
                lambda: boto3.client("s3").put_object(
                    Bucket=artifact_bucket,
                    Key=f"runs/{disruption.event_id}/chain-of-thought.json",
                    Body=json.dumps(
                        {
                            "event_id": str(disruption.event_id),
                            "reasoning": result.reasoning,
                            "trace": [step.model_dump(mode="json") for step in result.trace],
                            "fallback_used": result.fallback_used,
                            "fallback_reason": result.fallback_reason,
                            "selected_vendor": result.selected_vendor.vendor.vendor_name,
                        }
                    ).encode("utf-8"),
                    ContentType="application/json",
                ),
                attempts=settings.retry_attempts,
                base_delay_seconds=settings.retry_base_delay_seconds,
            )
        except (BotoCoreError, ClientError) as exc:
            raise IntegrationError(
                "The decision artifact could not be saved to S3.",
                details={"reason": str(exc)},
            ) from exc
    return {
        "result": result.model_dump(mode="json"),
        "draft_po": draft.model_dump(mode="json"),
    }


def execute_approved(event: dict[str, Any], context: object) -> dict[str, str]:
    """Execute a draft only when the callback state confirms explicit approval."""

    del context
    decision = event.get("approval", {}).get("decision")
    if decision != "approve":
        return {"status": "NOT_EXECUTED"}
    from chainmind.core.models import PurchaseOrder

    draft = PurchaseOrder.model_validate(event["orchestration"]["draft_po"])
    settings = Settings()
    sap, _ = create_sap_clients(settings)
    retry_integration_call(
        lambda: sap.create_draft_purchase_order(draft),
        attempts=settings.retry_attempts,
        base_delay_seconds=settings.retry_base_delay_seconds,
    )
    reference = retry_integration_call(
        lambda: sap.execute_purchase_order(draft),
        attempts=settings.retry_attempts,
        base_delay_seconds=settings.retry_base_delay_seconds,
    )
    return {"status": "EXECUTED", "sap_reference": reference}
