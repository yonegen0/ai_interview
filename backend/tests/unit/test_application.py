"""Business flows, replay ordering, atomicity, ownership and worker races."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from conftest import uid

from interview_backend.assets import load_questions, validate_bank
from interview_backend.models.internal import BusinessError
from interview_backend.models.public import CATEGORIES, ActiveAttempt

OWNER = "test-user"


def start(runtime, category="job_change"):
    session_id = runtime.application.create(
        OWNER, uid(100), {"category": category, "difficulty": "standard"}
    ).body["sessionId"]
    question = runtime.application.question(OWNER, session_id).body["question"]
    return session_id, {"questionId": question["id"], "answer": "  本文\nを保持します。"}


def submit(runtime):
    session_id, payload = start(runtime)
    reply = runtime.application.submit(OWNER, uid(101), session_id, payload)
    return session_id, payload, reply.body


def assert_error(code, operation):
    with pytest.raises(BusinessError) as error:
        operation()
    assert error.value.code == code


@pytest.mark.parametrize("category", CATEGORIES)
def test_question_cycle_and_retry(runtime, category):
    session_id, payload = start(runtime, category)
    first_question = payload["questionId"]
    ids = []
    for number in range(1, 5):
        current = runtime.application.question(OWNER, session_id).body
        ids.append(current["question"]["id"])
        assert current["questionNumber"] == number
        payload["questionId"] = current["question"]["id"]
        accepted = runtime.application.submit(OWNER, uid(200 + number), session_id, payload).body
        runtime.worker.run(accepted["evaluationId"])
        retry = runtime.application.submit(OWNER, uid(300 + number), session_id, payload).body
        assert retry["attemptId"] != accepted["attemptId"]
        runtime.worker.run(retry["evaluationId"])
        feedback = runtime.application.feedback(OWNER, retry["attemptId"]).body
        assert feedback["questionNumber"] == number
        assert feedback["answer"] == payload["answer"]
        runtime.application.next_question(
            OWNER, uid(400 + number), session_id, {"fromAttemptId": retry["attemptId"]}
        )
    assert len(set(ids[:3])) == 3
    assert ids[3] == first_question


def test_replay_after_completion_and_next_and_response_loss(runtime):
    session_id, payload, accepted = submit(runtime)
    for _ in range(3):
        assert runtime.application.submit(OWNER, uid(101), session_id, payload).body == accepted
    runtime.worker.run(accepted["evaluationId"])
    next_payload = {"fromAttemptId": accepted["attemptId"]}
    next_reply = runtime.application.next_question(OWNER, uid(102), session_id, next_payload)
    assert runtime.application.submit(OWNER, uid(101), session_id, payload).body == accepted
    assert (
        runtime.application.next_question(OWNER, uid(102), session_id, next_payload) == next_reply
    )
    assert runtime.application.create(
        OWNER, uid(100), {"category": "job_change", "difficulty": "standard"}
    ).body == {"sessionId": session_id}
    assert_error(
        "SESSION_STATE_CONFLICT",
        lambda: runtime.application.next_question(OWNER, uid(103), session_id, next_payload),
    )
    state = runtime.repository.snapshot()
    assert len(state.sessions) == len(state.attempts) == len(state.evaluations) == 1
    assert state.sessions[session_id].number == 2


def test_fingerprint_and_owner_scoping(runtime):
    session_id, payload, accepted = submit(runtime)
    equivalent = {"answer": payload["answer"], "questionId": payload["questionId"], "extra": 1}
    assert runtime.application.submit(OWNER, uid(101), session_id, equivalent).body == accepted
    for altered in [
        {**payload, "answer": "別回答"},
        {**payload, "answer": payload["answer"].strip()},
    ]:
        assert_error(
            "IDEMPOTENCY_CONFLICT",
            lambda altered=altered: runtime.application.submit(
                OWNER, uid(101), session_id, altered
            ),
        )
    assert_error(
        "IDEMPOTENCY_CONFLICT",
        lambda: runtime.application.next_question(
            OWNER, uid(101), session_id, {"fromAttemptId": accepted["attemptId"]}
        ),
    )
    assert_error(
        "IDEMPOTENCY_CONFLICT",
        lambda: runtime.application.submit(OWNER, uid(101), uid(999), payload),
    )
    other = runtime.application.create(
        "other", uid(100), {"category": "job_change", "difficulty": "standard"}
    )
    assert other.body["sessionId"] != session_id
    assert_error("SESSION_NOT_FOUND", lambda: runtime.application.question("other", session_id))
    assert_error(
        "SESSION_NOT_FOUND",
        lambda: runtime.application.submit("other", uid(101), session_id, payload),
    )
    assert_error(
        "ATTEMPT_NOT_FOUND",
        lambda: runtime.application.evaluation("other", accepted["evaluationId"]),
    )
    assert_error(
        "ATTEMPT_NOT_FOUND", lambda: runtime.application.feedback("other", accepted["attemptId"])
    )


def test_state_conflicts_and_unsuccessful_key_is_reusable(runtime):
    session_id, payload = start(runtime)
    assert_error(
        "SESSION_STATE_CONFLICT",
        lambda: runtime.application.submit(
            OWNER, uid(101), session_id, {**payload, "questionId": uid(999)}
        ),
    )
    accepted = runtime.application.submit(OWNER, uid(101), session_id, payload).body
    assert_error(
        "SESSION_STATE_CONFLICT",
        lambda: runtime.application.submit(OWNER, uid(102), session_id, payload),
    )
    assert_error(
        "SESSION_STATE_CONFLICT",
        lambda: runtime.application.next_question(
            OWNER, uid(103), session_id, {"fromAttemptId": accepted["attemptId"]}
        ),
    )
    runtime.worker.run(accepted["evaluationId"])
    assert runtime.application.submit(OWNER, uid(102), session_id, payload).status == 202


@pytest.mark.parametrize("same_key", [True, False])
def test_simultaneous_submission(runtime, same_key):
    session_id, payload = start(runtime)
    barrier = Barrier(2)

    def invoke(number):
        barrier.wait(timeout=5)
        try:
            return runtime.application.submit(
                OWNER, uid(101 if same_key else 101 + number), session_id, payload
            )
        except BusinessError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(invoke, range(2)))
    if same_key:
        assert results[0] == results[1]
    else:
        assert sum(result == 409 for result in results) == 1
    state = runtime.repository.snapshot()
    assert len(state.attempts) == len(state.evaluations) == 1


def test_concurrent_create_and_next(runtime):
    payload = {"category": "job_change", "difficulty": "standard"}
    with ThreadPoolExecutor(max_workers=4) as pool:
        replies = list(
            pool.map(lambda _: runtime.application.create(OWNER, uid(100), payload), range(8))
        )
    assert all(reply == replies[0] for reply in replies)
    session_id = replies[0].body["sessionId"]
    question = runtime.application.question(OWNER, session_id).body["question"]
    accepted = runtime.application.submit(
        OWNER, uid(101), session_id, {"questionId": question["id"], "answer": "回答"}
    ).body
    runtime.worker.run(accepted["evaluationId"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        replies = list(
            pool.map(
                lambda _: runtime.application.next_question(
                    OWNER, uid(102), session_id, {"fromAttemptId": accepted["attemptId"]}
                ),
                range(8),
            )
        )
    assert all(reply == replies[0] for reply in replies)
    assert runtime.application.question(OWNER, session_id).body["questionNumber"] == 2


def test_gets_never_run_worker_and_duplicate_worker_is_noop(runtime):
    session_id, _, accepted = submit(runtime)
    for _ in range(10):
        runtime.application.question(OWNER, session_id)
        assert (
            runtime.application.evaluation(OWNER, accepted["evaluationId"]).body["status"]
            == "processing"
        )
    assert runtime.provider.calls == 0
    entered, release = Event(), Event()

    def held(_):
        entered.set()
        assert release.wait(timeout=5)
        return {"score": 0, "summary": "", "strengths": [], "improvements": []}

    runtime.provider.behavior = held
    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(runtime.worker.run, accepted["evaluationId"])
        try:
            assert entered.wait(timeout=5)
            assert runtime.worker.run(accepted["evaluationId"]) is False
        finally:
            release.set()
        assert running.result(timeout=5)
    assert runtime.worker.run(accepted["evaluationId"]) is False
    assert runtime.provider.calls == 1
    assert runtime.application.feedback(OWNER, accepted["attemptId"]).body["strengths"] == []


@pytest.mark.parametrize("failure", ["exception", "invalid"])
def test_failed_then_retry_without_leaking_provider_data(runtime, failure, capsys):
    session_id, payload, accepted = submit(runtime)

    def fail(_):
        if failure == "exception":
            raise RuntimeError("SECRET RAW PROVIDER ANSWER")
        return {"score": True, "summary": "SECRET RAW PROVIDER ANSWER"}

    runtime.provider.behavior = fail
    runtime.worker.run(accepted["evaluationId"])
    result = runtime.application.evaluation(OWNER, accepted["evaluationId"])
    assert result.body["status"] == "failed"
    assert result.body["error"]["code"] == "EVALUATION_FAILED"
    assert "SECRET" not in repr(runtime.repository.snapshot())
    assert capsys.readouterr().out == ""
    assert_error(
        "EVALUATION_NOT_COMPLETED",
        lambda: runtime.application.feedback(OWNER, accepted["attemptId"]),
    )
    runtime.provider.behavior = None
    retry = runtime.application.submit(OWNER, uid(102), session_id, payload).body
    runtime.worker.run(retry["evaluationId"])
    assert (
        runtime.application.evaluation(OWNER, retry["evaluationId"]).body["status"] == "completed"
    )


@pytest.mark.parametrize("operation", ["create", "answer", "next", "claim", "finish"])
def test_commit_failure_is_atomic(runtime, monkeypatch, operation):
    session_id, payload = start(runtime)
    if operation in {"next", "claim", "finish"}:
        accepted = runtime.application.submit(OWNER, uid(101), session_id, payload).body
        if operation == "next":
            runtime.worker.run(accepted["evaluationId"])
        if operation == "finish":
            runtime.repository.claim(accepted["evaluationId"])
    before = runtime.repository.snapshot()

    def fail_commit(_):
        raise RuntimeError("injected before commit")

    monkeypatch.setattr(runtime.repository, "_commit", fail_commit)
    with pytest.raises(RuntimeError):
        if operation == "create":
            runtime.application.create(
                OWNER, uid(200), {"category": "career", "difficulty": "standard"}
            )
        elif operation == "answer":
            runtime.application.submit(OWNER, uid(200), session_id, payload)
        elif operation == "next":
            runtime.application.next_question(
                OWNER, uid(200), session_id, {"fromAttemptId": accepted["attemptId"]}
            )
        elif operation == "claim":
            runtime.repository.claim(accepted["evaluationId"])
        else:
            runtime.repository.finish(accepted["evaluationId"], None, "test")
    assert runtime.repository.snapshot() == before


def test_id_failure_mid_answer_leaves_no_records(runtime):
    session_id, payload = start(runtime)
    before = runtime.repository.snapshot()
    ids = iter([uid(900)])
    runtime.application.new_id = lambda: next(ids)
    with pytest.raises(StopIteration):
        runtime.application.submit(OWNER, uid(101), session_id, payload)
    assert runtime.repository.snapshot() == before


def test_detached_reads_and_question_snapshot(runtime):
    session_id, payload, accepted = submit(runtime)
    reply = runtime.application.question(OWNER, session_id)
    reply.body["question"]["question"] = "modified"
    reply.body["activeAttempt"]["status"] = "failed"
    snapshot = runtime.repository.snapshot()
    snapshot.sessions[session_id].number = 90
    runtime.application.questions[0].question = "new bank version"
    assert (
        runtime.application.question(OWNER, session_id).body["question"]["question"] != "modified"
    )
    assert runtime.application.question(OWNER, session_id).body["questionNumber"] == 1
    runtime.worker.run(accepted["evaluationId"])
    result = runtime.application.feedback(OWNER, accepted["attemptId"])
    result.body["strengths"].append("modified")
    assert (
        "modified"
        not in runtime.application.feedback(OWNER, accepted["attemptId"]).body["strengths"]
    )
    assert (
        runtime.application.feedback(OWNER, accepted["attemptId"]).body["answer"]
        == payload["answer"]
    )


def test_old_worker_does_not_overwrite_new_active(runtime):
    session_id, _, accepted = submit(runtime)
    runtime.repository.claim(accepted["evaluationId"])
    # Inject a later active pointer directly: this defensive state cannot be produced by P1 API.
    with runtime.repository._lock:
        runtime.repository._state.sessions[session_id].active = ActiveAttempt(
            attemptId=uid(900), evaluationId=uid(901), status="processing"
        )
    runtime.repository.finish(accepted["evaluationId"], None, "test")
    current = runtime.application.question(OWNER, session_id).body["activeAttempt"]
    assert current == {"attemptId": uid(900), "evaluationId": uid(901), "status": "processing"}


def test_bank_validation():
    bank = [question.wire() for question in load_questions()]
    assert len(bank) == 21
    for invalid in [bank + [bank[0]], bank[:3], [{**bank[0], "question": ""}] + bank[1:]]:
        with pytest.raises(ValueError):
            validate_bank(invalid)


def test_overlong_answer_leaves_no_records_and_key_reusable(runtime):
    session_id, payload = start(runtime)
    before = runtime.repository.snapshot()
    assert_error(
        "VALIDATION_ERROR",
        lambda: runtime.application.submit(
            OWNER, uid(101), session_id, {**payload, "answer": "あ" * 501}
        ),
    )
    assert runtime.repository.snapshot() == before
    assert (
        runtime.application.submit(
            OWNER, uid(101), session_id, {**payload, "answer": "あ" * 500}
        ).status
        == 202
    )


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_provider_score_fails_safely(runtime, score):
    _, _, accepted = submit(runtime)
    runtime.provider.behavior = lambda _: {
        "score": score,
        "summary": "",
        "strengths": [],
        "improvements": [],
    }
    runtime.worker.run(accepted["evaluationId"])
    state = runtime.application.evaluation(OWNER, accepted["evaluationId"]).body
    assert state["status"] == "failed"
    assert state["error"]["code"] == "EVALUATION_FAILED"
