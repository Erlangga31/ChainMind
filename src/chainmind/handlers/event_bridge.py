"""API Gateway Lambda entry point for signed Event Mesh events."""

import base64
import json
import os
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from chainmind.core.errors import ChainMindError
from chainmind.integrations.external.signing import parse_signed_event


def _response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Validate a signed event and forward it onto the configured EventBridge bus."""

    del context
    raw_body = event.get("body", "")
    if not isinstance(raw_body, str):
        return _response(400, {"code": "invalid_body", "message": "Request body must be text."})
    try:
        body = (
            base64.b64decode(raw_body, validate=True)
            if event.get("isBase64Encoded")
            else raw_body.encode("utf-8")
        )
    except (ValueError, base64.binascii.Error):
        return _response(400, {"code": "invalid_body", "message": "Request body is invalid."})
    headers = event.get("headers") or {}
    try:
        secret = os.environ.get("CHAINMIND_EVENT_BRIDGE_SECRET")
        secret_id = os.environ.get("CHAINMIND_EVENT_BRIDGE_SECRET_SECRET_ID")
        if secret_id:
            secret_response = boto3.client("secretsmanager").get_secret_value(SecretId=secret_id)
            secret = secret_response.get("SecretString")
        disruption = parse_signed_event(
            body,
            headers if isinstance(headers, dict) else {},
            secret,
        )
    except ChainMindError as exc:
        return _response(exc.status_code, {"code": exc.code, "message": exc.message})
    except (BotoCoreError, ClientError):
        return _response(
            503,
            {"code": "bridge_secret_unavailable", "message": "Bridge secret is unavailable."},
        )
    bus_name = os.environ.get("CHAINMIND_EVENT_BUS_NAME")
    if not bus_name:
        return _response(
            503,
            {"code": "event_bus_not_configured", "message": "Event bus is not configured."},
        )
    try:
        result = boto3.client("events").put_events(
            Entries=[
                {
                    "EventBusName": bus_name,
                    "Source": "chainmind.disruptions",
                    "DetailType": "SupplyChainDisruption",
                    "Detail": disruption.model_dump_json(),
                }
            ]
        )
    except (BotoCoreError, ClientError):
        return _response(
            503,
            {"code": "event_publish_failed", "message": "Event could not be published."},
        )
    if result.get("FailedEntryCount", 0):
        return _response(
            502,
            {"code": "event_publish_failed", "message": "Event could not be published."},
        )
    return _response(
        202,
        {"status": "accepted", "event_id": str(disruption.event_id)},
    )
