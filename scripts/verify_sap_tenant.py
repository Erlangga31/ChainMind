"""Opt-in smoke checks for a tenant-specific SAP Integration Suite deployment."""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

METADATA_PATHS = (
    "/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV/$metadata",
    "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/$metadata",
    "/sap/opu/odata/sap/API_BUSINESS_PARTNER/$metadata",
    "/ariba/$metadata",
)
READ_PATHS = (
    "/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV/A_MaterialStock",
    "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder",
    "/sap/opu/odata/sap/API_BUSINESS_PARTNER/A_Supplier",
    "/ariba/sourcing/vendors",
)
REQUIRED_ENV = (
    "SAP_LIVE_BASE_URL",
    "SAP_LIVE_TOKEN_URL",
    "SAP_LIVE_CLIENT_ID",
    "SAP_LIVE_CLIENT_SECRET",
)


@dataclass(frozen=True)
class CheckResult:
    """One non-secret outcome from the opt-in tenant smoke check."""

    name: str
    status: str
    detail: str


def _metadata_paths() -> tuple[str, ...]:
    env_names = (
        "SAP_LIVE_MATERIAL_METADATA_PATH",
        "SAP_LIVE_PURCHASE_ORDER_METADATA_PATH",
        "SAP_LIVE_BUSINESS_PARTNER_METADATA_PATH",
        "SAP_LIVE_ARIBA_METADATA_PATH",
    )
    return tuple(
        os.getenv(name, default) for name, default in zip(env_names, METADATA_PATHS, strict=True)
    )


def _read_paths() -> tuple[str, ...]:
    env_names = (
        "SAP_LIVE_MATERIAL_READ_PATH",
        "SAP_LIVE_PURCHASE_ORDER_READ_PATH",
        "SAP_LIVE_BUSINESS_PARTNER_READ_PATH",
        "SAP_LIVE_ARIBA_READ_PATH",
    )
    return tuple(
        os.getenv(name, default) for name, default in zip(env_names, READ_PATHS, strict=True)
    )


def verify_tenant(
    *,
    base_url: str,
    token_url: str,
    client_id: str,
    client_secret: str,
    client: httpx.Client | None = None,
) -> list[CheckResult]:
    """Acquire an OAuth token and verify metadata plus one read from each adapter."""

    http = client or httpx.Client(timeout=15.0, follow_redirects=True)
    owns_client = client is None
    results: list[CheckResult] = []
    try:
        try:
            token_response = http.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            token_response.raise_for_status()
            token = token_response.json().get("access_token")
            if not isinstance(token, str) or not token:
                raise ValueError("OAuth response omitted access_token.")
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            return [CheckResult("OAuth token", "FAIL", _safe_error(exc))]

        results.append(CheckResult("OAuth token", "PASS", "Client-credentials token acquired."))
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        for name, path in zip(
            (
                "Material stock $metadata",
                "Purchase orders $metadata",
                "Business partners $metadata",
                "Ariba adapter $metadata",
            ),
            _metadata_paths(),
            strict=True,
        ):
            try:
                response = http.get(f"{base_url.rstrip('/')}/{path.lstrip('/')}", headers=headers)
                response.raise_for_status()
                root = ET.fromstring(response.content)
                if not root.tag.endswith("Edmx"):
                    raise ValueError("Metadata root element is not Edmx.")
                results.append(CheckResult(name, "PASS", "EDMX document returned."))
            except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
                results.append(CheckResult(name, "FAIL", _safe_error(exc)))

        for name, path in zip(
            ("Material stock read", "Purchase-order read", "Supplier read", "Ariba vendor read"),
            _read_paths(),
            strict=True,
        ):
            try:
                response = http.get(
                    f"{base_url.rstrip('/')}/{path.lstrip('/')}",
                    params={"$top": "1"},
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("Read response is not a JSON object.")
                results.append(CheckResult(name, "PASS", "Service returned a JSON object."))
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                results.append(CheckResult(name, "FAIL", _safe_error(exc)))
        return results
    finally:
        if owns_client:
            http.close()


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}."
    if isinstance(exc, httpx.TimeoutException):
        return "Request timed out."
    if isinstance(exc, httpx.RequestError):
        return "Connection request failed."
    if isinstance(exc, ET.ParseError):
        return "Metadata is not valid XML."
    return str(exc)


def print_results(results: list[CheckResult]) -> None:
    """Print a compact verification table without exposing credentials or tokens."""

    print(f"{'Check':34} {'Result':6} Detail")
    print("-" * 84)
    for result in results:
        print(f"{result.name:34} {result.status:6} {result.detail}")


def main() -> int:
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        print("Set the required environment variables before running this live check:")
        print("\n".join(f"- {name}" for name in missing))
        return 2

    results = verify_tenant(
        base_url=os.environ["SAP_LIVE_BASE_URL"],
        token_url=os.environ["SAP_LIVE_TOKEN_URL"],
        client_id=os.environ["SAP_LIVE_CLIENT_ID"],
        client_secret=os.environ["SAP_LIVE_CLIENT_SECRET"],
    )
    print_results(results)
    return 0 if all(result.status == "PASS" for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
