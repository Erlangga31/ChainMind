"""HTTP-level tests for the disruption and human decision endpoints."""

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

import chainmind.api.main as api
from chainmind.api.identity import AuthenticatedUser, authenticated_user
from chainmind.core.config import Settings
from chainmind.core.events import EventStore
from chainmind.factory import create_pipeline

client = TestClient(api.app)


def fake_authenticated_user(request: Request) -> AuthenticatedUser:
    """Return deterministic test identities without bypassing route authorization."""

    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401)
    subject = authorization.removeprefix("Bearer ")
    if subject == "test-approver":
        return AuthenticatedUser(subject=subject, roles=frozenset({"approver"}))
    return AuthenticatedUser(subject=subject, roles=frozenset({"viewer"}))


@pytest.fixture(autouse=True)
def isolate_api_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep API tests independent of persisted local runs and test ordering."""

    monkeypatch.setattr(
        api,
        "pipeline",
        create_pipeline(
            Settings(mode="mock", notification_backends=[]),
            EventStore(),
        ),
    )
    monkeypatch.setitem(api.app.dependency_overrides, authenticated_user, fake_authenticated_user)


def test_disruption_api_lists_run_and_records_rejection() -> None:
    event = {
        "title": "Weather delay",
        "description": "Extreme weather has delayed the vessel.",
        "component_id": "microchip-x",
        "component_name": "Microchip X",
        "delay_days": 5,
    }
    created = client.post("/disruptions", json=event)

    assert created.status_code == 201
    run_id = created.json()["run_id"]
    run_response = client.get(f"/runs/{run_id}")
    assert run_response.status_code == 200
    assert run_response.json()["selected_vendor_id"] == "vendor-b"
    assert run_response.json()["draft_po"]["status"] == "PENDING_APPROVAL"
    assert any(run["run_id"] == run_id for run in client.get("/runs").json())

    decision = client.post(
        f"/runs/{run_id}/decision",
        json={"decision": "reject", "note": "Need supervisor review."},
        headers={"Authorization": "Bearer test-approver"},
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "REJECTED"


def test_viewer_and_missing_token_cannot_submit_decisions() -> None:
    run = client.post(
        "/disruptions",
        json={
            "title": "Weather delay",
            "description": "Extreme weather has delayed the vessel.",
            "delay_days": 5,
        },
    ).json()
    url = f"/runs/{run['run_id']}/decision"
    payload = {"decision": "reject", "note": "Viewer must not approve."}

    viewer = client.post(url, json=payload, headers={"Authorization": "Bearer test-viewer"})
    missing = client.post(url, json=payload)

    assert viewer.status_code == 403
    assert missing.status_code == 401


def test_validation_and_health_responses_are_structured() -> None:
    assert client.get("/health").json()["status"] == "ok"

    response = client.post("/disruptions", json={"delay_days": 0})
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_kpis_include_only_completed_tracking_and_are_labeled_illustrative() -> None:
    created = client.post(
        "/disruptions",
        json={
            "title": "Supplier shipment delay",
            "description": "Extreme weather delayed the component shipment.",
            "delay_days": 5,
        },
    )
    run_id = created.json()["run_id"]
    pending = client.get("/kpis").json()
    assert pending["simulated"] is True
    assert "illustrative" in pending["label"].lower()

    approved = client.post(
        f"/runs/{run_id}/decision",
        json={"decision": "approve"},
        headers={"Authorization": "Bearer test-approver"},
    )
    assert approved.status_code == 200
    report = client.get("/kpis")

    assert report.status_code == 200
    assert report.json()["tracked_runs"] >= pending["tracked_runs"] + 1
    assert report.json()["executed_runs"] >= pending["executed_runs"] + 1
    assert report.json()["line_stoppages_avoided"] >= 1


def test_dashboard_loopback_origin_is_allowed_by_cors() -> None:
    response = client.options(
        "/disruptions",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
