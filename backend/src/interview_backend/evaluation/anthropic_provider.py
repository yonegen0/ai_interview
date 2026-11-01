"""Anthropic Messages API Provider: bounded direct HTTPS, no SDK retries or fallback."""

import json
import re
from dataclasses import dataclass
from time import monotonic

from pydantic import ValidationError

from interview_backend.evaluation.coaching import InvalidCoachingResult, validate_coaching_result
from interview_backend.evaluation.openai_provider import (
    Deadline,
    HTTPTransport,
    ProviderFailure,
    schema_for,
    strict_json,
)
from interview_backend.evaluation.provider import CoachingPrompt, Prompt
from interview_backend.evaluation.provider_limits import validate_limits
from interview_backend.evaluation.structured import StructuredPrompt
from interview_backend.models.public import CoachingResult, EvaluationResult

MODEL = "claude-haiku-5-5"
API_VERSION = "2026-10-21"
_ALLOWED_FORMATS = frozenset(
    "date-time time date duration email hostname uri ipv4 ipv6 uuid".split()
)
_ALLOWED_SCHEMA_KEYS = frozenset(
    {
        "type",
        "properties",
        "items",
        "required",
        "additionalProperties",
        "$ref",
        "$defs",
        "definitions",
        "anyOf",
        "allOf",
        "enum",
        "const",
        "description",
        "title",
        "default",
        "format",
        "pattern",
        "minItems",
        "minimum",
        "maximum",
        "multipleOf",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "maxItems",
    }
)
_DESCRIBED_CONSTRAINTS = frozenset(
    {
        "minimum",
        "maximum",
        "multipleOf",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "maxItems",
    }
)


def anthropic_schema(original):
    """Create an API-compatible copy. The unmodified original stays authoritative.

    Unsupported validation limits are included in descriptions, never silently
    waived; unsupported schema structures are rejected before any API call.
    """

    def convert(node):
        if not isinstance(node, dict) or set(node) - _ALLOWED_SCHEMA_KEYS:
            raise ProviderFailure("CONFIGURATION")
        if node.get("additionalProperties", False) is not False:
            raise ProviderFailure("CONFIGURATION")
        if "$ref" in node and (
            not isinstance(node["$ref"], str)
            or not node["$ref"].startswith(("#/$defs/", "#/definitions/"))
        ):
            raise ProviderFailure("CONFIGURATION")
        if "allOf" in node and any(
            isinstance(part, dict) and "$ref" in part for part in node["allOf"]
        ):
            raise ProviderFailure("CONFIGURATION")
        result = {}
        annotations = []
        for key, value in node.items():
            if key in _DESCRIBED_CONSTRAINTS:
                annotations.append(f"{key}={value}")
            elif key == "minItems" and value not in (0, 1):
                annotations.append(f"minItems={value}")
            elif key == "format" and value not in _ALLOWED_FORMATS:
                annotations.append(f"format={value}")
            elif key == "pattern" and (
                not isinstance(value, str)
                or any(mark in value for mark in ("(?", r"\b", r"\B", r"\1", r"\2"))
            ):
                raise ProviderFailure("CONFIGURATION")
            elif key in {"properties", "$defs", "definitions"}:
                if not isinstance(value, dict):
                    raise ProviderFailure("CONFIGURATION")
                result[key] = {name: convert(child) for name, child in value.items()}
            elif key in {"anyOf", "allOf"}:
                if not isinstance(value, list) or not value:
                    raise ProviderFailure("CONFIGURATION")
                result[key] = [convert(child) for child in value]
            elif key == "items":
                result[key] = convert(value)
            else:
                result[key] = value
        if annotations:
            result["description"] = (
                (result.get("description", "") + " " if result.get("description") else "")
                + "Constraints: "
                + ", ".join(annotations)
            )
        if result.get("type") == "object" or "properties" in result:
            result["additionalProperties"] = False
        return result

    if not isinstance(original, dict):
        raise ProviderFailure("CONFIGURATION")
    schema = convert(original)
    # Ref cycles are not supported by the API. Reject before sending.
    # Keep the two JSON Pointer namespaces distinct. Merging them by name
    # can falsely accept a missing target and send an invalid paid API request.
    definitions = {
        (namespace, name): value
        for namespace in ("$defs", "definitions")
        for name, value in schema.get(namespace, {}).items()
    }

    def references(node):
        if isinstance(node, dict):
            if "$ref" in node:
                parts = node["$ref"][2:].split("/")
                if len(parts) != 2 or parts[0] not in {"$defs", "definitions"}:
                    raise ProviderFailure("CONFIGURATION")
                encoded = parts[1]
                if not encoded or re.search(r"~(?![01])", encoded):
                    raise ProviderFailure("CONFIGURATION")
                yield (parts[0], encoded.replace("~1", "/").replace("~0", "~"))
            for key, value in node.items():
                if key != "$ref":
                    yield from references(value)
        elif isinstance(node, list):
            for value in node:
                yield from references(value)

    def check_definition(identifier, ancestors):
        if identifier in ancestors or identifier not in definitions:
            raise ProviderFailure("CONFIGURATION")
        for ref in references(definitions[identifier]):
            check_definition(ref, ancestors | {identifier})

    for identifier in definitions:
        check_definition(identifier, set())
    for ref in references(schema):
        if ref not in definitions:
            raise ProviderFailure("CONFIGURATION")
    optional = 0
    union = 0

    def complexity(node):
        nonlocal optional, union
        if isinstance(node, dict):
            if "properties" in node:
                required = node.get("required", [])
                if not isinstance(required, list):
                    raise ProviderFailure("CONFIGURATION")
                optional += len(set(node["properties"]) - set(required))
            if "anyOf" in node or isinstance(node.get("type"), list):
                union += 1
            for value in node.values():
                complexity(value)
        elif isinstance(node, list):
            for value in node:
                complexity(value)

    complexity(schema)
    if optional > 24 or union > 16:
        raise ProviderFailure("CONFIGURATION")
    return schema


@dataclass(frozen=True)
class AnthropicSettings:
    model: str = MODEL
    api_version: str = API_VERSION
    effort: str = "medium"
    max_output_tokens: int = 4096
    monthly_user_limit: int = 100
    monthly_global_limit: int = 3000
    workspace_id: str | None = None

    def __post_init__(self):
        if (
            self.model != MODEL
            or self.api_version != API_VERSION
            or self.effort not in {"low", "medium", "high"}
            or type(self.max_output_tokens) is not int
            or not 1024 <= self.max_output_tokens <= 8192
            or (
                self.workspace_id is not None
                and not re.fullmatch(r"wrkspc_[A-Za-z0-9]+", self.workspace_id)
            )
        ):
            raise ProviderFailure("CONFIGURATION")
        try:
            validate_limits(self.monthly_user_limit, self.monthly_global_limit)
        except ValueError:
            raise ProviderFailure("CONFIGURATION") from None


class AnthropicProvider:
    model_id = MODEL

    def __init__(self, authentication, *, transport=None, settings=None, clock=monotonic):
        self.authentication = authentication
        self.transport = transport or HTTPTransport()
        self.settings = settings or AnthropicSettings()
        s = self.settings
        self.provider_id = (
            f"anthropic:{s.model}:{s.api_version}:{s.effort}:"
            f"{s.max_output_tokens}:{s.monthly_user_limit}:{s.monthly_global_limit}"
        )
        self.clock = clock
        self.last_observation = None

    def evaluate(self, prompt):
        return self.evaluate_with_deadline(prompt, Deadline(self.clock() + 40, self.clock))

    def evaluate_with_deadline(self, prompt, deadline):
        self.last_observation = None
        if isinstance(prompt, StructuredPrompt):
            instructions, data = prompt.instructions, prompt.data
        elif isinstance(prompt, CoachingPrompt):
            instructions = prompt.instructions
            data = prompt.context.model_dump(mode="json")
            data["question"] = {
                "question": prompt.context.question.question,
                "category": prompt.context.question.category,
            }
        elif isinstance(prompt, Prompt):
            instructions = prompt.instructions
            data = {
                "question": prompt.question,
                "category": prompt.category,
                "criteria": prompt.criteria,
                "user_answer": prompt.user_answer,
            }
        else:
            raise ProviderFailure("CONFIGURATION")

        payload = {
            "model": self.settings.model,
            "thinking": {"type": "adaptive"},
            "max_tokens": (
                prompt.max_tokens
                if isinstance(prompt, StructuredPrompt)
                else self.settings.max_output_tokens
            ),
            "system": instructions,
            "messages": [{"role": "user", "content": json.dumps(data, ensure_ascii=True)}],
            "output_config": {
                "effort": self.settings.effort,
                "format": {"type": "json_schema", "schema": anthropic_schema(schema_for(prompt))},
            },
        }
        if (
            isinstance(prompt, StructuredPrompt)
            and len(json.dumps(payload, ensure_ascii=True, allow_nan=False).encode())
            > prompt.max_request_bytes
        ):
            raise ProviderFailure("USAGE_LIMIT")
        deadline.seconds()
        token = self.authentication.token(deadline)
        if not isinstance(token, str) or not token or any(c.isspace() for c in token):
            raise ProviderFailure("AUTHENTICATION")
        headers = {
            "Authorization": "Bearer " + token,
            "anthropic-version": self.settings.api_version,
        }
        if self.settings.workspace_id:
            headers["anthropic-workspace-id"] = self.settings.workspace_id
        deadline.seconds()
        status, raw = self.transport.post(
            "api.anthropic.com", "/v1/messages", payload, headers, deadline
        )
        if status != 200:
            raise anthropic_http_error(status, raw)
        response = strict_json(raw)
        if not isinstance(response, dict) or response.get("type") != "message":
            raise ProviderFailure("OUTPUT_MISSING")
        if response.get("role") != "assistant" or response.get("model") != self.settings.model:
            raise ProviderFailure("OUTPUT_MISSING")
        self.last_observation = _usage(response.get("usage"))
        stop_reason = response.get("stop_reason")
        # In API version 2026-10-21, refusals can be reported through
        # stop_details even when stop_reason is end_turn.
        details = response.get("stop_details")
        if isinstance(details, dict) and details.get("type") == "refusal":
            raise ProviderFailure("REFUSAL")
        if stop_reason == "refusal":
            raise ProviderFailure("REFUSAL")
        if stop_reason in {"max_tokens", "model_context_window_exceeded"}:
            raise ProviderFailure("INCOMPLETE")
        if stop_reason != "end_turn":
            raise ProviderFailure("OUTPUT_MISSING")
        contents = response.get("content")
        if not isinstance(contents, list):
            raise ProviderFailure("OUTPUT_MISSING")
        texts = []
        for item in contents:
            if not isinstance(item, dict):
                raise ProviderFailure("OUTPUT_MISSING")
            if item.get("type") in {"thinking", "redacted_thinking"}:
                continue
            if item.get("type") != "text" or not isinstance(item.get("text"), str):
                raise ProviderFailure("OUTPUT_MISSING")
            texts.append(item["text"])
        if len(texts) != 1 or not texts[0]:
            raise ProviderFailure("OUTPUT_MISSING")
        result = strict_json(texts[0])
        if not isinstance(result, dict):
            raise ProviderFailure("INVALID_SCHEMA")
        if isinstance(prompt, StructuredPrompt):
            # The STAR caller performs the original Pydantic and grounding checks.
            deadline.seconds()
            return result
        try:
            if set(result) != set(schema_for(prompt)["required"]):
                raise ProviderFailure("INVALID_SCHEMA")
            if isinstance(prompt, Prompt) and result.get("exampleAnswer") is None:
                result = {k: v for k, v in result.items() if k != "exampleAnswer"}
            model = CoachingResult if isinstance(prompt, CoachingPrompt) else EvaluationResult
            parsed = model.model_validate(result)
            if isinstance(prompt, CoachingPrompt):
                validate_coaching_result(parsed, prompt.context)
        except ValidationError, InvalidCoachingResult, TypeError, ValueError:
            raise ProviderFailure("INVALID_SCHEMA") from None
        deadline.seconds()
        return parsed.wire()


def _usage(usage):
    if not isinstance(usage, dict):
        return None
    keys = (
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    )
    safe = {name: usage[name] for name in keys if type(usage.get(name)) is int and usage[name] >= 0}
    details = usage.get("output_tokens_details")
    if isinstance(details, dict):
        reasoning = details.get("thinking_tokens")
        if type(reasoning) is int and reasoning >= 0 and reasoning <= safe.get("output_tokens", -1):
            safe["reasoning_tokens"] = reasoning
    return safe or None


def anthropic_http_error(status, raw):
    if status in (401, 403):
        return ProviderFailure("AUTHENTICATION")
    if status == 402:
        return ProviderFailure("BILLING")
    if status in (400, 429):
        # Anthropic's fixed spend-cap error code is a 429, not a throughput limit.
        # Custom spend caps are 400 invalid_request_error responses. Inspect
        # allowlisted fields only; never persist or log raw API error content.
        try:
            envelope = strict_json(raw)
            error = envelope.get("error") if isinstance(envelope, dict) else None
            if isinstance(error, dict):
                details = error.get("details")
                if (
                    status == 429
                    and error.get("type") == "rate_limit_error"
                    and isinstance(details, dict)
                    and details.get("error_code") == "enforced_spend_limit_reached"
                ):
                    return ProviderFailure("BILLING")
                if status == 400 and error.get("type") == "invalid_request_error":
                    message = error.get("message")
                    if isinstance(message, str) and message.startswith(
                        (
                            "You have reached your specified API usage limits",
                            "You have reached your specified workspace API usage limits",
                        )
                    ):
                        return ProviderFailure("BILLING")
        except ProviderFailure:
            pass
        return ProviderFailure("RATE_LIMIT" if status == 429 else "HTTP_ERROR")
    # The API may have accepted a request before a 5xx response; never replay.
    if status >= 500:
        return ProviderFailure("SERVER_ERROR", uncertain=True)
    return ProviderFailure("HTTP_ERROR")
