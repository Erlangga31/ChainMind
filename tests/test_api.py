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
    parts = subject.split(":")
    tenant_id = parts[1] if len(parts) > 1 else "demo"
    role = parts[0].removeprefix("test-")
    roles = frozenset({role}) if role in {"approver", "admin"} else frozenset({"viewer"})
    return AuthenticatedUser(subject=subject, roles=roles, tenant_id=tenant_id)


def fake_tenant_context(request: Request) -> AuthenticatedUser:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return AuthenticatedUser(
            subject="anonymous-local",
            roles=frozenset(),
            tenant_id="demo",
        )
    subject = authorization.removeprefix("Bearer ")
    parts = subject.split(":")
    tenant_id = parts[1] if len(parts) > 1 else "demo"
    return AuthenticatedUser(subject=subject, roles=frozenset({"viewer"}), tenant_id=tenant_id)


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
    monkeypatch.setitem(api.app.dependency_overrides, api.tenant_context, fake_tenant_context)


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
    response_time = next(
        metric for metric in report.json()["comparison"] if metric["metric"] == "Response time"
    )
    assert response_time["chainmind_value"] is not None
    assert response_time["chainmind_is_illustrative"] is False
    consistency = next(
        metric
        for metric in report.json()["comparison"]
        if metric["metric"] == "Decision consistency"
    )
    assert consistency["chainmind_value"] is None
    assert consistency["chainmind_is_illustrative"] is True


def test_decision_consistency_uses_repeated_comparable_run_data() -> None:
    for index in range(2):
        created = client.post(
            "/disruptions",
            json={
                "title": f"Repeated weather scenario {index}",
                "description": "The same component and inventory conditions recur.",
                "component_id": "microchip-x",
                "delay_days": 5,
                "event_type": "weather",
            },
            headers={"Authorization": "Bearer viewer:tenant-a"},
        )
        assert created.status_code == 201
        approved = client.post(
            f"/runs/{created.json()['run_id']}/decision",
            json={"decision": "approve"},
            headers={"Authorization": "Bearer approver:tenant-a"},
        )
        assert approved.status_code == 200

    report = client.get("/kpis", headers={"Authorization": "Bearer viewer:tenant-a"})
    consistency = next(
        metric
        for metric in report.json()["comparison"]
        if metric["metric"] == "Decision consistency"
    )

    assert consistency["chainmind_value"] == 100
    assert consistency["chainmind_is_illustrative"] is False


def test_kpis_are_isolated_by_tenant() -> None:
    created = client.post(
        "/disruptions",
        json={
            "title": "Tenant A weather delay",
            "description": "Weather delayed the shipment.",
            "delay_days": 5,
        },
        headers={"Authorization": "Bearer viewer:tenant-a"},
    )
    run_id = created.json()["run_id"]
    approved = client.post(
        f"/runs/{run_id}/decision",
        json={"decision": "approve"},
        headers={"Authorization": "Bearer approver:tenant-a"},
    )
    assert approved.status_code == 200

    tenant_a = client.get("/kpis", headers={"Authorization": "Bearer viewer:tenant-a"})
    tenant_b = client.get("/kpis", headers={"Authorization": "Bearer viewer:tenant-b"})

    assert tenant_a.status_code == tenant_b.status_code == 200
    assert tenant_a.json()["executed_runs"] == 1
    assert tenant_b.json()["executed_runs"] == 0
    assert tenant_b.json()["tracked_runs"] == 0


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


def test_runs_idempotency_and_usage_are_isolated_by_tenant() -> None:
    payload = {
        "title": "Weather delay",
        "description": "Extreme weather delayed the vessel.",
        "delay_days": 5,
    }
    tenant_a = client.post(
        "/disruptions",
        json=payload,
        headers={"Authorization": "Bearer viewer:tenant-a", "Idempotency-Key": "shared-key"},
    )
    tenant_b = client.post(
        "/disruptions",
        json=payload,
        headers={"Authorization": "Bearer viewer:tenant-b", "Idempotency-Key": "shared-key"},
    )
    run_a_id = tenant_a.json()["run_id"]
    run_b_id = tenant_b.json()["run_id"]

    assert tenant_a.status_code == tenant_b.status_code == 201
    assert run_a_id != run_b_id
    assert (
        client.get("/runs", headers={"Authorization": "Bearer viewer:tenant-a"}).json()[0][
            "tenant_id"
        ]
        == "tenant-a"
    )
    inaccessible_run = client.get(
        f"/runs/{run_b_id}",
        headers={"Authorization": "Bearer viewer:tenant-a"},
    )
    assert inaccessible_run.status_code == 404

    usage_for_a = client.get("/usage", headers={"Authorization": "Bearer approver:tenant-a"})
    viewer_usage = client.get("/usage", headers={"Authorization": "Bearer viewer:tenant-a"})
    admin_usage = client.get("/usage", headers={"Authorization": "Bearer admin:tenant-a"})

    assert usage_for_a.status_code == 200
    assert usage_for_a.json()["tenant_id"] == "tenant-a"
    assert usage_for_a.json()["resolved_disruptions"] == 0
    assert viewer_usage.status_code == 403
    assert admin_usage.status_code == 200
