"""Anthropic API contracts use mocked HTTP and secrets; no external network access."""

import json

import pytest

from interview_backend.assets import load_questions
from interview_backend.evaluation.anthropic_provider import (
    API_VERSION,
    MODEL,
    AnthropicProvider,
    AnthropicSettings,
    anthropic_schema,
)
from interview_backend.evaluation.openai_provider import Deadline, ProviderFailure
from interview_backend.evaluation.provider import build_coaching_prompt, build_prompt
from interview_backend.evaluation.selection import select_provider
from interview_backend.evaluation.worker import Worker
from interview_backend.models.public import CoachingInput
from interview_backend.star_assist.grounding import source_realizations
from interview_backend.star_assist.live_provider import LiveStarProvider, select_star_provider
from interview_backend.star_assist.models import Notes, StarInput


def coaching_prompt():
    question = load_questions()[0]
    return build_coaching_prompt(
        CoachingInput(
            question=question,
            initial_answer="提案しました。",
            coaching_history=(),
            latest_answer="提案しました。",
            coaching_count=0,
            can_ask_follow_up=True,
            unavailable_questions=(),
        )
    )


def coaching_result():
    return {
        "status": "completed",
        "conclusion_score": 8,
        "specificity_score": 8,
        "reasoning_score": 8,
        "good_point": "結論が明確です。",
        "improvement": "行動を確認しましょう。",
        "follow_up_question": None,
        "example": "提案しました。",
    }


def response(value=None, **updates):
    return {
        "type": "message",
        "role": "assistant",
        "model": MODEL,
        "stop_reason": "end_turn",
        "content": [
            {"type": "thinking", "thinking": ""},
            {"type": "text", "text": json.dumps(value if value is not None else coaching_result())},
        ],
        "usage": {
            "input_tokens": 600,
            "output_tokens": 120,
            "cache_read_input_tokens": 30,
            "cache_creation_input_tokens": 10,
            "output_tokens_details": {"thinking_tokens": 40},
        },
        **updates,
    }


class Transport:
    def __init__(self, message=None, status=200, error=None):
        self.message = message if message is not None else response()
        self.status, self.error = status, error
        self.requests = []

    def post(self, host, path, payload, headers, deadline):
        deadline.seconds()
        self.requests.append((host, path, payload, headers))
        if self.error:
            raise self.error
        raw = self.message if isinstance(self.message, bytes) else json.dumps(self.message).encode()
        return self.status, raw


class Authentication:
    def token(self, deadline):
        deadline.seconds()
        return "mock-secret-not-a-real-key"


def test_messages_payload_auth_schema_and_usage():
    transport = Transport()
    provider = AnthropicProvider(Authentication(), transport=transport)
    assert provider.evaluate(coaching_prompt()) == coaching_result()
    host, path, payload, headers = transport.requests[0]
    assert (host, path) == ("api.anthropic.com", "/v1/messages")
    assert payload["model"] == MODEL and payload["max_tokens"] == 4096
    assert payload["thinking"] == {"type": "adaptive"}
    assert payload["output_config"]["effort"] == "medium"
    assert payload["output_config"]["format"]["type"] == "json_schema"
    assert payload["output_config"]["format"]["schema"]["additionalProperties"] is False
    assert payload["system"] == coaching_prompt().instructions
    assert json.loads(payload["messages"][0]["content"])["latest_answer"] == "提案しました。"
    assert headers == {
        "Authorization": "Bearer mock-secret-not-a-real-key",
        "anthropic-version": API_VERSION,
    }
    assert provider.last_observation == {
        "input_tokens": 600,
        "output_tokens": 120,
        "cache_read_input_tokens": 30,
        "cache_creation_input_tokens": 10,
        "reasoning_tokens": 40,
    }


def test_prompt_v1_nullable_answer_contract():
    prompt = build_prompt(load_questions()[0], "本人回答")
    data = {
        "score": 78,
        "summary": "回答",
        "strengths": ["結論"],
        "improvements": ["具体性"],
        "exampleAnswer": None,
    }
    transport = Transport(response(data))
    provider = AnthropicProvider(Authentication(), transport=transport)
    assert provider.evaluate(prompt) == {k: v for k, v in data.items() if k != "exampleAnswer"}
    assert (
        json.loads(transport.requests[0][2]["messages"][0]["content"])["user_answer"] == "本人回答"
    )


@pytest.mark.parametrize(
    "status,kind",
    [
        (401, "AUTHENTICATION"),
        (403, "AUTHENTICATION"),
        (402, "BILLING"),
        (429, "RATE_LIMIT"),
        (400, "HTTP_ERROR"),
        (500, "SERVER_ERROR"),
        (529, "SERVER_ERROR"),
    ],
)
def test_http_classification_and_single_attempt(status, kind):
    transport = Transport({"type": "error", "error": {"message": "sensitive"}}, status=status)
    with pytest.raises(ProviderFailure) as error:
        AnthropicProvider(Authentication(), transport=transport).evaluate(coaching_prompt())
    assert error.value.kind == kind and len(transport.requests) == 1
    assert "sensitive" not in str(error.value)
    if status >= 500:
        assert error.value.uncertain


@pytest.mark.parametrize(
    "status,api_error,kind",
    [
        (
            429,
            {
                "type": "rate_limit_error",
                "message": "Do not print sensitive billing details",
                "details": {"error_code": "enforced_spend_limit_reached"},
            },
            "BILLING",
        ),
        (
            429,
            {
                "type": "rate_limit_error",
                "message": "ordinary throughput limit",
                "details": {"error_code": "requests_per_minute"},
            },
            "RATE_LIMIT",
        ),
        (
            400,
            {
                "type": "invalid_request_error",
                "message": "You have reached your specified API usage limits for this month.",
            },
            "BILLING",
        ),
        (
            400,
            {
                "type": "invalid_request_error",
                "message": (
                    "You have reached your specified workspace API usage limits for this month."
                ),
            },
            "BILLING",
        ),
        (
            400,
            {"type": "invalid_request_error", "message": "Invalid output_config.format"},
            "HTTP_ERROR",
        ),
        (
            429,
            {"type": "rate_limit_error", "details": {"error_code": "unfamiliar_value"}},
            "RATE_LIMIT",
        ),
    ],
)
def test_spend_cap_vs_rate_limit_without_retry_or_secret_logging(status, api_error, kind):
    transport = Transport({"type": "error", "error": api_error}, status=status)
    with pytest.raises(ProviderFailure) as exc:
        AnthropicProvider(Authentication(), transport=transport).evaluate(coaching_prompt())
    assert exc.value.kind == kind
    assert not exc.value.uncertain
    assert len(transport.requests) == 1
    assert "sensitive" not in str(exc.value)


@pytest.mark.parametrize(
    "change,kind",
    [
        ({"stop_reason": "max_tokens"}, "INCOMPLETE"),
        ({"stop_reason": "model_context_window_exceeded"}, "INCOMPLETE"),
        ({"stop_reason": "refusal"}, "REFUSAL"),
        ({"stop_reason": "tool_use"}, "OUTPUT_MISSING"),
        ({"stop_reason": "pause_turn"}, "OUTPUT_MISSING"),
        ({"stop_reason": "unknown_value"}, "OUTPUT_MISSING"),
        ({"model": "other-model"}, "OUTPUT_MISSING"),
        ({"content": []}, "OUTPUT_MISSING"),
        ({"content": [{"type": "tool_use"}]}, "OUTPUT_MISSING"),
        ({"content": [{"type": "text", "text": "{}"}]}, "INVALID_SCHEMA"),
    ],
)
def test_invalid_message_fails_closed(change, kind):
    with pytest.raises(ProviderFailure, match=kind):
        AnthropicProvider(Authentication(), transport=Transport(response(**change))).evaluate(
            coaching_prompt()
        )


@pytest.mark.parametrize(
    "raw,kind",
    [
        (b'{"type":"message","type":"error"}', "INVALID_JSON"),
        (b"NaN", "INVALID_JSON"),
        (b"{", "INVALID_JSON"),
    ],
)
def test_invalid_envelope_json(raw, kind):
    with pytest.raises(ProviderFailure, match=kind):
        AnthropicProvider(Authentication(), transport=Transport(raw)).evaluate(coaching_prompt())


@pytest.mark.parametrize(
    "data",
    [
        '{"status":"completed","status":"coaching"}',
        "NaN",
        "{",
    ],
)
def test_invalid_response_json(data):
    with pytest.raises(ProviderFailure, match="INVALID_JSON"):
        AnthropicProvider(
            Authentication(),
            transport=Transport(response(content=[{"type": "text", "text": data}])),
        ).evaluate(coaching_prompt())


@pytest.mark.parametrize(
    "data",
    [
        {"conclusion_score": 11},
        {"reasoning_score": True},
        {"unexpected": "not allowed"},
        {"example": None},
    ],
)
def test_coaching_domain_validation(data):
    with pytest.raises(ProviderFailure, match="INVALID_SCHEMA"):
        AnthropicProvider(
            Authentication(),
            transport=Transport(response(coaching_result() | data)),
        ).evaluate(coaching_prompt())


def test_schema_removes_unsupported_constraints_but_does_not_modify_original():
    original = {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "minimum": 0, "maximum": 10},
            "items": {
                "type": "array",
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 50}},
                    "required": ["name"],
                },
            },
        },
        "required": ["count", "items"],
    }
    adapted = anthropic_schema(original)
    assert "minimum" not in adapted["properties"]["count"]
    assert "minimum=0" in adapted["properties"]["count"]["description"]
    assert adapted["properties"]["items"]["items"]["additionalProperties"] is False
    assert original["properties"]["count"]["minimum"] == 0


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "additionalProperties": True},
        {"$ref": "https://example.com/schema"},
        {"type": "object", "properties": {"x": {"type": "string", "futureRule": 1}}},
        {"$defs": {"x": {"$ref": "#/$defs/x"}}, "$ref": "#/$defs/x"},
    ],
)
def test_unsupported_schema_rejected_without_guesswork(schema):
    with pytest.raises(ProviderFailure, match="CONFIGURATION"):
        anthropic_schema(schema)


@pytest.mark.parametrize(
    "schema",
    [
        {
            "type": "object",
            "properties": {"value": {"$ref": "#/definitions/Item"}},
            "required": ["value"],
            "$defs": {"Item": {"type": "string"}},
        },
        {
            "type": "object",
            "properties": {"value": {"$ref": "#/$defs/Item"}},
            "required": ["value"],
            "definitions": {"Item": {"type": "string"}},
        },
        {
            "type": "object",
            "properties": {"value": {"$ref": "#/$defs/Item/missing"}},
            "required": ["value"],
            "$defs": {"Item": {"type": "string"}, "missing": {"type": "string"}},
        },
    ],
)
def test_schema_does_not_accept_wrong_ref_namespace_or_nested_pointer(schema):
    with pytest.raises(ProviderFailure, match="CONFIGURATION"):
        anthropic_schema(schema)


def test_schema_accepts_distinct_definition_namespaces():
    schema = {
        "type": "object",
        "properties": {
            "first": {"$ref": "#/$defs/Item"},
            "second": {"$ref": "#/definitions/Item"},
        },
        "required": ["first", "second"],
        "$defs": {"Item": {"type": "string"}},
        "definitions": {"Item": {"type": "integer"}},
    }
    assert anthropic_schema(schema)["properties"] == schema["properties"]


def test_refusal_stop_details_never_saves_valid_looking_output():
    # A malformed upstream combination must not silently pass domain validation.
    transport = Transport(
        response(
            stop_reason="end_turn",
            stop_details={"type": "refusal", "category": "cyber"},
        )
    )
    with pytest.raises(ProviderFailure, match="REFUSAL"):
        AnthropicProvider(Authentication(), transport=transport).evaluate(coaching_prompt())
    assert len(transport.requests) == 1


def test_unknown_schema_reference_is_rejected_before_http():
    with pytest.raises(ProviderFailure, match="CONFIGURATION"):
        anthropic_schema(
            {
                "type": "object",
                "properties": {"value": {"$ref": "#/$defs/missing"}},
                "required": ["value"],
            }
        )


def test_star_live_generation_uses_existing_validation():
    transport = Transport(
        response(
            {
                "status": "needs_information",
                "candidates": [],
                "missingInformation": ["本人の行動を詳しく教えてください。"],
            }
        )
    )
    provider = AnthropicProvider(Authentication(), transport=transport)
    live = select_star_provider(provider)
    assert isinstance(live, LiveStarProvider)
    assert live.provider_id.startswith("star:anthropic:claude-haiku-5-5:")
    value = StarInput(
        notes=Notes(S="", T="", A="確認しました。", R=""),
        targetCategory=None,
        industry="",
        company="",
        candidates=[],
        selectedCandidateId=None,
        generationId=None,
    )
    result = live.generate_with_deadline("工夫を教えて", value, Deadline(1000, lambda: 0))
    assert result.status == "needs_information"
    assert len(transport.requests) == 1
    assert transport.requests[0][2]["max_tokens"] == 2048
    assert live.last_observation["output_tokens"] == 120


@pytest.mark.parametrize("tamper", [None, "invented_result", "reversed_negation"])
def test_anthropic_star_natural_result_is_grounded_before_return(tamper):
    value = StarInput(
        notes=Notes(
            S="顧客から相談がありました。",
            T="状況の整理を担当しました。",
            A="顧客に状況を共有しました。",
            R="成果は確認できませんでした。",
        ),
        targetCategory="corporate_sales",
        industry="製造",
        company="応募先",
        candidates=[],
        selectedCandidateId=None,
        generationId=None,
    )
    realizations = source_realizations(value.notes.model_dump())
    orders = {
        "A": ["R", "S", "T", "A"],
        "B": ["A", "S", "T", "R"],
        "C": ["S", "T", "A", "R"],
    }
    candidates = [
        {
            "id": identifier,
            "style": style,
            "passages": [
                {"source": field, "text": realizations[field][identifier]}
                for field in orders[identifier]
            ],
        }
        for identifier, style in (
            ("A", "conclusion"),
            ("B", "action"),
            ("C", "conversational"),
        )
    ]
    if tamper == "invented_result":
        candidates[1]["passages"][0]["text"] = "売上を200%改善しました。"
    elif tamper == "reversed_negation":
        candidates[0]["passages"][0]["text"] = "成果を確認できました。"
    transport = Transport(
        response({"status": "ready", "candidates": candidates, "missingInformation": []})
    )
    live = LiveStarProvider(AnthropicProvider(Authentication(), transport=transport))
    result = live.generate_with_deadline("具体的な経験は？", value, Deadline(1000, lambda: 0))
    assert len(transport.requests) == 1
    assert transport.requests[0][2]["max_tokens"] == 2048
    assert live.last_observation["output_tokens"] == 120
    if tamper is None:
        assert result.status == "ready"
        assert [candidate.id for candidate in result.candidates] == ["A", "B", "C"]
        assert all(
            realizations["R"][candidate.id] in candidate.text for candidate in result.candidates
        )
    else:
        assert result.status == "needs_information"
        assert not result.candidates


def test_selection_requires_explicit_secret_and_no_fallback():
    arn = "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:anthropic-prod"
    environment = {
        "INTERVIEW_AI_PROVIDER": "anthropic",
        "INTERVIEW_ANTHROPIC_ENABLED": "true",
        "INTERVIEW_ANTHROPIC_AUTH": "secret",
        "INTERVIEW_ANTHROPIC_SECRET_ARN": arn,
        "INTERVIEW_ANTHROPIC_MODEL": MODEL,
        "INTERVIEW_ANTHROPIC_API_VERSION": API_VERSION,
        "INTERVIEW_REGION": "ap-northeast-1",
        "INTERVIEW_ACCOUNT_ID": "123456789012",
    }
    provider = select_provider(environment)
    assert isinstance(provider, AnthropicProvider)
    assert provider.settings.effort == "medium"
    assert provider.authentication.secret_arn == arn
    for key, value in [
        ("INTERVIEW_ANTHROPIC_ENABLED", "false"),
        ("INTERVIEW_ANTHROPIC_MODEL", "wrong"),
        ("INTERVIEW_ANTHROPIC_API_VERSION", "2023-06-01"),
        ("INTERVIEW_OPENAI_ENABLED", "true"),
        ("INTERVIEW_ANTHROPIC_MONTHLY_USER_LIMIT", "101"),
        ("INTERVIEW_ANTHROPIC_SECRET_ARN", arn.replace("123456789012", "000000000000")),
    ]:
        with pytest.raises(ProviderFailure, match="CONFIGURATION"):
            select_provider(environment | {key: value})


def test_transport_failure_never_retries():
    transport = Transport(error=ProviderFailure("NETWORK", uncertain=True))
    with pytest.raises(ProviderFailure) as error:
        AnthropicProvider(Authentication(), transport=transport).evaluate(coaching_prompt())
    assert error.value.uncertain
    assert len(transport.requests) == 1


def test_paid_worker_quota_and_duplicate_delivery(runtime):
    from conftest import uid

    provider = AnthropicProvider(
        Authentication(),
        transport=Transport(),
        settings=AnthropicSettings(monthly_user_limit=1),
    )
    worker = Worker(runtime.repository, provider, runtime.worker.clock)
    app = runtime.application

    def submit(number):
        owner = "owner"
        session = app.create(
            owner,
            uid(100 + number),
            {"mode": "category", "category": "career", "difficulty": "standard"},
        ).body["sessionId"]
        question = app.question(owner, session).body["question"]["id"]
        return app.submit(
            owner,
            uid(200 + number),
            session,
            {"kind": "initial_answer", "questionId": question, "answer": "提案しました。"},
        ).body["evaluationId"]

    first = submit(1)
    assert worker.run("owner", first)
    assert worker.run("owner", first) is False
    second = submit(2)
    assert worker.run("owner", second)
    assert runtime.repository.snapshot().evaluations[second].failure_reason == "PREPARATION_FAILED"
    assert len(provider.transport.requests) == 1
