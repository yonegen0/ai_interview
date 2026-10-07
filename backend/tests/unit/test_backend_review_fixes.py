"""Cross-route idempotency and accepted-bank lifecycle regressions, offline only."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError
from conftest import uid
from test_dynamodb import NOW, SnapshotClient, db, snapshot
from test_question_management import save

from interview_backend.application.service import Application
from interview_backend.assets import load_questions
from interview_backend.models.internal import BusinessError, QuestionBank
from interview_backend.models.public import Question
from interview_backend.repositories.codec import from_wire

OWNER = uid(500)
KEY = 800
FULL = {"mode": "full", "difficulty": "standard"}


def bank(last_length):
    question = load_questions()[0].wire()
    return [
        {**question, "id": uid(2000 + i), "question": "あ" * (1000 if i < 50 else last_length)}
        for i in range(51)
    ]


@pytest.mark.parametrize("adapter", ["memory", "dynamodb"])
def test_bank_without_answer_capacity_is_rejected_before_publication(runtime, adapter):
    # Historical texts are grandfathered; aggregate capacity still gates republication.
    runtime.repository._state.question_banks["CURRENT"] = QuestionBank(
        tuple(Question(**q) for q in bank(184)), 1, NOW, OWNER
    )
    runtime.repository._revisions[("QuestionBank", "", "CURRENT")] = 0
    client = SnapshotClient(snapshot(runtime.repository))
    target = runtime if adapter == "memory" else SimpleNamespace(repository=db(client))
    before = runtime.repository.snapshot()
    status, body = save(target, bank(184), 1, owner=OWNER)
    assert status == 400 and body["code"] == "QUESTION_BANK_TOO_LARGE"
    assert runtime.repository.snapshot() == before and not client.writes


@pytest.mark.parametrize("adapter", ["memory", "dynamodb"])
def test_previously_published_bank_without_capacity_cannot_start_new_session(runtime, adapter):
    questions = tuple(Question(**q) for q in bank(184))
    runtime.repository._state.question_banks["CURRENT"] = QuestionBank(questions, 1, NOW, OWNER)
    runtime.repository._revisions[("QuestionBank", "", "CURRENT")] = 0
    client = SnapshotClient(snapshot(runtime.repository))
    repository = runtime.repository if adapter == "memory" else db(client)
    app = Application(repository, load_questions(), lambda: uid(9000))
    before = runtime.repository.snapshot()
    with pytest.raises(BusinessError, match="QUESTION_BANK_TOO_LARGE"):
        app.create(OWNER, uid(801), FULL)
    assert runtime.repository.snapshot() == before and not client.writes
    target = SimpleNamespace(repository=repository)
    status, body = save(target, [q.wire() for q in questions], 1, owner=OWNER)
    assert status == 400 and body["code"] == "QUESTION_BANK_TOO_LARGE"
    assert runtime.repository.snapshot() == before and not client.writes


def test_near_limit_accepted_bank_supports_answer_evaluation_retry_and_next(runtime):
    questions = bank(30)
    runtime.repository._state.question_banks["CURRENT"] = QuestionBank(
        tuple(Question(**q) for q in questions), 1, NOW, OWNER
    )
    runtime.repository._revisions[("QuestionBank", "", "CURRENT")] = 0
    assert save(runtime, questions, 1, owner=OWNER)[0] == 200
    app = runtime.application
    sid = app.create(OWNER, uid(801), FULL).body["sessionId"]
    body = {"questionId": questions[0]["id"], "answer": "回答"}
    for key in (802, 803):
        accepted = app.submit(OWNER, uid(key), sid, body)
        assert accepted.status == 202
        runtime.worker.run(OWNER, accepted.body["evaluationId"])
        assert app.feedback(OWNER, accepted.body["attemptId"]).status == 200
    assert (
        app.next_question(OWNER, uid(804), sid, {"fromAttemptId": accepted.body["attemptId"]}).body[
            "questionNumber"
        ]
        == 2
    )

    # The production DynamoUnit also encodes a near-limit active Session successfully.
    client = SnapshotClient(snapshot(runtime.repository))
    ids = iter([uid(9001), uid(9002)])
    sdk_app = Application(db(client), load_questions(), lambda: next(ids))
    current = app.question(OWNER, sid).body["question"]
    assert (
        sdk_app.submit(OWNER, uid(805), sid, {"questionId": current["id"], "answer": "回答"}).status
        == 202
    )
    assert len(client.writes) == 1


@pytest.mark.parametrize("operation", ["create", "submit", "next"])
@pytest.mark.parametrize("first", ["api", "admin"])
def test_all_posts_share_owner_key_namespace_and_keep_successful_replays(runtime, operation, first):
    app = runtime.application
    questions = [load_questions()[0].wire()]
    if operation == "create":

        def invoke():
            return app.create(OWNER, uid(KEY), FULL)
    else:
        sid = app.create(OWNER, uid(801), FULL).body["sessionId"]
        payload = {"questionId": app.question(OWNER, sid).body["question"]["id"], "answer": "回答"}
        if operation == "submit":

            def invoke():
                return app.submit(OWNER, uid(KEY), sid, payload)
        else:
            accepted = app.submit(OWNER, uid(802), sid, payload)
            runtime.worker.run(OWNER, accepted.body["evaluationId"])

            def invoke():
                return app.next_question(
                    OWNER, uid(KEY), sid, {"fromAttemptId": accepted.body["attemptId"]}
                )

    if first == "api":
        original = invoke()
        before = runtime.repository.snapshot()
        status, body = save(runtime, questions, key=KEY, owner=OWNER)
        assert status == 409 and body["code"] == "IDEMPOTENCY_CONFLICT"
        assert runtime.repository.snapshot() == before and invoke() == original
    else:
        original = save(runtime, questions, key=KEY, owner=OWNER)
        before = runtime.repository.snapshot()
        with pytest.raises(BusinessError, match="IDEMPOTENCY_CONFLICT"):
            invoke()
        assert runtime.repository.snapshot() == before
        assert save(runtime, questions, key=KEY, owner=OWNER) == original
    version = runtime.repository.get_question_bank(load_questions())["version"]
    assert save(runtime, questions, version, KEY, "other-admin")[0] == 200


def test_concurrent_api_and_admin_same_key_only_one_commits(runtime):
    barrier = Barrier(2)

    def invoke(which):
        barrier.wait(timeout=10)
        if which == "admin":
            return save(runtime, [load_questions()[0].wire()], key=KEY, owner=OWNER)[0]
        try:
            return runtime.application.create(OWNER, uid(KEY), FULL).status
        except BusinessError as error:
            assert error.code == "IDEMPOTENCY_CONFLICT"
            return error.status

    with ThreadPoolExecutor(2) as pool:
        statuses = sorted(pool.map(invoke, ("api", "admin")))
    assert statuses in ([200, 409], [201, 409])
    state = runtime.repository.snapshot()
    assert bool(state.sessions) != bool(state.question_bank_changes)


@pytest.mark.parametrize("winner", ["api", "admin"])
def test_dynamodb_cross_route_race_checks_absence_and_returns_conflict(runtime, winner):
    before = snapshot(runtime.repository)
    questions = [load_questions()[0].wire()]
    if winner == "api":
        runtime.application.create(OWNER, uid(KEY), FULL)
    else:
        assert save(runtime, questions, key=KEY, owner=OWNER)[0] == 200
    winning_snapshot = snapshot(runtime.repository)
    client = SnapshotClient(before)

    def lost_race(_request):
        client.items = deepcopy(winning_snapshot)
        raise ClientError(
            {
                "Error": {"Code": "TransactionCanceledException"},
                "CancellationReasons": [{"Code": "ConditionalCheckFailed"}],
            },
            "TransactWriteItems",
        )

    client.on_write = lost_race
    repository = db(client, clock=lambda: NOW)
    if winner == "api":
        status, body = save(SimpleNamespace(repository=repository), questions, key=KEY, owner=OWNER)
        assert status == 409 and body["code"] == "IDEMPOTENCY_CONFLICT"
        expected = {"PK": f"USER#{OWNER}", "SK": f"IDEMPOTENCY#{uid(KEY)}"}
        key_reads = [r for _, r in client.reads if r.get("ProjectionExpression")]
        assert len(key_reads) == 2
        assert all(r["ProjectionExpression"] == "#pk, #sk" for r in key_reads)
    else:
        app = Application(repository, load_questions(), lambda: uid(9000))
        with pytest.raises(BusinessError, match="IDEMPOTENCY_CONFLICT"):
            app.create(OWNER, uid(KEY), FULL)
        expected = {"PK": "SYSTEM#QUESTION_BANK", "SK": f"OP#{OWNER}#{uid(KEY)}"}
    checks = [
        a["ConditionCheck"] for a in client.writes[0]["TransactItems"] if "ConditionCheck" in a
    ]
    matching = [c for c in checks if from_wire(c["Key"]) == expected]
    assert len(matching) == 1 and matching[0]["ConditionExpression"] == "attribute_not_exists(PK)"
    assert len(client.writes) == 1 and client.items == winning_snapshot


@pytest.mark.parametrize("version", [0, 0.0, -0.0])
def test_integer_version_spellings_share_fingerprint_and_replay(runtime, version):
    questions = [load_questions()[0].wire()]
    original = save(runtime, questions, owner=OWNER)
    assert save(runtime, questions, version=version, owner=OWNER) == original
    assert save(runtime, [load_questions()[1].wire()], 1.0, 801, OWNER)[0] == 200
    assert save(runtime, questions, version=version, owner=OWNER) == original
