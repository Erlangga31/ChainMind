"""Scheduled event-source poller that publishes normalized disruptions."""

import json
import os
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from chainmind.core.errors import IntegrationError
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
    try:
        events = [*weather_client.fetch_events(), *logistics_client.fetch_events()]
        if not events:
            return {"status": "completed", "published": 0}
        response = boto3.client("events").put_events(
            Entries=[
                {
                    "EventBusName": bus_name,
                    "Source": "chainmind.disruptions",
                    "DetailType": "SupplyChainDisruption",
                    "Detail": json.dumps(item.model_dump(mode="json")),
                }
                for item in events
            ]
        )
    except (BotoCoreError, ClientError) as exc:
        raise IntegrationError("External disruption events could not be published.") from exc
    failures = response.get("FailedEntryCount", 0)
    if failures:
        raise IntegrationError(
            "Some external disruption events could not be published.",
            details={"failed_entries": failures},
        )
    return {"status": "completed", "published": len(events)}
