"""End-to-end seeded scenario and human approval boundary tests."""

from importlib.resources import files
from uuid import uuid4

import pytest

from chainmind.core.config import Settings
from chainmind.core.events import EventStore
from chainmind.core.models import (
    DecisionRequest,
    DecisionType,
    DisruptionEvent,
    DisruptionType,
    RunStatus,
)
from chainmind.factory import create_pipeline
from chainmind.integrations.sap.mock_s4hana import MockSAPS4HANAClient


def seeded_event() -> DisruptionEvent:
    """Load the canonical local demo event."""

    raw = files("chainmind.data").joinpath("sample_disruption.json").read_text(encoding="utf-8")
    return DisruptionEvent.model_validate_json(raw)


def test_demo_recommends_vendor_b_and_creates_pending_135k_draft() -> None:
    pipeline = create_pipeline(Settings(mode="mock"), EventStore())

    run = pipeline.run(seeded_event())

    assert run.severity.value == "High"
    assert run.selected_vendor_id == "vendor-b"
    assert len(run.vendor_comparison) == 4
    assert run.status == RunStatus.PENDING_APPROVAL
    assert run.draft_po is not None
    assert run.draft_po.vendor_name == "Vendor B"
    assert run.draft_po.quantity == 5000
    assert run.draft_po.unit_price == 27
    assert run.draft_po.total_price == 135000
    assert run.draft_po.terms == "Air Freight"
    assert run.draft_po.status == "PENDING_APPROVAL"
    assert len(run.stages) == 7
    assert run.stages[-1].name == "Execution & tracking"
    assert all(entry.reasoning for entry in run.audit_log)


def test_approval_is_the_only_path_that_executes_the_purchase_order() -> None:
    sap = MockSAPS4HANAClient()
    pipeline = create_pipeline(Settings(mode="mock"), EventStore(), sap_client=sap)
    run = pipeline.run(seeded_event())

    result = pipeline.decide(
        run.run_id,
        DecisionRequest(decision=DecisionType.APPROVE, note="Budget checked."),
    )

    assert result.status == RunStatus.EXECUTED
    assert result.draft_po is not None
    assert result.draft_po.status == "EXECUTED"
    assert result.draft_po.sap_reference is not None
    approved_run = pipeline.get_run(run.run_id)
    assert approved_run.execution_tracking is not None
    assert approved_run.execution_tracking.ariba_reference.startswith("MOCK-ARIBA-")
    assert approved_run.execution_tracking.confirmation.confirmed_quantity == 5000
    assert approved_run.execution_tracking.line_stoppage_avoided is True
    assert approved_run.execution_tracking.eta_deviation_days == 0
    assert approved_run.execution_tracking.inventory_projection.projected_stock_at_arrival == 6000
    assert sap.get_inventory("microchip-x").current_stock == 3000
    assert sap.get_inventory_projection("microchip-x").projected_stock_at_arrival == 6000
    assert approved_run.kpis is not None
    assert approved_run.kpis.simulated is True
    assert approved_run.kpis.illustrative_savings == (approved_run.kpis.cost_of_inaction - 135000)
    assert any(entry.agent == "human" for entry in approved_run.audit_log)
    approval_stage = next(stage for stage in approved_run.stages if stage.name == "Human approval")
    assert approval_stage.summary == "A human approved the purchase order."
    assert (
        "Purchase order executed as MOCK-PO-"
        in next(stage for stage in approved_run.stages if stage.name == "PO execution").summary
    )
    assert approved_run.stages[-1].status == "COMPLETED"


@pytest.mark.parametrize("event_type", list(DisruptionType))
def test_all_disruption_scenarios_keep_vendor_b_approval_and_tracking_flow(
    event_type: DisruptionType,
) -> None:
    pipeline = create_pipeline(Settings(mode="mock"), EventStore())
    event = seeded_event().model_copy(update={"event_id": uuid4(), "event_type": event_type})

    run = pipeline.run(event)

    assert run.selected_vendor_id == "vendor-b"
    assert run.draft_po is not None
    assert run.draft_po.total_price == 135_000
    assert run.status == RunStatus.PENDING_APPROVAL

    pipeline.decide(run.run_id, DecisionRequest(decision=DecisionType.APPROVE))
    completed = pipeline.get_run(run.run_id)

    assert completed.status == RunStatus.EXECUTED
    assert completed.execution_tracking is not None
    assert completed.execution_tracking.shipment.status == "IN_TRANSIT"
    assert completed.stages[-1].status == "COMPLETED"


def test_revision_replaces_draft_and_still_requires_approval() -> None:
    pipeline = create_pipeline(Settings(mode="mock"), EventStore())
    run = pipeline.run(seeded_event())
    original_po_id = run.draft_po.po_id

    result = pipeline.decide(
        run.run_id,
        DecisionRequest(
            decision=DecisionType.REVISE,
            vendor_id="vendor-a",
            note="Review lower quoted price.",
        ),
    )

    assert result.status == RunStatus.PENDING_APPROVAL
    assert result.draft_po is not None
    assert result.draft_po.vendor_id == "vendor-a"
    assert result.draft_po.po_id != original_po_id
    assert result.draft_po.status == "PENDING_APPROVAL"
    assert "retained at a human's request" in pipeline.get_run(run.run_id).chain_of_thought[-1]


def test_revision_updates_existing_workflow_task_idempotently() -> None:
    pipeline = create_pipeline(Settings(mode="mock"), EventStore())
    run = pipeline.run(seeded_event())
    assert run.workflow_task_id is not None
    revision = DecisionRequest(
        decision=DecisionType.REVISE,
        vendor_id="vendor-a",
        note="Use the alternate supplier.",
    )

    first = pipeline.decide(run.run_id, revision)
    duplicate = pipeline.decide(run.run_id, revision)
    workflow = pipeline._workflow

    assert first.draft_po is not None
    assert duplicate.draft_po is not None
    assert duplicate.draft_po.po_id == first.draft_po.po_id
    task = workflow.task_for_run(str(run.run_id))
    assert task is not None
    assert task["po_id"] == str(first.draft_po.po_id)
    assert task["status"] == "PENDING"
