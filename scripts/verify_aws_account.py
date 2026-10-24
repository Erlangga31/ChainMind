"""Read-only AWS account preflight checks; does not invoke agents or publish events."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError


@dataclass(frozen=True)
class CheckResult:
    """One non-secret outcome from an AWS preflight check."""

    name: str
    status: str
    detail: str


def verify_account(
    *,
    region: str,
    model_id: str,
    event_bus_name: str,
    agent_id: str | None = None,
    agent_alias_id: str | None = None,
    state_machine_arn: str | None = None,
    client_factory: Callable[..., Any] = boto3.client,
) -> list[CheckResult]:
    """Check configured AWS resource visibility using read-only service APIs."""

    results: list[CheckResult] = []
    try:
        identity = client_factory("sts", region_name=region).get_caller_identity()
        account_id = identity.get("Account", "unknown")
        results.append(
            CheckResult(
                "AWS credentials",
                "PASS",
                f"Authenticated to account {account_id}.",
            )
        )
    except (BotoCoreError, ClientError) as exc:
        return [CheckResult("AWS credentials", "FAIL", _safe_error(exc))]

    try:
        models = client_factory("bedrock", region_name=region).list_foundation_models()
        available = {
            model.get("modelId")
            for model in models.get("modelSummaries", [])
            if isinstance(model, dict)
        }
        status = "PASS" if model_id in available else "FAIL"
        detail = (
            "Model is listed in this region; runtime invocation access is not proven."
            if status == "PASS"
            else "Configured model is not listed in this region."
        )
        results.append(CheckResult("Bedrock model catalog", status, detail))
    except (BotoCoreError, ClientError) as exc:
        results.append(CheckResult("Bedrock model catalog", "FAIL", _safe_error(exc)))

    if agent_id and agent_alias_id:
        try:
            agent_client = client_factory("bedrock-agent", region_name=region)
            agent_client.get_agent(agentId=agent_id)
            agent_client.get_agent_alias(agentId=agent_id, agentAliasId=agent_alias_id)
            results.append(
                CheckResult(
                    "Bedrock agent configuration",
                    "PASS",
                    "Agent and alias are visible; InvokeAgent was not called.",
                )
            )
        except (BotoCoreError, ClientError) as exc:
            results.append(CheckResult("Bedrock agent configuration", "FAIL", _safe_error(exc)))
    else:
        results.append(
            CheckResult(
                "Bedrock agent configuration",
                "SKIP",
                "Set agent ID and alias ID to check.",
            )
        )

    try:
        client_factory("events", region_name=region).describe_event_bus(Name=event_bus_name)
        results.append(
            CheckResult(
                "EventBridge bus",
                "PASS",
                "Bus is visible; no event was published.",
            )
        )
    except (BotoCoreError, ClientError) as exc:
        results.append(CheckResult("EventBridge bus", "FAIL", _safe_error(exc)))
    results.append(
        CheckResult(
            "EventBridge PutEvents dry run",
            "SKIP",
            "AWS provides no PutEvents dry-run API; no event was sent.",
        )
    )

    if state_machine_arn:
        try:
            client_factory("stepfunctions", region_name=region).describe_state_machine(
                stateMachineArn=state_machine_arn
            )
            results.append(
                CheckResult("Step Functions state machine", "PASS", "State machine is visible.")
            )
        except (BotoCoreError, ClientError) as exc:
            results.append(CheckResult("Step Functions state machine", "FAIL", _safe_error(exc)))
    else:
        results.append(
            CheckResult("Step Functions state machine", "SKIP", "Set CHAINMIND_STATE_MACHINE_ARN.")
        )
    return results


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, ClientError):
        return str(exc.response.get("Error", {}).get("Code", "AWS service error"))
    return type(exc).__name__


def print_results(results: list[CheckResult]) -> None:
    """Print check outcomes without showing credentials or response payloads."""

    print(f"{'Check':36} {'Result':6} Detail")
    print("-" * 88)
    for result in results:
        print(f"{result.name:36} {result.status:6} {result.detail}")


def main() -> int:
    results = verify_account(
        region=os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1")),
        model_id=os.getenv("CHAINMIND_BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"),
        event_bus_name=os.getenv("CHAINMIND_EVENT_BUS_NAME", "chainmind"),
        agent_id=os.getenv("CHAINMIND_BEDROCK_AGENT_ID"),
        agent_alias_id=os.getenv("CHAINMIND_BEDROCK_AGENT_ALIAS_ID"),
        state_machine_arn=os.getenv("CHAINMIND_STATE_MACHINE_ARN"),
    )
    print_results(results)
    return 0 if all(result.status != "FAIL" for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
