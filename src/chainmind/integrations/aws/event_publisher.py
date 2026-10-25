"""Idempotent publication of normalized events to Amazon EventBridge."""

import hashlib
from uuid import UUID

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from chainmind.core.errors import IntegrationError
from chainmind.core.models import DisruptionEvent, DisruptionRun


class EventBridgePublisher:
    """Reserve an idempotency key before starting a disruption state machine."""

    def __init__(self, table_name: str, bus_name: str, region_name: str) -> None:
        self._table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)
        self._events = boto3.client("events", region_name=region_name)
        self._bus_name = bus_name

    def publish(self, event: DisruptionEvent) -> tuple[UUID, bool]:
        """Publish once and return the canonical event ID plus whether it was new."""

        record_id = event_record_id(event)
        try:
            self._table.put_item(
                Item={
                    "run_id": record_id,
                    "event_key": event.dedupe_key,
                    "tenant_id": event.tenant_id,
                    "event_id": str(event.event_id),
                    "event_status": "PUBLISHING",
                },
                ConditionExpression="attribute_not_exists(run_id)",
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                try:
                    existing = self._table.get_item(Key={"run_id": record_id}).get("Item", {})
                    event_id = existing.get("event_id")
                    if event_id is None and existing.get("linked_run_id"):
                        run_item = self._table.get_item(
                            Key={"run_id": existing["linked_run_id"]}
                        ).get("Item", {})
                        event_id = str(
                            DisruptionRun.model_validate_json(run_item["run_data"]).event.event_id
                        )
                    return UUID(event_id), False
                except (
                    BotoCoreError,
                    ClientError,
                    KeyError,
                    TypeError,
                    ValueError,
                ) as lookup_error:
                    raise IntegrationError(
                        "The duplicate event's canonical ID could not be retrieved."
                    ) from lookup_error
            raise IntegrationError("Event idempotency could not be reserved.") from exc
        except BotoCoreError as exc:
            raise IntegrationError("Event idempotency could not be reserved.") from exc

        try:
            response = self._events.put_events(
                Entries=[
                    {
                        "EventBusName": self._bus_name,
                        "Source": "chainmind.disruptions",
                        "DetailType": "SupplyChainDisruption",
                        "Detail": event.model_dump_json(),
                    }
                ]
            )
        except (BotoCoreError, ClientError) as exc:
            raise IntegrationError(
                "The event publication outcome is uncertain; its idempotency reservation "
                "was retained to prevent duplicate workflow starts."
            ) from exc
        if response.get("FailedEntryCount", 0):
            try:
                self._table.delete_item(Key={"run_id": record_id})
            except (BotoCoreError, ClientError) as cleanup_error:
                raise IntegrationError(
                    "The event was rejected and its idempotency reservation could not be cleared.",
                    details={"reason": str(cleanup_error)},
                ) from cleanup_error
            raise IntegrationError("The disruption event could not be published.")
        try:
            self._table.update_item(
                Key={"run_id": record_id},
                UpdateExpression="SET event_status = :published",
                ExpressionAttributeValues={":published": "PUBLISHED"},
            )
        except (BotoCoreError, ClientError) as exc:
            raise IntegrationError(
                "The disruption was published, but its idempotency status could not be updated; "
                "the reservation was retained to prevent duplicate workflow starts."
            ) from exc
        return event.event_id, True


def event_record_id(event: DisruptionEvent) -> str:
    """Return the deterministic DynamoDB partition key used by the event ledger."""

    return event_record_id_for_key(event.dedupe_key, event.tenant_id)


def event_record_id_for_key(key: str, tenant_id: str = "demo") -> str:
    """Return a ledger key when only the external idempotency key is available."""

    scoped_key = key if tenant_id == "demo" else f"{tenant_id}:{key}"
    return f"event#{hashlib.sha256(scoped_key.encode()).hexdigest()}"
