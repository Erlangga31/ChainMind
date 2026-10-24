"""Persist Step Functions callback tokens for human-in-the-loop approval."""

import os
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import ValidationError

from chainmind.core.errors import IntegrationError
from chainmind.core.models import (
    AuditEntry,
    DisruptionEvent,
    DisruptionRun,
    InventorySnapshot,
    LogisticsResult,
    MonitoringResult,
    OrchestratorResult,
    ProcurementResult,
    RunStatus,
    StageResult,
)
from chainmind.integrations.aws.event_store import DynamoDBEventStore
from chainmind.workflow.definition import WorkflowState


def _persist_waiting_run(
    payload: dict[str, Any],
    table_name: str,
    region_name: str,
) -> DisruptionRun:
    """Map the Step Functions state to the API's persisted run model."""

    try:
        event = DisruptionEvent.model_validate(payload["event"])
        monitoring = MonitoringResult.model_validate(payload["monitoring"]["result"])
        inventory = InventorySnapshot.model_validate(payload["monitoring"]["inventory"])
        logistics = LogisticsResult.model_validate(payload["logistics"])
        procurement = ProcurementResult.model_validate(payload["procurement"])
        orchestration = OrchestratorResult.model_validate(payload["orchestration"]["result"])
        draft = payload["orchestration"]["draft_po"]
        from chainmind.core.models import PurchaseOrder

        purchase_order = PurchaseOrder.model_validate(draft)
        revision_count = int(payload.get("workflow", {}).get("revision_count", 0))
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise IntegrationError(
            "The Step Functions approval state could not be mapped to a disruption run."
        ) from exc
    run_id = event.event_id
    run = DisruptionRun(
        run_id=run_id,
        event=event,
        status=RunStatus.PENDING_APPROVAL,
        workflow_state=WorkflowState.HUMAN_APPROVAL,
        revision_count=revision_count,
        severity=monitoring.severity,
        significant=monitoring.significant,
        affected_records=monitoring.affected_records,
        stages=[
            StageResult(name="Monitoring", status="COMPLETED", summary=monitoring.summary),
            StageResult(name="Logistics", status="COMPLETED", summary=logistics.summary),
            StageResult(name="Procurement", status="COMPLETED", summary=procurement.summary),
            StageResult(
                name="Orchestrator",
                status="COMPLETED",
                summary=orchestration.summary,
            ),
            StageResult(
                name="Human approval",
                status="PENDING",
                summary="A human decision is required before purchase-order execution.",
            ),
            StageResult(
                name="PO execution",
                status="WAITING_FOR_APPROVAL",
                summary="No PO has been executed.",
            ),
            StageResult(
                name="Execution & tracking",
                status="WAITING_FOR_APPROVAL",
                summary="Supplier confirmation and shipment tracking start after approval.",
            ),
        ],
        vendor_comparison=procurement.evaluations,
        selected_vendor_id=orchestration.selected_vendor.vendor.vendor_id,
        chain_of_thought=[
            monitoring.reasoning,
            logistics.reasoning,
            procurement.reasoning,
            *(f"[{step.source}] {step.text}" for step in orchestration.trace),
            orchestration.reasoning,
        ],
        trace_steps=orchestration.trace,
        draft_po=purchase_order,
        cost_of_inaction=logistics.cost_of_inaction,
        inventory_snapshot=inventory,
        workflow_task_id=str(run_id),
        audit_log=[
            AuditEntry(
                agent="monitoring",
                input_summary=event.model_dump_json(),
                output_summary=monitoring.summary,
                reasoning=monitoring.reasoning,
            ),
            AuditEntry(
                agent="logistics",
                input_summary=event.component_id,
                output_summary=logistics.summary,
                reasoning=logistics.reasoning,
            ),
            AuditEntry(
                agent="procurement",
                input_summary=event.component_id,
                output_summary=procurement.summary,
                reasoning=procurement.reasoning,
            ),
            AuditEntry(
                agent="orchestrator",
                input_summary=event.component_id,
                output_summary=orchestration.summary,
                reasoning=orchestration.reasoning,
            ),
        ],
    )
    DynamoDBEventStore(table_name, region_name).save(run)
    return run


def store_task_token(event: dict[str, Any], context: object) -> dict[str, str]:
    """Persist a callback token; the approval API later completes the task."""

    del context
    run_id = event.get("run_id")
    task_token = event.get("taskToken")
    table_name = os.environ.get("CHAINMIND_EVENT_TABLE_NAME")
    if not run_id or not task_token or not table_name:
        raise IntegrationError("Approval callback is missing its run ID, token, or table name.")
    run_payload = event.get("run")
    region_name = os.environ.get("CHAINMIND_AWS_REGION", "us-east-1")
    run = None
    if isinstance(run_payload, dict):
        try:
            run = _persist_waiting_run(run_payload, table_name, region_name)
        except IntegrationError:
            raise
    try:
        boto3.resource("dynamodb", region_name=region_name).Table(table_name).put_item(
            Item={
                "run_id": f"approval#{run_id}",
                "approval_task_token": task_token,
            }
        )
    except (BotoCoreError, ClientError) as exc:
        raise IntegrationError("The approval callback token could not be stored.") from exc
    from chainmind.core.config import Settings
    from chainmind.factory import create_notification_service

    notification_service = create_notification_service(Settings())
    if notification_service is not None and run is not None:
        message = notification_service.notify(run, "draft_ready")
        run.audit_log.append(
            AuditEntry(
                agent="notifications",
                input_summary=f"run_id={run.run_id}; event=draft_ready",
                output_summary=(
                    f"Draft notification delivered to "
                    f"{notification_service.channel_count} channel(s)."
                ),
                reasoning=(notification_service.audit_summary(message)),
            )
        )
        DynamoDBEventStore(table_name, region_name).save(run)
    return {"run_id": run_id, "status": "PENDING_APPROVAL"}
