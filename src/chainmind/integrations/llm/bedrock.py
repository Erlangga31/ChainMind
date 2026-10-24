"""Amazon Bedrock Converse API adapter."""

import json

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import ValidationError

from chainmind.core.errors import IntegrationError
from chainmind.core.models import LLMExplanation, ReasoningTraceStep, VendorEvaluation


class BedrockLLMClient:
    """Call a configured Bedrock foundation model for decision explanations."""

    def __init__(self, model_id: str, region_name: str) -> None:
        self._model_id = model_id
        self._client = boto3.client("bedrock-runtime", region_name=region_name)

    def explain_vendor_choice(
        self,
        *,
        selected: VendorEvaluation,
        alternatives: list[VendorEvaluation],
        cost_of_inaction: float,
        run_id: str | None = None,
    ) -> LLMExplanation:
        """Ask Bedrock for a concise explanation based only on computed facts."""

        del run_id
        facts = {
            "selected_vendor": selected.model_dump(mode="json"),
            "alternatives": [item.model_dump(mode="json") for item in alternatives],
            "cost_of_inaction": cost_of_inaction,
            "instruction": (
                "Explain the economic tradeoff in plain language. Do not change the "
                "selected vendor, invent facts, or suggest executing without human approval."
            ),
        }
        try:
            response = self._client.converse(
                modelId=self._model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": json.dumps(facts, separators=(",", ":"))}],
                    }
                ],
                inferenceConfig={"maxTokens": 350, "temperature": 0},
            )
            text = response["output"]["message"]["content"][0]["text"]
            return LLMExplanation(
                text=text,
                trace=[
                    ReasoningTraceStep(
                        source="Amazon Bedrock",
                        text="Converse generated an explanation from deterministic inputs.",
                    )
                ],
            )
        except (
            BotoCoreError,
            ClientError,
            KeyError,
            IndexError,
            TypeError,
            ValidationError,
        ) as exc:
            raise IntegrationError(
                "Amazon Bedrock could not produce the decision explanation.",
                details={"provider": "bedrock", "reason": str(exc)},
            ) from exc
