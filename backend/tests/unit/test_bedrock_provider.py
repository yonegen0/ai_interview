"""Offline Bedrock Converse contract tests; zero real model or IAM calls."""

import json
from types import SimpleNamespace

import pytest

from interview_backend.assets import load_questions
from interview_backend.evaluation.bedrock_provider import (
    MODEL,
    BedrockProvider,
    BedrockSettings,
)
from interview_backend.evaluation.openai_provider import Deadline, ProviderFailure
from interview_backend.evaluation.provider import FakeProvider, build_coaching_prompt, build_prompt
from interview_backend.evaluation.selection import checked_provider_environment, select_provider
from interview_backend.models.public import CoachingInput


def coaching_input():
    return CoachingInput(
        question=load_questions()[0],
        initial_answer="提案しました。",
        coaching_history=(),
        latest_answer="提案しました。",
        coaching_count=0,
        can_ask_follow_up=True,
        unavailable_questions=(),
    )


def coaching_result(status="completed"):
    return dict(
        status=status,
        conclusion_score=8,
        specificity_score=8,
        reasoning_score=8,
        good_point="結論が明確です。",
        improvement="行動の具体化が必要です。",
        follow_up_question="どんな行動をしましたか？" if status == "coaching" else None,
        example=None if status == "coaching" else "提案しました。",
    )


def response(text=None, *, stop="end_turn"):
    if text is None:
        text = json.dumps(coaching_result(), ensure_ascii=False)
    return {
        "stopReason": stop,
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "usage": {"inputTokens": 120, "outputTokens": 50},
    }


class Client:
    def __init__(self, value=None, error=None):
        self.value = response() if value is None else value
        self.error = error
        self.calls = []

    def converse(self, **request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return self.value


def provider(client):
    return BedrockProvider(client=client, settings=BedrockSettings(effort="low"))


def test_default_bedrock_and_explicit_fake_only():
    assert select_provider({}).model_id == MODEL
    assert select_provider({"INTERVIEW_AI_PROVIDER": "bedrock"}).model_id == MODEL
    assert isinstance(select_provider({"INTERVIEW_AI_PROVIDER": "fake"}), FakeProvider)
    assert select_provider({"INTERVIEW_AI_PROVIDER": "bedrock"}).provider_id.startswith("bedrock:")
    for env in ({"INTERVIEW_AI_PROVIDER": "auto"}, {"INTERVIEW_AI_PROVIDER": "openai"}):
        with pytest.raises(ProviderFailure):
            select_provider(env)


def test_japan_profile_and_bounded_single_converse_call():
    client = Client()
    ai = provider(client)
    result = ai.evaluate(build_coaching_prompt(coaching_input()))
    assert result == coaching_result()
    assert len(client.calls) == 1
    request = client.calls[0]
    assert request["modelId"] == "jp.anthropic.claude-haiku-5-5"
    assert request["inferenceConfig"] == {"maxTokens": 2048}
    assert request["additionalModelRequestFields"]["thinking"] == {"type": "disabled"}
    assert request["additionalModelRequestFields"]["output_config"] == {"effort": "low"}
    assert request["messages"][0]["role"] == "user"
    assert "提案しました。" in request["messages"][0]["content"][0]["text"]
    assert ai.last_observation == {"inputTokens": 120, "outputTokens": 50}


@pytest.mark.parametrize(
    "bad_response,kind",
    [
        (response(stop="max_tokens"), "INCOMPLETE"),
        (response(stop="guardrail_intervened"), "REFUSAL"),
        (response(text="not json"), "INVALID_JSON"),
        (response(text='{"status":"completed"}'), "INVALID_SCHEMA"),
        (response(text=json.dumps({**coaching_result(), "extra": "invalid"})), "INVALID_SCHEMA"),
        (response(text=json.dumps({**coaching_result(), "conclusion_score": 11})), "INVALID_SCHEMA"),
        ({"stopReason": "end_turn", "output": {"message": {"content": [{"text": "{}"}, {"text": "{}"}]}}}, "OUTPUT_MISSING"),
        ({"stopReason": "end_turn", "output": {"message": {"content": [{"toolUse": {}}]}}}, "OUTPUT_MISSING"),
        ({}, "REFUSAL"),
    ],
)
def test_fail_closed_on_invalid_or_partial_model_response(bad_response, kind):
    client = Client(value=bad_response)
    with pytest.raises(ProviderFailure) as info:
        provider(client).evaluate(build_coaching_prompt(coaching_input()))
    assert info.value.kind == kind
    assert len(client.calls) == 1


def test_single_followup_and_no_invented_fallback():
    client = Client(value=response(json.dumps(coaching_result("coaching"), ensure_ascii=False)))
    result = provider(client).evaluate(build_coaching_prompt(coaching_input()))
    assert result["status"] == "coaching"
    assert len(client.calls) == 1
    broken = Client(error=OSError("no network and no provider fallback"))
    with pytest.raises(ProviderFailure) as info:
        provider(broken).evaluate(build_coaching_prompt(coaching_input()))
    assert info.value.kind == "OUTCOME_UNKNOWN"
    assert info.value.uncertain
    assert len(broken.calls) == 1


def test_invalid_settings_and_foreign_region_are_rejected():
    for kwargs in (
        {"effort": "xhigh"},
        {"max_output_tokens": 0},
        {"monthly_user_limit": 0},
        {"monthly_global_limit": True},
    ):
        with pytest.raises(ProviderFailure):
            BedrockSettings(**kwargs)
    with pytest.raises(ProviderFailure):
        BedrockProvider(region="us-east-1", client=Client())
    with pytest.raises(ValueError):
        checked_provider_environment(
            {"INTERVIEW_AI_PROVIDER": "bedrock", "INTERVIEW_OPENAI_ENABLED": "true"},
            "123456789012",
            "ap-northeast-1",
        )
    with pytest.raises(ValueError):
        checked_provider_environment(
            {"INTERVIEW_AI_PROVIDER": "bedrock", "INTERVIEW_BEDROCK_MAX_OUTPUT_TOKENS": "oops"},
            "123456789012",
            "ap-northeast-1",
        )
    assert checked_provider_environment(
        {"INTERVIEW_AI_PROVIDER": "bedrock", "INTERVIEW_BEDROCK_EFFORT": "medium"},
        "123456789012",
        "ap-northeast-1",
    )["INTERVIEW_AI_PROVIDER"] == "bedrock"


def test_deadline_expires_before_request():
    client = Client()
    with pytest.raises(ProviderFailure) as info:
        provider(client).evaluate_with_deadline(
            build_coaching_prompt(coaching_input()), Deadline(0, lambda: 1)
        )
    assert info.value.kind == "TIMEOUT"
    assert not client.calls


def test_v1_prompt_still_routes_without_new_contract():
    client = Client(
        response(
            json.dumps(
                {
                    "score": 78,
                    "summary": "回答できています。",
                    "strengths": ["結論がある"],
                    "improvements": ["理由を補う"],
                    "exampleAnswer": None,
                },
                ensure_ascii=False,
            )
        )
    )
    ai = provider(client)
    prompt = build_prompt(load_questions()[0], "提案しました。")
    result = ai.evaluate(prompt)
    assert result["score"] == 78
    assert len(client.calls) == 1
