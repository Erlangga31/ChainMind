"""Shared-secret signing and validation for Event Mesh bridge payloads."""

import hashlib
import hmac
import json
from collections.abc import Mapping

from pydantic import ValidationError

from chainmind.core.errors import ChainMindError
from chainmind.core.models import DisruptionEvent

SIGNATURE_HEADER = "X-ChainMind-Signature"


def sign_payload(body: bytes, secret: str) -> str:
    """Return the canonical SHA-256 HMAC header value."""

    if not secret:
        raise ValueError("A shared secret is required to sign an event.")
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def parse_signed_event(
    body: bytes,
    headers: Mapping[str, str],
    secret: str | None,
) -> DisruptionEvent:
    """Verify the exact request bytes and validate the normalized event payload."""

    if not secret:
        raise ChainMindError(
            "event_bridge_not_configured",
            "Event bridge shared-secret validation is not configured.",
            status_code=503,
        )
    signature = next(
        (value for name, value in headers.items() if name.lower() == SIGNATURE_HEADER.lower()),
        None,
    )
    if not signature:
        raise ChainMindError(
            "event_signature_missing",
            "The signed event header is required.",
            status_code=401,
        )
    expected = sign_payload(body, secret)
    if not hmac.compare_digest(signature, expected):
        raise ChainMindError(
            "event_signature_invalid",
            "The event signature is invalid.",
            status_code=401,
        )
    try:
        payload = json.loads(body)
        return DisruptionEvent.model_validate(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as exc:
        raise ChainMindError(
            "event_payload_invalid",
            "The signed event payload is invalid.",
            status_code=422,
        ) from exc
