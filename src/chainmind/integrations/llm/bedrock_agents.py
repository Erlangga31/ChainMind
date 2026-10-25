"""Amazon Bedrock Agents adapter with validated, source-attributed traces."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import ValidationError

from chainmind.core.errors import IntegrationError
from chainmind.core.models import LLMExplanation, ReasoningTraceStep, VendorEvaluation
from chainmind.integrations.llm.mock import MockLLMClient


class BedrockAgentsClient:
    """Invoke a prepared Bedrock Agent and preserve its trace for run evidence."""

    def __init__(
        self,
        agent_id: str,
        agent_alias_id: str,
        region_name: str,
        *,
        client: Any | None = None,
        fallback: MockLLMClient | None = None,
    ) -> None:
        if not agent_id or not agent_alias_id:
            raise IntegrationError("Bedrock Agent ID and alias ID are required.")
        self._agent_id = agent_id
        self._agent_alias_id = agent_alias_id
        self._client = client or boto3.client("bedrock-agent-runtime", region_name=region_name)
        self._fallback = fallback or MockLLMClient()

    def explain_vendor_choice(
        self,
        *,
        selected: VendorEvaluation,
        alternatives: list[VendorEvaluation],
        cost_of_inaction: float,
        run_id: str | None = None,
    ) -> LLMExplanation:
        """Invoke the agent for explanation only; retain Python's selected vendor."""

        facts = {
            "selected_vendor": selected.model_dump(mode="json"),
            "alternatives": [item.model_dump(mode="json") for item in alternatives],
            "cost_of_inaction": cost_of_inaction,
            "instruction": (
                "Explain only the supplied deterministic decision. Do not select a vendor, "
                "calculate or change money, invent facts, or bypass human approval."
            ),
        }
        try:
            response = self._client.invoke_agent(
                agentId=self._agent_id,
                agentAliasId=self._agent_alias_id,
                sessionId=run_id or uuid4().hex,
                inputText=json.dumps(facts, separators=(",", ":")),
                enableTrace=True,
            )
        except (BotoCoreError, ClientError) as exc:
            raise IntegrationError(
                "Amazon Bedrock Agent invocation failed.",
                details={"provider": "bedrock_agents"},
            ) from exc

        completion = bytearray()
        trace: list[ReasoningTraceStep] = []
        for event in response.get("completion", []):
            chunk = event.get("chunk")
            if isinstance(chunk, dict) and isinstance(chunk.get("bytes"), bytes):
                completion.extend(chunk["bytes"])
            if "trace" in event:
                trace.append(
                    ReasoningTraceStep(
                        source="Amazon Bedrock",
                        text=json.dumps(event["trace"], separators=(",", ":"), default=str),
                    )
                )

        try:
            output = completion.decode("utf-8").strip()
        except UnicodeDecodeError:
            output = ""
        try:
            explanation = self._parse_explanation(output, trace)
        except (ValidationError, TypeError, ValueError):
            return self._fallback_explanation(
                selected,
                alternatives,
                cost_of_inaction,
                run_id,
                trace,
                "Bedrock Agent output did not match the expected explanation schema.",
            )
        if explanation.confidence is not None and explanation.confidence < 0.6:
            return self._fallback_explanation(
                selected,
                alternatives,
                cost_of_inaction,
                run_id,
                trace,
                "Bedrock Agent confidence was below the configured threshold.",
            )
        if not explanation.trace:
            explanation.trace = trace or [
                ReasoningTraceStep(
                    source="Amazon Bedrock",
                    text="Agent completion received without provider trace events.",
                )
            ]
        return explanation

    @staticmethod
    def _parse_explanation(
        output: str,
        trace: list[ReasoningTraceStep],
    ) -> LLMExplanation:
        if output.startswith("{"):
            payload = json.loads(output)
            if not isinstance(payload, dict):
                raise ValueError("Agent response JSON must be an object.")
            return LLMExplanation.model_validate(
                {**payload, "trace": trace or payload.get("trace", [])}
            )
        return LLMExplanation(text=output, trace=trace)

    def _fallback_explanation(
        self,
        selected: VendorEvaluation,
        alternatives: list[VendorEvaluation],
        cost_of_inaction: float,
        run_id: str | None,
        trace: list[ReasoningTraceStep],
        reason: str,
    ) -> LLMExplanation:
        fallback = self._fallback.explain_vendor_choice(
            selected=selected,
            alternatives=alternatives,
            cost_of_inaction=cost_of_inaction,
            run_id=run_id,
        )
        return fallback.model_copy(
            update={
                "trace": [*trace, *fallback.trace],
                "fallback_used": True,
                "fallback_reason": reason,
            }
        )
