"""Scheduled event-source poller that publishes normalized disruptions."""

import os
from typing import Any

from chainmind.core.errors import IntegrationError
from chainmind.integrations.aws.event_publisher import EventBridgePublisher
from chainmind.integrations.external.base import LogisticsClient, WeatherClient
from chainmind.integrations.external.mock import MockLogisticsClient, MockWeatherClient
from chainmind.integrations.external.open_meteo import OpenMeteoWeatherClient


def _clients() -> tuple[WeatherClient, LogisticsClient]:
    if os.environ.get("CHAINMIND_EXTERNAL_WEATHER_ENABLED", "").lower() == "true":
        weather: WeatherClient = OpenMeteoWeatherClient(
            float(os.environ.get("CHAINMIND_WEATHER_LATITUDE", "47.6062")),
            float(os.environ.get("CHAINMIND_WEATHER_LONGITUDE", "-122.3321")),
            enabled=True,
        )
    else:
        weather = MockWeatherClient()
    return weather, MockLogisticsClient()


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Poll configured sources and place each normalized event onto EventBridge."""

    del event, context
    if os.environ.get("CHAINMIND_EXTERNAL_POLL_ENABLED", "").lower() != "true":
        return {"status": "disabled", "published": 0}
    bus_name = os.environ.get("CHAINMIND_EVENT_BUS_NAME")
    if not bus_name:
        raise IntegrationError("External polling requires CHAINMIND_EVENT_BUS_NAME.")
    weather_client, logistics_client = _clients()
    table_name = os.environ.get("CHAINMIND_EVENT_TABLE_NAME")
    if not table_name:
        raise IntegrationError("External polling requires CHAINMIND_EVENT_TABLE_NAME.")
    events = [*weather_client.fetch_events(), *logistics_client.fetch_events()]
    publisher = EventBridgePublisher(
        table_name,
        bus_name,
        os.environ.get("CHAINMIND_AWS_REGION", "us-east-1"),
    )
    results = [publisher.publish(item) for item in events]
    published = sum(is_new for _, is_new in results)
    return {
        "status": "completed",
        "published": published,
        "duplicates": len(events) - published,
    }
