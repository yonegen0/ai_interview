"""Storage-independent business assertions, also collected for P4 DynamoDB."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from conftest import uid

from interview_backend.models.internal import BusinessError


def start(runtime):
    app = runtime.application
    sid = app.create("owner", uid(100), {"category": "career", "difficulty": "standard"}).body[
        "sessionId"
    ]
    payload = {
        "questionId": app.question("owner", sid).body["question"]["id"],
        "answer": " \ud800\n🙂 ",
    }
    return sid, payload


def test_shared_ownership_replay_and_get_purity(contract_runtime):
    runtime = contract_runtime
    app = runtime.application
    sid, payload = start(runtime)
    accepted = app.submit("owner", uid(101), sid, payload)
    eid, aid = accepted.body["evaluationId"], accepted.body["attemptId"]
    for _ in range(3):
        assert app.evaluation("owner", eid).body["status"] == "processing"
        app.question("owner", sid)
        with pytest.raises(BusinessError) as pending:
            app.feedback("owner", aid)
        assert pending.value.status == 409
    assert runtime.provider.calls == 0 and not runtime.publisher.events
    runtime.worker.run("owner", eid)
    assert app.feedback("owner", aid).body["answer"] == payload["answer"]
    app.next_question("owner", uid(102), sid, {"fromAttemptId": aid})
    assert app.submit("owner", uid(101), sid, payload) == accepted
    for method, identifier in ((app.question, sid), (app.evaluation, eid), (app.feedback, aid)):
        with pytest.raises(BusinessError) as error:
            method("other", identifier)
        assert error.value.status == 404
    with pytest.raises(BusinessError) as conflict:
        app.submit("owner", uid(101), sid, {**payload, "answer": "different"})
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize("same_key", [True, False])
def test_shared_concurrent_answers(contract_runtime, same_key):
    app = contract_runtime.application
    sid, payload = start(contract_runtime)
    barrier = Barrier(2)

    def submit(n):
        barrier.wait(timeout=10)
        try:
            return app.submit("owner", uid(101 if same_key else 101 + n), sid, payload)
        except BusinessError as error:
            return error.status

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(submit, range(2)))
    if same_key:
        assert results[0] == results[1]
    else:
        assert sum(r == 409 for r in results) == 1


@pytest.mark.parametrize("operation", ["create", "next"])
def test_shared_concurrent_post_replay(contract_runtime, operation):
    runtime = contract_runtime
    app = runtime.application
    sid, payload = start(runtime)
    if operation == "next":
        reply = app.submit("owner", uid(101), sid, payload)
        runtime.worker.run("owner", reply.body["evaluationId"])
    barrier = Barrier(2)

    def invoke(_):
        barrier.wait(timeout=10)
        if operation == "create":
            return app.create("owner", uid(110), {"category": "career", "difficulty": "standard"})
        return app.next_question("owner", uid(110), sid, {"fromAttemptId": reply.body["attemptId"]})

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(invoke, range(2)))
    assert results[0] == results[1]


def test_shared_answer_next_race_is_serializable(contract_runtime):
    runtime = contract_runtime
    app = runtime.application
    sid, payload = start(runtime)
    reply = app.submit("owner", uid(101), sid, payload)
    runtime.worker.run("owner", reply.body["evaluationId"])
    barrier = Barrier(2)

    def invoke(action):
        barrier.wait(timeout=10)
        try:
            if action == "next":
                return app.next_question(
                    "owner", uid(102), sid, {"fromAttemptId": reply.body["attemptId"]}
                ).status
            return app.submit("owner", uid(103), sid, payload).status
        except BusinessError as error:
            return error.status

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(invoke, ("next", "answer")))
    assert sorted(results) in ([200, 409], [202, 409])
