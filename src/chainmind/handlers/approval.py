"""Persist Step Functions callback tokens for human-in-the-loop approval."""

import os
from typing import Any

import boto3

from chainmind.core.errors import IntegrationError


def store_task_token(event: dict[str, Any], context: object) -> dict[str, str]:
    """Persist a callback token; the approval API later completes the task."""

    del context
    run_id = event.get("run_id")
    task_token = event.get("taskToken")
    table_name = os.environ.get("CHAINMIND_EVENT_TABLE_NAME")
    if not run_id or not task_token or not table_name:
        raise IntegrationError("Approval callback is missing its run ID, token, or table name.")
    boto3.resource("dynamodb").Table(table_name).put_item(
        Item={"run_id": run_id, "approval_task_token": task_token}
    )
    return {"run_id": run_id, "status": "PENDING_APPROVAL"}
