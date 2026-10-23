"""Step Functions task-token callback client with idempotent decision records."""

import json
from uuid import UUID

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from chainmind.core.errors import ChainMindError, IntegrationError
from chainmind.core.models import DecisionRequest, DecisionType


class StepFunctionsApprovalClient:
    """Complete a waiting approval task using its stored Step Functions token."""

    def __init__(self, table_name: str, region_name: str) -> None:
        self._table = boto3.resource("dynamodb", region_name=region_name).Table(table_name)
        self._stepfunctions = boto3.client("stepfunctions", region_name=region_name)

    def complete(self, run_id: UUID, decision: DecisionRequest, role: str) -> None:
        """Send an approver decision to Step Functions, safely handling repeats."""

        if role != "approver":
            raise ChainMindError(
                "approver_role_required",
                "Only a user with the approver role can decide a purchase order.",
                status_code=403,
            )
        key = f"approval#{run_id}"
        payload = decision.model_dump_json()
        try:
            record = self._table.get_item(Key={"run_id": key}).get("Item")
            if not record or not record.get("approval_task_token"):
                raise ChainMindError(
                    "approval_task_not_found",
                    "No active Step Functions approval task exists for this run.",
                    status_code=409,
                    details={"run_id": str(run_id)},
                )
            previous = record.get("decision_payload")
            if previous is not None:
                if previous == payload:
                    return
                raise ChainMindError(
                    "decision_conflict",
                    "A different decision has already been submitted for this approval task.",
                    status_code=409,
                )
            token = record["approval_task_token"]
            if decision.decision is DecisionType.REJECT:
                self._stepfunctions.send_task_failure(
                    taskToken=token,
                    error="HumanRejected",
                    cause=decision.note or "Rejected by an authorized human approver.",
                )
            else:
                self._stepfunctions.send_task_success(
                    taskToken=token,
                    output=json.dumps(
                        {
                            "decision": decision.decision.value,
                            "note": decision.note,
                            "vendor_id": decision.vendor_id,
                        }
                    ),
                )
            self._table.update_item(
                Key={"run_id": key},
                UpdateExpression="SET decision_payload = :payload",
                ConditionExpression="attribute_not_exists(decision_payload)",
                ExpressionAttributeValues={":payload": payload},
            )
        except ChainMindError:
            raise
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"TaskDoesNotExist", "InvalidToken"}:
                latest = self._table.get_item(Key={"run_id": key}).get("Item", {})
                if latest.get("decision_payload") == payload:
                    return
                raise ChainMindError(
                    "approval_task_expired",
                    "The Step Functions approval task is no longer active.",
                    status_code=409,
                ) from exc
            raise IntegrationError(
                "The Step Functions approval decision could not be recorded.",
                details={"reason": error_code or "AWS request failed"},
            ) from exc
        except (BotoCoreError, KeyError, TypeError, ValueError) as exc:
            raise IntegrationError(
                "The Step Functions approval decision could not be recorded."
            ) from exc
