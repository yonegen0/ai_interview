"""JP Geo Claude Haiku 5.5 Converse boundary. One invocation; no calls at import."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from time import monotonic

from pydantic import ValidationError

from interview_backend.evaluation.coaching import InvalidCoachingResult, validate_coaching_result
from interview_backend.evaluation.openai_provider import (
    Deadline,
    ProviderFailure,
    schema_for,
    strict_json,
)
from interview_backend.evaluation.provider import CoachingPrompt, Prompt
from interview_backend.evaluation.provider_configuration import provider_values
from interview_backend.evaluation.provider_limits import validate_limits
from interview_backend.evaluation.structured import StructuredPrompt
from interview_backend.models.public import CoachingResult, EvaluationResult

PROFILE = "jp.anthropic.claude-haiku-5-5"
REGION = "ap-northeast-1"
MODEL = "anthropic.claude-haiku-5-5"
SEND_BUDGET_SECONDS = 35  # connect 3 + read 30 + response validation reserve 2


@dataclass(frozen=True)
class BedrockSettings:
    profile_id: str = PROFILE
    region: str = REGION
    effort: str = "low"
    max_tokens: int = 2048
    monthly_user_limit: int = 20
    monthly_global_limit: int = 600

    def __post_init__(self):
        if (
            self.profile_id != PROFILE
            or self.region != REGION
            or type(self.effort) is not str
            or self.effort != "low"
            or type(self.max_tokens) is not int
            or self.max_tokens != 2048
        ):
            raise ProviderFailure("CONFIGURATION")
        try:
            validate_limits(self.monthly_user_limit, self.monthly_global_limit)
        except ValueError:
            raise ProviderFailure("CONFIGURATION") from None

    @classmethod
    def from_environment(cls, env):
        provider_values(env)
        if (
            not isinstance(env, Mapping)
            or env.get("INTERVIEW_AI_PROVIDER") != "bedrock"
            or env.get("INTERVIEW_BEDROCK_ENABLED") != "true"
            or env.get("INTERVIEW_BEDROCK_PROFILE_ID", PROFILE) != PROFILE
            or env.get("INTERVIEW_REGION", REGION) != REGION
        ):
            raise ProviderFailure("CONFIGURATION")

        def checked_uint(key: str, default: str) -> int:
            value = env.get(key, default)
            if type(value) is not str or re.fullmatch(r"[0-9]+", value) is None:
                raise ProviderFailure("CONFIGURATION")
            return int(value)

        return cls(
            profile_id=env.get("INTERVIEW_BEDROCK_PROFILE_ID", PROFILE),
            region=env.get("INTERVIEW_REGION", REGION),
            effort=env.get("INTERVIEW_BEDROCK_EFFORT", "low"),
            max_tokens=checked_uint("INTERVIEW_BEDROCK_MAX_TOKENS", "2048"),
            monthly_user_limit=checked_uint("INTERVIEW_BEDROCK_MONTHLY_USER_LIMIT", "20"),
            monthly_global_limit=checked_uint("INTERVIEW_BEDROCK_MONTHLY_GLOBAL_LIMIT", "600"),
        )


class BedrockProvider:
    model_id = MODEL

    def __init__(self, *, settings=None, client_factory=None, clock=monotonic):
        self.settings = settings or BedrockSettings()
        self.clock = clock
        self.client_factory = client_factory
        self.provider_id = (
            f"bedrock:jp:haiku-5-5:{self.settings.effort}:{self.settings.max_tokens}:"
            f"{self.settings.monthly_user_limit}:{self.settings.monthly_global_limit}"
        )
        self.last_observation = None

    def evaluate(self, prompt):
        return self.evaluate_with_deadline(prompt, Deadline(self.clock() + 40, self.clock))

    def _client(self, remaining):
        import boto3
        from botocore.config import Config

        # total_max_attempts includes the original request: exactly one network attempt.
        # These are per-I/O timeouts, not a hard wall-clock limit.
        if remaining < SEND_BUDGET_SECONDS:
            raise ProviderFailure("TIMEOUT")
        settings = Config(
            region_name=REGION,
            retries={"total_max_attempts": 1, "mode": "standard"},
            connect_timeout=3,
            read_timeout=30,
        )
        factory = self.client_factory or boto3.client
        return factory("bedrock-runtime", region_name=REGION, config=settings)

    def evaluate_with_deadline(self, prompt, deadline):
        self.last_observation = None
        if isinstance(prompt, StructuredPrompt):
            data, instruction = prompt.data, prompt.instructions
        elif isinstance(prompt, CoachingPrompt):
            data = prompt.context.model_dump(mode="json")
            data["question"] = {
                "question": prompt.context.question.question,
                "category": prompt.context.question.category,
            }
            instruction = prompt.instructions
        elif isinstance(prompt, Prompt):
            data = {
                "question": prompt.question,
                "category": prompt.category,
                "criteria": prompt.criteria,
                "user_answer": prompt.user_answer,
            }
            instruction = prompt.instructions
        else:
            raise ProviderFailure("CONFIGURATION")
        try:
            wire = json.dumps(data, ensure_ascii=True, allow_nan=False)
        except TypeError, ValueError:
            raise ProviderFailure("CONFIGURATION") from None
        # Service does not enforce JSON schema for this model. Validation is local.
        instruction += (
            " JSON objectのみを返す。Markdown/コードフェンス/余分な文章を返さない。"
            " 必須キーと型は次のschemaに完全に従い、余分なキーを返さない: "
            + json.dumps(schema_for(prompt), ensure_ascii=True)
        )
        kwargs = {
            "modelId": PROFILE,
            "system": [{"text": instruction}],
            "messages": [{"role": "user", "content": [{"text": wire}]}],
            "inferenceConfig": {
                "maxTokens": prompt.max_tokens
                if isinstance(prompt, StructuredPrompt)
                else self.settings.max_tokens
            },
            "additionalModelRequestFields": {
                "thinking": {"type": "adaptive"},
                "output_config": {"effort": self.settings.effort},
            },
        }
        if (
            isinstance(prompt, StructuredPrompt)
            and len(json.dumps(kwargs, ensure_ascii=True, allow_nan=False).encode())
            > prompt.max_request_bytes
        ):
            raise ProviderFailure("USAGE_LIMIT")
        client = None
        try:
            client = self._client(deadline.seconds())
            if deadline.seconds() < SEND_BUDGET_SECONDS:
                raise ProviderFailure("TIMEOUT")
        except ProviderFailure:
            raise
        except Exception:
            raise ProviderFailure("CONFIGURATION") from None
        # The request-specific hook guards the actual wire boundary after signing.
        events = getattr(getattr(client, "meta", None), "events", None)
        hook_id = f"bedrock-deadline-{id(deadline)}"
        sends = 0

        def before_send(**_):
            nonlocal sends
            if sends:
                raise ProviderFailure("OUTCOME_UNKNOWN", uncertain=True)
            if deadline.seconds() < SEND_BUDGET_SECONDS:
                raise ProviderFailure("TIMEOUT")
            sends += 1

        if events is not None:
            events.register("before-send.bedrock-runtime.Converse", before_send, unique_id=hook_id)
        # Do not retry ambiguous delivery, even on SQS redelivery.
        try:
            if deadline.seconds() < SEND_BUDGET_SECONDS:
                raise ProviderFailure("TIMEOUT")
            response = client.converse(**kwargs)
        except ProviderFailure:
            raise
        except Exception as exc:
            from botocore.exceptions import (
                ClientError,
                ConnectionClosedError,
                ConnectTimeoutError,
                EndpointConnectionError,
                ParamValidationError,
                ReadTimeoutError,
            )

            if isinstance(exc, ParamValidationError):
                raise ProviderFailure("CONFIGURATION") from None
            if isinstance(exc, ClientError):
                error = exc.response.get("Error", {})
                code = error.get("Code")
                if code in {
                    "AccessDeniedException",
                    "UnrecognizedClientException",
                    "ExpiredTokenException",
                }:
                    raise ProviderFailure("AUTHENTICATION") from None
                if code in {
                    "ThrottlingException",
                    "TooManyRequestsException",
                    "ServiceQuotaExceededException",
                }:
                    raise ProviderFailure("RATE_LIMIT") from None
                if code in {"ValidationException", "ResourceNotFoundException"}:
                    raise ProviderFailure("CONFIGURATION") from None
                raise ProviderFailure("SERVER_ERROR", uncertain=True) from None
            if isinstance(exc, (ReadTimeoutError, ConnectTimeoutError)):
                raise ProviderFailure("TIMEOUT", uncertain=True) from None
            if isinstance(exc, (EndpointConnectionError, ConnectionClosedError, OSError)):
                raise ProviderFailure("NETWORK", uncertain=True) from None
            raise ProviderFailure("OUTCOME_UNKNOWN", uncertain=True) from None
        finally:
            if events is not None:
                events.unregister("before-send.bedrock-runtime.Converse", unique_id=hook_id)
        deadline.seconds()
        if not isinstance(response, dict):
            raise ProviderFailure("OUTPUT_MISSING")
        usage = response.get("usage")
        if isinstance(usage, dict):
            safe = {}
            for key in (
                "inputTokens",
                "outputTokens",
                "totalTokens",
                "cacheReadInputTokens",
                "cacheWriteInputTokens",
            ):
                value = usage.get(key)
                if type(value) is int and value >= 0:
                    safe[key] = value
            self.last_observation = safe
        stop = response.get("stopReason")
        if stop == "max_tokens":
            raise ProviderFailure("INCOMPLETE")
        if stop in {"guardrail_intervened", "content_filtered"}:
            raise ProviderFailure("REFUSAL")
        if stop != "end_turn":
            raise ProviderFailure("OUTPUT_MISSING")
        output = response.get("output")
        message = output.get("message") if isinstance(output, dict) else None
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise ProviderFailure("OUTPUT_MISSING")
        contents = message.get("content")
        if not isinstance(contents, list):
            raise ProviderFailure("OUTPUT_MISSING")
        texts = []
        for block in contents:
            if not isinstance(block, dict):
                raise ProviderFailure("OUTPUT_MISSING")
            if "reasoningContent" in block and len(block) == 1:
                continue
            if "refusal" in block:
                raise ProviderFailure("REFUSAL")
            if set(block) != {"text"}:
                raise ProviderFailure("OUTPUT_MISSING")
            texts.append(block["text"])
        if len(texts) != 1 or not isinstance(texts[0], str) or not texts[0]:
            raise ProviderFailure("OUTPUT_MISSING")
        result = strict_json(texts[0])
        if not isinstance(result, dict):
            raise ProviderFailure("INVALID_SCHEMA")
        if isinstance(prompt, StructuredPrompt):
            deadline.seconds()
            return result  # Caller owns domain type and semantic validation.
        try:
            required = set(schema_for(prompt)["required"])
            if isinstance(prompt, CoachingPrompt):
                if set(result) != required:
                    raise ProviderFailure("INVALID_SCHEMA")
            elif set(result) not in (required, required - {"exampleAnswer"}):
                raise ProviderFailure("INVALID_SCHEMA")
            if isinstance(prompt, Prompt) and result.get("exampleAnswer") is None:
                result.pop("exampleAnswer", None)
            model = CoachingResult if isinstance(prompt, CoachingPrompt) else EvaluationResult
            parsed = model.model_validate(result)
            if isinstance(prompt, CoachingPrompt):
                validate_coaching_result(parsed, prompt.context)
        except ValidationError, InvalidCoachingResult, TypeError:
            raise ProviderFailure("INVALID_SCHEMA") from None
        deadline.seconds()
        return parsed.wire()
