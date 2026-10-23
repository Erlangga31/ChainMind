"""Local HTTP contract tests for authenticated SAP integration clients."""

from datetime import date
from uuid import uuid4

import httpx
import pytest

from chainmind.core.config import Settings
from chainmind.core.errors import IntegrationError
from chainmind.core.models import (
    DecisionRequest,
    DisruptionEvent,
    InventoryProjection,
    PurchaseOrder,
)
from chainmind.factory import create_pipeline
from chainmind.integrations.sap.http import SAPCredentials, SAPHttpTransport
from chainmind.integrations.sap.real_clients import (
    RealAribaClient,
    RealS4HANAClient,
    SandboxWorkflowClient,
)


def settings_for_sandbox(url: str) -> Settings:
    """Build credential-only settings for a local sandbox endpoint."""

    return Settings(
        sap_backend="sandbox",
        sap_integration_suite_url=url,
        sap_token_url=f"{url}/oauth/token",
        sap_client_id="local-contract-client",
        sap_client_secret="local-contract-secret",
        sap_timeout_seconds=2,
        retry_base_delay_seconds=0,
    )


def test_s4hana_client_reads_typed_inventory_and_writes_approved_order(
    sap_sandbox_url: str,
) -> None:
    transport = SAPHttpTransport(
        base_url=sap_sandbox_url,
        token_url=f"{sap_sandbox_url}/oauth/token",
        credentials=SAPCredentials("local-contract-client", "local-contract-secret"),
        timeout_seconds=2,
        retry_base_delay_seconds=0,
    )
    client = RealS4HANAClient(transport)
    inventory = client.get_inventory("microchip-x")

    assert inventory.current_stock == 3000
    assert inventory.daily_consumption == 1000

    draft = PurchaseOrder(
        vendor_id="vendor-b",
        vendor_name="Vendor B",
        component_id="microchip-x",
        component_name="Microchip X",
        quantity=5000,
        unit_price=27,
        total_price=135000,
    )
    created = client.create_draft_purchase_order(draft)
    assert created.status == "PENDING_APPROVAL"
    assert client.execute_purchase_order(created) == f"MOCK-PO-{created.po_id.hex[:8].upper()}"
    transport.close()


def test_ariba_client_maps_vendor_records_from_the_sandbox(sap_sandbox_url: str) -> None:
    transport = SAPHttpTransport(
        base_url=sap_sandbox_url,
        token_url=f"{sap_sandbox_url}/oauth/token",
        credentials=SAPCredentials("local-contract-client", "local-contract-secret"),
        timeout_seconds=2,
        retry_base_delay_seconds=0,
    )
    client = RealAribaClient(transport)

    vendors = client.list_alternative_vendors(
        DisruptionEvent(
            title="Port delay",
            description="Shipment of Microchip X is delayed.",
            delay_days=5,
        )
    )

    assert len(vendors) == 4
    assert next(vendor for vendor in vendors if vendor.vendor_id == "vendor-b").total_cost == 135000
    order = PurchaseOrder(
        vendor_id="vendor-b",
        vendor_name="Vendor B",
        component_id="microchip-x",
        component_name="Microchip X",
        quantity=5000,
        unit_price=27,
        total_price=135000,
    )
    reference = client.submit_purchase_order(order)
    confirmation = client.get_vendor_confirmation(order)
    shipment = client.get_shipment_tracking(order)
    assert reference.startswith("MOCK-ARIBA-")
    assert confirmation.confirmed_quantity == 5000
    assert shipment.tracking_id.startswith("ASN-")
    transport.close()


def test_workflow_client_and_dashboard_callback_are_idempotent(
    sap_sandbox_url: str,
) -> None:
    client = SandboxWorkflowClient(sap_sandbox_url, timeout_seconds=2)
    run_id = str(uuid4())
    task_id = client.create_task(run_id, "draft-po")

    assert client.create_task(run_id, "draft-po") == task_id
    client.update_draft(task_id, "revised-po")
    client.record_decision(task_id, "approve", "Approved via dashboard.")
    client.record_decision(task_id, "approve", "Approved via dashboard.")
    response = httpx.get(f"{sap_sandbox_url}/workflow/tasks/{task_id}", timeout=2)

    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    assert response.json()["po_id"] == "revised-po"
    client.close()


def test_pipeline_runs_through_sandbox_and_keeps_approval_workflow_consistent(
    sap_sandbox_url: str,
) -> None:
    settings = settings_for_sandbox(sap_sandbox_url).model_copy(
        update={"sap_workflow_base_url": sap_sandbox_url}
    )
    pipeline = create_pipeline(settings)
    event = DisruptionEvent(
        title="Weather delay",
        description="Severe weather delays the Microchip X cargo.",
        delay_days=5,
    )

    run = pipeline.run(event)
    task_id = run.workflow_task_id
    assert run.selected_vendor_id == "vendor-b"
    assert run.draft_po is not None
    assert run.draft_po.total_price == 135000
    assert task_id is not None
    assert (
        httpx.get(
            f"{sap_sandbox_url}/workflow/tasks/{task_id}",
            timeout=2,
        ).json()["status"]
        == "PENDING"
    )

    decision = DecisionRequest(decision="approve", note="Approved in contract test.")
    result = pipeline.decide(run.run_id, decision)
    duplicate = pipeline.decide(run.run_id, decision)
    workflow_task = httpx.get(
        f"{sap_sandbox_url}/workflow/tasks/{task_id}",
        timeout=2,
    ).json()

    assert result.status.value == "EXECUTED"
    completed = pipeline.get_run(run.run_id)
    assert completed.execution_tracking is not None
    assert completed.execution_tracking.confirmation.confirmed_quantity == 5000
    assert completed.execution_tracking.shipment.estimated_arrival
    assert completed.kpis is not None
    assert completed.stages[-1].name == "Execution & tracking"
    assert completed.stages[-1].status == "COMPLETED"
    assert duplicate.message == "This decision was already recorded."
    assert workflow_task["status"] == "APPROVED"
    assert workflow_task["decision"] == "approve"


def test_sap_sandbox_persists_inventory_projection(sap_sandbox_url: str) -> None:
    transport = SAPHttpTransport(
        base_url=sap_sandbox_url,
        token_url=f"{sap_sandbox_url}/oauth/token",
        credentials=SAPCredentials("local-contract-client", "local-contract-secret"),
        timeout_seconds=2,
        retry_base_delay_seconds=0,
    )
    client = RealS4HANAClient(transport)
    projection = InventoryProjection(
        component_id="microchip-x",
        current_stock=3000,
        daily_consumption=1000,
        confirmed_receipt_quantity=5000,
        expected_arrival=date.today(),
        projected_stock_at_arrival=6000,
        projected_coverage_days=6,
    )

    client.record_inventory_projection(projection)

    saved = transport.request(
        "GET",
        "/sap/opu/odata/sap/Z_CHAINMIND_TRACKING_SRV/InventoryProjection/microchip-x",
    )
    assert saved["d"]["projected_stock_at_arrival"] == 6000
    transport.close()


def test_oauth_transport_does_not_retry_client_errors(sap_sandbox_url: str) -> None:
    transport = SAPHttpTransport(
        base_url=sap_sandbox_url,
        token_url=f"{sap_sandbox_url}/oauth/token",
        credentials=SAPCredentials("local-contract-client", "local-contract-secret"),
        timeout_seconds=2,
        retry_attempts=3,
        retry_base_delay_seconds=0,
    )

    with pytest.raises(IntegrationError, match="SAP rejected the request"):
        transport.request("GET", "/missing-route")
    transport.close()


def test_oauth_transport_refreshes_invalid_token_before_retrying() -> None:
    token_calls = 0
    authorization_headers: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.path == "/oauth/token":
            token_calls += 1
            return httpx.Response(
                200,
                json={"access_token": f"token-{token_calls}", "expires_in": 3600},
            )
        authorization_headers.append(request.headers.get("Authorization", ""))
        if request.method == "GET" and request.headers.get("Authorization", "").endswith("token-1"):
            return httpx.Response(401, json={"error": "invalid_token"})
        if request.method == "GET":
            return httpx.Response(200, headers={"X-CSRF-Token": "csrf-token"}, json={})
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(respond), timeout=2)
    transport = SAPHttpTransport(
        base_url="https://sap.example.invalid",
        token_url="https://sap.example.invalid/oauth/token",
        credentials=SAPCredentials("client", "secret"),
        retry_base_delay_seconds=0,
        client=client,
    )

    result = transport.request("POST", "/purchase-orders", csrf=True)

    assert result == {"ok": True}
    assert token_calls == 2
    assert len(authorization_headers) == 3
    assert all(header.startswith("Bearer ") for header in authorization_headers)
    transport.close()
    client.close()


def test_aws_credentials_require_a_secret_reference() -> None:
    settings = Settings(
        mode="aws",
        sap_backend="real",
        sap_integration_suite_url="https://integration.example.invalid",
        sap_token_url="https://integration.example.invalid/oauth/token",
    )

    with pytest.raises(IntegrationError, match="Secrets Manager secret ID"):
        RealS4HANAClient(settings=settings)
