"""HMAC-protected, expiring notification action links."""

import base64
import binascii
import hashlib
import hmac
import json
import time
from uuid import UUID

from pydantic import ValidationError

from chainmind.core.errors import ChainMindError
from chainmind.core.models import NotificationLinkPayload


class NotificationLinkSigner:
    """Create and validate scoped links without authorizing silent PO execution."""

    def __init__(self, secret: str, ttl_minutes: int) -> None:
        if len(secret) < 32:
            raise ValueError("Notification link signing secret must be at least 32 characters.")
        self._secret = secret.encode("utf-8")
        self._ttl_seconds = ttl_minutes * 60

    def create(
        self,
        run_id: UUID,
        action: str,
        *,
        tenant_id: str = "demo",
        now: int | None = None,
    ) -> str:
        """Create a URL-safe signed token scoped to ``approve`` or ``view``."""

        if action not in {"approve", "view"}:
            raise ValueError("Notification link action must be approve or view.")
        payload = NotificationLinkPayload(
            run_id=run_id,
            tenant_id=tenant_id,
            action=action,
            expires_at=(now if now is not None else int(time.time())) + self._ttl_seconds,
        )
        encoded = (
            base64.urlsafe_b64encode(payload.model_dump_json().encode("utf-8"))
            .decode("ascii")
            .rstrip("=")
        )
        signature = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
        signature_text = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
        return f"{encoded}.{signature_text}"

    def validate(self, token: str, *, now: int | None = None) -> NotificationLinkPayload:
        """Validate signature and expiration, returning the typed link claims."""

        try:
            encoded, signature_text = token.split(".", maxsplit=1)
            supplied = _decode(signature_text)
            expected = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
            if not hmac.compare_digest(supplied, expected):
                raise ValueError("signature")
            payload = NotificationLinkPayload.model_validate_json(_decode(encoded))
        except (
            ValueError,
            UnicodeDecodeError,
            binascii.Error,
            json.JSONDecodeError,
            ValidationError,
        ) as exc:
            raise ChainMindError(
                "invalid_notification_link",
                "The notification link is invalid.",
                status_code=401,
            ) from exc
        current_time = now if now is not None else int(time.time())
        if payload.action not in {"approve", "view"}:
            raise ChainMindError(
                "invalid_notification_link",
                "The notification link has an unsupported action.",
                status_code=401,
            )
        if payload.expires_at <= current_time:
            raise ChainMindError(
                "expired_notification_link",
                "The notification link has expired.",
                status_code=410,
            )
        return payload


def _decode(value: str) -> bytes:
    """Decode unpadded URL-safe base64 and reject malformed input."""

    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
