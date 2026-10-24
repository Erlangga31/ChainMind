import json
from typing import Any

from chainmind.core.config import Settings
from chainmind.core.events import EventStore
from chainmind.core.models import DisruptionEvent
from chainmind.factory import create_pipeline
from chainmind.integrations.aws import event_store as event_store_module
from chainmind.integrations.aws.event_store import DynamoDBEventStore


def test_dynamodb_store_archives_run_audit_and_trace_to_s3(
    monkeypatch: Any,
) -> None:
    dynamodb_items: list[dict[str, Any]] = []
    s3_objects: list[dict[str, Any]] = []

    class Table:
        def put_item(self, *, Item: dict[str, Any]) -> None:
            dynamodb_items.append(Item)

    class S3:
        def put_object(self, **kwargs: Any) -> None:
            s3_objects.append(kwargs)

    class Resource:
        def Table(self, table_name: str):
            assert table_name == "chainmind-events"
            return Table()

    monkeypatch.setenv("CHAINMIND_ARTIFACT_BUCKET", "chainmind-audit")
    monkeypatch.setattr(event_store_module.boto3, "resource", lambda *args, **kwargs: Resource())
    monkeypatch.setattr(event_store_module.boto3, "client", lambda *args, **kwargs: S3())
    run = create_pipeline(Settings(mode="mock"), EventStore()).run(
        DisruptionEvent(
            title="Weather delay",
            description="A storm delayed the component vessel.",
            delay_days=5,
        )
    )

    DynamoDBEventStore("chainmind-events", "us-east-1").save(run)

    assert len(dynamodb_items) == 2
    assert {item["Key"] for item in s3_objects} == {
        f"runs/{run.run_id}/audit.json",
        f"runs/{run.run_id}/trace-audit.json",
    }
    archive = next(item for item in s3_objects if item["Key"].endswith("trace-audit.json"))
    payload = json.loads(archive["Body"])
    assert payload["run_id"] == str(run.run_id)
    assert payload["audit_log"]
    assert payload["trace_steps"]
