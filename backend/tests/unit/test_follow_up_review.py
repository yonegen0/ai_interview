"""Focused offline tests for isolated follow-up review and legacy compatibility."""

import pytest
from conftest import uid
from pydantic import ValidationError

from interview_backend.evaluation.provider import FOLLOWUP_PROMPT_VERSION
from interview_backend.models.public import FollowUpReview
from interview_backend.repositories.codec import decode, encode


def start(runtime):
    app = runtime.application
    sid = app.create(
        "owner", uid(500), {"mode": "category", "category": "job_change", "difficulty": "standard"}
    ).body["sessionId"]
    qid = app.question("owner", sid).body["question"]["id"]
    accepted = app.submit(
        "owner",
        uid(501),
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
        "good_point": "結論が伝わります。",
        "improvement": "判断理由を補足してください。",
        "follow_up_question": question,
        "example": None if question else "営業に挑戦したいです。",
    }


def review():
    return {
        "question_fit_score": 9,
        "detail_score": 8,
        "coherence_score": 9,
        "suitability": "ready",
        "good_point": "具体的な方法を説明しています。",
        "improvement": "現時点で重要な改善点はありません。",
    }


def follow(runtime, sid, qid, initial):
    return runtime.application.submit(
        "owner",
        uid(502),
        sid,
        {
            "kind": "coaching_answer",
            "questionId": qid,
            "attemptId": initial["attemptId"],
            "fromEvaluationId": initial["evaluationId"],
            "answer": "集荷先で他社の送り状を確認し、利用状況を尋ねました。",
        },
    ).body


@pytest.mark.parametrize(
    "invalid",
    [
        {"question_fit_score": True},
        {"question_fit_score": -1},
        {"question_fit_score": 11},
        {"detail_score": 7.5},
        {"coherence_score": "9"},
        {"suitability": "unknown"},
        {"improvement": ""},
        {"improvement": "あ" * 201},
        {"question_fit_score": 2},
    ],
)
def test_follow_up_strict_validation(invalid):
    raw = review() | invalid
    with pytest.raises(ValidationError):
        FollowUpReview.model_validate(raw)


def test_initial_legacy_and_new_follow_up_one_call(runtime):
    runtime.repository.coaching_review_enabled = True
    sid, qid, initial = start(runtime)
    runtime.provider.behavior = lambda prompt: overall("あなたはどのように提案しましたか？")
    assert runtime.worker.run("owner", initial["evaluationId"])
    assert runtime.provider.calls == 1
    assert (
        runtime.repository.snapshot().evaluations[initial["evaluationId"]].review_prompt_version
        is None
    )
    first = runtime.application.feedback("owner", initial["attemptId"]).body
    assert "followUpReviews" not in first and first["totalScore"] >= 0
    answered = follow(runtime, sid, qid, initial)
    job = runtime.repository.snapshot().evaluations[answered["evaluationId"]]
    assert job.review_prompt_version == FOLLOWUP_PROMPT_VERSION
    assert job.round_index == 1
    runtime.provider.behavior = lambda prompt: {"coaching": overall(), "follow_up_review": review()}
    assert runtime.worker.run("owner", answered["evaluationId"])
    assert runtime.provider.calls == 2  # exactly one call per Evaluation
    traditional = runtime.application.feedback("owner", answered["attemptId"]).body
    assert "followUpReviews" not in traditional
    extended = runtime.application.feedback(
        "owner", answered["attemptId"], answered["evaluationId"], True
    ).body
    assert extended["feedback"] == traditional
    entry = extended["followUpReviews"][0]
    assert entry["evaluationId"] == answered["evaluationId"]
    assert entry["review"]["totalScore"] == 26
    assert entry["review"]["question_fit_score"] == 9
    assert "rank" not in entry["review"] and "lengthPenalty" not in entry["review"]
    assert not runtime.worker.run("owner", answered["evaluationId"])
    assert runtime.provider.calls == 2
    stored = runtime.repository.snapshot().follow_up_reviews[answered["evaluationId"]]
    assert decode(encode("FollowUpReviewRecord", stored, 0))[0] == stored


def test_bad_optional_review_does_not_lose_good_overall(runtime):
    from interview_backend.observability import Metrics

    # A production-like allowlisted metric callback must not turn partial failure
    # into an overall evaluation failure.
    runtime.worker.metric = Metrics(
        "worker", environment="test", sink=lambda _: None
    ).classification
    runtime.repository.coaching_review_enabled = True
    sid, qid, initial = start(runtime)
    runtime.provider.behavior = lambda prompt: overall("そのとき何をしましたか？")
    assert runtime.worker.run("owner", initial["evaluationId"])
    answered = follow(runtime, sid, qid, initial)
    runtime.provider.behavior = lambda prompt: {
        "coaching": overall(),
        "follow_up_review": review() | {"question_fit_score": -4},
    }
    assert runtime.worker.run("owner", answered["evaluationId"])
    extended = runtime.application.feedback(
        "owner", answered["attemptId"], answered["evaluationId"], True
    ).body
    assert extended["feedback"]["result"]["status"] == "completed"
    assert extended["followUpReviews"][0]["review"] is None
    assert answered["evaluationId"] not in runtime.repository.snapshot().follow_up_reviews


def test_missing_optional_review_keeps_valid_coaching(runtime):
    """A missing dedicated review must not discard a valid overall evaluation."""
    runtime.repository.coaching_review_enabled = True
    sid, qid, initial = start(runtime)
    runtime.provider.behavior = lambda prompt: overall("そのとき何をしましたか？")
    assert runtime.worker.run("owner", initial["evaluationId"])
    answered = follow(runtime, sid, qid, initial)
    runtime.provider.behavior = lambda prompt: {"coaching": overall()}
    assert runtime.worker.run("owner", answered["evaluationId"])
    extended = runtime.application.feedback(
        "owner", answered["attemptId"], answered["evaluationId"], True
    ).body
    assert extended["feedback"]["result"]["status"] == "completed"
    assert extended["followUpReviews"][0]["review"] is None


def test_invalid_overall_remains_failed(runtime):
    runtime.repository.coaching_review_enabled = True
    sid, qid, initial = start(runtime)
    runtime.provider.behavior = lambda prompt: overall("そのとき何をしましたか？")
    assert runtime.worker.run("owner", initial["evaluationId"])
    answered = follow(runtime, sid, qid, initial)
    runtime.provider.behavior = lambda prompt: {
        "coaching": overall() | {"conclusion_score": -1},
        "follow_up_review": review(),
    }
    assert runtime.worker.run("owner", answered["evaluationId"])
    status = runtime.application.evaluation("owner", answered["evaluationId"]).body["status"]
    assert status == "failed"
    assert answered["evaluationId"] not in runtime.repository.snapshot().follow_up_reviews


def test_job_method_frozen_before_enable_toggle_and_retry(runtime):
    sid, qid, initial = start(runtime)
    runtime.provider.behavior = lambda prompt: overall("そのとき何をしましたか？")
    assert runtime.worker.run("owner", initial["evaluationId"])
    answered = follow(runtime, sid, qid, initial)
    runtime.repository.coaching_review_enabled = True
    assert (
        runtime.repository.snapshot().evaluations[answered["evaluationId"]].review_prompt_version
        is None
    )
    runtime.provider.behavior = lambda prompt: overall()
    assert runtime.worker.run("owner", answered["evaluationId"])
    status = runtime.application.feedback("owner", answered["attemptId"]).body["result"]["status"]
    assert status == "completed"


def test_owner_read_separation(runtime):
    runtime.repository.coaching_review_enabled = True
    sid, qid, initial = start(runtime)
    runtime.provider.behavior = lambda prompt: overall("そのとき何をしましたか？")
    assert runtime.worker.run("owner", initial["evaluationId"])
    answered = follow(runtime, sid, qid, initial)
    runtime.provider.behavior = lambda prompt: {"coaching": overall(), "follow_up_review": review()}
    assert runtime.worker.run("owner", answered["evaluationId"])
    from interview_backend.models.internal import BusinessError

    with pytest.raises(BusinessError) as err:
        runtime.application.feedback("other-owner", answered["attemptId"], None, True)
    assert err.value.status == 404
