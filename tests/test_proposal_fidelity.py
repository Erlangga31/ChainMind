"""Behavioral checks for proposal claims that can run against the local mock pipeline."""

import json
from datetime import date, timedelta
from importlib.resources import files
from typing import Any

import pytest
from fastapi.testclient import TestClient

import chainmind.api.main as api
from chainmind.api.identity import AuthenticatedUser, authenticated_user
from chainmind.core.config import Settings
from chainmind.core.events import EventStore
from chainmind.core.models import DecisionRequest, DecisionType, DisruptionEvent, RunStatus
from chainmind.factory import create_pipeline
from chainmind.integrations.aws import event_store as event_store_module
from chainmind.integrations.aws.event_store import DynamoDBEventStore
from chainmind.notifications.links import NotificationLinkSigner
from chainmind.notifications.service import NotificationService


def seeded_event() -> DisruptionEvent:
    seed = files("chainmind.data").joinpath("sample_disruption.json").read_text(encoding="utf-8")
    return DisruptionEvent.model_validate_json(seed)


def make_pipeline():
    notification_service = NotificationService(
        [],
        NotificationLinkSigner("proposal-fidelity-test-secret-at-least-32", 60),
        api_base_url="http://localhost:8000",
        dashboard_url="http://localhost:5173",
    )
    return create_pipeline(
        Settings(mode="mock", notification_backends=[]),
        EventStore(),
        notification_service=notification_service,
    )


def test_seeded_run_matches_proposal_agents_vendors_and_draft_po() -> None:
    run = make_pipeline().run(seeded_event())

    assert [stage.name for stage in run.stages[:4]] == [
        "Monitoring",
        "Logistics",
        "Procurement",
        "Orchestrator",
    ]
    assert run.significant is True
    assert len(run.vendor_comparison) >= 2
    assert run.selected_vendor_id == "vendor-b"
    assert run.status == RunStatus.PENDING_APPROVAL
    assert run.draft_po is not None
    assert run.draft_po.status == "PENDING_APPROVAL"
    assert run.draft_po.component_name == "Microchip X"
    assert run.draft_po.quantity == 5000
    assert run.draft_po.unit_price == 27
    assert run.draft_po.total_price == 135000
    assert run.draft_po.vendor_name == "Vendor B"
    assert run.draft_po.expected_date == date.today() + timedelta(days=2)
    assert run.draft_po.terms == "Air Freight"


def test_proposal_steps_are_audited_in_order_with_cot_and_notification_format() -> None:
    pipeline = make_pipeline()
    run = pipeline.run(seeded_event())

    mapped_steps = [
        entry.proposal_step for entry in run.audit_log if entry.proposal_step is not None
    ]
    assert mapped_steps == sorted(mapped_steps)
    assert mapped_steps[0] == 1
    assert set(mapped_steps) == set(range(1, 8))
    assert run.audit_log[0].agent == "event_ingestion"
    assert any(entry.agent == "monitoring" and entry.proposal_step == 2 for entry in run.audit_log)
    assert any(entry.agent == "procurement" and entry.proposal_step == 4 for entry in run.audit_log)
    assert any(
        entry.agent == "orchestrator" and entry.proposal_step == 5 for entry in run.audit_log
    )
    assert any(
        entry.agent == "sap_business_workflow" and entry.proposal_step == 6
        for entry in run.audit_log
    )
    assert any(
        entry.agent == "notifications" and entry.proposal_step == 7 for entry in run.audit_log
    )
    assert any(step.startswith("[SAP S/4HANA]") for step in run.chain_of_thought)
    assert any(step.startswith("[SAP Ariba]") for step in run.chain_of_thought)
    assert any(step.startswith("[Amazon Bedrock]") for step in run.chain_of_thought)
    assert "cost of inaction" in run.chain_of_thought[-1].lower()
    assert "human must approve" in run.chain_of_thought[-1].lower()

    service = NotificationService(
        [],
        NotificationLinkSigner("proposal-fidelity-test-secret-at-least-32", 60),
        api_base_url="http://localhost:8000",
        dashboard_url="http://localhost:5173",
    )
    notification = service.notify(run, "draft_ready")
    assert notification.text.startswith("Bahan baku Microchip X terlambat 5 hari.")
    assert "(sumber: SAP S/4HANA)." in notification.text
    assert (
        "Rekomendasi: beli dari Vendor B seharga $135,000 (sumber: SAP Ariba)." in notification.text
    )
    assert "Setujui (membuka tinjauan eksplisit; tidak langsung mengeksekusi):" in notification.text
    assert "Lihat detail:" in notification.text


def test_execution_requires_approval_and_adds_explicit_eight_step_audit() -> None:
    pipeline = make_pipeline()
    pending = pipeline.run(seeded_event())

    assert pending.draft_po is not None
    assert pending.draft_po.sap_reference is None
    assert pending.execution_tracking is None
    assert all(entry.proposal_step != 8 for entry in pending.audit_log)

    result = pipeline.decide(pending.run_id, DecisionRequest(decision=DecisionType.APPROVE))
    executed = pipeline.get_run(pending.run_id)

    assert result.status == RunStatus.EXECUTED
    assert executed.draft_po is not None
    assert executed.draft_po.status == "EXECUTED"
    assert executed.execution_tracking is not None
    assert [entry.kind for entry in executed.execution_tracking.monitoring_outputs] == [
        "shipment",
        "eta",
        "inventory",
        "deviation",
        "kpi",
    ]
    step_eight = [entry for entry in executed.audit_log if entry.proposal_step == 8]
    assert any(entry.agent == "human" for entry in step_eight)
    assert any(entry.agent == "execution_tracking" for entry in step_eight)
    mapped_steps = [entry.proposal_step for entry in executed.audit_log if entry.proposal_step]
    assert mapped_steps == sorted(mapped_steps)
    assert set(mapped_steps) == set(range(1, 9))


def test_kpi_api_exposes_all_four_proposal_comparison_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    pipeline = make_pipeline()
    monkeypatch.setattr(api, "pipeline", pipeline)
    monkeypatch.setattr(api, "settings", Settings(mode="mock", notification_backends=[]))
    approver = AuthenticatedUser(
        subject="test-approver:demo",
        roles=frozenset({"approver"}),
        tenant_id="demo",
    )
    monkeypatch.setitem(api.app.dependency_overrides, authenticated_user, lambda: approver)
    monkeypatch.setitem(api.app.dependency_overrides, api.tenant_context, lambda: approver)

    with TestClient(api.app) as client:
        created = client.post(
            "/disruptions",
            json={
                "title": "Extreme weather delays cargo ship",
                "description": "The vessel carrying Microchip X is delayed.",
                "delay_days": 5,
                "event_type": "weather",
            },
            headers={"Authorization": "Bearer test-approver:demo"},
        )
        run_id = created.json()["run_id"]
        client.post(
            f"/runs/{run_id}/decision",
            json={"decision": "approve"},
            headers={"Authorization": "Bearer test-approver:demo"},
        )
        report = client.get("/kpis", headers={"Authorization": "Bearer test-approver:demo"})

    assert report.status_code == 200
    assert len(report.json()["comparison"]) == 4
    assert {row["metric"] for row in report.json()["comparison"]} == {
        "Response time",
        "Line-stoppage risk",
        "Procurement workload",
        "Decision consistency",
    }


def test_s3_equivalent_archive_contains_the_audit_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    dynamodb_items: list[dict[str, Any]] = []
    s3_objects: list[dict[str, Any]] = []

    class Table:
        def put_item(self, *, Item: dict[str, Any]) -> None:
            dynamodb_items.append(Item)

    class S3:
        def put_object(self, **kwargs: Any) -> None:
            s3_objects.append(kwargs)

    class Resource:
        def Table(self, table_name: str):
            assert table_name == "chainmind-events"
            return Table()

    monkeypatch.setenv("CHAINMIND_ARTIFACT_BUCKET", "test-audit-archive")
    monkeypatch.setattr(event_store_module.boto3, "resource", lambda *args, **kwargs: Resource())
    monkeypatch.setattr(event_store_module.boto3, "client", lambda *args, **kwargs: S3())
    pipeline = make_pipeline()
    run = pipeline.run(seeded_event())
    pipeline.decide(run.run_id, DecisionRequest(decision=DecisionType.APPROVE))
    completed = pipeline.get_run(run.run_id)

    DynamoDBEventStore("chainmind-events", "us-east-1").save(completed)

    archived_trace = next(item for item in s3_objects if item["Key"].endswith("trace-audit.json"))
    payload = json.loads(archived_trace["Body"])
    archived_steps = {
        entry["proposal_step"]
        for entry in payload["audit_log"]
        if entry.get("proposal_step") is not None
    }
    assert len(dynamodb_items) == 2
    assert archived_steps == set(range(1, 9))
