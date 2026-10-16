"""Amazon Bedrock Converse adapter. One bounded call; never falls back to Fake/OpenAI."""

import json
from dataclasses import dataclass
from time import monotonic

from pydantic import ValidationError

from interview_backend.evaluation.coaching import InvalidCoachingResult, validate_coaching_result
from interview_backend.evaluation.openai_provider import Deadline, ProviderFailure, schema_for, strict_json
from interview_backend.evaluation.provider import (
    CoachingPrompt,
    INSTRUCTIONS,
    Prompt,
)
from interview_backend.models.public import CoachingResult, EvaluationResult

MODEL = "jp.anthropic.claude-haiku-5-5"
REGION = "ap-northeast-1"


@dataclass(frozen=True)
class BedrockSettings:
    effort: str = "low"
    max_output_tokens: int = 2048
    monthly_user_limit: int = 100
    monthly_global_limit: int = 3000

    def __post_init__(self):
        if (
            self.effort not in {"low", "medium"}
            or type(self.max_output_tokens) is not int
            or not 1024 <= self.max_output_tokens <= 8192
            or type(self.monthly_user_limit) is not int
            or not 1 <= self.monthly_user_limit <= 1000
            or type(self.monthly_global_limit) is not int
            or not 1 <= self.monthly_global_limit <= 10000
        ):
            raise ProviderFailure("CONFIGURATION")


class BedrockProvider:
    """Only the dev Worker may use this adapter; region and model are pinned."""

    model_id = MODEL

    def __init__(self, *, region=REGION, client=None, settings=None, clock=monotonic):
        if region != REGION:
            raise ProviderFailure("CONFIGURATION")
        self.region = region
        self.client = client
        self.settings = settings or BedrockSettings()
        self.clock = clock
        self.provider_id = (
            f"bedrock:jp:haiku-5-5:{self.settings.effort}:"
            f"{self.settings.max_output_tokens}:"
            f"{self.settings.monthly_user_limit}:{self.settings.monthly_global_limit}"
        )
        self.last_observation = None

    def evaluate(self, prompt):
        return self.evaluate_with_deadline(prompt, Deadline(self.clock() + 40, self.clock))

    def evaluate_with_deadline(self, prompt, deadline):
        self.last_observation = None
        if isinstance(prompt, CoachingPrompt):
            instructions = prompt.instructions
            data = prompt.context.model_dump(mode="json")
            data["question"] = {
                "question": prompt.context.question.question,
                "category": prompt.context.question.category,
            }
            model = CoachingResult
        elif isinstance(prompt, Prompt):
            instructions = INSTRUCTIONS
            data = {
                "question": prompt.question,
                "category": prompt.category,
                "criteria": prompt.criteria,
                "user_answer": prompt.user_answer,
            }
            model = EvaluationResult
        else:
            raise ProviderFailure("CONFIGURATION")

        # Haiku 5.5 currently has no Bedrock Structured Outputs support. Never
        # trust the textual JSON: existing Pydantic/domain validation is mandatory.
        instructions += (
            "\n出力はJSONオブジェクトのみ。Markdown・コードフェンス・説明文は禁止。"
            "必須フィールドを省略せず、余分なフィールドや本人未申告の事実を加えない。"
            "以下のJSON Schemaに完全に従う。"
            + json.dumps(schema_for(prompt), ensure_ascii=False, separators=(",", ":"))
        )
        request = {
            "modelId": MODEL,
            "system": [{"text": instructions}],
            "messages": [{
                "role": "user",
                "content": [{"text": json.dumps(data, ensure_ascii=False, allow_nan=False)}],
            }],
            "inferenceConfig": {"maxTokens": self.settings.max_output_tokens},
            "additionalModelRequestFields": {
                "thinking": {"type": "disabled"},
                "output_config": {"effort": self.settings.effort},
            },
        }
        deadline.seconds()
        attempted = False
        try:
            client = self.client
            if client is None:
                import boto3
                from botocore.config import Config

                client = boto3.client(
                    "bedrock-runtime",
                    region_name=self.region,
                    endpoint_url=f"https://bedrock-runtime.{self.region}.amazonaws.com",
                    config=Config(
                        retries={"total_max_attempts": 1},
                        connect_timeout=min(3, deadline.seconds()),
                        read_timeout=min(40, deadline.seconds()),
                    ),
                )
            deadline.seconds()
            # Once called, request outcome can be unknown. Never replay.
            attempted = True
            response = client.converse(**request)
            deadline.seconds()
        except ProviderFailure as error:
            if error.kind == "TIMEOUT" and attempted:
                raise ProviderFailure("TIMEOUT", uncertain=True) from None
            raise
        except Exception:
            # No SDK exception text, credentials, prompts or response bodies in logs.
            raise ProviderFailure("OUTCOME_UNKNOWN", uncertain=True) from None

        if not isinstance(response, dict):
            raise ProviderFailure("OUTPUT_MISSING")
        stop = response.get("stopReason")
        if stop != "end_turn":
            kind = "INCOMPLETE" if stop in {"max_tokens", "model_context_window_exceeded"} else "REFUSAL"
            raise ProviderFailure(kind)
        output = response.get("output")
        message = output.get("message") if isinstance(output, dict) else None
        blocks = message.get("content") if isinstance(message, dict) else None
        if not isinstance(blocks, list) or len(blocks) != 1:
            raise ProviderFailure("OUTPUT_MISSING")
        block = blocks[0]
        if not isinstance(block, dict) or set(block) != {"text"}:
            raise ProviderFailure("OUTPUT_MISSING")
        raw = block["text"]
        if not isinstance(raw, str) or not raw or len(raw.encode("utf-8")) > 65536:
            raise ProviderFailure("OUTPUT_MISSING")
        parsed = strict_json(raw)
        if not isinstance(parsed, dict):
            raise ProviderFailure("INVALID_SCHEMA")
        try:
            result = model.model_validate(parsed)
            if isinstance(prompt, CoachingPrompt):
                validate_coaching_result(result, prompt.context)
        except (ValidationError, InvalidCoachingResult, ValueError, TypeError):
            raise ProviderFailure("INVALID_SCHEMA") from None
        usage = response.get("usage", {})
        if isinstance(usage, dict):
            self.last_observation = {
                key: usage[key]
                for key in ("inputTokens", "outputTokens")
                if type(usage.get(key)) is int and usage[key] >= 0
            }
        return result.model_dump(mode="json")
