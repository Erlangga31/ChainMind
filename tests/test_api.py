"""HTTP-level tests for the disruption and human decision endpoints."""

from fastapi.testclient import TestClient

from chainmind.api.main import app

client = TestClient(app)


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
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "REJECTED"


def test_validation_and_health_responses_are_structured() -> None:
    assert client.get("/health").json()["status"] == "ok"

    response = client.post("/disruptions", json={"delay_days": 0})
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_dashboard_loopback_origin_is_allowed_by_cors() -> None:
    response = client.options(
        "/disruptions",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
