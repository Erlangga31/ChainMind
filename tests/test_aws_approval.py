"""Unit tests for authenticated Step Functions approval callbacks."""

from typing import Any
from uuid import uuid4

import pytest

from chainmind.agents.logistics import LogisticsAgent
from chainmind.agents.monitoring import MonitoringAgent
from chainmind.agents.orchestrator import OrchestratorAgent
from chainmind.agents.procurement import ProcurementAgent
from chainmind.core.config import Settings
from chainmind.core.errors import ChainMindError
from chainmind.core.models import DecisionRequest, DecisionType, DisruptionEvent
from chainmind.handlers import approval as approval_handler
from chainmind.integrations.aws import approval
from chainmind.integrations.llm.mock import MockLLMClient
from chainmind.integrations.sap.mock_ariba import MockAribaClient
from chainmind.integrations.sap.mock_s4hana import MockSAPS4HANAClient


class FakeTable:
    def __init__(self) -> None:
        self.item: dict[str, Any] = {
            "run_id": "approval#test",
            "approval_task_token": "opaque-task-token",
        }

    def get_item(self, *, Key: dict[str, str]) -> dict[str, Any]:
        del Key
        return {"Item": self.item.copy()}

    def update_item(
        self,
        *,
        Key: dict[str, str],
        UpdateExpression: str,
        ConditionExpression: str,
        ExpressionAttributeValues: dict[str, str],
    ) -> None:
        del Key, UpdateExpression, ConditionExpression
        self.item["decision_payload"] = ExpressionAttributeValues[":payload"]


class FakeStepFunctions:
    def __init__(self) -> None:
        self.successes: list[dict[str, str]] = []
        self.failures: list[dict[str, str]] = []

    def send_task_success(self, **kwargs: str) -> None:
        self.successes.append(kwargs)

    def send_task_failure(self, **kwargs: str) -> None:
        self.failures.append(kwargs)


def install_clients(monkeypatch: Any) -> tuple[FakeTable, FakeStepFunctions]:
    table = FakeTable()
    stepfunctions = FakeStepFunctions()
    monkeypatch.setattr(
        approval.boto3,
        "resource",
        lambda *args, **kwargs: type("Resource", (), {"Table": lambda self, name: table})(),
    )
    monkeypatch.setattr(approval.boto3, "client", lambda *args, **kwargs: stepfunctions)
    return table, stepfunctions


def test_approver_completes_task_and_same_decision_is_idempotent(monkeypatch: Any) -> None:
    table, stepfunctions = install_clients(monkeypatch)
    client = approval.StepFunctionsApprovalClient("events", "us-east-1")
    run_id = uuid4()
    table.item["run_id"] = f"approval#{run_id}"
    decision = DecisionRequest(decision=DecisionType.APPROVE, note="Approved.")

    client.complete(run_id, decision, "approver")
    client.complete(run_id, decision, "approver")

    assert len(stepfunctions.successes) == 1
    assert stepfunctions.successes[0]["taskToken"] == "opaque-task-token"
    assert '"decision": "approve"' in stepfunctions.successes[0]["output"]


def test_rejection_fails_waiting_task_and_viewer_is_denied(monkeypatch: Any) -> None:
    _, stepfunctions = install_clients(monkeypatch)
    client = approval.StepFunctionsApprovalClient("events", "us-east-1")
    run_id = uuid4()

    with pytest.raises(ChainMindError) as denied:
        client.complete(run_id, DecisionRequest(decision=DecisionType.REJECT), "viewer")
    assert denied.value.status_code == 403

    client.complete(
        run_id,
        DecisionRequest(decision=DecisionType.REJECT, note="Not required."),
        "approver",
    )

    assert stepfunctions.failures[0]["error"] == "HumanRejected"


def test_conflicting_duplicate_decision_is_rejected(monkeypatch: Any) -> None:
    table, _ = install_clients(monkeypatch)
    client = approval.StepFunctionsApprovalClient("events", "us-east-1")
    run_id = uuid4()
    table.item["run_id"] = f"approval#{run_id}"
    table.item["decision_payload"] = DecisionRequest(decision=DecisionType.REJECT).model_dump_json()

    with pytest.raises(ChainMindError) as conflict:
        client.complete(run_id, DecisionRequest(decision=DecisionType.APPROVE), "approver")

    assert conflict.value.code == "decision_conflict"


def test_waiting_approval_handler_persists_run_and_stores_callback_token(
    monkeypatch: Any,
) -> None:
    settings = Settings(mode="mock")
    event = DisruptionEvent(
        title="Weather delay",
        description="Severe weather delayed the cargo vessel.",
        delay_days=5,
    )
    sap = MockSAPS4HANAClient()
    inventory = sap.get_inventory(event.component_id)
    monitoring = MonitoringAgent().analyze(
        event,
        inventory.current_stock / inventory.daily_consumption,
        sap.find_affected_records(event),
    )
    logistics = LogisticsAgent().analyze(event, inventory)
    procurement = ProcurementAgent(MockAribaClient(), settings).compare(
        event,
        inventory,
        logistics,
    )
    orchestrator = OrchestratorAgent(MockLLMClient())
    recommendation = orchestrator.choose(procurement, logistics)
    draft = orchestrator.draft_purchase_order(recommendation.selected_vendor, inventory)
    state = {
        "event": event.model_dump(mode="json"),
        "monitoring": {
            "result": monitoring.model_dump(mode="json"),
            "inventory": inventory.model_dump(mode="json"),
        },
        "logistics": logistics.model_dump(mode="json"),
        "procurement": procurement.model_dump(mode="json"),
        "orchestration": {
            "result": recommendation.model_dump(mode="json"),
            "draft_po": draft.model_dump(mode="json"),
        },
        "workflow": {"revision_count": 1},
    }
    saved_runs = []
    token_items: list[dict[str, Any]] = []

    class RunStore:
        def __init__(self, table_name: str, region_name: str) -> None:
            del table_name, region_name

        def save(self, run: Any) -> None:
            saved_runs.append(run)

    class Table:
        def put_item(self, *, Item: dict[str, Any]) -> None:
            token_items.append(Item)

    monkeypatch.setenv("CHAINMIND_EVENT_TABLE_NAME", "events")
    monkeypatch.setattr(approval_handler, "DynamoDBEventStore", RunStore)
    monkeypatch.setattr(
        approval_handler.boto3,
        "resource",
        lambda *args, **kwargs: type("Resource", (), {"Table": lambda self, name: Table()})(),
    )

    result = approval_handler.store_task_token(
        {
            "run_id": str(event.event_id),
            "taskToken": "opaque-task-token",
            "run": state,
        },
        None,
    )

    assert result == {"run_id": str(event.event_id), "status": "PENDING_APPROVAL"}
    assert saved_runs[0].run_id == event.event_id
    assert saved_runs[0].revision_count == 1
    assert saved_runs[0].draft_po.vendor_id == "vendor-b"
    assert token_items[0]["run_id"] == f"approval#{event.event_id}"
    assert token_items[0]["approval_task_token"] == "opaque-task-token"
