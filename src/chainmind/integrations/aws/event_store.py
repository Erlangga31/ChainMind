"""DynamoDB-backed run store for AWS deployments."""

from uuid import UUID

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from chainmind.core.errors import IntegrationError
from chainmind.core.events import RunStore
from chainmind.core.models import DisruptionRun


class DynamoDBEventStore(RunStore):
    """Persist typed disruption runs in a DynamoDB table keyed by run ID."""

    def __init__(self, table_name: str, region_name: str) -> None:
        self._table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)

    def save(self, run: DisruptionRun) -> None:
        """Write the current JSON run snapshot to DynamoDB."""

        try:
            self._table.put_item(
                Item={
                    "run_id": str(run.run_id),
                    "created_at": run.created_at.isoformat(),
                    "run_data": run.model_dump_json(),
                }
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

    def list(self) -> list[DisruptionRun]:
        """Scan all local-demo runs; production should use a paginated query index."""

        runs: list[DisruptionRun] = []
        try:
            response = self._table.scan(ProjectionExpression="run_id, created_at, run_data")
            runs.extend(
                DisruptionRun.model_validate_json(item["run_data"])
                for item in response.get("Items", [])
            )
            while "LastEvaluatedKey" in response:
                response = self._table.scan(
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
