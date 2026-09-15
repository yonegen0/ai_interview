"""SDK boundary tests: scripted snapshots, never a DynamoDB emulator."""

from copy import deepcopy
from dataclasses import replace
from itertools import count

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError
from botocore.stub import ANY, Stubber
from conftest import uid

from interview_backend.application.service import Application
from interview_backend.assets import load_questions
from interview_backend.evaluation.provider import PROMPT_VERSION
from interview_backend.models.internal import (
    BusinessError,
    ExecutionConfig,
    RetryExhausted,
    StorageFormatError,
    StorageUnavailable,
)
from interview_backend.repositories.codec import PARTITIONS, decode, encode, from_wire, key, to_wire
from interview_backend.repositories.domain import ref
from interview_backend.repositories.dynamodb import DynamoDBRepository
from interview_backend.repositories.memory import MemoryRepository

NOW = 1789171200000
OWNER = "synthetic-user"
CONFIG = ExecutionConfig(prompt_version=PROMPT_VERSION)


def prepared():
    repo = MemoryRepository(lambda: NOW)
    ids = count(1)
    app = Application(repo, load_questions(), lambda: uid(next(ids)))
    sid = app.create(OWNER, uid(100), {"category": "career", "difficulty": "standard"}).body[
        "sessionId"
    ]
    qid = app.question(OWNER, sid).body["question"]["id"]
    payload = {"questionId": qid, "answer": "  answer\n\ud800"}
    before = snapshot(repo)
    reply = app.submit(OWNER, uid(101), sid, payload)
    return repo, app, sid, payload, reply, before


def snapshot(repo):
    state = repo.snapshot()
    result = {}
    for kind, records in (
        ("Session", state.sessions),
        ("Attempt", state.attempts),
        ("Evaluation", state.evaluations),
        ("Dispatch", state.dispatches),
        ("IdempotencyRecord", state.requests),
        ("RecoveryCursor", state.cursors),
    ):
        for record in records.values():
            identifier = (
                record.key
                if kind == "IdempotencyRecord"
                else record.partition.removeprefix("WORK#")
                if kind == "RecoveryCursor"
                else record.id
            )
            reference = ref(kind, getattr(record, "owner", ""), identifier)
            item = encode(kind, record, repo._revisions[reference])
            result[(item["PK"], item["SK"])] = to_wire(item)
    return result


class SnapshotClient:
    """Reads only a supplied immutable snapshot; writes are captured, not evaluated."""

    def __init__(self, items):
        self.items = deepcopy(items)
        self.writes, self.reads = [], []
        self.on_write = lambda request: {}

    def get_item(self, **request):
        self.reads.append(("get", deepcopy(request)))
        assert request["ConsistentRead"] is True
        k = from_wire(request["Key"])
        item = self.items.get((k["PK"], k["SK"]))
        return {"Item": deepcopy(item)} if item else {}

    def transact_get_items(self, **request):
        self.reads.append(("transact_get", deepcopy(request)))
        responses = []
        for action in request["TransactItems"]:
            k = from_wire(action["Get"]["Key"])
            item = self.items.get((k["PK"], k["SK"]))
            responses.append({"Item": deepcopy(item)} if item else {})
        return {"Responses": responses}

    def transact_write_items(self, **request):
        self.writes.append(deepcopy(request))
        return self.on_write(request)


def db(client, clock=lambda: NOW, **kwargs):
    return DynamoDBRepository(client, "test-table", clock, sleeper=lambda _: None, **kwargs)


def written(client):
    actions = client.writes[-1]["TransactItems"]
    keys = []
    result = {}
    for action in actions:
        name, body = next(iter(action.items()))
        item = from_wire(body["Item"] if name == "Put" else body["Key"])
        keys.append((item["PK"], item["SK"]))
        if name == "Put":
            record, _ = decode(item)
            result[item["kind"]] = record
        if "ExpressionAttributeValues" in body:
            values = from_wire(body["ExpressionAttributeValues"])
            assert values[":v"] == 1 and type(values[":r"]) is int
        else:
            assert body["ConditionExpression"] == "attribute_not_exists(PK)"
    assert len(keys) == len(set(keys)), "one Action per item"
    return result


def test_t01_and_t02_sdk_shape_and_five_item_acceptance():
    memory, _, sid, payload, _, before = prepared()
    client = SnapshotClient(before)
    repository = db(client)
    ids = iter([uid(2), uid(3)])
    reply = repository.accept_once(
        OWNER,
        uid(101),
        Application._fingerprint(f"/sessions/{sid}/answers", payload),
        sid,
        payload["questionId"],
        payload["answer"],
        lambda: next(ids),
    )
    assert reply.status == 202
    records = written(client)
    assert set(records) == {"Session", "Attempt", "Evaluation", "Dispatch", "IdempotencyRecord"}
    assert records["IdempotencyRecord"].reply == reply
    assert records["Session"].version == 1 and records["Dispatch"].generation == 1
    assert all(record.created_at == NOW for kind, record in records.items() if kind != "Session")
    assert records["Attempt"].answer == payload["answer"]
    empty = SnapshotClient({})
    db(empty).create_once(OWNER, uid(100), "a" * 64, load_questions()[:3], lambda: uid(1))
    assert set(written(empty)) == {"Session", "IdempotencyRecord"}


def test_t02_commit_response_loss_replays_without_second_write():
    memory, _, sid, payload, expected, before = prepared()
    client = SnapshotClient(before)

    def lost(request):
        client.items = snapshot(memory)  # Explicit post-commit fixture, no transaction simulation.
        raise EndpointConnectionError(endpoint_url="http://synthetic")

    client.on_write = lost
    app = Application(db(client), load_questions(), iter([uid(2), uid(3)]).__next__)
    assert app.submit(OWNER, uid(101), sid, payload) == expected
    assert len(client.writes) == 1


def test_identical_retry_token_and_bounded_unknown():
    _, _, sid, payload, _, before = prepared()
    client = SnapshotClient(before)
    client.on_write = lambda _: (_ for _ in ()).throw(
        EndpointConnectionError(endpoint_url="http://synthetic")
    )
    app = Application(db(client), load_questions(), iter([uid(2), uid(3)]).__next__)
    with pytest.raises(StorageUnavailable):
        app.submit(OWNER, uid(101), sid, payload)
    assert len(client.writes) == 3
    assert client.writes[0] == client.writes[1] == client.writes[2]


def test_condition_conflict_fresh_state_is_business_conflict():
    memory, _, sid, payload, _, before = prepared()
    client = SnapshotClient(before)

    def conflict(request):
        client.items = snapshot(memory)
        raise ClientError(
            {
                "Error": {"Code": "TransactionCanceledException"},
                "CancellationReasons": [{"Code": "ConditionalCheckFailed"}],
            },
            "TransactWriteItems",
        )

    client.on_write = conflict
    app = Application(db(client), load_questions(), iter([uid(7), uid(8)]).__next__)
    with pytest.raises(BusinessError) as exc:
        app.submit(OWNER, uid(102), sid, payload)
    assert exc.value.code == "SESSION_STATE_CONFLICT"
    assert len(client.writes) == 1


@pytest.mark.parametrize(
    "operation",
    [
        "claim",
        "start",
        "finish",
        "acquire",
        "confirm",
        "fail",
        "queued",
        "unstarted",
        "unknown",
        "deadline",
    ],
)
def test_t04_through_t13_actions(operation):
    memory, _, sid, _, accepted, _ = prepared()
    eid = accepted.body["evaluationId"]
    lease = delivery = None
    if operation in {"start", "finish", "unstarted", "unknown"}:
        lease = memory.claim(OWNER, eid, 1, uid(800), CONFIG).lease
    if operation in {"finish", "unknown"}:
        memory.mark_call_started(lease)
    if operation in {"confirm", "fail", "queued"}:
        delivery = memory.acquire_delivery(OWNER, eid, 1, uid(801)).delivery
    if operation == "queued":
        memory.confirm_delivery(delivery)
    clock = NOW + (
        900000
        if operation == "deadline"
        else 120000
        if operation == "queued"
        else 90000
        if operation in {"unstarted", "unknown"}
        else 0
    )
    client = SnapshotClient(snapshot(memory))
    repository = db(client, lambda: clock)
    if operation == "claim":
        assert repository.claim(OWNER, eid, 1, uid(800), CONFIG).status == "acquired"
    elif operation == "start":
        assert repository.mark_call_started(lease).status == "applied"
    elif operation == "finish":
        assert repository.finish(lease).status == "applied"
    elif operation == "acquire":
        assert repository.acquire_delivery(OWNER, eid, 1, uid(801)).status == "acquired"
    elif operation == "confirm":
        assert repository.confirm_delivery(delivery).status == "applied"
    elif operation == "fail":
        assert repository.fail_delivery(delivery, NOW + 5000).status == "applied"
    else:
        repository.recover(OWNER, eid)
    records = written(client)
    expected = {
        "claim": {"Evaluation", "Dispatch"},
        "start": {"Evaluation"},
        "finish": {"Evaluation", "Dispatch", "Session"},
        "acquire": {"Dispatch"},
        "confirm": {"Dispatch"},
        "fail": {"Dispatch"},
        "queued": {"Dispatch"},
        "unstarted": {"Evaluation", "Dispatch"},
        "unknown": {"Evaluation", "Dispatch", "Session"},
        "deadline": {"Evaluation", "Dispatch", "Session"},
    }
    assert set(records) == expected[operation]
    assert any(method == "transact_get" for method, _ in client.reads)
    if operation in {"queued", "unstarted"}:
        assert records["Dispatch"].generation == 2


def test_t14_cursor_cas_and_lost_ack():
    memory = MemoryRepository(lambda: NOW)
    initial = memory.get_cursor(PARTITIONS[0])
    target = replace(initial.cursor, updated_at=NOW + 1)
    memory.save_cursor(initial, target)
    client = SnapshotClient({})

    def lost(request):
        client.items = snapshot(memory)
        raise EndpointConnectionError(endpoint_url="http://synthetic")

    client.on_write = lost
    # False is safe: caller stops; the durable checkpoint is preserved.
    assert db(client).save_cursor(initial, target) is False
    assert set(written(client)) == {"RecoveryCursor"}


def test_start_commit_loss_confirms_same_execution():
    memory, _, _, _, accepted, _ = prepared()
    eid = accepted.body["evaluationId"]
    lease = memory.claim(OWNER, eid, 1, uid(800), CONFIG).lease
    client = SnapshotClient(snapshot(memory))
    memory.mark_call_started(lease)

    def lost(request):
        client.items = snapshot(memory)
        raise EndpointConnectionError(endpoint_url="http://synthetic")

    client.on_write = lost
    assert db(client).mark_call_started(lease).status == "confirmed_same_execution"
    assert len(client.writes) == 1


@pytest.fixture
def sdk():
    return boto3.client(
        "dynamodb",
        region_name="us-east-1",
        aws_access_key_id="synthetic",
        aws_secret_access_key="synthetic",
        config=Config(retries={"total_max_attempts": 1}),
    )


def test_stubber_strong_get_and_query_continuation(sdk):
    memory, _, sid, _, _, _ = prepared()
    item = snapshot(memory)[(f"USER#{OWNER}", f"SESSION#{sid}")]
    cursor = {
        "PK": f"USER#{OWNER}",
        "SK": f"DISPATCH#{uid(3)}",
        "work_pk": PARTITIONS[0],
        "work_sk": f"{NOW:013d}#{uid(3)}",
    }
    with Stubber(sdk) as stub:
        stub.add_response(
            "get_item",
            {"Item": item},
            {
                "TableName": "test-table",
                "Key": to_wire(key("Session", OWNER, sid)),
                "ConsistentRead": True,
            },
        )
        stub.add_response(
            "query",
            {"Items": [to_wire(cursor)], "LastEvaluatedKey": to_wire(cursor)},
            {
                "TableName": "test-table",
                "IndexName": "WorkIndex",
                "KeyConditionExpression": "work_pk = :p AND work_sk <= :cutoff",
                "ExpressionAttributeValues": to_wire(
                    {":p": PARTITIONS[0], ":cutoff": f"{NOW:013d}#~"}
                ),
                "Limit": 100,
                "ScanIndexForward": True,
                "ExclusiveStartKey": to_wire(cursor),
            },
        )
        repository = db(sdk)
        assert repository.get_session(OWNER, sid).status == 200
        page = repository.due_candidates(PARTITIONS[0], NOW, cursor)
        assert page.continuation == cursor and len(page.candidates) == 1
        stub.assert_no_pending_responses()


def test_stubber_real_transaction_request_validation(sdk):
    with Stubber(sdk) as stub:
        stub.add_response(
            "get_item",
            {},
            {
                "TableName": "test-table",
                "Key": to_wire(key("IdempotencyRecord", OWNER, uid(100))),
                "ConsistentRead": True,
            },
        )
        stub.add_response(
            "transact_write_items", {}, {"TransactItems": ANY, "ClientRequestToken": ANY}
        )
        assert (
            db(sdk)
            .create_once(OWNER, uid(100), "a" * 64, load_questions()[:3], lambda: uid(1))
            .status
            == 201
        )
        stub.assert_no_pending_responses()


@pytest.mark.parametrize(
    "code,expected",
    [
        ("ValidationException", StorageFormatError),
        ("ProvisionedThroughputExceededException", StorageUnavailable),
        ("AccessDeniedException", StorageUnavailable),
    ],
)
def test_sdk_failure_not_business_409(sdk, code, expected):
    with Stubber(sdk) as stub:
        for _ in range(1 if expected is StorageFormatError else 4):
            stub.add_client_error("get_item", code, "SECRET")
        with pytest.raises(expected) as exc:
            db(sdk).get_session(OWNER, uid(1))
        assert "SECRET" not in str(exc.value)


def test_retry_budget_prevents_request():
    client = SnapshotClient({})
    ticks = iter([0, 4.7])
    with pytest.raises(RetryExhausted):
        db(client, monotonic_clock=lambda: next(ticks)).get_session(OWNER, uid(1))
    assert not client.reads


@pytest.mark.parametrize("phase", ["claim", "acquire", "finish", "next"])
def test_commit_ack_loss_for_internal_and_next(phase):
    from interview_backend.evaluation.provider import FakeProvider
    from interview_backend.evaluation.worker import Worker

    memory, app, sid, _, reply, _ = prepared()
    eid = reply.body["evaluationId"]
    if phase == "finish":
        lease = memory.claim(OWNER, eid, 1, uid(800), CONFIG).lease
        memory.mark_call_started(lease)
    if phase == "next":
        Worker(memory, FakeProvider(), clock=lambda: NOW).run(OWNER, eid)
    client = SnapshotClient(snapshot(memory))
    if phase == "claim":
        memory.claim(OWNER, eid, 1, uid(800), CONFIG)

        def operation(repo):
            return repo.claim(OWNER, eid, 1, uid(800), CONFIG)
    elif phase == "acquire":
        memory.acquire_delivery(OWNER, eid, 1, uid(801))

        def operation(repo):
            return repo.acquire_delivery(OWNER, eid, 1, uid(801))
    elif phase == "finish":
        memory.finish(lease)

        def operation(repo):
            return repo.finish(lease)
    else:
        payload = {"fromAttemptId": reply.body["attemptId"]}
        expected = app.next_question(OWNER, uid(102), sid, payload)

        def operation(repo):
            return repo.next_once(
                OWNER,
                uid(102),
                Application._fingerprint(f"/sessions/{sid}/questions/next", payload),
                sid,
                reply.body["attemptId"],
            )

    def lost(request):
        client.items = snapshot(memory)
        raise EndpointConnectionError(endpoint_url="synthetic")

    client.on_write = lost
    result = operation(db(client))
    assert len(client.writes) == 1
    if phase == "next":
        assert result == expected
    else:
        assert result.status == ("already_terminal" if phase == "finish" else "acquired")


def test_finish_uses_session_condition_when_active_differs():
    from interview_backend.models.public import ActiveAttempt

    memory, _, sid, _, reply, _ = prepared()
    eid = reply.body["evaluationId"]
    lease = memory.claim(OWNER, eid, 1, uid(800), CONFIG).lease
    with memory._lock:
        memory._state.sessions[sid].active = ActiveAttempt(
            attemptId=uid(901), evaluationId=uid(902), status="processing"
        )
    client = SnapshotClient(snapshot(memory))
    db(client).finish(lease, reason="PREPARATION_FAILED")
    assert set(written(client)) == {"Evaluation", "Dispatch"}
    checks = [
        from_wire(a["ConditionCheck"]["Key"])["SK"]
        for a in client.writes[-1]["TransactItems"]
        if "ConditionCheck" in a
    ]
    assert checks == [f"SESSION#{sid}"]


def test_changed_snapshot_changes_token_but_keeps_request_ids():
    memory, _, sid, payload, _, before = prepared()
    client = SnapshotClient(before)

    def conflict_once(request):
        if len(client.writes) == 1:
            original = from_wire(client.items[(f"USER#{OWNER}", f"SESSION#{sid}")])
            original["rev"] += 1
            client.items[(original["PK"], original["SK"])] = to_wire(original)
            raise ClientError(
                {
                    "Error": {"Code": "TransactionCanceledException"},
                    "CancellationReasons": [{"Code": "ConditionalCheckFailed"}],
                },
                "TransactWriteItems",
            )
        return {}

    client.on_write = conflict_once
    app = Application(db(client), load_questions(), iter([uid(2), uid(3)]).__next__)
    assert app.submit(OWNER, uid(101), sid, payload).status == 202
    assert client.writes[0]["ClientRequestToken"] != client.writes[1]["ClientRequestToken"]
    records = written(client)
    assert records["Attempt"].id == uid(2) and records["Evaluation"].id == uid(3)


def test_time_rechecked_before_temporal_write():
    memory, _, _, _, reply, _ = prepared()
    eid = reply.body["evaluationId"]
    lease = memory.claim(OWNER, eid, 1, uid(800), CONFIG).lease
    client = SnapshotClient(snapshot(memory))
    clock = iter([NOW, NOW + 90000])
    assert db(client, clock=lambda: next(clock)).mark_call_started(lease).status == "lost_lease"
    assert not client.writes


def test_invocation_budget_wins_over_repository_budget():
    from interview_backend.repositories.budget import storage_budget

    client = SnapshotClient({})
    with storage_budget(lambda: 399), pytest.raises(RetryExhausted):
        db(client).get_session(OWNER, uid(1))
    assert not client.reads


def test_same_key_commits_between_idempotency_and_session_read():
    memory, _, sid, payload, expected, before = prepared()
    client = SnapshotClient(before)
    original = client.get_item

    def interleaved(**request):
        if from_wire(request["Key"])["SK"] == f"SESSION#{sid}":
            client.items = snapshot(memory)
        return original(**request)

    client.get_item = interleaved
    app = Application(db(client), load_questions(), lambda: uid(900))
    assert app.submit(OWNER, uid(101), sid, payload) == expected
    assert not client.writes


def test_worker_retries_only_same_feedback_save():
    from interview_backend.evaluation.provider import FakeProvider
    from interview_backend.evaluation.worker import Worker

    memory, _, _, _, reply, _ = prepared()
    eid = reply.body["evaluationId"]
    client = SnapshotClient(snapshot(memory))
    lease = memory.claim(OWNER, eid, 1, uid(800), CONFIG).lease
    claimed = snapshot(memory)
    memory.mark_call_started(lease)
    started = snapshot(memory)

    def responses(request):
        stage = len(client.writes)
        if stage == 1:
            client.items = claimed
        elif stage == 2:
            client.items = started
        elif stage == 3:
            raise EndpointConnectionError(endpoint_url="synthetic-finish-failure")
        return {}

    client.on_write = responses
    provider = FakeProvider()
    worker = Worker(db(client), provider, lambda: NOW, new_execution_id=lambda: uid(800))
    assert worker.run(OWNER, eid)
    assert provider.calls == 1 and len(client.writes) == 4
    assert client.writes[2] == client.writes[3]
    records = written(client)
    assert records["Evaluation"].status == "completed"


def test_recovery_reclassifies_after_started_wins_conflict():
    memory, _, _, _, reply, _ = prepared()
    eid = reply.body["evaluationId"]
    lease = memory.claim(OWNER, eid, 1, uid(800), CONFIG).lease
    client = SnapshotClient(snapshot(memory))
    memory.mark_call_started(lease)

    def conflict(request):
        if len(client.writes) == 1:
            client.items = snapshot(memory)
            raise ClientError(
                {
                    "Error": {"Code": "TransactionCanceledException"},
                    "CancellationReasons": [{"Code": "ConditionalCheckFailed"}],
                },
                "TransactWriteItems",
            )
        return {}

    client.on_write = conflict
    assert db(client, lambda: NOW + 90000).recover(OWNER, eid).status == "failed"
    assert written(client)["Evaluation"].failure_reason == "OUTCOME_UNKNOWN"
    assert written(client)["Dispatch"].generation == 1
