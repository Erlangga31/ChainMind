"""In-memory SAP Ariba vendor adapter backed by packaged seed data."""

import json
from importlib.resources import files

from chainmind.core.models import DisruptionEvent, Vendor


class MockAribaClient:
    """Return deterministic alternative supplier quotes with OData-like data."""

    def __init__(self) -> None:
        raw = files("chainmind.data").joinpath("seed_vendors.json").read_text(encoding="utf-8")
        self._vendors = [Vendor.model_validate(item) for item in json.loads(raw)]

    def list_alternative_vendors(self, event: DisruptionEvent) -> list[Vendor]:
        """Return seeded supplier offers for the requested component."""

        del event
        return [vendor.model_copy(deep=True) for vendor in self._vendors]
