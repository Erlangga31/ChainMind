"""EventBridge Lambda wrapper around the core disruption pipeline."""

from typing import Any

from chainmind.core.models import DisruptionEvent
from chainmind.factory import create_pipeline

pipeline = create_pipeline()


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Parse an EventBridge detail and return a JSON-serializable run summary."""

    del context
    detail = event.get("detail", event)
    disruption = DisruptionEvent.model_validate(detail)
    run = pipeline.run(disruption)
    return run.model_dump(mode="json")
