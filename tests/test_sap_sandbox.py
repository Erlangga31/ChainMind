"""Contract tests for the local SAP, Event Mesh, and Workflow simulators."""

from typing import Any

import httpx
from fastapi.testclient import TestClient

from sandbox.sap_sandbox.config import SandboxSettings
from sandbox.sap_sandbox.main import create_app


def make_client() -> TestClient:
    """Return an isolated test client for the SAP sandbox."""

    settings = SandboxSettings(
        event_webhook_url="http://chainmind.test/disruptions",
        workflow_callback_url="http://chainmind.test",
    )
    return TestClient(create_app(settings))


def test_s4hana_exposes_stock_and_odata_query_options() -> None:
    client = make_client()

    response = client.get(
        "/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV/A_MaterialStock",
        params={"$filter": "Material eq 'microchip-x'", "$select": "Material,DailyConsumption"},
    )

    assert response.status_code == 200
    assert response.json()["d"]["results"] == [
        {"Material": "microchip-x", "DailyConsumption": 1000}
    ]
    assert (
        client.get(
            "/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV/A_MaterialStock('microchip-x')"
        ).json()["d"]["Material"]
        == "microchip-x"
    )
    assert (
        client.get("/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV/A_ProductionSchedule").json()["d"][
            "results"
        ][0]["PlannedQuantity"]
        == 1000
    )
    assert (
        client.get("/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV/A_ScheduledReceipt").json()["d"][
            "results"
        ][0]["Quantity"]
        == 1000
    )
    assert (
        client.get(
            "/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV/A_BillOfMaterialItem",
            params={"$top": 1},
        ).json()["d"]["results"][0]["BillOfMaterial"]
        == "BOM-MICROCHIP-X"
    )


def test_odata_invalid_filter_uses_odata_error_format() -> None:
    client = make_client()

    response = client.get(
        "/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV/A_MaterialStock",
        params={"$filter": "Material contains 'microchip'"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "400"


def test_odata_write_requires_csrf_token() -> None:
    client = make_client()
    response = client.post(
        "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder",
        json={
            "vendor_id": "vendor-b",
            "vendor_name": "Vendor B",
            "component_id": "microchip-x",
            "component_name": "Microchip X",
            "quantity": 5000,
            "unit_price": 27,
            "total_price": 135000,
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_token_required"


def test_purchase_order_can_be_created_read_and_patched() -> None:
    client = make_client()
    order = {
        "vendor_id": "vendor-b",
        "vendor_name": "Vendor B",
        "component_id": "microchip-x",
        "component_name": "Microchip X",
        "quantity": 5000,
        "unit_price": 27,
        "total_price": 135000,
        "terms": "Air Freight",
    }

    po_collection = "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder"
    csrf_token = client.get(po_collection, headers={"X-CSRF-Token": "Fetch"}).headers[
        "X-CSRF-Token"
    ]
    created = client.post(po_collection, json=order, headers={"X-CSRF-Token": csrf_token})

    assert created.status_code == 201
    assert created.json()["d"]["status"] == "PENDING_APPROVAL"
    po_id = created.json()["d"]["po_id"]
    assert (
        client.get(
            f"/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder/{po_id}"
        ).json()["d"]["total_price"]
        == 135000
    )
    assert (
        client.get(
            f"/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder('{po_id}')"
        ).json()["d"]["total_price"]
        == 135000
    )

    patched = client.patch(
        f"/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder('{po_id}')",
        json={"status": "APPROVED"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert patched.json()["d"]["status"] == "APPROVED"
    assert (
        client.get(
            "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder",
            params={"$filter": "status eq 'APPROVED'", "$top": 1},
        ).json()["d"]["results"][0]["po_id"]
        == po_id
    )


def test_ariba_returns_four_seed_vendors_and_offer_details() -> None:
    client = make_client()

    vendors = client.get("/ariba/sourcing/vendors").json()["d"]["results"]
    offer = client.get("/ariba/sourcing/vendors/vendor-b/offers").json()["d"]["results"][0]

    assert [vendor["vendor_id"] for vendor in vendors] == [
        "vendor-a",
        "vendor-b",
        "vendor-c",
        "vendor-d",
    ]
    assert offer["lead_time_days"] == 2
    assert offer["total_cost"] == 135000
    assert offer["capacity"] == 8000
    assert offer["risk_score"] == 88
    assert offer["rating"] == 1.5


def test_oauth_token_endpoint_issues_ephemeral_client_credentials_token() -> None:
    client = make_client()

    response = client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "local-demo-client",
            "client_secret": "local-demo-secret",
        },
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "Bearer"
    assert response.json()["expires_in"] == 3600
    assert response.json()["access_token"]


def test_scenarios_include_weather_geopolitics_supplier_failure_and_congestion() -> None:
    client = make_client()

    scenarios = client.get("/scenarios").json()

    assert len(scenarios) == 4
    assert {scenario["event_type"] for scenario in scenarios} == {
        "weather",
        "geopolitical",
        "vendor_failure",
        "port_congestion",
    }


def test_event_mesh_injects_scenario_to_configured_webhook(
    monkeypatch: Any,
) -> None:
    import sandbox.sap_sandbox.main as sandbox_main

    delivered: list[tuple[str, dict[str, Any]]] = []

    async def capture_webhook(url: str, payload: dict[str, Any]) -> None:
        delivered.append((url, payload))

    monkeypatch.setattr(sandbox_main, "post_webhook", capture_webhook)
    client = make_client()

    response = client.post("/scenarios/border-closure/inject")

    assert response.status_code == 202
    assert delivered[0][0] == "http://chainmind.test/disruptions"
    assert delivered[0][1]["source"] == "geopolitical-risk-feed"


def test_event_mesh_reports_webhook_failure(monkeypatch: Any) -> None:
    import sandbox.sap_sandbox.main as sandbox_main

    async def fail_webhook(_: str, __: dict[str, Any]) -> None:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(sandbox_main, "post_webhook", fail_webhook)
    client = make_client()
    event = {
        "title": "Weather delay",
        "description": "A weather event delays a vessel.",
        "delay_days": 5,
    }

    response = client.post("/event-mesh/publish", json={"event": event})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "webhook_delivery_failed"
    assert client.get("/event-mesh/events").json()["events"] == []


def test_workflow_task_is_idempotent_and_callback_runs_once(monkeypatch: Any) -> None:
    import sandbox.sap_sandbox.main as sandbox_main

    delivered: list[tuple[str, dict[str, Any]]] = []

    async def capture_webhook(url: str, payload: dict[str, Any]) -> None:
        delivered.append((url, payload))

    monkeypatch.setattr(sandbox_main, "post_webhook", capture_webhook)
    client = make_client()
    task_input = {"run_id": "run-123", "po_id": "po-456"}
    created = client.post("/workflow/tasks", json=task_input).json()
    duplicated = client.post("/workflow/tasks", json=task_input).json()

    assert duplicated["task_id"] == created["task_id"]
    decision_url = f"/workflow/tasks/{created['task_id']}/decision"
    decision = {"decision": "approve", "note": "Approved for demo."}
    first = client.post(decision_url, json=decision)
    second = client.post(decision_url, json=decision)

    assert first.status_code == 200
    assert second.json()["status"] == "APPROVED"
    assert delivered == [
        (
            "http://chainmind.test/runs/run-123/decision",
            {"decision": "approve", "note": "Approved for demo."},
        )
    ]


def test_workflow_rejects_conflicting_duplicate_decision(monkeypatch: Any) -> None:
    import sandbox.sap_sandbox.main as sandbox_main

    async def capture_webhook(_: str, __: dict[str, Any]) -> None:
        return None

    monkeypatch.setattr(sandbox_main, "post_webhook", capture_webhook)
    client = make_client()
    task = client.post(
        "/workflow/tasks",
        json={"run_id": "run-conflict", "po_id": "po-conflict"},
    ).json()
    endpoint = f"/workflow/tasks/{task['task_id']}/decision"

    assert client.post(endpoint, json={"decision": "reject"}).status_code == 200
    response = client.post(endpoint, json={"decision": "approve"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "decision_conflict"
