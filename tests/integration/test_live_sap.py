"""Opt-in smoke test for SAP tenants; never runs against real SAP by default."""

import os

import pytest

from scripts.verify_sap_tenant import REQUIRED_ENV, verify_tenant

pytestmark = [
    pytest.mark.integration,
    pytest.mark.live_sap,
    pytest.mark.skipif(
        not all(os.getenv(name) for name in REQUIRED_ENV),
        reason="Set SAP_LIVE_* URL and credential variables to opt into live SAP checks.",
    ),
]


def test_live_sap_metadata_and_read_services() -> None:
    results = verify_tenant(
        base_url=os.environ["SAP_LIVE_BASE_URL"],
        token_url=os.environ["SAP_LIVE_TOKEN_URL"],
        client_id=os.environ["SAP_LIVE_CLIENT_ID"],
        client_secret=os.environ["SAP_LIVE_CLIENT_SECRET"],
    )

    assert all(result.status == "PASS" for result in results), results
