"""Offline progress regression tests: no AI calls, network, or AWS resources."""

from types import SimpleNamespace as Obj

import pytest

from interview_backend.api.handler import Handler
from interview_backend.application.service import Application
from interview_backend.models.internal import IntegrityError
from interview_backend.repositories.memory import MemoryRepository
from interview_backend.repositories.practice_progress import count_completed_questions


def attempt(index, question, *, owner="user-a", v2=False):
    return Obj(
        owner=owner,
        id=f"a{index}",
        evaluation_id=f"e{index}",
        question=Obj(id=question),
        coaching_contract_version=2 if v2 else None,
    )


def evaluation(
    index,
    attempt_id,
    *,
    owner="user-a",
    status="completed",
    v2=False,
    round_index=None,
    retry=None,
    score=80,
):
    return Obj(
        owner=owner,
        id=f"e{index}",
        attempt_id=attempt_id,
        status=status,
        coaching_contract_version=2 if v2 else None,
        round_index=round_index,
        retry_of_evaluation_id=retry,
        feedback=Obj(attemptId=attempt_id, evaluationId=f"e{index}", totalScore=score, score=score)
        if status == "completed"
        else None,
    )


def count(attempts, evaluations, size=15):
    ids = {f"q{i}" for i in range(size)}
    return count_completed_questions("user-a", ids, attempts, evaluations)


def test_empty_partial_and_complete_progress():
    assert count([], []) == 0
    a = [attempt(i, f"q{i}") for i in range(15)]
    e = [evaluation(i, f"a{i}") for i in range(15)]
    assert count(a, e[:5]) == 5
    assert count(a, e) == 15
    assert count(a, e, size=10) == 10
    assert count(a, e, size=0) == 0


def test_repeat_different_modes_failure_and_zero_score():
    a = [attempt(0, "q0"), attempt(1, "q0", v2=True), attempt(2, "q1")]
    e = [
        evaluation(0, "a0", status="failed"),
        evaluation(1, "a1", v2=True, round_index=0, score=0),
        evaluation(2, "a2", score=0),
    ]
    assert count(a, e) == 2
    assert count(a, [evaluation(0, "a0"), *e[1:]]) == 2


def test_old_success_survives_later_failure_and_followups():
    a = [attempt(0, "q0", v2=True), attempt(1, "q0")]
    e = [
        evaluation(0, "a0", v2=True, round_index=0),
        evaluation(42, "a0", v2=True, round_index=1),
        evaluation(1, "a1", status="failed"),
    ]
    assert count(a, e) == 1
    assert count(a, e[1:]) == 0


def test_failed_initial_can_succeed_on_coaching_retry():
    a = [attempt(0, "q0", v2=True)]
    e = [
        evaluation(0, "a0", v2=True, round_index=0, status="failed"),
        evaluation(9, "a0", v2=True, round_index=0, retry="e0"),
        evaluation(10, "a0", v2=True, round_index=2),
    ]
    assert count(a, e) == 1
    assert count(a, [e[0], e[2]]) == 0


@pytest.mark.parametrize(
    "attempts,evaluations",
    [
        ([attempt(0, "q0")], [evaluation(0, "a0", owner="user-b")]),
        ([attempt(0, "q0")], [evaluation(0, "other")]),
        ([attempt(0, "q0")], [evaluation(1, "a0")]),
        ([attempt(0, "q0", v2=True)], [evaluation(2, "a0", v2=True, round_index=0)]),
        (
            [attempt(0, "q0", v2=True)],
            [
                evaluation(0, "a0", v2=True, round_index=0, status="failed"),
                evaluation(2, "a0", v2=True, round_index=0, retry="missing"),
            ],
        ),
    ],
)
def test_corrupt_relations_do_not_count(attempts, evaluations):
    with pytest.raises(IntegrityError):
        count(attempts, evaluations)


def test_app_and_handler_return_bank_version_and_no_private_details():
    repo = MemoryRepository()
    app = Application(repo, (), lambda: "unused")
    # No bank and no attempts is valid, including a zero-question bank.
    assert app.practice_progress("user-a").body == {
        "bankVersion": 0,
        "totalQuestions": 0,
        "completedQuestions": 0,
    }
    handler = Handler(app)
    event = {
        "rawPath": "/me/practice-progress",
        "requestContext": {
            "http": {"method": "GET"},
            "authorizer": {"jwt": {"claims": {"sub": "user-a"}}},
        },
    }
    import json

    response = handler(event)
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == app.practice_progress("user-a").body
    assert response["headers"]["Cache-Control"] == "no-store"
    anonymous = {**event, "requestContext": {"http": {"method": "GET"}}}
    assert Handler(app)(anonymous)["statusCode"] == 401
