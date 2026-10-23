"""Scripted external disruption feeds for offline development and demos."""

import json
from importlib.resources import files

from chainmind.core.models import DisruptionEvent, DisruptionType


def _events() -> list[DisruptionEvent]:
    raw = files("chainmind.data").joinpath("seed_disruptions.json").read_text(encoding="utf-8")
    return [DisruptionEvent.model_validate(item) for item in json.loads(raw)]


class MockWeatherClient:
    """Return the seeded extreme-weather event without network access."""

    def fetch_events(self) -> list[DisruptionEvent]:
        """Return all weather disruptions in the scripted feed."""

        return [event for event in _events() if event.event_type is DisruptionType.WEATHER]


class MockLogisticsClient:
    """Return scripted logistics, geopolitical, and supplier incidents."""

    def fetch_events(self) -> list[DisruptionEvent]:
        """Return non-weather disruptions in the scripted feed."""

        return [event for event in _events() if event.event_type is not DisruptionType.WEATHER]
