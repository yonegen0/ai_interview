"""Real adapter wire/grounding/deadline tests; all transports are offline stubs."""

import json
from copy import deepcopy
from types import SimpleNamespace

import boto3
import pytest
from botocore.exceptions import ReadTimeoutError
from botocore.validate import validate_parameters

from interview_backend.evaluation.bedrock_provider import BedrockProvider
from interview_backend.evaluation.openai_provider import Deadline, OpenAIProvider, ProviderFailure
from interview_backend.star_assist.live_provider import LiveStarProvider, select_star_provider
from interview_backend.star_assist.models import StarInput


def value():
    return StarInput(
        notes={
            "S": "顧客に課題があった。",
            "T": "整理を担当した。",
            "A": "課題を共有した。",
            "R": "改善しなかった。",
        },
        targetCategory="corporate_sales",
        industry="製造",
        company="応募先",
        candidates=[],
        selectedCandidateId=None,
        generationId=None,
    )


def plan():
    return {
        "status": "ready",
        "candidates": [
            {"id": "A", "style": "conclusion", "fields": ["R", "S", "T", "A"]},
            {"id": "B", "style": "action", "fields": ["A", "S", "T", "R"]},
            {"id": "C", "style": "conversational", "fields": ["S", "T", "A", "R"]},
        ],
        "missingInformation": [],
    }


class Client:
    def __init__(self, body=None, stop="end_turn", error=None):
        self.raw = json.dumps(plan() if body is None else body)
        self.stop, self.error, self.calls, self.kwargs = stop, error, 0, None

    def converse(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return {
            "stopReason": self.stop,
            "output": {"message": {"role": "assistant", "content": [{"text": self.raw}]}},
        }


def adapter(client):
    return LiveStarProvider(BedrockProvider(client_factory=lambda *a, **k: client), mode="source")


def test_bedrock_sdk_shape_grounding_styles_and_independent_token_cap():
    client = Client()
    live = adapter(client)
    result = live.generate("経験は？", value())
    assert [c.id for c in result.candidates] == ["A", "B", "C"]
    assert all("改善しなかった。" in c.text for c in result.candidates)
    assert result.candidates[0].text.startswith("改善しなかった。")
    assert client.calls == 1
    request = client.kwargs
    assert request["modelId"] == "jp.anthropic.claude-haiku-5-5"
    assert request["inferenceConfig"] == {"maxTokens": 2048}
    assert request["additionalModelRequestFields"] == {
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "low"},
    }
    data = json.loads(request["messages"][0]["content"][0]["text"])
    assert data["industry"] == "製造" and data["targetCategory"] == "corporate_sales"
    # Actual installed botocore service model; construction uses only synthetic keys.
    sdk = boto3.client(
        "bedrock-runtime",
        region_name="ap-northeast-1",
        aws_access_key_id="synthetic",
        aws_secret_access_key="synthetic",
    )
    validate_parameters(request, sdk.meta.service_model.operation_model("Converse").input_shape)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(extra="invented"),
        lambda p: p["candidates"][0].update(text="売上を200%改善した"),
        lambda p: p["candidates"][0].update(fields=["R", "A"]),
        lambda p: p["candidates"][0].update(fields=["R", "S", "T", "A", "A"]),
        lambda p: p["candidates"][0].update(fields=["R", "S", "T", "invented"]),
        lambda p: p["candidates"][0].update(style="action"),
        lambda p: p["candidates"][0].update(fields=["S", "R", "T", "A"]),
        lambda p: p["candidates"].pop(),
        lambda p: p.pop("missingInformation"),
        lambda p: p.update(status="needs_information"),
    ],
)
def test_schema_and_semantic_rejection_no_retry(mutate):
    body = deepcopy(plan())
    mutate(body)
    client = Client(body)
    with pytest.raises(ProviderFailure, match="INVALID_SCHEMA"):
        adapter(client).generate("経験は？", value())
    assert client.calls == 1


@pytest.mark.parametrize("raw", ["{} garbage", '{"status":"ready","status":"ready"}', "NaN"])
def test_invalid_json_no_retry(raw):
    client = Client()
    client.raw = raw
    with pytest.raises(ProviderFailure):
        adapter(client).generate("経験は？", value())
    assert client.calls == 1


@pytest.mark.parametrize(
    "stop,kind",
    [
        ("max_tokens", "INCOMPLETE"),
        ("content_filtered", "REFUSAL"),
        ("guardrail_intervened", "REFUSAL"),
        ("tool_use", "OUTPUT_MISSING"),
    ],
)
def test_refusal_and_incomplete(stop, kind):
    client = Client(stop=stop)
    with pytest.raises(ProviderFailure, match=kind):
        adapter(client).generate("経験は？", value())
    assert client.calls == 1


def test_unknown_send_and_expired_deadline_do_not_replay():
    client = Client(error=ReadTimeoutError(endpoint_url="https://synthetic"))
    with pytest.raises(ProviderFailure) as exc:
        adapter(client).generate("経験は？", value())
    assert exc.value.uncertain and client.calls == 1
    client = Client()
    with pytest.raises(ProviderFailure, match="TIMEOUT"):
        adapter(client).generate_with_deadline("経験は？", value(), Deadline(34, lambda: 0))
    assert client.calls == 0


def test_missing_action_and_long_facts_ask_information_without_send():
    client = Client()
    live = adapter(client)
    for notes in (
        {"S": "状況", "T": "", "A": "", "R": ""},
        {"S": "", "T": "", "A": "あ" * 401, "R": ""},
    ):
        v = value().model_copy(update={"notes": value().notes.model_validate(notes)})
        assert live.generate("経験は？", v).status == "needs_information"
    assert client.calls == 0


def test_model_needs_information_and_full_input_size_cap():
    client = Client(
        {"status": "needs_information", "candidates": [], "missingInformation": ["本人の役割は？"]}
    )
    assert adapter(client).generate("経験は？", value()).status == "needs_information"
    assert client.calls == 1
    with pytest.raises(ProviderFailure, match="USAGE_LIMIT"):
        adapter(client).generate("q" * 25000, value())
    assert client.calls == 1


@pytest.mark.parametrize(
    "question",
    [
        "売上を200%改善した理由は何ですか？",
        "入力していない成果を達成した理由を説明してください。",
    ],
)
def test_source_mode_needs_information_never_uses_untrusted_model_question(question):
    client = Client(
        {"status": "needs_information", "candidates": [], "missingInformation": [question]}
    )
    result = adapter(client).generate("経験は？", value())
    assert result.status == "needs_information"
    assert not result.candidates
    assert result.missingInformation == [
        "入力根拠を保った表現を確認できませんでした。行動と結果を具体的にしてください。"
    ]
    assert client.calls == 1


@pytest.mark.parametrize("stop", ["end_turn", "max_tokens"])
def test_usage_survives_response_rejection_but_not_local_clarification(stop):
    client = Client(stop=stop)
    converse = client.converse

    def response(**kwargs):
        return {**converse(**kwargs), "usage": {"inputTokens": 123, "outputTokens": 45}}

    client.converse = response
    live = adapter(client)
    if stop == "end_turn":
        assert live.generate("経験は？", value()).status == "ready"
    else:
        with pytest.raises(ProviderFailure, match="INCOMPLETE"):
            live.generate("経験は？", value())
    assert live.last_observation == {"inputTokens": 123, "outputTokens": 45}
    missing = value().model_copy(update={"notes": value().notes.model_copy(update={"A": ""})})
    assert live.generate("経験は？", missing).status == "needs_information"
    assert live.last_observation is None and client.calls == 1
    with pytest.raises(ProviderFailure, match="TIMEOUT"):
        live.generate_with_deadline("経験は？", value(), Deadline(0, lambda: 1))
    assert live.last_observation is None and client.calls == 1


def test_no_implicit_fake_or_automatic_fallback():
    with pytest.raises(ProviderFailure, match="CONFIGURATION"):
        select_star_provider(SimpleNamespace(provider_id="unknown"))
    client = Client(error=RuntimeError("synthetic"))
    with pytest.raises(ProviderFailure, match="OUTCOME_UNKNOWN"):
        adapter(client).generate("経験は？", value())
    assert client.calls == 1


def test_manual_openai_reuses_transport_schema_and_star_cap():
    class Transport:
        calls = 0

        def post(self, host, path, payload, headers, deadline):
            self.calls += 1
            self.payload = payload
            return 200, json.dumps(
                {
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [{"type": "output_text", "text": json.dumps(plan())}],
                        }
                    ],
                }
            )

    transport = Transport()
    live = LiveStarProvider(
        OpenAIProvider(SimpleNamespace(token=lambda d: "synthetic"), transport=transport),
        mode="source",
    )
    assert live.generate("経験は？", value()).status == "ready"
    assert transport.calls == 1
    assert transport.payload["max_output_tokens"] == 2048
    assert transport.payload["text"]["format"]["strict"] is True
    assert transport.payload["model"] == "gpt-6-luna"
