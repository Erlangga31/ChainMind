"""Small exponential-backoff helper for external integration calls."""

import time
from collections.abc import Callable

from chainmind.core.errors import IntegrationError


def retry_integration_call[T](
    operation: Callable[[], T],
    *,
    attempts: int,
    base_delay_seconds: float,
) -> T:
    """Retry expected integration failures with bounded exponential backoff."""

    for attempt in range(attempts):
        try:
            return operation()
        except IntegrationError:
            if attempt + 1 == attempts:
                raise
            time.sleep(base_delay_seconds * (2**attempt))
    raise RuntimeError("Retry loop ended without returning or raising.")
