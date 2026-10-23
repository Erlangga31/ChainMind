"""Tests for external disruptions, classification, signing, and deduplication."""

import base64
import json
from typing import Any

import httpx
import pytest

from chainmind.agents.monitoring import MonitoringAgent
from chainmind.core.config import Settings
from chainmind.core.errors import ChainMindError
from chainmind.core.events import EventStore, SQLiteEventStore
from chainmind.core.models import DisruptionEvent, DisruptionRun, DisruptionType
from chainmind.factory import create_pipeline
from chainmind.handlers import event_bridge, external_poll
from chainmind.integrations.external.mock import MockLogisticsClient, MockWeatherClient
from chainmind.integrations.external.open_meteo import OpenMeteoWeatherClient
from chainmind.integrations.external.signing import parse_signed_event, sign_payload

BRIDGE_SECRET = "unit-test-event-bridge-secret"


def test_mock_feeds_cover_all_four_disruption_types() -> None:
    events = [*MockWeatherClient().fetch_events(), *MockLogisticsClient().fetch_events()]

    assert {event.event_type for event in events} == set(DisruptionType)


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Severe weather stopped the vessel.", DisruptionType.WEATHER),
        ("A transport delay blocks the shipment.", DisruptionType.LOGISTICS_DELAY),
        ("A geopolitical border closure blocks trade.", DisruptionType.GEOPOLITICAL),
        ("A supplier factory fire halted production.", DisruptionType.VENDOR_FAILURE),
    ],
)
def test_monitoring_classifies_supported_disruption_types(
    description: str,
    expected: DisruptionType,
) -> None:
    event = DisruptionEvent(
        title="Supply disruption",
        description=description,
        delay_days=5,
    )

    result = MonitoringAgent().analyze(event, 3)

    assert result.disruption_type is expected
    assert result.severity.value in {"High", "Critical"}


def test_monitoring_result_contains_matched_sap_records() -> None:
    run = create_pipeline(Settings(mode="mock"), EventStore()).run(
        DisruptionEvent(
            title="Weather delay",
            description="Severe weather delayed a shipment.",
            delay_days=5,
        )
    )

    assert run.affected_records is not None
    assert run.affected_records.shipment_ids == ["SHIP-MICROCHIP-X-001"]
    assert run.affected_records.open_purchase_order_ids == ["4500000001"]


def test_pipeline_is_idempotent_by_event_key() -> None:
    pipeline = create_pipeline(Settings(mode="mock"), EventStore())
    event = DisruptionEvent(
        title="Weather delay",
        description="Severe weather delayed a shipment.",
        delay_days=5,
        idempotency_key="evt-weather-123",
    )

    first = pipeline.run(event)
    second = pipeline.run(event.model_copy(update={"title": "Duplicate payload"}))

    assert first.run_id == second.run_id
    assert len(pipeline.store.list()) == 1


def test_sqlite_store_persists_run_and_idempotency_key(tmp_path: Any) -> None:
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    run = DisruptionRun(
        event=DisruptionEvent(
            title="Weather delay",
            description="Severe weather delayed a shipment.",
            delay_days=5,
            idempotency_key="sqlite-event-1",
        )
    )

    store.save(run)

    assert store.get(run.run_id) == run
    assert store.get_by_idempotency_key("sqlite-event-1") == run
    assert store.list() == [run]
    store.close()


def test_hmac_verification_accepts_exact_signed_body_and_rejects_tampering() -> None:
    event = DisruptionEvent(
        title="Weather delay",
        description="Severe weather delayed a shipment.",
        delay_days=5,
    )
    body = event.model_dump_json().encode()
    headers = {"x-chainmind-signature": sign_payload(body, BRIDGE_SECRET)}

    assert parse_signed_event(body, headers, BRIDGE_SECRET) == event
    with pytest.raises(ChainMindError, match="signature is invalid"):
        parse_signed_event(body + b" ", headers, BRIDGE_SECRET)


def test_event_bridge_lambda_publishes_valid_event(monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setenv("CHAINMIND_EVENT_BRIDGE_SECRET", BRIDGE_SECRET)
    monkeypatch.setenv("CHAINMIND_EVENT_BUS_NAME", "chainmind")
    monkeypatch.setattr(
        event_bridge.boto3,
        "client",
        lambda service: (
            type(
                "Events",
                (),
                {
                    "put_events": lambda self, **kwargs: (
                        calls.append(kwargs) or {"FailedEntryCount": 0}
                    )
                },
            )()
            if service == "events"
            else None
        ),
    )
    event = DisruptionEvent(
        title="Weather delay",
        description="Severe weather delayed a shipment.",
        delay_days=5,
    )
    body = event.model_dump_json().encode()
    response = event_bridge.handler(
        {
            "body": base64.b64encode(body).decode(),
            "isBase64Encoded": True,
            "headers": {"X-ChainMind-Signature": sign_payload(body, BRIDGE_SECRET)},
        },
        None,
    )

    assert response["statusCode"] == 202
    assert json.loads(response["body"])["event_id"] == str(event.event_id)
    assert calls[0]["Entries"][0]["EventBusName"] == "chainmind"


def test_event_bridge_lambda_rejects_bad_signature_without_publishing(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("CHAINMIND_EVENT_BRIDGE_SECRET", BRIDGE_SECRET)
    monkeypatch.setenv("CHAINMIND_EVENT_BUS_NAME", "chainmind")
    event = DisruptionEvent(
        title="Weather delay",
        description="Severe weather delayed a shipment.",
        delay_days=5,
    )
    response = event_bridge.handler(
        {
            "body": event.model_dump_json(),
            "headers": {"X-ChainMind-Signature": "sha256=invalid"},
        },
        None,
    )

    assert response["statusCode"] == 401
    assert json.loads(response["body"])["code"] == "event_signature_invalid"


def test_external_poll_is_disabled_by_default(monkeypatch: Any) -> None:
    monkeypatch.delenv("CHAINMIND_EXTERNAL_POLL_ENABLED", raising=False)

    assert external_poll.handler({}, None) == {"status": "disabled", "published": 0}


def test_open_meteo_client_is_opt_in_and_maps_severe_weather() -> None:
    calls: list[httpx.Request] = []

    def transport(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"current": {"weather_code": 99}})

    client = httpx.Client(transport=httpx.MockTransport(transport))
    disabled = OpenMeteoWeatherClient(1, 2, client=client)
    assert disabled.fetch_events() == []
    assert calls == []

    enabled = OpenMeteoWeatherClient(1, 2, enabled=True, client=client)
    events = enabled.fetch_events()

    assert len(events) == 1
    assert events[0].event_type is DisruptionType.WEATHER
    assert events[0].source == "open-meteo"
    assert calls[0].url.host == "api.open-meteo.com"
    client.close()
