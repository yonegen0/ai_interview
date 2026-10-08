"""Responses API boundary. No SDK retries, logging, credential discovery or calls on import."""

import http.client
import json
import ssl
from dataclasses import dataclass, field
from time import monotonic

from pydantic import ValidationError

from interview_backend.evaluation.coaching import InvalidCoachingResult, validate_coaching_result
from interview_backend.evaluation.provider import CoachingPrompt, Prompt
from interview_backend.models.public import CoachingResult, EvaluationResult

MODEL = "gpt-6-luna"
ERRORS = frozenset(
    "AUTHENTICATION BILLING RATE_LIMIT SERVER_ERROR HTTP_ERROR REFUSAL INCOMPLETE "
    "OUTPUT_MISSING INVALID_JSON INVALID_SCHEMA TIMEOUT NETWORK OUTCOME_UNKNOWN "
    "CONFIGURATION USAGE_LIMIT".split()
)


class ProviderFailure(Exception):
    def __init__(self, kind, *, uncertain=False):
        self.kind = kind if kind in ERRORS else "CONFIGURATION"
        self.uncertain = uncertain
        super().__init__(self.kind)


@dataclass(frozen=True)
class Deadline:
    expires: float
    clock: object = field(default=monotonic, repr=False, compare=False)

    def seconds(self):
        remaining = self.expires - self.clock()
        if remaining <= 0:
            raise ProviderFailure("TIMEOUT")
        return remaining


def strict_json(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError
            result[k] = v
        return result

    def nonfinite(_):
        raise ValueError

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    except ValueError, UnicodeError, TypeError:
        raise ProviderFailure("INVALID_JSON") from None


class HTTPTransport:
    """Fixed TLS endpoints, bounded body, no redirects/proxy/cookies/retries."""

    def post(self, host, path, payload, headers, deadline):
        if (host, path) not in {
            ("api.openai.com", "/v1/responses"),
            ("auth.openai.com", "/oauth/token"),
        }:
            raise ProviderFailure("CONFIGURATION")
        connection = http.client.HTTPSConnection(
            host, timeout=deadline.seconds(), context=ssl.create_default_context()
        )
        sent = False
        try:
            body = json.dumps(payload, ensure_ascii=True, allow_nan=False).encode()
            connection.connect()
            network_socket = connection.sock
            network_socket.settimeout(deadline.seconds())
            # A failed send may have reached the service. Never replay it.
            sent = True
            connection.request(
                "POST", path, body=body, headers={"Content-Type": "application/json", **headers}
            )
            network_socket.settimeout(deadline.seconds())
            response = connection.getresponse()
            chunks, size = [], 0
            while True:
                # getresponse may clear connection.sock for Connection: close while the
                # response still owns its socket file. Keep the original socket handle.
                network_socket.settimeout(deadline.seconds())
                chunk = response.read1(8192)
                if not chunk:
                    break
                size += len(chunk)
                if size > 128 * 1024:
                    raise ProviderFailure("OUTPUT_MISSING")
                chunks.append(chunk)
                if response.isclosed():
                    break
            deadline.seconds()
            return response.status, b"".join(chunks)
        except ProviderFailure as error:
            if error.kind == "TIMEOUT":
                raise ProviderFailure("TIMEOUT", uncertain=sent) from None
            raise
        except TimeoutError:
            raise ProviderFailure("TIMEOUT", uncertain=sent) from None
        except OSError, http.client.HTTPException:
            raise ProviderFailure("NETWORK", uncertain=sent) from None
        finally:
            connection.close()


def http_error(status, raw):
    if status == 429:
        # Retain only an allowlisted classification, never API error text.
        try:
            code = strict_json(raw).get("error", {}).get("code")
        except ProviderFailure, AttributeError:
            code = None
        return ProviderFailure("BILLING" if code == "insufficient_quota" else "RATE_LIMIT")
    if status in (401, 403):
        return ProviderFailure("AUTHENTICATION")
    return ProviderFailure("SERVER_ERROR" if status >= 500 else "HTTP_ERROR")


def schema_for(prompt):
    if isinstance(prompt, CoachingPrompt):
        # Preserve all eight required keys; cross-field semantics remain domain validation.
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "status": {"type": "string", "enum": ["coaching", "completed"]},
                **{
                    name: {"type": "integer", "minimum": 0, "maximum": 10}
                    for name in ("conclusion_score", "specificity_score", "reasoning_score")
                },
                **{
                    name: {"type": "string", "minLength": 1, "maxLength": 200}
                    for name in ("good_point", "improvement")
                },
                "follow_up_question": {"type": ["string", "null"], "maxLength": 200},
                "example": {"type": ["string", "null"], "maxLength": 400},
            },
            "required": [
                "status",
                "conclusion_score",
                "specificity_score",
                "reasoning_score",
                "good_point",
                "improvement",
                "follow_up_question",
                "example",
            ],
        }
    schema = EvaluationResult.model_json_schema()
    schema["properties"]["exampleAnswer"] = {"type": ["string", "null"]}
    schema["additionalProperties"] = False
    schema["required"] = list(schema["properties"])
    return schema


@dataclass(frozen=True)
class OpenAISettings:
    effort: str = "low"
    max_output_tokens: int = 4096
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


class OpenAIProvider:
    provider_id = "openai"
    model_id = MODEL

    def __init__(self, authentication, *, transport=None, settings=None, clock=monotonic):
        self.authentication = authentication
        self.transport = transport or HTTPTransport()
        self.settings = settings or OpenAISettings()
        # Existing execution_config captures these server-selected parameters across retries.
        self.provider_id = (
            f"openai:standard:{self.settings.effort}:{self.settings.max_output_tokens}:"
            f"{self.settings.monthly_user_limit}:{self.settings.monthly_global_limit}"
        )
        self.clock = clock
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
        elif isinstance(prompt, Prompt):
            from interview_backend.evaluation.provider import INSTRUCTIONS

            instructions = INSTRUCTIONS
            data = {
                "question": prompt.question,
                "category": prompt.category,
                "criteria": prompt.criteria,
                "user_answer": prompt.user_answer,
            }
        else:
            raise ProviderFailure("CONFIGURATION")
        payload = {
            "model": MODEL,
            "reasoning": {"mode": "standard", "effort": self.settings.effort},
            "store": False,
            "background": False,
            "tools": [],
            "max_output_tokens": self.settings.max_output_tokens,
            "input": [
                {"role": "developer", "content": instructions},
                {"role": "user", "content": json.dumps(data, ensure_ascii=True)},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": prompt.version.replace("-", "_"),
                    "strict": True,
                    "schema": schema_for(prompt),
                }
            },
        }
        deadline.seconds()
        token = self.authentication.token(deadline)
        if not isinstance(token, str) or not token or any(c.isspace() for c in token):
            raise ProviderFailure("AUTHENTICATION")
        deadline.seconds()
        status, raw = self.transport.post(
            "api.openai.com",
            "/v1/responses",
            payload,
            {"Authorization": "Bearer " + token},
            deadline,
        )
        if status != 200:
            raise http_error(status, raw)
        response = strict_json(raw)
        if not isinstance(response, dict):
            raise ProviderFailure("OUTPUT_MISSING")
        usage = response.get("usage")
        if isinstance(usage, dict):
            # Numeric usage only. No response ID, content, JWT or owner is retained.
            safe = {}
            for name in ("input_tokens", "output_tokens"):
                value = usage.get(name)
                if type(value) is int and value >= 0:
                    safe[name] = value
            for container, key in (
                ("input_tokens_details", "cached_tokens"),
                ("output_tokens_details", "reasoning_tokens"),
            ):
                details = usage.get(container)
                value = details.get(key) if isinstance(details, dict) else None
                if type(value) is int and value >= 0:
                    safe[key] = value
            self.last_observation = safe
        if response.get("status") == "incomplete":
            raise ProviderFailure("INCOMPLETE")
        if response.get("status") != "completed":
            raise ProviderFailure("OUTCOME_UNKNOWN", uncertain=True)
        messages = []
        if not isinstance(response.get("output"), list):
            raise ProviderFailure("OUTPUT_MISSING")
        for item in response["output"]:
            if not isinstance(item, dict):
                raise ProviderFailure("OUTPUT_MISSING")
            if item.get("type") == "reasoning":
                continue
            if item.get("type") != "message" or item.get("role") != "assistant":
                raise ProviderFailure("OUTPUT_MISSING")
            if item.get("status") != "completed":
                raise ProviderFailure("OUTPUT_MISSING")
            if not isinstance(item.get("content"), list):
                raise ProviderFailure("OUTPUT_MISSING")
            for content in item["content"]:
                if not isinstance(content, dict):
                    raise ProviderFailure("OUTPUT_MISSING")
                if content.get("type") == "refusal":
                    raise ProviderFailure("REFUSAL")
                if content.get("type") != "output_text":
                    raise ProviderFailure("OUTPUT_MISSING")
                messages.append(content.get("text"))
        if len(messages) != 1 or not isinstance(messages[0], str) or not messages[0]:
            raise ProviderFailure("OUTPUT_MISSING")
        result = strict_json(messages[0])
        try:
            model = CoachingResult if isinstance(prompt, CoachingPrompt) else EvaluationResult
            if set(result) != set(schema_for(prompt)["required"]):
                raise ProviderFailure("INVALID_SCHEMA")
            if isinstance(prompt, Prompt) and result.get("exampleAnswer") is None:
                result = {k: v for k, v in result.items() if k != "exampleAnswer"}
            parsed = model.model_validate(result)
            if isinstance(prompt, CoachingPrompt):
                validate_coaching_result(parsed, prompt.context)
        except ValidationError, InvalidCoachingResult, TypeError:
            raise ProviderFailure("INVALID_SCHEMA") from None
        deadline.seconds()
        return parsed.wire()
