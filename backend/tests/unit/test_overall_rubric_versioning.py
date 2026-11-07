"""Offline compatibility tests for versioned 30-point overall coaching scoring."""

import json
from dataclasses import replace

import pytest
from conftest import uid

from interview_backend.evaluation.openai_provider import schema_for
from interview_backend.evaluation.provider import (
    COACHING_INSTRUCTIONS,
    COACHING_PROMPT_VERSION,
    FOLLOWUP_PROMPT_VERSION,
    OVERALL_RUBRIC_PROMPT_VERSION,
    build_coaching_prompt,
)
from interview_backend.repositories.codec import decode, encode


def begin(runtime):
    app = runtime.application
    sid = app.create(
        "owner", uid(650), {"mode": "category", "category": "job_change", "difficulty": "standard"}
    ).body["sessionId"]
    qid = app.question("owner", sid).body["question"]["id"]
    accepted = app.submit(
        "owner",
        uid(651),
        sid,
        {"kind": "initial_answer", "questionId": qid, "answer": "営業に挑戦したいです。"},
    ).body
    return sid, qid, accepted


def overall(question=None):
    return {
        "status": "coaching" if question else "completed",
        "conclusion_score": 8,
        "specificity_score": 7,
        "reasoning_score": 8,
        "good_point": "志望する仕事が明確です。",
        "improvement": "転職を決めた具体的な理由を補足すると伝わります。",
        "follow_up_question": question,
        "example": None if question else "営業に挑戦したいです。",
    }


def answer_followup(runtime, sid, qid, initial):
    return runtime.application.submit(
        "owner",
        uid(652),
        sid,
        {
            "kind": "coaching_answer",
            "questionId": qid,
            "attemptId": initial["attemptId"],
            "fromEvaluationId": initial["evaluationId"],
            "answer": "顧客の利用状況を聞き、自分で集荷を提案しました。",
        },
    ).body


@pytest.mark.parametrize("new_rubric", [False, True])
@pytest.mark.parametrize("dedicated_review", [False, True])
def test_four_scoring_combinations_keep_one_call_and_schema(
    runtime, new_rubric, dedicated_review
):
    runtime.repository.coaching_overall_rubric_v2_enabled = new_rubric
    runtime.repository.coaching_review_enabled = dedicated_review
    sid, qid, initial = begin(runtime)
    expected = OVERALL_RUBRIC_PROMPT_VERSION if new_rubric else COACHING_PROMPT_VERSION
    initial_job = runtime.repository.snapshot().evaluations[initial["evaluationId"]]
    assert initial_job.overall_prompt_version == (expected if new_rubric else None)
    runtime.provider.behavior = lambda prompt: overall("そのとき何をしましたか？")
    assert runtime.worker.run("owner", initial["evaluationId"])
    answered = answer_followup(runtime, sid, qid, initial)
    job = runtime.repository.snapshot().evaluations[answered["evaluationId"]]
    assert job.overall_prompt_version == initial_job.overall_prompt_version
    assert job.review_prompt_version == (
        FOLLOWUP_PROMPT_VERSION if dedicated_review else None
    )
    prompts = []

    def evaluate(prompt):
        prompts.append(prompt)
        return (
            {"coaching": overall(), "follow_up_review": None}
            if dedicated_review
            else overall()
        )

    runtime.provider.behavior = evaluate
    assert runtime.worker.run("owner", answered["evaluationId"])
    assert runtime.provider.calls == 2
    assert len(prompts) == 1
    prompt = prompts[0]
    assert prompt.follow_up_review is dedicated_review
    assert prompt.version == (
        FOLLOWUP_PROMPT_VERSION
        if dedicated_review and not new_rubric
        else expected
    )
    assert schema_for(prompt)["required"] == (
        ["coaching", "follow_up_review"]
        if dedicated_review
        else list(overall())
    )
    evaluated = runtime.repository.snapshot().evaluations[answered["evaluationId"]]
    assert evaluated.execution_config.prompt_version == prompt.version
    feedback = runtime.application.feedback("owner", answered["attemptId"]).body
    assert feedback["result"]["conclusion_score"] == 8


def test_old_attempt_keeps_old_rubric_even_after_enablement(runtime):
    sid, qid, initial = begin(runtime)
    runtime.provider.behavior = lambda _: overall("そのとき何をしましたか？")
    assert runtime.worker.run("owner", initial["evaluationId"])
    runtime.repository.coaching_overall_rubric_v2_enabled = True
    next_job = answer_followup(runtime, sid, qid, initial)
    record = runtime.repository.snapshot().evaluations[next_job["evaluationId"]]
    assert record.overall_prompt_version is None
    observed = []
    runtime.provider.behavior = lambda prompt: observed.append(prompt) or overall()
    assert runtime.worker.run("owner", next_job["evaluationId"])
    assert observed[0].instructions == COACHING_INSTRUCTIONS
    assert observed[0].version == COACHING_PROMPT_VERSION


def test_retry_inherits_frozen_method_and_codec_readability(runtime):
    runtime.repository.coaching_overall_rubric_v2_enabled = True
    sid, _, initial = begin(runtime)
    first = runtime.repository.snapshot().evaluations[initial["evaluationId"]]
    recovered = decode(encode("Evaluation", first, 0))[0]
    assert recovered.overall_prompt_version == OVERALL_RUBRIC_PROMPT_VERSION
    runtime.provider.behavior = lambda _: {"invalid": True}
    assert runtime.worker.run("owner", initial["evaluationId"])
    retry = runtime.application.submit(
        "owner",
        uid(653),
        sid,
        {
            "kind": "retry_evaluation",
            "attemptId": initial["attemptId"],
            "fromEvaluationId": initial["evaluationId"],
        },
    ).body
    runtime.repository.coaching_overall_rubric_v2_enabled = False
    saved = runtime.repository.snapshot().evaluations[retry["evaluationId"]]
    assert saved.overall_prompt_version == OVERALL_RUBRIC_PROMPT_VERSION
    assert decode(encode("Evaluation", saved, 0))[0] == saved
    legacy = replace(saved, overall_prompt_version=None)
    item = encode("Evaluation", legacy, 0)
    assert "overall_prompt_version" not in json.loads(item["data"])
    assert decode(item)[0].overall_prompt_version is None


def test_unknown_overall_method_never_calls_provider(runtime):
    _, _, initial = begin(runtime)
    evaluation = runtime.repository._state.evaluations[initial["evaluationId"]]
    evaluation.overall_prompt_version = "unsupported-future-version"
    assert runtime.worker.run("owner", initial["evaluationId"])
    assert runtime.provider.calls == 0
    stopped = runtime.repository.snapshot().evaluations[initial["evaluationId"]]
    assert stopped.status == "failed"
    assert stopped.failure_reason == "PREPARATION_FAILED"
    assert not runtime.worker.run("owner", initial["evaluationId"])
    assert runtime.provider.calls == 0


def test_rubric_prioritizes_question_and_preserves_old_instructions(runtime):
    _, _, initial = begin(runtime)
    context = runtime.repository.snapshot().evaluations[initial["evaluationId"]].coaching_input
    old = build_coaching_prompt(context)
    new = build_coaching_prompt(context, overall_prompt_version=OVERALL_RUBRIC_PROMPT_VERSION)
    assert old.instructions == COACHING_INSTRUCTIONS
    assert old.result_schema == new.result_schema
    assert new.instructions.startswith(old.instructions)
    for fragment in (
        "質問本文", "強み", "判断理由", "重大矛盾", "0〜10整数",
        "重複減点", "good_point", "improvement", "深掘り",
    ):
        assert fragment in new.instructions
    with pytest.raises(ValueError, match="Unsupported overall"):
        build_coaching_prompt(context, overall_prompt_version="unknown")
