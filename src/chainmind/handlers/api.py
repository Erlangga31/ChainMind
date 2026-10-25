"""API Gateway Lambda adapter."""

from typing import Any

from mangum import Mangum

from chainmind.api.main import app

_mangum_handler = Mangum(app)


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Pass API Gateway's bearer token through to the shared JWT verifier."""

    headers = event.get("headers")
    if isinstance(headers, dict):
        event = {
            **event,
            "headers": {
                key: value for key, value in headers.items() if key.lower() != "x-chainmind-role"
            },
        }
    return _mangum_handler(event, context)
