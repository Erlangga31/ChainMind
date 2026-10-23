"""Tests for the Bedrock action-group Lambda contract."""

import json

from chainmind.core.models import InventorySnapshot, Vendor, VendorEvaluation
from chainmind.handlers.action_groups import handler


def test_get_inventory_action_returns_bedrock_response_envelope() -> None:
    event = {
        "actionGroup": "inventory-actions",
        "apiPath": "/get_inventory",
        "httpMethod": "POST",
        "parameters": [{"name": "component_id", "value": "microchip-x"}],
        "sessionAttributes": {"run_id": "demo-run"},
    }

    response = handler(event, None)

    assert response["messageVersion"] == "1.0"
    assert response["response"]["httpStatusCode"] == 200
    body = json.loads(response["response"]["responseBody"]["application/json"]["body"])
    assert body["result"]["current_stock"] == 3000
    assert response["sessionAttributes"] == {"run_id": "demo-run"}


def test_action_group_reports_invalid_body_without_success_fallback() -> None:
    response = handler(
        {
            "actionGroup": "coverage-actions",
            "apiPath": "/compute_coverage",
            "httpMethod": "POST",
            "requestBody": {"content": {"application/json": {"properties": {}}}},
        },
        None,
    )

    assert response["response"]["httpStatusCode"] == 422
    body = json.loads(response["response"]["responseBody"]["application/json"]["body"])
    assert body["error"]["code"] == "invalid_action_input"
    assert response["response"]["responseState"] == "REPROMPT"


def test_unknown_action_returns_structured_error() -> None:
    response = handler(
        {"actionGroup": "unknown", "apiPath": "/not-supported", "httpMethod": "POST"},
        None,
    )

    assert response["response"]["httpStatusCode"] == 404
    body = json.loads(response["response"]["responseBody"]["application/json"]["body"])
    assert body["error"]["code"] == "unknown_action"


def test_coverage_vendor_search_and_comparison_actions() -> None:
    inventory = InventorySnapshot(
        component_id="microchip-x",
        component_name="Microchip X",
        current_stock=3000,
        daily_consumption=1000,
        line_stoppage_cost_per_day=100000,
        purchase_quantity=5000,
    ).model_dump(mode="json")
    event = {
        "title": "Weather delay",
        "description": "Weather delays the Microchip X shipment.",
        "delay_days": 5,
    }
    coverage = handler(
        {
            "apiPath": "/compute_coverage",
            "requestBody": {
                "content": {
                    "application/json": {"properties": [{"name": "inventory", "value": inventory}]}
                }
            },
        },
        None,
    )
    searched = handler(
        {
            "apiPath": "/search_alternative_vendors",
            "parameters": [
                {"name": "title", "value": event["title"]},
                {"name": "description", "value": event["description"]},
                {"name": "delay_days", "value": 5},
            ],
        },
        None,
    )
    compared = handler(
        {
            "apiPath": "/compare_vendors",
            "requestBody": {
                "content": {
                    "application/json": {
                        "properties": [
                            {"name": "event", "value": event},
                            {"name": "inventory", "value": inventory},
                        ]
                    }
                }
            },
        },
        None,
    )

    coverage_body = json.loads(coverage["response"]["responseBody"]["application/json"]["body"])
    vendor_body = json.loads(searched["response"]["responseBody"]["application/json"]["body"])
    comparison_body = json.loads(compared["response"]["responseBody"]["application/json"]["body"])
    assert coverage_body["result"]["coverage_days"] == 3
    assert len(vendor_body["result"]["vendors"]) == 4
    assert len(comparison_body["result"]["evaluations"]) == 4


def test_create_draft_action_never_executes_purchase_order() -> None:
    inventory = InventorySnapshot(
        component_id="microchip-x",
        component_name="Microchip X",
        current_stock=3000,
        daily_consumption=1000,
        line_stoppage_cost_per_day=100000,
        purchase_quantity=5000,
    )
    vendor = Vendor(
        vendor_id="vendor-b",
        vendor_name="Vendor B",
        lead_time_days=2,
        total_cost=135000,
        risk_score=88,
        capacity=8000,
    )
    evaluation = VendorEvaluation(
        vendor=vendor,
        feasible=True,
        action_cost=135000,
        residual_stockout_days=0,
        residual_stockout_loss=0,
        risk_adjusted_total=135000,
        rationale="Fastest feasible offer.",
    )
    response = handler(
        {
            "apiPath": "/create_draft_po",
            "requestBody": {
                "content": {
                    "application/json": {
                        "properties": [
                            {"name": "inventory", "value": inventory.model_dump(mode="json")},
                            {
                                "name": "selected_vendor",
                                "value": evaluation.model_dump(mode="json"),
                            },
                        ]
                    }
                }
            },
        },
        None,
    )
    body = json.loads(response["response"]["responseBody"]["application/json"]["body"])

    assert response["response"]["httpStatusCode"] == 200
    assert body["result"]["status"] == "PENDING_APPROVAL"
    assert body["result"]["total_price"] == 135000
