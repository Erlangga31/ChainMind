"""Validate SAP sandbox payloads and adapter mappings against checked-in contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sap_sandbox.config import SandboxSettings
from sap_sandbox.main import create_app

from chainmind.core.models import DisruptionEvent, PurchaseOrder
from chainmind.integrations.sap.real_clients import RealAribaClient, RealS4HANAClient

CONTRACTS = Path(__file__).parents[1] / "contracts" / "sap"
ODATA = "/sap/opu/odata/sap"


def _schema(name: str) -> dict[str, Any]:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def _assert_contract(name: str, payload: dict[str, Any]) -> None:
    Draft202012Validator(_schema(name)).validate(payload)


def _sandbox_client() -> TestClient:
    settings = SandboxSettings(
        event_webhook_url="http://chainmind.test/events",
        event_bridge_secret="contract-test-secret",
        workflow_callback_url="http://chainmind.test",
    )
    client = TestClient(create_app(settings))
    response = client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "contract-test",
            "client_secret": "contract-test",
        },
    )
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    return client


def test_material_stock_sandbox_response_and_metadata_follow_contract() -> None:
    client = _sandbox_client()
    response = client.get(f"{ODATA}/API_MATERIAL_STOCK_SRV/A_MaterialStock")
    _assert_contract("material-stock.schema.json", response.json())
    entity = response.json()["d"]["results"][0]
    assert entity["Material"] == "microchip-x"
    assert entity["MatlWrhsStkQtyInMatBaseUnit"] == 3000
    assert entity["__metadata"]["type"] == "API_MATERIAL_STOCK_SRV.A_MaterialStock"

    metadata = client.get(f"{ODATA}/API_MATERIAL_STOCK_SRV/$metadata")
    root = ET.fromstring(metadata.text)
    assert root.tag.endswith("Edmx")
    assert "MatlWrhsStkQtyInMatBaseUnit" in metadata.text
    assert "DailyConsumption" in metadata.text


def test_business_partner_and_purchase_order_sandbox_responses_follow_contract() -> None:
    client = _sandbox_client()
    supplier_response = client.get(f"{ODATA}/API_BUSINESS_PARTNER/A_Supplier")
    _assert_contract("business-partner.schema.json", supplier_response.json())
    supplier_metadata = client.get(f"{ODATA}/API_BUSINESS_PARTNER/$metadata")
    assert supplier_metadata.status_code == 200
    assert ET.fromstring(supplier_metadata.content).tag.endswith("Edmx")

    po_path = f"{ODATA}/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder"
    csrf = client.get(po_path, headers={"X-CSRF-Token": "Fetch"}).headers["X-CSRF-Token"]
    order_request = {
        "PurchaseOrder": "4500000999",
        "PurchaseOrderItem": "00010",
        "Supplier": "vendor-b",
        "Material": "microchip-x",
        "OrderQuantity": 5000,
        "NetPriceAmount": 27,
        "DocumentCurrency": "USD",
        "ChainMindPurchaseOrderId": "11111111-1111-4111-8111-111111111111",
        "ChainMindVendorName": "Vendor B",
        "ChainMindMaterialName": "Microchip X",
        "ChainMindTotalPrice": 135000,
        "ChainMindTerms": "Air Freight",
    }
    created = client.post(
        po_path,
        headers={"X-CSRF-Token": csrf},
        json=order_request,
    )
    _assert_contract("purchase-order-request.schema.json", order_request)
    assert created.status_code == 201
    _assert_contract("purchase-order.schema.json", created.json())
    assert created.json()["d"]["Supplier"] == "vendor-b"
    metadata = client.get(f"{ODATA}/API_PURCHASEORDER_PROCESS_SRV/$metadata")
    assert metadata.status_code == 200
    assert "NetPriceAmount" in metadata.text
    assert ET.fromstring(metadata.content).tag.endswith("Edmx")


def test_ariba_custom_sourcing_confirmation_and_asn_contracts() -> None:
    client = _sandbox_client()
    _assert_contract(
        "ariba-sourcing-confirmation.schema.json",
        client.get("/ariba/sourcing/vendors").json(),
    )
    metadata = client.get("/ariba/$metadata")
    assert metadata.status_code == 200
    assert ET.fromstring(metadata.content).tag.endswith("Edmx")
    order = {
        "po_id": "11111111-1111-4111-8111-111111111111",
        "vendor_id": "vendor-b",
        "vendor_name": "Vendor B",
        "component_id": "microchip-x",
        "component_name": "Microchip X",
        "quantity": 5000,
        "unit_price": 27,
        "total_price": 135000,
    }
    submitted = client.post("/ariba/po", json=order)
    assert submitted.status_code == 200
    _assert_contract("ariba-sourcing-confirmation.schema.json", submitted.json())
    offer = client.get("/ariba/sourcing/vendors/vendor-b/offers").json()["d"]["results"][0]
    assert offer["vendor_id"] == "vendor-b"
    assert offer["__metadata"]["type"] == "CHAINMIND_ARIBA_ADAPTER.SupplierOffer"
    created_po_id = order["po_id"]
    _assert_contract(
        "ariba-sourcing-confirmation.schema.json",
        client.get(f"/ariba/po/{created_po_id}/confirmation").json(),
    )
    _assert_contract(
        "ariba-sourcing-confirmation.schema.json",
        client.get(f"/ariba/po/{created_po_id}/asn").json(),
    )


class StubTransport:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        self.requests.append({"method": method, "path": path, **kwargs})
        return self.responses.pop(0)


def test_real_sap_client_maps_standard_fields_and_emits_contract_request() -> None:
    inventory_transport = StubTransport(
        [
            {
                "d": {
                    "results": [
                        {
                            "__metadata": {"uri": "stock/1", "type": "MaterialStock"},
                            "Material": "microchip-x",
                            "MaterialDescription": "Microchip X",
                            "Plant": "1000",
                            "StorageLocation": "0001",
                            "MatlWrhsStkQtyInMatBaseUnit": 3000,
                            "MaterialBaseUnit": "EA",
                            "DailyConsumption": 1000,
                            "LineStoppageCostPerDay": 100000,
                            "PurchaseQuantity": 5000,
                        }
                    ]
                }
            }
        ]
    )
    inventory = RealS4HANAClient(inventory_transport).get_inventory("microchip-x")
    assert inventory.current_stock == 3000

    order = PurchaseOrder(
        vendor_id="vendor-b",
        vendor_name="Vendor B",
        component_id="microchip-x",
        component_name="Microchip X",
        quantity=5000,
        unit_price=27,
        total_price=135000,
    )
    po_transport = StubTransport(
        [
            {
                "d": {
                    "__metadata": {"uri": "po/1", "type": "PurchaseOrder"},
                    "PurchaseOrder": "4500000999",
                    "PurchaseOrderItem": "00010",
                    "Supplier": "vendor-b",
                    "Material": "microchip-x",
                    "OrderQuantity": 5000,
                    "NetPriceAmount": 27,
                    "DocumentCurrency": "USD",
                    "ChainMindPurchaseOrderId": str(order.po_id),
                    "ChainMindVendorName": "Vendor B",
                    "ChainMindMaterialName": "Microchip X",
                    "ChainMindTotalPrice": 135000,
                    "ChainMindStatus": "PENDING_APPROVAL",
                }
            }
        ]
    )
    mapped = RealS4HANAClient(po_transport).create_draft_purchase_order(order)
    _assert_contract("purchase-order-request.schema.json", po_transport.requests[0]["json_body"])
    assert mapped.vendor_id == "vendor-b"
    assert mapped.quantity == 5000
    assert mapped.total_price == 135000


def test_real_ariba_client_maps_supplier_named_fields() -> None:
    transport = StubTransport(
        [
            {
                "d": {
                    "results": [
                        {
                            "Supplier": "vendor-b",
                            "SupplierName": "Vendor B",
                            "LeadTimeDays": 2,
                            "NetPriceAmount": 135000,
                            "DocumentCurrency": "USD",
                            "Capacity": 8000,
                            "RiskScore": 88,
                        }
                    ]
                }
            }
        ]
    )
    vendors = RealAribaClient(transport).list_alternative_vendors(
        DisruptionEvent(
            title="Contract test disruption",
            description="A standard-field mapping test.",
            delay_days=5,
        )
    )
    assert vendors[0].vendor_id == "vendor-b"
    assert vendors[0].total_cost == 135000
