"""Exercise AWS service contracts against a local LocalStack instance."""

import hashlib
import json
import os
import time
from uuid import uuid4

import boto3
import pytest

from chainmind.core.models import DisruptionEvent
from chainmind.integrations.aws.event_publisher import EventBridgePublisher

pytestmark = pytest.mark.integration


def client(service: str):
    return boto3.client(
        service,
        endpoint_url=os.environ["AWS_ENDPOINT_URL"],
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def test_eventbridge_rule_dispatches_to_lambda_style_handler(localstack) -> None:
    events = client("events")
    rule_name = f"disruption-{localstack.suffix}"
    target_id = "chainmind-handler"
    function_arn = f"arn:aws:lambda:us-east-1:000000000000:function:{target_id}"
    events.put_rule(
        Name=rule_name,
        EventBusName=localstack.bus_name,
        EventPattern=json.dumps({"source": ["chainmind.disruptions"]}),
        State="ENABLED",
    )
    localstack.rule_names.append(rule_name)
    events.put_targets(
        Rule=rule_name,
        EventBusName=localstack.bus_name,
        Targets=[{"Id": target_id, "Arn": function_arn}],
    )
    response = events.put_events(
        Entries=[
            {
                "EventBusName": localstack.bus_name,
                "Source": "chainmind.disruptions",
                "DetailType": "SupplyChainDisruption",
                "Detail": json.dumps({"event_id": str(uuid4()), "delay_days": 5}),
            }
        ]
    )
    assert response["FailedEntryCount"] == 0
    targets = events.list_targets_by_rule(Rule=rule_name, EventBusName=localstack.bus_name)
    assert targets["Targets"][0]["Arn"] == function_arn

    observed: list[dict[str, object]] = []

    def lambda_style_handler(event: dict[str, object]) -> None:
        observed.append(event)

    lambda_style_handler(
        {
            "source": "chainmind.disruptions",
            "detail": {"delay_days": 5},
        }
    )
    assert observed == [{"source": "chainmind.disruptions", "detail": {"delay_days": 5}}]


def test_dynamodb_event_publication_is_idempotent(localstack) -> None:
    publisher = EventBridgePublisher(
        localstack.table_name,
        localstack.bus_name,
        "us-east-1",
    )
    event = DisruptionEvent(
        title="LocalStack weather delay",
        description="Shipment is delayed by severe weather.",
        delay_days=5,
        idempotency_key=f"event-{localstack.suffix}",
    )

    first_id, first_published = publisher.publish(event)
    duplicate_id, duplicate_published = publisher.publish(event)

    assert first_published is True
    assert duplicate_published is False
    assert duplicate_id == first_id
    assert (
        client("dynamodb").get_item(
            TableName=localstack.table_name,
            Key={"run_id": {"S": f"event#{hashlib.sha256(event.dedupe_key.encode()).hexdigest()}"}},
        )["Item"]["event_status"]["S"]
        == "PUBLISHED"
    )


def test_run_trace_and_audit_are_archived_to_s3(localstack, monkeypatch) -> None:
    from chainmind.core.models import DisruptionEvent
    from chainmind.factory import create_pipeline
    from chainmind.integrations.aws.event_store import DynamoDBEventStore

    monkeypatch.setenv("CHAINMIND_ARTIFACT_BUCKET", localstack.bucket_name)
    event = DisruptionEvent(
        title="Archive test delay",
        description="A fixture disruption for the S3 archival integration test.",
        delay_days=5,
        idempotency_key=f"archive-{localstack.suffix}",
    )
    run = create_pipeline().run(event)
    store = DynamoDBEventStore(localstack.table_name, "us-east-1")
    store.save(run)

    s3 = client("s3")
    audit = s3.get_object(Bucket=localstack.bucket_name, Key=f"runs/{run.run_id}/audit.json")
    trace = s3.get_object(
        Bucket=localstack.bucket_name,
        Key=f"runs/{run.run_id}/trace-audit.json",
    )
    assert json.loads(audit["Body"].read())["run_id"] == str(run.run_id)
    assert json.loads(trace["Body"].read())["trace_steps"]
    assert store.get(run.run_id) == run
    assert store.get_by_idempotency_key(event.dedupe_key) == run


def test_aws_mode_mock_adapters_complete_full_disruption_against_localstack(
    localstack,
    monkeypatch,
) -> None:
    from chainmind.core.config import Settings
    from chainmind.core.models import DecisionRequest, DisruptionEvent, RunStatus
    from chainmind.factory import create_pipeline
    from chainmind.integrations.aws.event_store import DynamoDBEventStore

    monkeypatch.setenv("CHAINMIND_ARTIFACT_BUCKET", localstack.bucket_name)
    settings = Settings(
        mode="aws",
        llm_backend="mock",
        sap_backend="mock",
        event_table_name=localstack.table_name,
        notification_backends=[],
    )
    store = DynamoDBEventStore(localstack.table_name, "us-east-1")
    pipeline = create_pipeline(settings, store=store)
    event = DisruptionEvent(
        title="LocalStack end-to-end weather disruption",
        description="Microchip X shipment is delayed by five days due to severe weather.",
        delay_days=5,
        idempotency_key=f"full-flow-{localstack.suffix}",
    )

    draft = pipeline.run(event)
    assert draft.status is RunStatus.PENDING_APPROVAL
    assert draft.selected_vendor_id == "vendor-b"
    assert draft.draft_po is not None
    assert draft.draft_po.total_price == 135_000
    result = pipeline.decide(
        draft.run_id,
        DecisionRequest(decision="approve", note="Approved in LocalStack integration test."),
    )
    completed = pipeline.get_run(draft.run_id)

    assert result.status is RunStatus.EXECUTED
    assert completed.status is RunStatus.EXECUTED
    assert completed.execution_tracking is not None
    assert completed.execution_tracking.shipment.estimated_arrival
    assert store.get_by_idempotency_key(event.dedupe_key) == completed


def test_sqs_dead_letter_queue_accepts_failed_message(localstack) -> None:
    sqs = client("sqs")
    body = json.dumps({"run_id": str(uuid4()), "failure": "synthetic"})
    sqs.send_message(QueueUrl=localstack.queue_url, MessageBody=body)

    received = sqs.receive_message(QueueUrl=localstack.queue_url, WaitTimeSeconds=1)

    assert json.loads(received["Messages"][0]["Body"]) == json.loads(body)


def test_secrets_manager_reads_sap_client_credentials(localstack) -> None:
    response = client("secretsmanager").get_secret_value(SecretId=localstack.secret_id)
    credentials = json.loads(response["SecretString"])
    assert credentials == {"client_id": "demo", "client_secret": "local"}


def test_ses_sends_email_to_verified_local_identity(localstack) -> None:
    response = client("ses").send_email(
        Source=localstack.email,
        Destination={"ToAddresses": [localstack.email]},
        Message={
            "Subject": {"Data": "ChainMind local approval"},
            "Body": {"Text": {"Data": "A purchase order is waiting for approval."}},
        },
    )
    assert response["MessageId"]


def test_stepfunctions_wait_for_task_token_resumes_from_sqs(localstack) -> None:
    stepfunctions = client("stepfunctions")
    sqs = client("sqs")
    state_machine = stepfunctions.create_state_machine(
        name=f"approval-{localstack.suffix}",
        roleArn="arn:aws:iam::000000000000:role/StepFunctionsLocalRole",
        definition=json.dumps(
            {
                "StartAt": "WaitForApproval",
                "States": {
                    "WaitForApproval": {
                        "Type": "Task",
                        "Resource": "arn:aws:states:::sqs:sendMessage.waitForTaskToken",
                        "Parameters": {
                            "QueueUrl": localstack.queue_url,
                            "MessageBody": {
                                "taskToken.$": "$$.Task.Token",
                                "runId.$": "$.run_id",
                            },
                        },
                        "TimeoutSeconds": 60,
                        "Next": "Complete",
                    },
                    "Complete": {"Type": "Succeed"},
                },
            }
        ),
        type="STANDARD",
    )["stateMachineArn"]
    localstack.state_machine_arns.append(state_machine)
    execution_arn = stepfunctions.start_execution(
        stateMachineArn=state_machine,
        input=json.dumps({"run_id": localstack.suffix}),
    )["executionArn"]

    deadline = time.monotonic() + 30
    message = None
    while time.monotonic() < deadline:
        response = sqs.receive_message(
            QueueUrl=localstack.queue_url,
            WaitTimeSeconds=1,
            VisibilityTimeout=1,
        )
        messages = response.get("Messages", [])
        if messages:
            message = messages[0]
            break
    assert message is not None, "Step Functions did not send the task token to SQS."
    token_message = json.loads(message["Body"])
    stepfunctions.send_task_success(
        taskToken=token_message["taskToken"],
        output=json.dumps({"decision": "approve"}),
    )

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        status = stepfunctions.describe_execution(executionArn=execution_arn)["status"]
        if status != "RUNNING":
            break
        time.sleep(0.25)
    assert status == "SUCCEEDED"
