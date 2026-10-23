"""Console, webhook, and email notification channel implementations."""

from pathlib import Path
from typing import Any

import boto3
import httpx
from botocore.exceptions import BotoCoreError, ClientError

from chainmind.core.errors import IntegrationError
from chainmind.core.models import NotificationMessage


class ConsoleNotifier:
    """Print the complete rendered notification for a local demo."""

    def send(self, message: NotificationMessage) -> None:
        print(f"[ChainMind notification] {message.subject}\n{message.text}")


class TeamsNotifier:
    """Send an Adaptive Card to a Microsoft Teams incoming webhook."""

    def __init__(self, webhook_url: str, client: httpx.Client | None = None) -> None:
        self._webhook_url = webhook_url
        self._client = client or httpx.Client(timeout=10)
        self._owns_client = client is None

    def send(self, message: NotificationMessage) -> None:
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {"type": "TextBlock", "text": message.subject, "weight": "Bolder"},
                            {"type": "TextBlock", "text": message.text, "wrap": True},
                        ],
                        "actions": [
                            {
                                "type": "Action.OpenUrl",
                                "title": "Approve (review required)",
                                "url": message.approve_url,
                            },
                            {
                                "type": "Action.OpenUrl",
                                "title": "View details",
                                "url": message.view_url,
                            },
                        ],
                    },
                }
            ],
        }
        _post_json(self._client, self._webhook_url, payload, "Microsoft Teams")

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


class SlackNotifier:
    """Send a Block Kit message to a Slack incoming webhook."""

    def __init__(self, webhook_url: str, client: httpx.Client | None = None) -> None:
        self._webhook_url = webhook_url
        self._client = client or httpx.Client(timeout=10)
        self._owns_client = client is None

    def send(self, message: NotificationMessage) -> None:
        payload = {
            "text": message.subject,
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*{message.subject}*\n{message.text}"},
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Review approval"},
                            "url": message.approve_url,
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "View details"},
                            "url": message.view_url,
                        },
                    ],
                },
            ],
        }
        _post_json(self._client, self._webhook_url, payload, "Slack")

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


class EmailNotifier:
    """Send email through SES in AWS or append messages to a local JSONL outbox."""

    def __init__(
        self,
        *,
        mode: str,
        sender: str,
        recipient: str,
        region_name: str,
        outbox_path: str | Path,
    ) -> None:
        self._mode = mode
        self._sender = sender
        self._recipient = recipient
        self._region_name = region_name
        self._outbox_path = Path(outbox_path)

    def send(self, message: NotificationMessage) -> None:
        if self._mode == "aws":
            try:
                boto3.client("ses", region_name=self._region_name).send_email(
                    Source=self._sender,
                    Destination={"ToAddresses": [self._recipient]},
                    Message={
                        "Subject": {"Data": message.subject, "Charset": "UTF-8"},
                        "Body": {"Text": {"Data": message.text, "Charset": "UTF-8"}},
                    },
                )
            except (BotoCoreError, ClientError) as exc:
                raise IntegrationError(
                    "The notification email could not be sent through SES."
                ) from exc
            return

        self._outbox_path.parent.mkdir(parents=True, exist_ok=True)
        with self._outbox_path.open("a", encoding="utf-8") as outbox:
            outbox.write(message.model_dump_json() + "\n")


def _post_json(
    client: httpx.Client,
    webhook_url: str,
    payload: dict[str, Any],
    channel: str,
) -> None:
    try:
        response = client.post(webhook_url, json=payload)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise IntegrationError(f"The {channel} notification could not be delivered.") from exc
