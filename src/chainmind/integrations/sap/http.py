"""Authenticated HTTP transport for SAP Integration Suite endpoints."""

from __future__ import annotations

import json
import random
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from chainmind.core.errors import IntegrationError


@dataclass(frozen=True)
class SAPCredentials:
    """OAuth client credentials used by the Integration Suite transport."""

    client_id: str
    client_secret: str


class SAPHttpTransport:
    """OAuth2, CSRF, timeout, and bounded retry support for SAP HTTP calls."""

    def __init__(
        self,
        *,
        base_url: str,
        token_url: str,
        credentials: SAPCredentials,
        timeout_seconds: float = 10.0,
        retry_attempts: int = 3,
        retry_base_delay_seconds: float = 0.1,
        client: httpx.Client | None = None,
    ) -> None:
        if not credentials.client_id or not credentials.client_secret:
            raise IntegrationError("SAP client credentials are required.")
        self._base_url = base_url.rstrip("/")
        self._token_url = token_url
        self._credentials = credentials
        self._retry_attempts = retry_attempts
        self._retry_base_delay_seconds = retry_base_delay_seconds
        self._client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=True)
        self._owns_client = client is None
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._csrf_token: str | None = None
        self._lock = threading.RLock()

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        csrf: bool = False,
    ) -> dict[str, Any]:
        """Send an authenticated request and return its JSON object response."""

        url = f"{self._base_url}/{path.lstrip('/')}"
        for attempt in range(self._retry_attempts):
            try:
                headers = {"Authorization": f"Bearer {self._access_token()}"}
                if csrf:
                    headers["X-CSRF-Token"] = self._csrf_token_for(path)
                response = self._client.request(
                    method,
                    url,
                    json=json_body,
                    params=params,
                    headers=headers,
                )
                if response.status_code == 401 and attempt + 1 < self._retry_attempts:
                    self._invalidate_access_token()
                    self._sleep_before_retry(attempt)
                    continue
                if response.status_code == 403 and csrf and attempt + 1 < self._retry_attempts:
                    self._invalidate_csrf_token()
                    self._sleep_before_retry(attempt)
                    continue
                if response.status_code in {400, 401, 403, 404}:
                    raise self._integration_error(
                        "SAP rejected the request.",
                        httpx.HTTPStatusError(
                            "SAP request rejected",
                            request=response.request,
                            response=response,
                        ),
                    )
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt + 1 < self._retry_attempts:
                        self._sleep_before_retry(attempt)
                        continue
                response.raise_for_status()
                return self._json_object(response)
            except IntegrationError:
                raise
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                if not self._should_retry(exc, attempt):
                    raise self._integration_error("SAP request failed.", exc) from exc
                self._sleep_before_retry(attempt)
        raise IntegrationError("SAP request failed after retries.")

    def _access_token(self) -> str:
        with self._lock:
            if self._token and time.monotonic() < self._token_expires_at:
                return self._token
            try:
                response = self._client.post(
                    self._token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self._credentials.client_id,
                        "client_secret": self._credentials.client_secret,
                    },
                    timeout=self._client.timeout,
                )
                response.raise_for_status()
                payload = response.json()
                token = payload.get("access_token")
                if not isinstance(token, str) or not token:
                    raise ValueError("OAuth response omitted access_token.")
                expires_in = float(payload.get("expires_in", 300))
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                raise self._integration_error("SAP OAuth token request failed.", exc) from exc
            self._token = token
            self._token_expires_at = time.monotonic() + max(1.0, expires_in - 30.0)
            return token

    def _csrf_token_for(self, path: str) -> str:
        with self._lock:
            if self._csrf_token:
                return self._csrf_token
            url = f"{self._base_url}/{path.lstrip('/')}"
            for attempt in range(self._retry_attempts):
                try:
                    response = self._client.get(
                        url,
                        headers={
                            "Authorization": f"Bearer {self._access_token()}",
                            "X-CSRF-Token": "Fetch",
                        },
                    )
                    if response.status_code == 401 and attempt + 1 < self._retry_attempts:
                        self._invalidate_access_token()
                        self._sleep_before_retry(attempt)
                        continue
                    response.raise_for_status()
                    token = response.headers.get("X-CSRF-Token")
                    if not token:
                        raise ValueError("SAP response omitted the CSRF token.")
                    self._csrf_token = token
                    return token
                except (httpx.HTTPError, ValueError) as exc:
                    if not self._should_retry(exc, attempt):
                        raise self._integration_error(
                            "SAP CSRF token request failed.",
                            exc,
                        ) from exc
                    self._sleep_before_retry(attempt)
            raise IntegrationError("SAP CSRF token request failed after retries.")

    def _invalidate_access_token(self) -> None:
        with self._lock:
            self._token = None
            self._token_expires_at = 0.0

    def _invalidate_csrf_token(self) -> None:
        with self._lock:
            self._csrf_token = None

    def _sleep_before_retry(self, attempt: int) -> None:
        ceiling = self._retry_base_delay_seconds * (2**attempt)
        if ceiling > 0:
            time.sleep(random.uniform(ceiling * 0.5, ceiling))

    def _should_retry(self, error: Exception, attempt: int) -> bool:
        if attempt + 1 >= self._retry_attempts:
            return False
        if isinstance(error, httpx.HTTPStatusError):
            return error.response.status_code == 429 or error.response.status_code >= 500
        return isinstance(error, (httpx.TimeoutException, httpx.TransportError))

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        if not response.content:
            return {}
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise IntegrationError(
                "SAP returned an invalid JSON response.",
                details={"status_code": response.status_code},
            ) from exc
        if not isinstance(payload, dict):
            raise IntegrationError("SAP returned an unexpected response shape.")
        return payload

    @staticmethod
    def _integration_error(message: str, cause: Exception) -> IntegrationError:
        status_code = (
            cause.response.status_code if isinstance(cause, httpx.HTTPStatusError) else None
        )
        details = {"status_code": status_code} if status_code is not None else {}
        return IntegrationError(message, details=details)

    def close(self) -> None:
        """Close the underlying HTTP connection pool when owned by this transport."""

        if self._owns_client:
            self._client.close()
