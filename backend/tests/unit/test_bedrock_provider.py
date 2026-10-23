"""Bedrock JP Geo Provider contract tests using real app models; no network or AWS."""

import json
from time import monotonic
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError

from interview_backend.evaluation.bedrock_provider import (
    BedrockProvider,
    BedrockSettings,
)
from interview_backend.evaluation.openai_provider import Deadline, ProviderFailure
from interview_backend.evaluation.provider import (
    INSTRUCTIONS,
    PROMPT_VERSION,
    Prompt,
    build_coaching_prompt,
)
from interview_backend.models.public import CoachingInput, Question


class StubClient:
    def __init__(self, body=None, error=None):
        self.calls = 0
        self.arguments = None
        self.error = error
        self.body = (
            body
            if body is not None
            else {
                "stopReason": "end_turn",
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "text": json.dumps(
                                    {
                                        "score": 75,
                                        "summary": "業務内容を説明しています。",
                                        "strengths": ["説明が明確です。"],
                                        "improvements": ["行動の詳細が必要です。"],
                                    }
                                )
                            }
                        ],
                    }
                },
                "usage": {"inputTokens": 12, "outputTokens": 3},
            }
        )

    def converse(self, **kwargs):
        self.calls += 1
        self.arguments = kwargs
        if self.error is not None:
            raise self.error
        return self.body


def v1_prompt():
    return Prompt(
        PROMPT_VERSION,
        INSTRUCTIONS,
        "仕事内容を教えてください。",
        "experience",
        "具体性と根拠",
        "受注管理を担当しました。",
    )


def make_provider(client):
    return BedrockProvider(client_factory=lambda *args, **kwargs: client)


def test_v1_jp_geo_converse_output_and_single_call():
    client = StubClient()
    provider = make_provider(client)
    assert provider.evaluate(v1_prompt())["score"] == 75
    assert client.calls == 1
    assert client.arguments["modelId"] == "jp.anthropic.claude-haiku-5-5"
    assert client.arguments["additionalModelRequestFields"] == {
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "low"},
    }
    assert client.arguments["inferenceConfig"]["maxTokens"] == 2048
    assert provider.last_observation == {"inputTokens": 12, "outputTokens": 3}


def test_v2_completed_with_real_domain_contract():
    question = Question(
        id="00000000-0000-4000-8000-000000000001",
        category="experience",
        difficulty="standard",
        question="どんな仕事をしていますか。",
    )
    context = CoachingInput(
        question=question,
        initial_answer="配送の担当をしています。",
        coaching_history=(),
        latest_answer="配送の担当をしています。",
        coaching_count=0,
        can_ask_follow_up=True,
        unavailable_questions=(),
    )
    response = {
        "status": "completed",
        "conclusion_score": 8,
        "specificity_score": 8,
        "reasoning_score": 8,
        "good_point": "担当内容が明確です。",
        "improvement": "行動を具体化するとさらに伝わります。",
        "follow_up_question": None,
        "example": "配送の担当をしています。",
    }
    client = StubClient(
        body={
            "stopReason": "end_turn",
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"text": json.dumps(response, ensure_ascii=False)},
                    ],
                }
            },
        }
    )
    result = make_provider(client).evaluate(build_coaching_prompt(context))
    assert result["status"] == "completed"
    assert result["reasoning_score"] == 8
    assert client.calls == 1


@pytest.mark.parametrize(
    "text",
    [
        '{"score":75,"score":81}',
        '{"score":75,"summary":"ok","strengths":[],"improvements":[],"inject":1}',
        '{"score":NaN,"summary":"ok","strengths":[],"improvements":[]}',
        '```json\n{"score":75}\n```',
    ],
)
def test_strict_json_malformed_rejected_without_retry(text):
    client = StubClient(
        body={
            "stopReason": "end_turn",
            "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        }
    )
    with pytest.raises(ProviderFailure) as error:
        make_provider(client).evaluate(v1_prompt())
    assert error.value.kind in {"INVALID_JSON", "INVALID_SCHEMA"}
    assert client.calls == 1


@pytest.mark.parametrize(
    "environment",
    [
        {"INTERVIEW_BEDROCK_ENABLED": "true", "INTERVIEW_AI_PROVIDER": "openai"},
        {"INTERVIEW_BEDROCK_ENABLED": "false", "INTERVIEW_AI_PROVIDER": "bedrock"},
        {
            "INTERVIEW_BEDROCK_ENABLED": "true",
            "INTERVIEW_AI_PROVIDER": "bedrock",
            "INTERVIEW_BEDROCK_PROFILE_ID": "global.anthropic.claude-haiku-5-5",
        },
        {
            "INTERVIEW_BEDROCK_ENABLED": "true",
            "INTERVIEW_AI_PROVIDER": "bedrock",
            "INTERVIEW_OPENAI_ENABLED": "true",
        },
        {
            "INTERVIEW_BEDROCK_ENABLED": "true",
            "INTERVIEW_AI_PROVIDER": "bedrock",
            "INTERVIEW_BEDROCK_MAX_TOKENS": " 2048",
        },
        {
            "INTERVIEW_BEDROCK_ENABLED": "true",
            "INTERVIEW_AI_PROVIDER": "bedrock",
            "INTERVIEW_BEDROCK_EXTRA": "true",
        },
    ],
)
def test_invalid_configuration_rejected(environment):
    with pytest.raises(ProviderFailure) as error:
        BedrockSettings.from_environment(environment)
    assert error.value.kind == "CONFIGURATION"


def test_read_timeout_is_uncertain_and_never_retried():
    client = StubClient(
        error=ReadTimeoutError(endpoint_url="https://bedrock-runtime.ap-northeast-1.amazonaws.com")
    )
    with pytest.raises(ProviderFailure) as error:
        make_provider(client).evaluate(v1_prompt())
    assert error.value.kind == "TIMEOUT"
    assert error.value.uncertain is True
    assert client.calls == 1


def test_service_failure_is_uncertain_and_private_error_not_logged():
    client = StubClient(
        error=ClientError(
            {"Error": {"Code": "InternalServerException", "Message": "private candidate details"}},
            "Converse",
        )
    )
    with pytest.raises(ProviderFailure) as error:
        make_provider(client).evaluate(v1_prompt())
    assert error.value.kind == "SERVER_ERROR"
    assert error.value.uncertain is True
    assert "private" not in str(error.value)
    assert client.calls == 1


def test_output_cutoff_does_not_retry():
    client = StubClient(body={"stopReason": "max_tokens"})
    with pytest.raises(ProviderFailure) as error:
        make_provider(client).evaluate(v1_prompt())
    assert error.value.kind == "INCOMPLETE"
    assert client.calls == 1


def test_deadline_expiry_before_invocation():
    client = StubClient()
    with pytest.raises(ProviderFailure) as error:
        make_provider(client).evaluate_with_deadline(v1_prompt(), Deadline(monotonic() + 1.5))
    assert error.value.kind == "TIMEOUT"
    assert error.value.uncertain is False
    assert client.calls == 0


class ManualClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Events:
    def __init__(self):
        self.handlers = {}

    def register(self, name, handler, unique_id):
        self.handlers[unique_id] = handler

    def unregister(self, name, unique_id):
        self.handlers.pop(unique_id)


class HookClient:
    def __init__(self, clock, signing_delay=0):
        self.clock = clock
        self.signing_delay = signing_delay
        self.meta = SimpleNamespace(events=Events())
        self.wire_calls = 0

    def converse(self, **kwargs):
        self.clock.now += self.signing_delay
        for handler in tuple(self.meta.events.handlers.values()):
            handler()
        self.wire_calls += 1
        return StubClient().body


def test_factory_delay_does_not_send_with_half_second_remaining():
    clock = ManualClock()
    client = HookClient(clock)

    def factory(*args, **kwargs):
        clock.now += 39.5
        return client

    provider = BedrockProvider(client_factory=factory, clock=clock)
    with pytest.raises(ProviderFailure) as error:
        provider.evaluate_with_deadline(v1_prompt(), Deadline(40, clock))
    assert (error.value.kind, error.value.uncertain, client.wire_calls) == ("TIMEOUT", False, 0)


def test_before_send_guard_and_hook_lifecycle():
    clock = ManualClock()
    client = HookClient(clock, signing_delay=6)
    provider = BedrockProvider(client_factory=lambda *a, **k: client, clock=clock)
    with pytest.raises(ProviderFailure) as error:
        provider.evaluate_with_deadline(v1_prompt(), Deadline(40, clock))
    assert (error.value.kind, error.value.uncertain, client.wire_calls) == ("TIMEOUT", False, 0)
    assert not client.meta.events.handlers
    client.signing_delay = 0
    assert (
        provider.evaluate_with_deadline(v1_prompt(), Deadline(clock.now + 40, clock))["score"] == 75
    )
    assert client.wire_calls == 1
    assert not client.meta.events.handlers


@pytest.mark.parametrize("remaining,expected_calls", [(35, 1), (34.999, 0)])
def test_send_budget_boundary(remaining, expected_calls):
    clock = ManualClock()
    client = HookClient(clock)
    provider = BedrockProvider(client_factory=lambda *a, **k: client, clock=clock)
    if expected_calls:
        assert (
            provider.evaluate_with_deadline(v1_prompt(), Deadline(remaining, clock))["score"] == 75
        )
    else:
        with pytest.raises(ProviderFailure) as error:
            provider.evaluate_with_deadline(v1_prompt(), Deadline(remaining, clock))
        assert not error.value.uncertain
    assert client.wire_calls == expected_calls


def test_real_botocore_before_send_blocks_after_signing_delay():
    from botocore.config import Config
    from botocore.session import get_session

    clock = ManualClock()
    sent = []
    client = get_session().create_client(
        "bedrock-runtime",
        region_name="ap-northeast-1",
        aws_access_key_id="synthetic",
        aws_secret_access_key="synthetic",
        config=Config(retries={"total_max_attempts": 1}),
    )
    client.meta.events.register(
        "before-send.bedrock-runtime.Converse",
        lambda **_: setattr(clock, "now", clock.now + 6),
        unique_id="synthetic-signing-delay",
    )
    client._endpoint.http_session.send = lambda request: sent.append(request)
    provider = BedrockProvider(client_factory=lambda *a, **k: client, clock=clock)
    with pytest.raises(ProviderFailure) as error:
        provider.evaluate_with_deadline(v1_prompt(), Deadline(40, clock))
    assert (error.value.kind, error.value.uncertain, sent) == ("TIMEOUT", False, [])


@pytest.mark.parametrize(
    "stop,expected",
    [
        ("max_tokens", "INCOMPLETE"),
        ("guardrail_intervened", "REFUSAL"),
        ("content_filtered", "REFUSAL"),
        ("tool_use", "OUTPUT_MISSING"),
        ("stop_sequence", "OUTPUT_MISSING"),
        ("malformed_model_output", "OUTPUT_MISSING"),
        ("model_context_window_exceeded", "OUTPUT_MISSING"),
        ("future_reason", "OUTPUT_MISSING"),
    ],
)
def test_all_nonfinal_stop_reasons_are_terminal_without_retry(stop, expected):
    client = StubClient(body={"stopReason": stop})
    with pytest.raises(ProviderFailure) as error:
        make_provider(client).evaluate(v1_prompt())
    assert error.value.kind == expected
    assert client.calls == 1


@pytest.mark.parametrize(
    "blocks",
    [
        [{"text": "{}"}, {"text": "{}"}],
        [{"toolUse": {"toolUseId": "synthetic"}}],
        [{"reasoningContent": {"reasoningText": {"text": "synthetic"}}}],
        [{"futureBlock": "synthetic"}],
    ],
)
def test_invalid_content_union_never_retries(blocks):
    client = StubClient(
        body={
            "stopReason": "end_turn",
            "output": {"message": {"role": "assistant", "content": blocks}},
        }
    )
    with pytest.raises(ProviderFailure):
        make_provider(client).evaluate(v1_prompt())
    assert client.calls == 1


def test_sdk_retry_setting_counts_initial_attempt_only():
    captured = []
    client = StubClient()
    provider = BedrockProvider(
        client_factory=lambda *args, **kwargs: captured.append(kwargs["config"]) or client
    )
    assert provider.evaluate(v1_prompt())["score"] == 75
    assert captured[0].retries["total_max_attempts"] == 1
    assert (captured[0].connect_timeout, captured[0].read_timeout) == (3, 30)
