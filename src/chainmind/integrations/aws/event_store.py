"""DynamoDB-backed run store for AWS deployments."""

import json
import os
from uuid import UUID

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import BotoCoreError, ClientError

from chainmind.core.errors import IntegrationError
from chainmind.core.events import RunStore
from chainmind.core.models import DisruptionRun
from chainmind.integrations.aws.event_publisher import (
    event_record_id,
    event_record_id_for_key,
)


class DynamoDBEventStore(RunStore):
    """Persist typed disruption runs in a DynamoDB table keyed by run ID."""

    def __init__(self, table_name: str, region_name: str) -> None:
        self._table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)

    def save(self, run: DisruptionRun) -> None:
        """Write the run snapshot to DynamoDB and its audit evidence to S3."""

        try:
            self._table.put_item(
                Item={
                    "run_id": str(run.run_id),
                    "created_at": run.created_at.isoformat(),
                    "run_data": run.model_dump_json(),
                }
            )
            self._table.put_item(
                Item={
                    "run_id": event_record_id(run.event),
                    "created_at": run.created_at.isoformat(),
                    "event_key": run.event.dedupe_key,
                    "tenant_id": run.tenant_id,
                    "event_id": str(run.event.event_id),
                    "linked_run_id": str(run.run_id),
                }
            )
            artifact_bucket = os.environ.get("CHAINMIND_ARTIFACT_BUCKET")
            if artifact_bucket:
                payload = {
                    "run_id": str(run.run_id),
                    "event_id": str(run.event.event_id),
                    "audit_log": [entry.model_dump(mode="json") for entry in run.audit_log],
                    "trace_steps": [step.model_dump(mode="json") for step in run.trace_steps],
                    "chain_of_thought": run.chain_of_thought,
                }
                boto3.client("s3").put_object(
                    Bucket=artifact_bucket,
                    Key=f"runs/{run.run_id}/audit.json",
                    Body=run.model_dump_json().encode("utf-8"),
                    ContentType="application/json",
                )
                boto3.client("s3").put_object(
                    Bucket=artifact_bucket,
                    Key=f"runs/{run.run_id}/trace-audit.json",
                    Body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                    ContentType="application/json",
                )
        except (BotoCoreError, ClientError) as exc:
            raise IntegrationError(
                "The disruption run could not be saved to DynamoDB.",
                details={"reason": str(exc)},
            ) from exc

    def get(self, run_id: UUID) -> DisruptionRun | None:
        """Read and validate one run from DynamoDB."""

        try:
            item = self._table.get_item(Key={"run_id": str(run_id)}).get("Item")
        except (BotoCoreError, ClientError) as exc:
            raise IntegrationError(
                "The disruption run could not be read from DynamoDB.",
                details={"reason": str(exc)},
            ) from exc
        return DisruptionRun.model_validate_json(item["run_data"]) if item else None

    def get_by_idempotency_key(self, key: str, tenant_id: str = "demo") -> DisruptionRun | None:
        """Resolve an idempotency index record to its stored run."""

        try:
            link = self._table.get_item(
                Key={"run_id": event_record_id_for_key(key, tenant_id)}
            ).get("Item")
            if not link or not link.get("linked_run_id"):
                return None
            item = self._table.get_item(Key={"run_id": link["linked_run_id"]}).get("Item")
        except (BotoCoreError, ClientError, KeyError) as exc:
            raise IntegrationError(
                "The event idempotency key could not be read from DynamoDB.",
                details={"reason": str(exc)},
            ) from exc
        if not item:
            return None
        run = DisruptionRun.model_validate_json(item["run_data"])
        return run if run.tenant_id == tenant_id else None

    def list(self) -> list[DisruptionRun]:
        """Scan all local-demo runs; production should use a paginated query index."""

        runs: list[DisruptionRun] = []
        try:
            response = self._table.scan(
                FilterExpression=Attr("run_data").exists(),
                ProjectionExpression="run_id, created_at, run_data",
            )
            runs.extend(
                DisruptionRun.model_validate_json(item["run_data"])
                for item in response.get("Items", [])
            )
            while "LastEvaluatedKey" in response:
                response = self._table.scan(
                    FilterExpression=Attr("run_data").exists(),
                    ProjectionExpression="run_id, created_at, run_data",
                    ExclusiveStartKey=response["LastEvaluatedKey"],
                )
                runs.extend(
                    DisruptionRun.model_validate_json(item["run_data"])
                    for item in response.get("Items", [])
                )
        except (BotoCoreError, ClientError, KeyError, ValueError) as exc:
            raise IntegrationError(
                "Disruption runs could not be listed from DynamoDB.",
                details={"reason": str(exc)},
            ) from exc
        return sorted(runs, key=lambda run: run.created_at, reverse=True)

    def delete_tenant(self, tenant_id: str) -> int:
        """Delete a tenant's runs and event idempotency records."""

        deleted = 0
        try:
            for run in self.list():
                if run.tenant_id != tenant_id:
                    continue
                self._table.delete_item(Key={"run_id": str(run.run_id)})
                self._table.delete_item(Key={"run_id": event_record_id(run.event)})
                deleted += 1
        except (BotoCoreError, ClientError) as exc:
            raise IntegrationError(
                "Tenant run history could not be deleted from DynamoDB.",
                details={"reason": str(exc)},
            ) from exc
        return deleted
