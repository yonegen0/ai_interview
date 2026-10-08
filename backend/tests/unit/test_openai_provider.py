"""Real HTTP request contracts behind mock transport; the global socket guard stays enabled."""

import json
from types import SimpleNamespace

import pytest

from interview_backend.assets import load_questions
from interview_backend.evaluation.openai_auth import AWSFederation, SecretAuthentication
from interview_backend.evaluation.openai_provider import (
    Deadline,
    HTTPTransport,
    OpenAIProvider,
    OpenAISettings,
    ProviderFailure,
    schema_for,
)
from interview_backend.evaluation.provider import build_coaching_prompt, build_prompt
from interview_backend.evaluation.selection import select_provider
from interview_backend.evaluation.worker import Worker
from interview_backend.models.public import CoachingInput


def context():
    return CoachingInput(
        question=load_questions()[0],
        initial_answer="提案しました。",
        coaching_history=(),
        latest_answer="提案しました。",
        coaching_count=0,
        can_ask_follow_up=True,
        unavailable_questions=(),
    )


def result(status="completed"):
    return dict(
        status=status,
        conclusion_score=8,
        specificity_score=8,
        reasoning_score=8,
        good_point="結論が明確です。",
        improvement="行動を確認しましょう。",
        follow_up_question="どんな行動をしましたか？" if status == "coaching" else None,
        example=None if status == "coaching" else "提案しました。",
    )


def response(value=None, **changes):
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(value or result())}],
            }
        ],
        **changes,
    }


class Transport:
    def __init__(self, value=None, status=200, error=None):
        self.value, self.status, self.error = value or response(), status, error
        self.requests = []

    def post(self, host, path, payload, headers, deadline):
        deadline.seconds()
        self.requests.append((host, path, payload, headers))
        if self.error:
            raise self.error
        return self.status, json.dumps(self.value).encode()


class Authentication:
    def __init__(self, error=None):
        self.calls, self.error = 0, error

    def token(self, deadline):
        self.calls += 1
        deadline.seconds()
        if self.error:
            raise self.error
        return "offline-placeholder"


@pytest.mark.parametrize("status", ["coaching", "completed"])
def test_responses_strict_contract_and_data_separation(status):
    transport = Transport(response(result(status)))
    provider = OpenAIProvider(Authentication(), transport=transport)
    assert provider.evaluate(build_coaching_prompt(context())) == result(status)
    host, path, payload, _ = transport.requests[0]
    assert (host, path) == ("api.openai.com", "/v1/responses")
    assert payload["model"] == "gpt-6-luna"
    assert payload["reasoning"] == {"mode": "standard", "effort": "low"}
    assert payload["store"] is payload["background"] is False
    assert payload["tools"] == [] and payload["max_output_tokens"] == 4096
    assert set(payload) == {
        "model",
        "reasoning",
        "store",
        "background",
        "tools",
        "max_output_tokens",
        "input",
        "text",
    }
    assert payload["input"][0]["role"] == "developer"
    expected = context().model_dump(mode="json")
    expected["question"] = {
        "question": context().question.question,
        "category": context().question.category,
    }
    assert json.loads(payload["input"][1]["content"]) == expected
    assert payload["text"]["format"]["strict"] is True
    schema = payload["text"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(result())
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "http,code,kind",
    [
        (429, "rate_limit_exceeded", "RATE_LIMIT"),
        (429, "insufficient_quota", "BILLING"),
        (503, "unavailable", "SERVER_ERROR"),
        (401, "invalid_key", "AUTHENTICATION"),
        (403, "denied", "AUTHENTICATION"),
        (302, "redirect", "HTTP_ERROR"),
    ],
)
def test_http_errors_no_retry_no_error_text(http, code, kind):
    transport = Transport({"error": {"code": code, "message": "private-content"}}, http)
    with pytest.raises(ProviderFailure) as caught:
        OpenAIProvider(Authentication(), transport=transport).evaluate(
            build_coaching_prompt(context())
        )
    assert caught.value.kind == kind and str(caught.value) == kind
    assert "private-content" not in repr(caught.value)
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "value,kind",
    [
        (response(status="incomplete"), "INCOMPLETE"),
        (response(status="in_progress"), "OUTCOME_UNKNOWN"),
        (response(output=[]), "OUTPUT_MISSING"),
        (response(output=None), "OUTPUT_MISSING"),
        (response(output=[{}]), "OUTPUT_MISSING"),
        (
            response(
                output=[
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "refusal", "refusal": "private refusal"}],
                    }
                ]
            ),
            "REFUSAL",
        ),
        (response(result() | {"conclusion_score": 11}), "INVALID_SCHEMA"),
        (response(result() | {"conclusion_score": True}), "INVALID_SCHEMA"),
        (response(result() | {"good_point": " "}), "INVALID_SCHEMA"),
        (response(result() | {"example": None}), "INVALID_SCHEMA"),
        (response(result() | {"untrusted_extra": "ignored?"}), "INVALID_SCHEMA"),
    ],
)
def test_response_and_domain_failures(value, kind):
    with pytest.raises(ProviderFailure, match=kind):
        OpenAIProvider(Authentication(), transport=Transport(value)).evaluate(
            build_coaching_prompt(context())
        )


@pytest.mark.parametrize("raw", ["{", '{"status":"completed","status":"coaching"}', "NaN"])
def test_invalid_json(raw):
    value = response()
    value["output"][0]["content"][0]["text"] = raw
    with pytest.raises(ProviderFailure, match="INVALID_JSON"):
        OpenAIProvider(Authentication(), transport=Transport(value)).evaluate(
            build_coaching_prompt(context())
        )


def test_authentication_deadline_prevents_billable_request():
    now = [0]

    class SlowAuth:
        def token(self, deadline):
            now[0] = 41
            return "offline-placeholder"

    transport = Transport()
    provider = OpenAIProvider(SlowAuth(), transport=transport, clock=lambda: now[0])
    with pytest.raises(ProviderFailure, match="TIMEOUT"):
        provider.evaluate(build_coaching_prompt(context()))
    assert transport.requests == []


def test_auth_failure_never_falls_back():
    transport = Transport()
    with pytest.raises(ProviderFailure, match="AUTHENTICATION"):
        OpenAIProvider(
            Authentication(ProviderFailure("AUTHENTICATION")), transport=transport
        ).evaluate(build_coaching_prompt(context()))
    assert transport.requests == []


def test_selection_explicit_and_settings_bounded():
    assert select_provider({}).__class__.__name__ == "FakeProvider"
    for env in ({"INTERVIEW_AI_PROVIDER": "openai"}, {"INTERVIEW_AI_PROVIDER": "unknown"}):
        with pytest.raises(ProviderFailure, match="CONFIGURATION"):
            select_provider(env)
    with pytest.raises(ProviderFailure):
        OpenAISettings(max_output_tokens=999999)
    provider = select_provider(
        {
            "INTERVIEW_AI_PROVIDER": "openai",
            "INTERVIEW_OPENAI_ENABLED": "true",
            "INTERVIEW_OPENAI_EFFORT": "medium",
            "INTERVIEW_REGION": "ap-northeast-1",
        }
    )
    assert provider.settings.effort == "medium"
    with pytest.raises(ProviderFailure, match="AUTHENTICATION"):
        provider.evaluate(build_coaching_prompt(context()))


def start(runtime, owner="owner", number=1):
    from conftest import uid

    app = runtime.application
    sid = app.create(
        owner,
        uid(100 + number),
        {"mode": "category", "category": "career", "difficulty": "standard"},
    ).body["sessionId"]
    qid = app.question(owner, sid).body["question"]["id"]
    return app.submit(
        owner,
        uid(200 + number),
        sid,
        {
            "kind": "initial_answer",
            "questionId": qid,
            "answer": "提案しました。",
        },
    ).body["evaluationId"]


def test_worker_duplicate_delivery_and_monthly_usage_cap(runtime):
    transport = Transport()
    provider = OpenAIProvider(
        Authentication(), transport=transport, settings=OpenAISettings(monthly_user_limit=1)
    )
    worker = Worker(runtime.repository, provider, runtime.worker.clock)
    first = start(runtime)
    assert worker.run("owner", first)
    assert worker.run("owner", first) is False
    second = start(runtime, number=2)
    assert worker.run("owner", second)
    assert len(transport.requests) == 1
    assert runtime.repository.snapshot().evaluations[second].failure_reason == "PREPARATION_FAILED"
    other = start(runtime, owner="other", number=3)
    assert worker.run("other", other)
    assert len(transport.requests) == 2
    usage = runtime.repository.snapshot().provider_usage.values()
    assert len([r for r in usage if r.owner != "@ai-global-budget"]) == 2


@pytest.mark.parametrize("kind", ["TIMEOUT", "NETWORK", "OUTCOME_UNKNOWN"])
def test_ambiguous_failure_never_recalled(runtime, kind):
    transport = Transport(error=ProviderFailure(kind, uncertain=True))
    worker = Worker(
        runtime.repository,
        OpenAIProvider(Authentication(), transport=transport),
        runtime.worker.clock,
    )
    eid = start(runtime)
    assert worker.run("owner", eid)
    assert runtime.repository.snapshot().evaluations[eid].failure_reason == "OUTCOME_UNKNOWN"
    assert worker.run("owner", eid) is False
    assert len(transport.requests) == 1


def test_wif_explicit_exchange_offline():
    transport = Transport(
        {"token_type": "Bearer", "access_token": "offline-placeholder", "expires_at": 500}
    )
    observed = []

    def token(**kwargs):
        observed.append(kwargs)
        return {"WebIdentityToken": "offline-subject-placeholder"}

    auth = AWSFederation(
        "ap-northeast-1",
        "idp-offline",
        "sa-offline",
        client_factory=lambda _: SimpleNamespace(get_web_identity_token=token),
        transport=transport,
        wall_clock=lambda: 0,
    )
    assert auth.token(Deadline(40, lambda: 0)) == "offline-placeholder"
    assert observed == [
        {
            "Audience": ["https://api.openai.com/v1"],
            "SigningAlgorithm": "ES384",
            "DurationSeconds": 300,
        }
    ]
    assert transport.requests[0][:2] == ("auth.openai.com", "/oauth/token")
    assert transport.requests[0][2]["subject_token_type"].endswith(":jwt")
    assert "offline-placeholder" not in repr(auth)


def test_secret_explicit_not_fallback_and_expiry():
    auth = SecretAuthentication("ap-northeast-1", "invalid")
    with pytest.raises(ProviderFailure, match="AUTHENTICATION"):
        auth.token(Deadline(40, lambda: 0))
    transport = Transport(
        {"token_type": "bearer", "access_token": "offline-placeholder", "expires_at": 1}
    )
    auth = AWSFederation(
        "ap-northeast-1",
        "idp",
        "sa",
        client_factory=lambda _: SimpleNamespace(
            get_web_identity_token=lambda **_: {"WebIdentityToken": "offline-subject-placeholder"}
        ),
        transport=transport,
        wall_clock=lambda: 0,
    )
    with pytest.raises(ProviderFailure, match="AUTHENTICATION"):
        auth.token(Deadline(40, lambda: 0))


def test_v1_nullable_example_preserves_public_contract(runtime):
    value = {
        "score": 78,
        "summary": "回答",
        "strengths": ["結論"],
        "improvements": ["具体性"],
        "exampleAnswer": None,
    }
    prompt = build_prompt(runtime.application.questions[0], "本人回答")
    provider = OpenAIProvider(Authentication(), transport=Transport(response(value)))
    actual = provider.evaluate(prompt)
    assert actual == {k: v for k, v in value.items() if k != "exampleAnswer"}
    assert schema_for(prompt)["properties"]["exampleAnswer"]["type"] == ["string", "null"]


def test_transport_endpoint_allowlist():
    with pytest.raises(ProviderFailure, match="CONFIGURATION"):
        HTTPTransport().post("example.com", "/v1/responses", {}, {}, Deadline(40, lambda: 0))
