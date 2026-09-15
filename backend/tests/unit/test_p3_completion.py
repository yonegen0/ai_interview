"""Regression evidence for the three P3 completion review findings."""

import pytest
from test_dynamodb import CONFIG, NOW, OWNER, SnapshotClient, db, prepared, snapshot, uid

from interview_backend.evaluation.dispatch import Dispatcher, FakePublisher, Recovery
from interview_backend.evaluation.provider import FakeProvider
from interview_backend.evaluation.worker import Worker
from interview_backend.models.internal import IntegrityError
from interview_backend.repositories.codec import to_wire
from interview_backend.repositories.dynamodb import DynamoUnit


@pytest.mark.parametrize(
    "field", ["attemptId", "sessionId", "question", "questionNumber", "answer"]
)
def test_feedback_snapshot_mismatch_rejected(field):
    memory, _, _, _, reply, _ = prepared()
    eid = reply.body["evaluationId"]
    Worker(memory, FakeProvider(), clock=lambda: NOW).run(OWNER, eid)
    e = memory._state.evaluations[eid]
    values = {
        "attemptId": uid(998),
        "sessionId": uid(999),
        "questionNumber": 2,
        "question": e.feedback.question.model_copy(update={"question": "different"}),
        "answer": "different synthetic answer",
    }
    e.feedback = e.feedback.model_copy(update={field: values[field]})
    client = SnapshotClient(snapshot(memory))
    with pytest.raises(IntegrityError):
        db(client).get_feedback(OWNER, reply.body["attemptId"])
    assert not client.writes


def test_feedback_mismatch_is_fixed_http_500_without_side_effects(capsys):
    import json

    from interview_backend.api.handler import Handler
    from interview_backend.application.service import Application
    from interview_backend.assets import load_questions
    from interview_backend.demo import demo_event

    memory, _, sid, _, reply, _ = prepared()
    eid = reply.body["evaluationId"]
    provider = FakeProvider()
    Worker(memory, provider, clock=lambda: NOW).run(OWNER, eid)
    memory.next_once(OWNER, uid(102), "a" * 64, sid, reply.body["attemptId"])
    assert memory.get_feedback(OWNER, reply.body["attemptId"]).status == 200
    memory._state.evaluations[eid].feedback.answer = "different"
    client = SnapshotClient(snapshot(memory))
    handler = Handler(Application(db(client), load_questions(), lambda: uid(999)))
    result = handler(
        demo_event("GET", f"/attempts/{reply.body['attemptId']}/feedback", owner=OWNER)
    )
    assert result["statusCode"] == 500
    assert json.loads(result["body"]) == {
        "code": "INTERNAL_SERVER_ERROR",
        "message": "An internal error occurred.",
    }
    assert not client.writes and provider.calls == 1
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("phase", ["claim", "acquire", "fail"])
def test_remaining_temporal_operations_expire_before_send(monkeypatch, phase):
    memory, _, _, _, reply, _ = prepared()
    eid = reply.body["evaluationId"]
    if phase == "fail":
        delivery = memory.acquire_delivery(OWNER, eid, 1, uid(800)).delivery
    now = [NOW + (44999 if phase == "fail" else 899999)]
    client = SnapshotClient(snapshot(memory))
    original = DynamoUnit.actions

    def delayed(unit):
        result = original(unit)
        now[0] += 1
        return result

    monkeypatch.setattr(DynamoUnit, "actions", delayed)
    repo = db(client, clock=lambda: now[0])
    if phase == "claim":
        result = repo.claim(OWNER, eid, 1, uid(800), CONFIG)
    elif phase == "acquire":
        result = repo.acquire_delivery(OWNER, eid, 1, uid(800))
    else:
        result = repo.fail_delivery(delivery, now[0] + 5000)
    assert result.status == ("obsolete" if phase == "fail" else "deadline_due")
    assert not client.writes


def test_assembly_consumes_last_storage_budget(monkeypatch):
    from interview_backend.models.internal import RetryExhausted
    from interview_backend.repositories.budget import storage_budget

    memory, _, _, _, reply, _ = prepared()
    lease = memory.claim(OWNER, reply.body["evaluationId"], 1, uid(800), CONFIG).lease
    client = SnapshotClient(snapshot(memory))
    remaining = [1000]
    original = DynamoUnit.actions

    def delayed(unit):
        result = original(unit)
        remaining[0] = 399
        return result

    monkeypatch.setattr(DynamoUnit, "actions", delayed)
    with storage_budget(lambda: remaining[0]), pytest.raises(RetryExhausted):
        db(client).finish(lease)
    assert not client.writes


@pytest.mark.parametrize("malformation", ["key", "continuation"])
def test_sdk_query_retains_valid_entries_with_invalid_metadata(malformation):
    from interview_backend.models.internal import CorruptCandidate
    from interview_backend.repositories.codec import PARTITIONS

    client = SnapshotClient({})
    valid = {
        "PK": "USER#synthetic",
        "SK": f"DISPATCH#{uid(1)}",
        "work_pk": PARTITIONS[0],
        "work_sk": f"{NOW:013d}#{uid(1)}",
    }
    response = {"Items": [to_wire(valid)]}
    if malformation == "key":
        response["Items"].append(to_wire({"SK": "bad"}))
    else:
        response["LastEvaluatedKey"] = to_wire({"SK": "bad"})
    client.query = lambda **kwargs: response
    page = db(client).due_candidates(PARTITIONS[0], NOW)
    assert page.candidates[0].evaluation_id == uid(1)
    if malformation == "key":
        assert isinstance(page.candidates[1], CorruptCandidate)
        assert page.candidates[1].key is None
    else:
        assert not page.continuation_valid


def test_memory_corrupt_candidate_is_revisited_next_sweep():
    from interview_backend.repositories.codec import PARTITIONS

    memory, _, _, _, reply, _ = prepared()
    eid = reply.body["evaluationId"]
    memory._state.dispatches[eid].generation = 0
    before = memory.snapshot()
    metrics = []
    publisher = FakePublisher()
    recovery = Recovery(
        memory, Dispatcher(memory, publisher), clock=lambda: NOW, metric=metrics.append
    )
    recovery.tick(remaining_ms=lambda: 30000)
    recovery.tick(remaining_ms=lambda: 30000)
    assert metrics == ["IntegrityError", "IntegrityError"]
    assert memory.get_cursor(PARTITIONS[0]).cursor.after is None
    assert memory.snapshot().dispatches == before.dispatches
    assert not publisher.events


@pytest.mark.parametrize("corruption", ["first", "middle", "last", "all"])
def test_corrupt_pages_over_100_same_sort_key_owners(corruption, monkeypatch):
    from interview_backend.models.internal import Candidate, CandidatePage, CorruptCandidate
    from interview_backend.repositories.codec import PARTITIONS
    from interview_backend.repositories.memory import MemoryRepository

    repo = MemoryRepository(lambda: NOW)
    handled, metrics, queried = [], [], []

    def query(partition, cutoff, after):
        queried.append(partition)
        start = 0 if after is None else int(after["PK"].rsplit("-", 1)[1]) + 1
        candidates = []
        for n in range(start, min(start + 100, 103)):
            prefix = "EVALUATION" if partition == PARTITIONS[2] else "DISPATCH"
            key = {
                "PK": f"USER#synthetic-{n:03d}",
                "SK": f"{prefix}#{uid(1)}",
                "work_pk": partition,
                "work_sk": f"{NOW:013d}#{uid(1)}",
            }
            bad = corruption == "all" or n == {"first": 0, "middle": 50, "last": 102}.get(
                corruption
            )
            candidates.append(
                CorruptCandidate(key) if bad else Candidate(key["PK"][5:], uid(1), key)
            )
        return CandidatePage(tuple(candidates), candidates[-1].key if start == 0 else None)

    monkeypatch.setattr(repo, "due_candidates", query)
    monkeypatch.setattr(repo, "recover", lambda owner, eid: handled.append((owner, eid)))
    monkeypatch.setattr(repo, "dispatch_event", lambda *args: None)
    Recovery(
        repo, Dispatcher(repo, FakePublisher()), clock=lambda: NOW, metric=metrics.append
    ).tick(remaining_ms=lambda: 30000)
    assert queried == list(PARTITIONS) * 2
    assert len(metrics) == (309 if corruption == "all" else 3)
    assert len(handled) == (0 if corruption == "all" else 306)


def test_corrupt_candidate_checkpoint_at_five_seconds(monkeypatch):
    from interview_backend.models.internal import CandidatePage, CorruptCandidate
    from interview_backend.repositories.codec import PARTITIONS
    from interview_backend.repositories.memory import MemoryRepository

    repo = MemoryRepository(lambda: NOW)
    raw = {
        "PK": "USER#synthetic",
        "SK": "DISPATCH#bad",
        "work_pk": PARTITIONS[0],
        "work_sk": f"{NOW:013d}#bad",
    }
    remaining = [30000]
    monkeypatch.setattr(
        repo,
        "due_candidates",
        lambda *args: CandidatePage((CorruptCandidate(raw), CorruptCandidate(raw)), None),
    )

    def metric(_):
        remaining[0] = 5000

    Recovery(repo, Dispatcher(repo, FakePublisher()), clock=lambda: NOW, metric=metric).tick(
        remaining_ms=lambda: remaining[0]
    )
    assert repo.get_cursor(PARTITIONS[0]).cursor.after == raw


@pytest.mark.parametrize("stage", ["actions", "signature", "token"])
@pytest.mark.parametrize(
    "phase", ["start", "finish", "confirm", "queued", "unstarted", "unknown", "deadline"]
)
def test_time_guard_after_all_assembly_stages(monkeypatch, stage, phase):
    from interview_backend.repositories import dynamodb

    memory, _, _, _, reply, _ = prepared()
    eid = reply.body["evaluationId"]
    if phase in {"start", "finish", "unstarted", "unknown"}:
        lease = memory.claim(OWNER, eid, 1, uid(800), CONFIG).lease
        if phase == "unknown":
            memory.mark_call_started(lease)
    if phase in {"confirm", "queued"}:
        delivery = memory.acquire_delivery(OWNER, eid, 1, uid(801)).delivery
        if phase == "queued":
            memory.confirm_delivery(delivery)
    deadlines = {
        "start": NOW + 40000,
        "finish": NOW + 89999,
        "confirm": NOW + 44999,
        "queued": NOW + 899999,
        "unstarted": NOW + 899999,
        "unknown": NOW + 899999,
        "deadline": NOW + 900000,
    }
    now = [deadlines[phase]]
    client = SnapshotClient(snapshot(memory))

    def advance():
        now[0] += -1 if phase == "deadline" else 1

    if stage == "actions":
        original = DynamoUnit.actions

        def delayed(unit):
            result = original(unit)
            advance()
            return result

        monkeypatch.setattr(DynamoUnit, "actions", delayed)
    elif stage == "signature":
        original = dynamodb.canonical

        def delayed(value):
            result = original(value)
            advance()
            return result

        monkeypatch.setattr(dynamodb, "canonical", delayed)

    def token():
        if stage == "token":
            advance()
        return uid(900)

    repository = db(client, clock=lambda: now[0], token_factory=token)
    if phase == "start":
        assert repository.mark_call_started(lease).status == "lost_lease"
    elif phase == "finish":
        assert repository.finish(lease).status == "lost_lease"
    elif phase == "confirm":
        assert repository.confirm_delivery(delivery).status == "obsolete"
    else:
        result = repository.recover(OWNER, eid)
        assert result.status == ("unchanged" if phase == "deadline" else "failed")
    assert len(client.writes) == (1 if phase in {"queued", "unstarted", "unknown"} else 0)


@pytest.mark.parametrize("kind", ["bad_id", "missing_key", "bad_continuation", "bad_cursor"])
def test_recovery_corruption_is_partition_local(kind, monkeypatch):
    from interview_backend.models.internal import Candidate, CandidatePage, CorruptCandidate
    from interview_backend.repositories.codec import PARTITIONS
    from interview_backend.repositories.memory import MemoryRepository

    repository = MemoryRepository(lambda: NOW)
    seen, handled, metrics = [], [], []

    def key(n):
        return {
            "PK": "USER#synthetic",
            "SK": f"DISPATCH#{uid(n)}",
            "work_pk": PARTITIONS[0],
            "work_sk": f"{NOW:013d}#{uid(n)}",
        }

    first, last = Candidate("synthetic", uid(1), key(1)), Candidate("synthetic", uid(3), key(3))
    corrupt_key = dict(key(2), SK="DISPATCH#bad", work_sk=f"{NOW:013d}#bad")

    def query(partition, cutoff, after):
        seen.append(partition)
        if partition != PARTITIONS[0]:
            return CandidatePage((), None)
        bad = CorruptCandidate(None if kind == "missing_key" else corrupt_key)
        return CandidatePage((first, bad, last), None, kind != "bad_continuation")

    original_cursor = repository.get_cursor

    def cursor(partition):
        if kind == "bad_cursor" and partition == PARTITIONS[0]:
            from interview_backend.models.internal import StorageFormatError

            raise StorageFormatError("cursor")
        return original_cursor(partition)

    monkeypatch.setattr(repository, "get_cursor", cursor)
    monkeypatch.setattr(repository, "due_candidates", query)
    monkeypatch.setattr(repository, "recover", lambda owner, eid: handled.append(eid))
    monkeypatch.setattr(repository, "dispatch_event", lambda *args: None)
    publisher = FakePublisher()
    Recovery(
        repository, Dispatcher(repository, publisher), clock=lambda: NOW, metric=metrics.append
    ).tick(remaining_ms=lambda: 30000)
    assert PARTITIONS[1] in seen and PARTITIONS[2] in seen
    assert not publisher.events
    assert metrics
    expected = (
        [] if kind == "bad_cursor" else [uid(1)] if kind == "missing_key" else [uid(1), uid(3)]
    )
    assert handled == expected
    position = original_cursor(PARTITIONS[0]).cursor.after
    assert position == (
        key(1) if kind == "missing_key" else key(3) if kind == "bad_continuation" else None
    )


def test_corrupt_cursor_position_roundtrip_and_resume():
    from dataclasses import replace

    from interview_backend.repositories.codec import PARTITIONS, decode, encode
    from interview_backend.repositories.memory import MemoryRepository

    repo = MemoryRepository(lambda: NOW)
    initial = repo.get_cursor(PARTITIONS[0])
    raw = {
        "PK": "USER#synthetic",
        "SK": "DISPATCH#bad",
        "work_pk": PARTITIONS[0],
        "work_sk": f"{NOW:013d}#bad",
    }
    target = replace(initial.cursor, after=raw)
    assert repo.save_cursor(initial, target)
    assert decode(encode("RecoveryCursor", target, 0))[0].after == raw
    assert repo.get_cursor(PARTITIONS[0]).cursor.after == raw


def test_memory_expiry_discards_candidate_and_revision(monkeypatch):
    from interview_backend.repositories import memory as adapter

    memory, _, _, _, reply, _ = prepared()
    lease = memory.claim(OWNER, reply.body["evaluationId"], 1, uid(800), CONFIG).lease
    now = [lease.expires_at - 1]
    memory.clock = lambda: now[0]
    before, revisions = memory.snapshot(), dict(memory._revisions)
    original = adapter.encode

    def delayed(*args):
        result = original(*args)
        now[0] += 1
        return result

    monkeypatch.setattr(adapter, "encode", delayed)
    assert memory.finish(lease).status == "lost_lease"
    assert memory.snapshot() == before and memory._revisions == revisions


def test_nested_invocation_budget_does_not_expand_outer_budget():
    from interview_backend.repositories.budget import (
        invocation_budget,
        remaining_budget,
        storage_budget,
    )

    class Task:
        now = 0

        def monotonic(self):
            return self.now

        @invocation_budget(60000)
        def run(self, remaining_ms=None):
            self.now += 10
            return remaining_budget.get()()

    with storage_budget(lambda: 399):
        assert Task().run() == 399
    assert Task().run() == 50000


def test_invalid_gsi_candidate_does_not_stop_other_partitions():
    client = SnapshotClient({})
    queried, metrics = [], []

    def query(**request):
        p = request["ExpressionAttributeValues"][":p"]["S"]
        queried.append(p)
        return {
            "Items": [
                to_wire(
                    {
                        "PK": "USER#synthetic",
                        "SK": "DISPATCH#bad",
                        "work_pk": p,
                        "work_sk": f"{NOW:013d}#bad",
                    }
                )
            ]
        }

    client.query = query
    repo = db(client)
    Recovery(
        repo, Dispatcher(repo, FakePublisher()), clock=lambda: NOW, metric=metrics.append
    ).tick(remaining_ms=lambda: 30000)
    assert len(queried) == 3
    assert metrics == ["IntegrityError"] * 3


def test_expiry_during_transaction_assembly_prevents_send(monkeypatch):
    memory, _, _, _, reply, _ = prepared()
    lease = memory.claim(OWNER, reply.body["evaluationId"], 1, uid(800), CONFIG).lease
    client = SnapshotClient(snapshot(memory))
    now = [lease.expires_at - 1]
    original = DynamoUnit.actions

    def delayed(unit):
        actions = original(unit)
        now[0] += 1
        return actions

    monkeypatch.setattr(DynamoUnit, "actions", delayed)
    assert db(client, clock=lambda: now[0]).finish(lease).status == "lost_lease"
    assert not client.writes
