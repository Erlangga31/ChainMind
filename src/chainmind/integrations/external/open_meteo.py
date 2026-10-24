"""Optional free Open-Meteo weather feed, disabled unless explicitly selected."""

from datetime import UTC, datetime

import httpx

from chainmind.core.errors import IntegrationError
from chainmind.core.models import DisruptionEvent, DisruptionType


class OpenMeteoWeatherClient:
    """Map severe current weather codes into disruption events."""

    def __init__(
        self,
        latitude: float,
        longitude: float,
        *,
        enabled: bool = False,
        client: httpx.Client | None = None,
    ) -> None:
        self._latitude = latitude
        self._longitude = longitude
        self._enabled = enabled
        self._client = client or httpx.Client(timeout=8.0)
        self._owns_client = client is None

    def fetch_events(self) -> list[DisruptionEvent]:
        """Fetch a weather code; return no events when the integration is disabled."""

        if not self._enabled:
            return []
        try:
            response = self._client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": self._latitude,
                    "longitude": self._longitude,
                    "current": "weather_code",
                },
            )
            response.raise_for_status()
            payload = response.json()
            weather_code = payload["current"]["weather_code"]
            if isinstance(weather_code, bool) or not isinstance(weather_code, int):
                raise ValueError("Current weather code is not an integer.")
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise IntegrationError("Open-Meteo weather data could not be retrieved.") from exc
        if weather_code < 95:
            return []
        occurred_at = datetime.now(UTC)
        return [
            DisruptionEvent(
                title="Severe thunderstorm weather alert",
                description=(
                    f"Open-Meteo reported severe weather code {weather_code}; "
                    "review affected shipments."
                ),
                delay_days=1,
                event_type=DisruptionType.WEATHER,
                idempotency_key=f"open-meteo:{weather_code}:{occurred_at.date().isoformat()}",
                source="open-meteo",
                occurred_at=occurred_at,
            )
        ]

    def close(self) -> None:
        """Close the HTTP client when this adapter created it."""

        if self._owns_client:
            self._client.close()
