"""Bounded owner-scoped history tests; no real AWS or AI calls."""

from types import SimpleNamespace

import pytest

from interview_backend.models.internal import AssistHistory, Attempt, AttemptCoaching, BusinessError
from interview_backend.models.public import Question
from interview_backend.repositories.history import build_history, parse_history_query
from interview_backend.repositories.memory import MemoryRepository

OWNER = "owner-a"
OTHER = "owner-b"
NOW = 1789084800000


def uid(index):
    return f"10000000-0000-4000-8000-{index:012d}"


def attempt(index, created=NOW - 1000, owner=OWNER, v2=False):
    return Attempt(
        owner=owner,
        id=uid(index),
        session_id=uid(100),
        evaluation_id=uid(index + 1000),
        question=Question(
            id=uid(200),
            category="strengths",
            difficulty="standard",
            question="あなたの強みを教えてください。",
        ),
        question_number=1,
        answer="丁寧に確認した",
        created_at=created,
        coaching_contract_version=2 if v2 else None,
    )


def evaluation(a, score=80, status="completed"):
    return SimpleNamespace(
        id=a.evaluation_id,
        owner=a.owner,
        attempt_id=a.id,
        status=status,
        coaching_contract_version=a.coaching_contract_version,
        feedback=SimpleNamespace(
            score=score,
            totalScore=score,
        )
        if status == "completed"
        else None,
    )


def test_stable_pagination_null_scores_and_coaching_scale():
    attempts = [attempt(i) for i in (1, 2, 3, 4, 5, 6)]
    coaching = attempt(7, v2=True)
    pending = attempt(8, created=NOW - 500)
    all_attempts = attempts + [coaching, pending]
    evaluations = [evaluation(a) for a in attempts]
    evaluations += [evaluation(coaching, score=21), evaluation(pending, status="processing")]
    coachings = [
        AttemptCoaching(
            owner=OWNER,
            id=coaching.id,
            session_id=coaching.session_id,
            current_evaluation_id=coaching.evaluation_id,
            created_at=coaching.created_at,
            updated_at=coaching.created_at,
        )
    ]
    first = build_history(
        OWNER, {"limit": "5"}, NOW, all_attempts, evaluations, coachings, [], []
    ).body
    assert len(first["items"]) == 5
    assert first["nextCursor"]
    assert first["items"][0]["id"] == "attempt:" + pending.id
    assert first["items"][0]["score"] is None
    assert first["items"][0]["status"] == "processing"
    later = build_history(
        OWNER,
        {"limit": "5", "cursor": first["nextCursor"]},
        NOW,
        all_attempts,
        evaluations,
        coachings,
        [],
        [],
    ).body
    ids = [x["id"] for x in first["items"] + later["items"]]
    assert len(ids) == len(set(ids)) == 8
    result = next(x for x in first["items"] + later["items"] if x["id"] == "attempt:" + coaching.id)
    assert (result["score"], result["scoreMax"]) == (21, 30)
    assert first["usage"]["practiceAttempts"] == 8
    assert first["usage"]["evaluatedAttempts"] == 7


def test_summary_remains_after_generation_ttl_and_mode_is_real():
    record = AssistHistory(
        owner=OWNER,
        id=uid(10),
        question_id=uid(200),
        question="自己PR",
        assist_type="prep",
        created_at=NOW - 5000,
        status="SUCCEEDED",
        finished_at=NOW - 4000,
    )
    reply = build_history(OWNER, {"mode": "assist"}, NOW, [], [], [], [record], []).body
    assert reply["items"][0]["assistType"] == "prep"
    assert reply["items"][0]["score"] is None
    assert reply["items"][0]["generationId"] == uid(10)
    assert build_history(OWNER, {"mode": "star"}, NOW, [], [], [], [record], []).body["items"] == []


def test_cursor_must_match_owner_and_filters():
    page = build_history(
        OWNER,
        {"limit": "1"},
        NOW,
        [attempt(1), attempt(2)],
        [evaluation(attempt(1)), evaluation(attempt(2))],
        [],
        [],
        [],
    ).body
    cursor = page["nextCursor"]
    with pytest.raises(BusinessError) as owner_error:
        parse_history_query(OTHER, {"limit": "1", "cursor": cursor}, NOW)
    assert owner_error.value.status == 400
    with pytest.raises(BusinessError):
        parse_history_query(OWNER, {"mode": "assist", "limit": "1", "cursor": cursor}, NOW)
    with pytest.raises(BusinessError):
        parse_history_query(OWNER, {"limit": "-4"}, NOW)
    with pytest.raises(BusinessError) as oversized:
        parse_history_query(OWNER, {"limit": "9" * 10000}, NOW)
    assert oversized.value.status == 400
    assert oversized.value.code == "VALIDATION_ERROR"


def test_memory_repository_separates_owner_records():
    store = MemoryRepository(clock=lambda: NOW)
    a, other = attempt(1), attempt(2, owner=OTHER)
    store._state.attempts = {a.id: a, other.id: other}
    store._state.evaluations = {
        a.evaluation_id: evaluation(a),
        other.evaluation_id: evaluation(other),
    }
    result = store.history(OWNER, {"limit": "5"}).body
    assert [row["attemptId"] for row in result["items"]] == [a.id]
