"""Thin Bedrock Action Group adapter to deterministic ChainMind agents."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from chainmind.agents.logistics import LogisticsAgent
from chainmind.agents.orchestrator import OrchestratorAgent
from chainmind.agents.procurement import ProcurementAgent
from chainmind.core.config import Settings
from chainmind.core.errors import ChainMindError
from chainmind.core.models import (
    DisruptionEvent,
    InventorySnapshot,
    VendorEvaluation,
)
from chainmind.core.retry import retry_integration_call
from chainmind.factory import create_sap_clients

ACTION_PATHS = {
    "/get_inventory": "get_inventory",
    "/compute_coverage": "compute_coverage",
    "/search_alternative_vendors": "search_alternative_vendors",
    "/compare_vendors": "compare_vendors",
    "/create_draft_po": "create_draft_po",
}


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Dispatch one Bedrock action-group request and return its documented envelope."""

    del context
    action_group = str(event.get("actionGroup", "ChainMindActions"))
    api_path = str(event.get("apiPath", ""))
    http_method = str(event.get("httpMethod", "POST"))
    try:
        action_name = ACTION_PATHS[api_path]
        result = dispatch_action(action_name, _request_values(event))
        status_code = 200
        body: dict[str, Any] = {"result": result}
    except KeyError as exc:
        status_code = 404
        body = {"error": {"code": "unknown_action", "message": str(exc)}}
    except ValidationError as exc:
        status_code = 422
        body = {
            "error": {
                "code": "invalid_action_input",
                "message": "Action input did not match the required schema.",
                "details": exc.errors(include_input=False),
            }
        }
    except ChainMindError as exc:
        status_code = exc.status_code
        body = {"error": {"code": exc.code, "message": exc.message, "details": exc.details}}

    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": action_group,
            "apiPath": api_path,
            "httpMethod": http_method,
            "httpStatusCode": status_code,
            "responseBody": {"application/json": {"body": json.dumps(body)}},
            "responseState": "SUCCESS" if status_code < 400 else "REPROMPT",
        },
        "sessionAttributes": event.get("sessionAttributes", {}),
        "promptSessionAttributes": event.get("promptSessionAttributes", {}),
    }


def dispatch_action(action_name: str, values: dict[str, Any]) -> dict[str, Any]:
    """Call existing agents and SAP adapters for one validated action."""

    settings = Settings()
    sap, ariba, _ = create_sap_clients(settings)
    component_id = str(values.get("component_id", "microchip-x"))
    if action_name == "get_inventory":
        inventory = retry_integration_call(
            lambda: sap.get_inventory(component_id),
            attempts=settings.retry_attempts,
            base_delay_seconds=settings.retry_base_delay_seconds,
        )
        return inventory.model_dump(mode="json")
    if action_name == "compute_coverage":
        inventory = InventorySnapshot.model_validate(values.get("inventory", values))
        coverage = inventory.current_stock / inventory.daily_consumption
        return {"coverage_days": coverage, "component_id": inventory.component_id}
    if action_name == "search_alternative_vendors":
        event = _event(values)
        vendors = retry_integration_call(
            lambda: ariba.list_alternative_vendors(event),
            attempts=settings.retry_attempts,
            base_delay_seconds=settings.retry_base_delay_seconds,
        )
        return {"vendors": [vendor.model_dump(mode="json") for vendor in vendors]}
    if action_name == "compare_vendors":
        event = _event(values)
        inventory = InventorySnapshot.model_validate(values["inventory"])
        logistics = LogisticsAgent().analyze(event, inventory)
        result = retry_integration_call(
            lambda: ProcurementAgent(ariba, settings).compare(event, inventory, logistics),
            attempts=settings.retry_attempts,
            base_delay_seconds=settings.retry_base_delay_seconds,
        )
        return result.model_dump(mode="json")
    if action_name == "create_draft_po":
        inventory = InventorySnapshot.model_validate(values["inventory"])
        selected = VendorEvaluation.model_validate(values["selected_vendor"])
        draft = OrchestratorAgent.draft_purchase_order(selected, inventory)
        created = retry_integration_call(
            lambda: sap.create_draft_purchase_order(draft),
            attempts=settings.retry_attempts,
            base_delay_seconds=settings.retry_base_delay_seconds,
        )
        return created.model_dump(mode="json")
    raise ChainMindError(
        "unknown_action",
        "The requested Bedrock action is not supported.",
        status_code=404,
        details={"action": action_name},
    )


def _request_values(event: dict[str, Any]) -> dict[str, Any]:
    """Normalize Bedrock's parameter list and JSON request-body envelope."""

    values: dict[str, Any] = {}
    for parameter in event.get("parameters", []):
        if isinstance(parameter, dict) and "name" in parameter:
            values[str(parameter["name"])] = parameter.get("value")
    request_body = event.get("requestBody", {})
    content = request_body.get("content", {}) if isinstance(request_body, dict) else {}
    application_json = content.get("application/json", {}) if isinstance(content, dict) else {}
    properties = (
        application_json.get("properties", []) if isinstance(application_json, dict) else []
    )
    if isinstance(properties, dict):
        values.update(properties)
    elif isinstance(properties, list):
        for prop in properties:
            if isinstance(prop, dict) and "name" in prop:
                values[str(prop["name"])] = prop.get("value")
    return values


def _event(values: dict[str, Any]) -> DisruptionEvent:
    """Validate disruption fields required by procurement."""

    event_values = values.get("event", values)
    return DisruptionEvent.model_validate(event_values)
