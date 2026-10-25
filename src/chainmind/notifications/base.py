"""Channel-independent notifier contract."""

from typing import Protocol

from chainmind.core.models import NotificationMessage


class Notifier(Protocol):
    """Deliver a pre-rendered notification to one destination."""

    def send(self, message: NotificationMessage) -> None:
        """Send a notification or raise a typed integration error."""
