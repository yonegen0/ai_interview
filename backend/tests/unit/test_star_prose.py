"""Prose-v5 natural generation and bounded recovery; no paid AI tests."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from botocore.exceptions import ReadTimeoutError

from interview_backend.evaluation.bedrock_provider import BedrockProvider
from interview_backend.evaluation.openai_provider import Deadline, OpenAIProvider, ProviderFailure
from interview_backend.star_assist.live_provider import (
    ASSIST_COMMON_INSTRUCTIONS,
    PROSE_V5_INSTRUCTIONS,
    LiveStarProvider,
)
from interview_backend.star_assist.models import StarInput

STYLES = (("A", "conclusion"), ("B", "action"), ("C", "conversational"))


def value(**notes):
    return StarInput(
        notes={field: notes.get(field, "") for field in "STAR"},
        targetCategory="corporate_sales",
        industry="",
        company="",
        candidates=[],
        selectedCandidateId=None,
        generationId=None,
    )


def reply(data):
    facts = data["notes"]
    orders = ("RSTA", "ASTR", "STAR")
    return {
        "status": "ready",
        "candidates": [
            {
                "id": identifier,
                "style": style,
                "text": "。".join(
                    facts[field].strip("。") for field in order if facts[field].strip()
                )
                + "。",
            }
            for (identifier, style), order in zip(STYLES, orders, strict=True)
        ],
        "missingInformation": [],
    }


class Client:
    def __init__(self, mutate=None, error=None, clock=None):
        self.mutate, self.error, self.clock = mutate, error, clock
        self.calls = 0

    def converse(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        self.data = json.loads(kwargs["messages"][0]["content"][0]["text"])
        if self.error:
            raise self.error
        body = reply(self.data)
        if self.mutate:
            self.mutate(body)
        if self.clock is not None:
            self.clock[0] = 41
        return {
            "stopReason": "end_turn",
            "output": {"message": {"role": "assistant", "content": [{"text": json.dumps(body)}]}},
        }


def live(client, *, clock=None):
    kwargs = {} if clock is None else {"clock": lambda: clock[0]}
    return LiveStarProvider(BedrockProvider(client_factory=lambda *args, **kw: client, **kwargs))


def sample():
    return value(
        S="顧客の売上が伸び悩んでいた。",
        T="売上改善が課題だった。",
        A="売場の配置を変えた。",
        R="改善は未確認だった。",
    )


def test_natural_prose_v5_preserves_direct_model_text_with_unlisted_action():
    client = Client()
    provider = live(client)
    result = provider.generate("工夫したことは？", sample())
    assert provider.provider_id.endswith(":prose-v5:4096:24000")
    assert provider.last_prompt_version == "star_prose_v5"
    assert not provider.last_fallback_used and provider.last_reason_code is None
    assert [c.model_dump() for c in result.candidates] == reply(client.data)["candidates"]
    assert len({c.text for c in result.candidates}) == 3
    assert client.calls == 1
    assert client.kwargs["inferenceConfig"] == {"maxTokens": 4096}
    assert "完成文章3案" in PROSE_V5_INSTRUCTIONS
    assert "なぜその行動" in PROSE_V5_INSTRUCTIONS


@pytest.mark.parametrize(
    "operation_kind, expected",
    [
        ("initial_answer", [250, 330]),
        ("retry_attempt", [250, 330]),
        ("coaching_answer", [150, 220]),
    ],
)
def test_operation_length_targets_are_guidance_only(operation_kind, expected):
    client = Client()
    result = live(client).generate("経験は？", sample(), operation_kind=operation_kind)
    assert result.status == "ready"
    assert client.data["lengthTarget"] == expected


def test_partial_candidate_is_preserved_and_only_missing_one_is_restored():
    def mutate(body):
        body["candidates"][0]["text"] = "私は売場の配置を変えた。"
        body["candidates"][1]["text"] = "売場の配置を変えたことで課題に向き合った。"
        body["candidates"].pop()

    provider = live(Client(mutate))
    result = provider.generate("経験は？", sample())
    assert result.status == "ready"
    assert [c.text for c in result.candidates[:2]] == [
        "私は売場の配置を変えた。",
        "売場の配置を変えたことで課題に向き合った。",
    ]
    assert "配置を変えた" in result.candidates[2].text
    assert provider.last_fallback_used
    assert provider.last_reason_code == "MODEL_STRUCTURE_MISMATCH"


def test_out_of_order_candidates_are_reordered_not_discarded():
    def mutate(body):
        body["candidates"] = list(reversed(body["candidates"]))

    provider = live(Client(mutate))
    result = provider.generate("経験は？", sample())
    assert [c.text for c in result.candidates] == [
        entry["text"] for entry in reply({"notes": sample().notes.model_dump()})["candidates"]
    ]
    assert not provider.last_fallback_used
    assert provider.last_reason_code == "MODEL_STRUCTURE_MISMATCH"


def test_unique_style_mismatch_is_corrected_without_rewriting_prose():
    def mutate(body):
        body["candidates"][1]["style"] = "conclusion"

    provider = live(Client(mutate))
    result = provider.generate("経験は？", sample())
    assert result.candidates[1].style == "action"
    assert result.candidates[1].text.startswith("売場の配置を変えた")
    assert not provider.last_fallback_used
    assert provider.last_reason_code == "MODEL_STRUCTURE_MISMATCH"


def test_duplicated_id_does_not_adopt_ambiguous_candidates():
    def mutate(body):
        body["candidates"].insert(1, deepcopy(body["candidates"][0]))

    provider = live(Client(mutate))
    result = provider.generate("経験は？", sample())
    assert result.status == "ready" and provider.last_fallback_used
    assert result.candidates[0].text.startswith("結果については、")
    assert result.candidates[1].text.startswith("売場の配置を変えた")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r["candidates"][0].update(text=""),
        lambda r: r["candidates"][0].update(text="あ" * 601),
        lambda r: r["candidates"][0].update(text="売上を200%改善しました。"),
        lambda r: r["candidates"][0].update(extra="untrusted"),
    ],
)
def test_invalid_candidate_or_schema_never_becomes_unchecked_answer(mutate):
    provider = live(Client(mutate))
    result = provider.generate("経験は？", sample())
    assert result.status == "ready" and provider.last_fallback_used
    assert all(c.text.strip() and len(c.text) <= 600 for c in result.candidates)
    assert all("200%" not in c.text for c in result.candidates)


def test_missing_information_key_does_not_discard_safe_ready_candidates():
    def mutate(body):
        body.pop("missingInformation")

    provider = live(Client(mutate))
    result = provider.generate("経験は？", sample())
    assert result.status == "ready"
    assert [c.text for c in result.candidates] == [
        entry["text"] for entry in reply({"notes": sample().notes.model_dump()})["candidates"]
    ]
    assert provider.last_fallback_used is False
    assert provider.last_reason_code == "INVALID_SCHEMA"


def test_missing_information_key_keeps_only_safe_candidates():
    def mutate(body):
        body.pop("missingInformation")
        body["candidates"][0]["text"] = "私は売場の配置を変えた。"
        body["candidates"][1]["text"] = "売場の配置を見直した。"
        body["candidates"][2]["text"] = "売上を200%改善しました。"

    provider = live(Client(mutate))
    result = provider.generate("経験は？", sample())
    assert [c.text for c in result.candidates[:2]] == [
        "私は売場の配置を変えた。",
        "売場の配置を見直した。",
    ]
    assert provider.last_fallback_used
    assert provider.last_reason_code == "INVALID_SCHEMA"
    assert "200%" not in result.candidates[2].text


def test_model_clarification_uses_safe_fallback_once():
    def mutate(body):
        body.update(
            status="needs_information",
            candidates=[],
            missingInformation=["売上が200%伸びた理由は？"],
        )

    client = Client(mutate)
    provider = live(client)
    result = provider.generate("経験は？", sample())
    assert result.status == "ready" and len(result.candidates) == 3
    assert "200%" not in str(result.model_dump())
    assert provider.last_reason_code == "MODEL_REQUESTED_INFORMATION"
    assert provider.last_fallback_used and client.calls == 1


@pytest.mark.parametrize(
    "notes",
    [
        {"A": "", "S": "状況があった。"},
        {"A": "記録を共有した。", "R": "記録を共有しなかった。"},
        {"A": "あ" * 601},
    ],
)
def test_empty_action_contradiction_and_input_limit_no_paid_send(notes):
    client = Client()
    result = live(client).generate("経験は？", value(**notes))
    assert result.status == "needs_information"
    assert client.calls == 0


def test_new_or_reversed_numbers_are_rejected_without_changing_safe_candidates():
    sample_input = value(
        S="山崎製パンでスーパー向けの法人営業を担当した。",
        T="売上改善と販管費削減の両立が課題だった。",
        A="販売実績の低い商品の削減を提案した。",
        R="取扱商品を120品から95品に削減し、前年比98％から103％に改善した。",
    )

    def mutate(body):
        body["candidates"][0]["text"] = "取扱商品を95品から120品に変更しました。"
        body["candidates"][1]["text"] = "取扱商品を120品から94品に削減しました。"
        body["candidates"][2]["text"] = (
            "取扱商品を120品から95品に削減し、前年比98％から103％になりました。"
        )

    provider = live(Client(mutate))
    result = provider.generate("経験は？", sample_input)
    assert result.status == "ready" and provider.last_fallback_used
    assert result.candidates[0].text != "取扱商品を95品から120品に変更しました。"
    assert "94品" not in str(result.model_dump())
    assert result.candidates[2].text.startswith("取扱商品を120品")
    assert provider.last_reason_code == "MODEL_STRUCTURE_MISMATCH"


@pytest.mark.parametrize(
    "text, rejected",
    [
        ("取扱商品を120品から95品に削減しました。", False),
        ("取扱商品を120品→95品に削減しました。", False),
        ("取扱商品を120品から98品に変更しました。", True),
        ("前年比98％から103％に改善しました。", False),
        ("前年比95％から103％に改善しました。", True),
        ("取扱商品を1,200件から950件に削減しました。", False),
        ("120品に絞り、前年比103％でした。", False),
    ],
)
def test_explicit_numeric_relationships_only_reject_clear_mispairing(text, rejected):
    from interview_backend.star_assist.prose_v5 import _unsafe_claim

    facts = {
        "S": "",
        "T": "",
        "A": "商品の配置を変えた。",
        "R": "取扱商品120品から95品、前年比98％から103％。件数1,200件から950件。",
    }
    assert _unsafe_claim(text, facts) is rejected


@pytest.mark.parametrize(
    "action,missing",
    [
        ("", True),
        ("　 ", True),
        ("特になし。", True),
        ("何もしていない", True),
        ("一切行っていない", True),
        ("行動は不明", True),
        ("売場を見直した。", False),
        ("顧客の希望を聞いた。", False),
        ("最初は何もしていない状態でしたが、その後売場を見直しました。", False),
    ],
)
def test_action_checks_reject_only_unambiguous_whole_field_non_action(action, missing):
    from interview_backend.star_assist.prose_v5 import missing_action

    assert missing_action({"A": action}) is missing


def test_non_action_clarification_does_not_call_paid_transport():
    client = Client()
    provider = live(client)
    result = provider.generate("経験は？", value(A="特になし", R="改善した。"))
    assert result.status == "needs_information"
    assert provider.last_reason_code == "INPUT_ACTION_MISSING"
    assert client.calls == 0


def test_action_with_negative_intro_is_not_preemptively_blocked():
    client = Client()
    provider = live(client)
    result = provider.generate(
        "経験は？", value(A="最初は何もしていない状態でしたが、その後売場を見直しました。")
    )
    assert result.status == "ready"
    assert client.calls == 1


def test_obvious_negation_flip_is_rejected():
    def mutate(body):
        body["candidates"][0]["text"] = "売上が改善しました。"

    provider = live(Client(mutate))
    result = provider.generate("経験は？", value(A="記録を確認した。", R="売上が改善しなかった。"))
    assert provider.last_fallback_used
    assert "売上が改善しました。" not in result.candidates[0].text


def test_yamazaki_bakery_three_meaningfully_distinct_structured_prose():
    case = value(
        S="・山崎製パンでスーパー向けの法人営業を担当\n・取引先ではパンの売上が伸び悩んでいた",
        T="・売上改善と販管費削減の両立が課題だった",
        A="・販売実績の低い商品が売場を占めていることにも着目\n・販売実績の低い商品の削減を提案",
        R="・取扱商品を120品から95品に削減\n・取引先のパン全体の販売金額が前年比98％から103％に改善",
    )
    texts = [
        "取扱商品を120品から95品に削減し、パンの販売金額の前年比が98％から103％に改善しました。山崎製パンでスーパー向け営業を担当した際、売上と販管費の両立が課題でした。私は販売実績の低い商品に着目し、削減を提案しました。",
        "売上改善に向けて私が着目したのは、販売実績の低い商品が売場を占めていたことです。山崎製パンで法人営業を担当し、売上と販管費の両立が求められる中、取扱商品の削減を提案しました。その結果、120品から95品になり、販売金額の前年比も98％から103％に改善しました。",
        "山崎製パンでスーパー向けの営業をしていたとき、取引先のパンの売上が伸び悩んでいました。売上と販管費の両立が課題だったため、実績の低い商品に注目して削減を提案しました。取扱商品は120品から95品となり、パン全体の前年比は98％から103％に改善しました。",
    ]

    def mutate(body):
        for item, text in zip(body["candidates"], texts, strict=True):
            item["text"] = text

    provider = live(Client(mutate))
    result = provider.generate("工夫と成果を教えてください", case)
    assert result.status == "ready" and not provider.last_fallback_used
    assert [c.text for c in result.candidates] == texts
    assert len({c.text.split("。")[0] for c in result.candidates}) == 3
    assert all(len(c.text) <= 600 for c in result.candidates)
    assert all("120品から95品" in c.text and "98％から103％" in c.text for c in result.candidates)
    assert all("販管費削減を達成" not in c.text for c in result.candidates)


def test_provider_transport_outcome_unknown_never_fallbacks():
    client = Client(error=ReadTimeoutError(endpoint_url="https://synthetic"))
    with pytest.raises(ProviderFailure) as error:
        live(client).generate("経験は？", sample())
    assert error.value.uncertain and client.calls == 1


def test_result_after_deadline_does_not_get_persisted_as_success():
    clock = [0]
    client = Client(clock=clock)
    with pytest.raises(ProviderFailure, match="TIMEOUT"):
        live(client, clock=clock).generate("経験は？", sample())
    assert client.calls == 1
    with pytest.raises(ProviderFailure, match="TIMEOUT"):
        live(Client()).generate_with_deadline("経験は？", sample(), Deadline(0, lambda: 1))


def test_source_mode_remains_available_and_legacy_provider_ids_are_recognized():
    from interview_backend.star_assist.live_provider import PROVIDER_IDS
    from interview_backend.star_assist.models import StarGeneration
    from interview_backend.star_assist.storage import validate_star

    provider = live(Client())
    for version in ("grounded-v1", "prose-v2", "prose-v3", "prose-v4", "prose-v5"):
        legacy = provider.provider_id.replace(":prose-v5:", f":{version}:")
        assert legacy in PROVIDER_IDS
        record = StarGeneration(
            owner="owner",
            id="gen",
            context_id="ctx",
            star_draft_id="draft",
            input=sample(),
            question="経験は？",
            month="2026-11",
            created_at=0,
            deadline_at=100000,
            provider_id=legacy,
        )
        validate_star(record)
    assert ":grounded-v1:" in LiveStarProvider(BedrockProvider(), mode="source").provider_id


def test_manual_openai_natural_transport_stays_strict_and_single_call():
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
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        reply(json.loads(payload["input"][1]["content"]))
                                    ),
                                }
                            ],
                        }
                    ],
                }
            )

    transport = Transport()
    provider = LiveStarProvider(
        OpenAIProvider(SimpleNamespace(token=lambda _: "synthetic"), transport=transport)
    )
    result = provider.generate("経験は？", sample())
    assert result.status == "ready" and transport.calls == 1
    assert transport.payload["text"]["format"]["name"] == "star_prose_v5"
    assert transport.payload["text"]["format"]["strict"] is True
    assert transport.payload["max_output_tokens"] == 4096


@pytest.mark.parametrize("mode", ["prep", "motivation", "career_change", "career_plan"])
def test_other_assist_prompt_version_v3_is_reported(mode):
    from interview_backend.operational_logs import invocation_context, log_event

    class AssistClient(Client):
        def converse(self, **kwargs):
            self.calls += 1
            self.kwargs = kwargs
            return {
                "stopReason": "end_turn",
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "text": json.dumps(
                                    {"answer": "確認しました。", "missingInformation": []}
                                )
                            }
                        ],
                    }
                },
            }

    client = AssistClient()
    provider = live(client)
    data = StarInput.model_validate({**value(S="確認した。").model_dump(), "assistType": mode})
    result = provider.generate("経験は？", data)
    assert result.status == "ready" and len(result.candidates) == 1
    assert provider.last_prompt_version == "answer_assist_v3"
    assert client.kwargs["inferenceConfig"] == {"maxTokens": 2048}
    output = []
    with invocation_context("worker", "test", {}, None):
        log_event(
            "assist_generation_terminal",
            sink=output.append,
            promptVersion=provider.last_prompt_version,
        )
        log_event(
            "assist_generation_terminal", sink=output.append, promptVersion="answer_assist_v2"
        )
    assert [json.loads(record)["promptVersion"] for record in output] == [
        "answer_assist_v3",
        "answer_assist_v2",
    ]


def test_other_assist_prompts_keep_contract_and_editing_goals():
    assert "500 UTF-16コード単位以内" in ASSIST_COMMON_INSTRUCTIONS
    assert "強み" in ASSIST_COMMON_INSTRUCTIONS
    assert "具体的行動" in ASSIST_COMMON_INSTRUCTIONS
    assert "脚色" not in ASSIST_COMMON_INSTRUCTIONS
