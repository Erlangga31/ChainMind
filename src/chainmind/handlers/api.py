"""API Gateway Lambda adapter."""

from collections.abc import Mapping
from typing import Any

from mangum import Mangum

from chainmind.api.main import app

_mangum_handler = Mangum(app)


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Translate trusted Cognito groups to the role expected by the API routes."""

    request_context = event.get("requestContext", {})
    authorizer = request_context.get("authorizer", {}) if isinstance(request_context, dict) else {}
    claims = authorizer.get("claims", {}) if isinstance(authorizer, dict) else {}
    if isinstance(claims, Mapping):
        group_claim = str(claims.get("cognito:groups", ""))
        groups = {group.strip().strip('"') for group in group_claim.strip("[]").split(",")}
        role = "approver" if "approver" in groups else "viewer"
        headers = event.get("headers", {})
        event = {
            **event,
            "headers": {
                **(headers if isinstance(headers, dict) else {}),
                "X-ChainMind-Role": role,
            },
        }
    return _mangum_handler(event, context)
