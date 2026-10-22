"""End-to-end seeded scenario and human approval boundary tests."""

from importlib.resources import files

from chainmind.core.config import Settings
from chainmind.core.events import EventStore
from chainmind.core.models import DecisionRequest, DecisionType, DisruptionEvent, RunStatus
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
    assert len(run.stages) == 6
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
    assert approved_run.audit_log[-1].agent == "human"
    assert approved_run.stages[-2].summary == "A human approved the purchase order."
    assert "Purchase order executed as MOCK-PO-" in approved_run.stages[-1].summary


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
