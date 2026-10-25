"""Contracts for external event sources."""

from typing import Protocol

from chainmind.core.models import DisruptionEvent


class WeatherClient(Protocol):
    """Source of weather-related supply-chain disruptions."""

    def fetch_events(self) -> list[DisruptionEvent]:
        """Fetch current events from the configured weather source."""


class LogisticsClient(Protocol):
    """Source of transport, geopolitical, and supplier disruptions."""

    def fetch_events(self) -> list[DisruptionEvent]:
        """Fetch current events from the configured logistics source."""
