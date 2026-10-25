"""Fixtures for LocalStack service integration tests."""

import os
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import uuid4

import boto3
import pytest
from botocore.exceptions import BotoCoreError, ClientError


@dataclass(frozen=True)
class LocalStackResources:
    endpoint_url: str
    suffix: str
    table_name: str
    bucket_name: str
    bus_name: str
    queue_url: str
    secret_id: str
    email: str
    rule_names: list[str]
    state_machine_arns: list[str]


def _client(service: str):
    return boto3.client(
        service,
        endpoint_url=os.environ["AWS_ENDPOINT_URL"],
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
    )


@pytest.fixture(scope="session")
def localstack_endpoint() -> str:
    endpoint = os.environ.get("AWS_ENDPOINT_URL")
    if not endpoint:
        pytest.skip("Set AWS_ENDPOINT_URL to run LocalStack integration tests.")
    return endpoint


@pytest.fixture
def aws_endpoint(localstack_endpoint: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv("AWS_ENDPOINT_URL", localstack_endpoint)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    yield localstack_endpoint


@pytest.fixture
def localstack(aws_endpoint: str) -> Iterator[LocalStackResources]:
    suffix = uuid4().hex[:12]
    table_name = f"chainmind-it-{suffix}"
    bucket_name = f"chainmind-it-{suffix}"
    bus_name = f"chainmind-it-{suffix}"
    queue_name = f"chainmind-dlq-{suffix}"
    secret_id = f"chainmind/integration/{suffix}"
    email = f"chainmind-{suffix}@example.com"
    dynamodb = _client("dynamodb")
    s3 = _client("s3")
    events = _client("events")
    sqs = _client("sqs")
    secrets = _client("secretsmanager")
    ses = _client("ses")
    state_machines = _client("stepfunctions")

    dynamodb.create_table(
        TableName=table_name,
        KeySchema=[{"AttributeName": "run_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "run_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    s3.create_bucket(Bucket=bucket_name)
    events.create_event_bus(Name=bus_name)
    queue_url = sqs.create_queue(QueueName=queue_name)["QueueUrl"]
    secrets.create_secret(
        Name=secret_id,
        SecretString='{"client_id":"demo","client_secret":"local"}',
    )
    ses.verify_email_identity(EmailAddress=email)
    resources = LocalStackResources(
        endpoint_url=aws_endpoint,
        suffix=suffix,
        table_name=table_name,
        bucket_name=bucket_name,
        bus_name=bus_name,
        queue_url=queue_url,
        secret_id=secret_id,
        email=email,
        rule_names=[],
        state_machine_arns=[],
    )
    yield resources

    for state_machine_arn in resources.state_machine_arns:
        try:
            state_machines.delete_state_machine(stateMachineArn=state_machine_arn)
        except (BotoCoreError, ClientError):
            pass
    try:
        for rule_name in resources.rule_names:
            for target in events.list_targets_by_rule(
                Rule=rule_name,
                EventBusName=bus_name,
            ).get("Targets", []):
                events.remove_targets(
                    Rule=rule_name,
                    EventBusName=bus_name,
                    Ids=[target["Id"]],
                )
            events.delete_rule(Name=rule_name, EventBusName=bus_name)
        for item in dynamodb.scan(TableName=table_name).get("Items", []):
            dynamodb.delete_item(
                TableName=table_name,
                Key={"run_id": item["run_id"]},
            )
        dynamodb.delete_table(TableName=table_name)
        for item in s3.list_objects_v2(Bucket=bucket_name).get("Contents", []):
            s3.delete_object(Bucket=bucket_name, Key=item["Key"])
        s3.delete_bucket(Bucket=bucket_name)
        events.delete_event_bus(Name=bus_name)
        sqs.delete_queue(QueueUrl=queue_url)
        secrets.delete_secret(SecretId=secret_id, ForceDeleteWithoutRecovery=True)
        ses.delete_identity(Identity=email)
    except (BotoCoreError, ClientError):
        raise
