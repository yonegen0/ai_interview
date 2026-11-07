"""Offline follow-up assist acceptance: scope, live state, history, one candidate."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from interview_backend.models.internal import BusinessError
from interview_backend.star_assist.models import StarInput
from interview_backend.star_assist.provider import FakeStarProvider
from interview_backend.star_assist.repository import StarRepositoryMixin


def call(runtime, method, path, body=None, owner="owner"):
    response = runtime.handler({
        "requestContext": {
            "authorizer": {"jwt": {"claims": {"sub": owner}}},
            "http": {"method": method},
        },
        "rawPath": path,
        "headers": {"Idempotency-Key": str(uuid4())},
        "body": json.dumps(body),
    })
    return response["statusCode"], json.loads(response["body"])


def memo(mode="follow_up", text="自分から声をかけ、3社が新しく集荷を利用した。"):
    return {
        "assistType": mode,
        "notes": {"S": text, "T": "", "A": "", "R": ""},
        "targetCategory": None, "industry": "", "company": "",
        "candidates": [], "selectedCandidateId": None, "generationId": None,
    }


def coaching(question):
    return {
        "status": "coaching",
        "conclusion_score": 8, "specificity_score": 6, "reasoning_score": 7,
        "good_point": "具体的な行動を伝えています。",
        "improvement": "判断の理由をさらに説明しましょう。",
        "follow_up_question": question, "example": None,
    }


def test_follow_up_scoped_history_snapshot_and_apply(runtime):
    app = runtime.application
    owner = "owner"
    sid = app.create(owner, str(uuid4()), {
        "mode": "category", "category": "job_change", "difficulty": "standard"
    }).body["sessionId"]
    qid = app.question(owner, sid).body["question"]["id"]
    question_1 = "なぜ自分から声をかけたのですか？"
    question_2 = "何社が新たに利用しましたか？"
    accepted = app.submit(owner, str(uuid4()), sid, {
        "kind": "initial_answer", "questionId": qid,
        "answer": "送り状を見て、自分から提案しました。",
    }).body
    runtime.provider.behavior = lambda _: coaching(question_1)
    assert runtime.worker.run(owner, accepted["evaluationId"])

    context = call(runtime, "POST", f"/sessions/{sid}/answer-contexts", {
        "operationKind": "coaching_answer", "questionId": qid,
        "fromAttemptId": accepted["attemptId"],
        "fromEvaluationId": accepted["evaluationId"],
    })[1]["contextId"]

    # Legacy draft remains visible; it cannot be generated in a coaching round.
    legacy = call(runtime, "POST", f"/answer-contexts/{context}/star-drafts",
                  memo("career_change"))[1]
    forbidden = call(runtime, "POST", "/star-assist/generations", {
        "starDraftId": legacy["id"], "expectedVersion": legacy["version"],
    })
    assert forbidden[0] == 403 and forbidden[1]["code"] == "ASSIST_MODE_FORBIDDEN"
    saved_drafts = call(runtime, "GET", f"/answer-contexts/{context}/drafts")[1]
    assert saved_drafts["starDraft"]["id"] == legacy["id"]
    assert call(runtime, "POST", f"/star-drafts/{legacy['id']}/discard", {
        "expectedVersion": legacy["version"],
    })[0] == 200

    notes = memo()
    star = call(runtime, "POST", f"/answer-contexts/{context}/star-drafts", notes)[1]
    answer = call(runtime, "POST", f"/answer-contexts/{context}/answer-drafts",
                  {"answer": "", "applicationId": None})[1]
    queued = call(runtime, "POST", "/star-assist/generations", {
        "starDraftId": star["id"], "expectedVersion": star["version"],
    })
    assert queued[0] == 202
    generation_id = queued[1]["generationId"]
    lease = runtime.repository.star_claim(owner, generation_id, 1, str(uuid4()))
    assert lease.follow_up_context["initialAnswer"] == "送り状を見て、自分から提案しました。"
    assert lease.follow_up_context["history"] == []
    assert lease.follow_up_context["originalQuestion"]
    assert lease.question == question_1
    assert runtime.repository.star_start(lease)
    generated = FakeStarProvider().generate(lease.question, lease.input)
    assert runtime.repository.star_finish(lease, "SUCCEEDED", generated)
    assert len(generated.candidates) == 1 and generated.candidates[0].id == "A"

    current = call(runtime, "PUT", f"/star-drafts/{star['id']}", {
        **notes, "candidates": [v.model_dump() for v in generated.candidates],
        "selectedCandidateId": "A", "generationId": generation_id,
        "expectedVersion": star["version"],
    })[1]
    assert call(runtime, "POST", f"/star-drafts/{star['id']}/applications", {
        "expectedVersion": current["version"], "candidateId": "A",
        "answerDraftId": answer["id"], "expectedAnswerVersion": answer["version"],
    })[0] == 200

    next_attempt = app.submit(owner, str(uuid4()), sid, {
        "kind": "coaching_answer", "questionId": qid,
        "attemptId": accepted["attemptId"],
        "fromEvaluationId": accepted["evaluationId"],
        "answer": "自分から声をかけて、3社に利用いただきました。",
    }).body
    runtime.provider.behavior = lambda _: coaching(question_2)
    assert runtime.worker.run(owner, next_attempt["evaluationId"])
    next_context = call(runtime, "POST", f"/sessions/{sid}/answer-contexts", {
        "operationKind": "coaching_answer", "questionId": qid,
        "fromAttemptId": accepted["attemptId"],
        "fromEvaluationId": next_attempt["evaluationId"],
    })[1]["contextId"]
    next_draft = call(runtime, "POST", f"/answer-contexts/{next_context}/star-drafts", memo())[1]
    queued_2 = call(runtime, "POST", "/star-assist/generations", {
        "starDraftId": next_draft["id"], "expectedVersion": next_draft["version"],
    })[1]
    lease_2 = runtime.repository.star_claim(owner, queued_2["generationId"], 1, str(uuid4()))
    assert lease_2.follow_up_context["history"] == [
        {"question": question_1, "answer": "自分から声をかけて、3社に利用いただきました。"}
    ]
    assert lease_2.question == question_2


def test_follow_up_rejected_before_coaching_and_for_none(runtime):
    app = runtime.application
    sid = app.create("owner", str(uuid4()), {
        "mode": "category", "category": "job_change", "difficulty": "standard"
    }).body["sessionId"]
    qid = app.question("owner", sid).body["question"]["id"]
    context = call(runtime, "POST", f"/sessions/{sid}/answer-contexts", {
        "operationKind": "initial_answer", "questionId": qid,
    })[1]["contextId"]
    draft = call(runtime, "POST", f"/answer-contexts/{context}/star-drafts", memo())[1]
    status, result = call(runtime, "POST", "/star-assist/generations", {
        "starDraftId": draft["id"], "expectedVersion": draft["version"],
    })
    assert status == 403 and result["code"] == "ASSIST_MODE_FORBIDDEN"
    dummy = StarRepositoryMixin()
    tx = SimpleNamespace(get=lambda _: SimpleNamespace(question=SimpleNamespace(assistType="none")))
    with pytest.raises(BusinessError) as error:
        dummy._allowed_assist_mode(
            tx, "owner",
            SimpleNamespace(session_id="session", operation_kind="initial_answer"),
            "star",
        )
    assert error.value.status == 403


def test_follow_up_notes_are_single_field_and_one_candidate():
    from pydantic import ValidationError

    assert StarInput.model_validate(memo()).assistType == "follow_up"
    with pytest.raises(ValidationError):
        StarInput.model_validate({
            **memo(), "notes": {"S": "メモ", "T": "旧ステップ", "A": "", "R": ""},
        })
    result = FakeStarProvider().generate("なぜですか？", StarInput.model_validate(memo()))
    assert len(result.candidates) == 1
