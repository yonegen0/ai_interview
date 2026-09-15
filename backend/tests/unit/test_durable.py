"""R01-R22 domain and storage-format scenarios without an external database."""

import json
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from itertools import count
from pathlib import Path

import pytest
from conftest import uid

from interview_backend.application.service import Application
from interview_backend.assets import load_questions
from interview_backend.evaluation.dispatch import Dispatcher, FakePublisher, Recovery
from interview_backend.evaluation.provider import PROMPT_VERSION, FakeProvider
from interview_backend.evaluation.worker import Worker
from interview_backend.models.internal import (
    ExecutionConfig,
    IntegrityError,
    ItemTooLarge,
    StorageFormatError,
    StorageUnavailable,
)
from interview_backend.repositories.codec import (
    PARTITIONS,
    canonical,
    decode,
    encode,
    from_wire,
    to_wire,
)
from interview_backend.repositories.memory import MemoryRepository

SAMPLES = json.loads(
    (Path(__file__).parents[3] / "docs/p2/sample-items.json").read_text(encoding="utf-8")
)


class Clock:
    def __init__(self):
        self.now = 1789171200000

    def __call__(self):
        return self.now


@pytest.fixture
def durable():
    clock = Clock()
    repo = MemoryRepository(clock)
    ids = count(1)
    app = Application(repo, load_questions(), lambda: uid(next(ids)))
    provider = FakeProvider()
    worker = Worker(repo, provider, clock)
    publisher = FakePublisher()
    dispatcher = Dispatcher(repo, publisher, clock, jitter=lambda low, high: low)
    return clock, repo, app, worker, publisher, dispatcher


def accept(app, owner="synthetic-user", key=100):
    sid = app.create(owner, uid(key), {"category": "career", "difficulty": "standard"}).body[
        "sessionId"
    ]
    qid = app.question(owner, sid).body["question"]["id"]
    payload = {"questionId": qid, "answer": " \ud800\n🙂 "}
    reply = app.submit(owner, uid(key + 1), sid, payload)
    return sid, payload, reply.body["evaluationId"]


@pytest.mark.parametrize("snapshot", SAMPLES["snapshots"], ids=lambda s: s["name"])
def test_p2_sample_roundtrip(snapshot):
    for item in snapshot["items"]:
        record, rev = decode(from_wire(to_wire(item)))
        actual = encode(item["kind"], record, rev)
        assert {k: v for k, v in actual.items() if k != "data"} == {
            k: v for k, v in item.items() if k != "data"
        }
        assert json.loads(actual["data"]) == json.loads(item["data"])


@pytest.mark.parametrize(
    "attribute,value",
    [("rev", True), ("schema_version", 2), ("rev", Decimal("1.2")), ("kind", "Unknown")],
)
def test_bad_physical_schema(attribute, value):
    item = deepcopy(SAMPLES["snapshots"][0]["items"][0])
    item[attribute] = value
    with pytest.raises(StorageFormatError):
        decode(item)


def test_size_limit_and_bool_rejection(durable):
    _, repo, app, *_ = durable
    sid, _, _ = accept(app)
    record = repo.snapshot().sessions[sid]
    with pytest.raises(StorageFormatError):
        encode("Session", replace(record, version=True), 0)
    q = record.questions[0].model_copy(update={"question": "x" * (350 * 1024)})
    with pytest.raises(ItemTooLarge):
        encode("Session", replace(record, questions=(q,)), 0)


def test_five_records_and_original_202_after_next(durable):
    clock, repo, app, worker, publisher, dispatcher = durable
    sid, payload, eid = accept(app)
    state = repo.snapshot()
    assert len(state.requests) == 2
    assert len(state.attempts) == len(state.evaluations) == len(state.dispatches) == 1
    expected = app.submit("synthetic-user", uid(101), sid, payload)
    assert state.sessions[sid].version == 1
    assert not publisher.events
    assert dispatcher.dispatch("synthetic-user", eid, 1) == "applied"
    assert worker.run("synthetic-user", eid)
    app.next_question(
        "synthetic-user", uid(102), sid, {"fromAttemptId": expected.body["attemptId"]}
    )
    assert app.submit("synthetic-user", uid(101), sid, payload) == expected
    assert repo.snapshot().sessions[sid].version == 3
    assert repo.snapshot().evaluations[eid].feedback.answer == payload["answer"]
    assert not any(
        "work_pk" in encode(kind, record, 0)
        for kind, record in [
            ("Evaluation", repo.snapshot().evaluations[eid]),
            ("Dispatch", repo.snapshot().dispatches[eid]),
        ]
    )


@pytest.mark.parametrize("started", [False, True])
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_worker_lease_recovery_boundaries(durable, started, offset):
    clock, repo, app, worker, *_ = durable
    _, _, eid = accept(app)
    lease = repo.claim("synthetic-user", eid, 1, uid(800), worker.config).lease
    if started:
        assert repo.mark_call_started(lease).status == "applied"
    clock.now = lease.expires_at + offset
    result = repo.recover("synthetic-user", eid)
    assert result.status == ("unchanged" if offset < 0 else "failed" if started else "requeued")
    if offset >= 0:
        assert repo.mark_call_started(lease).status == "lost_lease"
        assert repo.finish(lease).status == ("already_terminal" if started else "lost_lease")
        if started:
            assert not worker.run("synthetic-user", eid, 1)
            assert repo.snapshot().evaluations[eid].failure_reason == "OUTCOME_UNKNOWN"
            assert worker.provider.calls == 0
        else:
            assert repo.snapshot().dispatches[eid].generation == 2
            assert worker.run("synthetic-user", eid, 2)


@pytest.mark.parametrize("remaining", [49999, 50000])
def test_provider_start_budget(durable, remaining):
    _, repo, app, worker, *_ = durable
    _, _, eid = accept(app)
    worker.run("synthetic-user", eid, remaining_ms=lambda: remaining)
    assert worker.provider.calls == (1 if remaining == 50000 else 0)
    assert repo.snapshot().evaluations[eid].status == (
        "completed" if remaining == 50000 else "failed"
    )


def test_delayed_marker_does_not_call_provider(durable, monkeypatch):
    clock, repo, app, worker, *_ = durable
    _, _, eid = accept(app)
    original = repo.mark_call_started

    def delayed(lease):
        result = original(lease)
        clock.now += 41000
        return result

    monkeypatch.setattr(repo, "mark_call_started", delayed)
    worker.run("synthetic-user", eid)
    assert worker.provider.calls == 0


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_deadline_preempts_future_delivery(durable, offset):
    clock, repo, app, worker, *_ = durable
    _, _, eid = accept(app)
    with repo._lock:
        repo._state.dispatches[eid].next_at = clock.now + 2000000
    clock.now += 900000 + offset
    page = repo.due_candidates(PARTITIONS[0], clock.now)
    assert len(page.candidates) == int(offset >= 0)
    repo.recover("synthetic-user", eid)
    if offset >= 0:
        assert repo.snapshot().evaluations[eid].failure_reason == "DEADLINE_EXCEEDED"
        assert not worker.run("synthetic-user", eid)


def test_late_delivery_confirmation_cannot_reopen(durable):
    _, repo, app, worker, publisher, dispatcher = durable
    _, _, eid = accept(app)
    publisher.behavior = lambda event: worker.run(event["ownerSub"], event["evaluationId"])
    assert dispatcher.dispatch("synthetic-user", eid, 1) == "obsolete"
    assert repo.snapshot().dispatches[eid].status == "DONE"
    assert worker.provider.calls == 1


def test_send_failure_and_queued_recovery(durable):
    clock, repo, app, worker, publisher, dispatcher = durable
    _, _, eid = accept(app)

    def fail(event):
        raise TimeoutError("SENSITIVE")

    publisher.behavior = fail
    assert dispatcher.dispatch("synthetic-user", eid, 1) == "deferred"
    assert dispatcher.dispatch("synthetic-user", eid, 1) == "not_due"
    assert repo.snapshot().dispatches[eid].generation == 1
    clock.now += 5000
    publisher.behavior = None
    dispatcher.dispatch("synthetic-user", eid, 1)
    clock.now += 120000
    assert repo.recover("synthetic-user", eid).status == "requeued"
    assert not worker.run("synthetic-user", eid, 1)
    assert worker.run("synthetic-user", eid, 2)


def test_partial_relations_do_not_call_provider(durable):
    _, repo, app, worker, *_ = durable
    _, _, eid = accept(app)
    with repo._lock:
        del repo._state.dispatches[eid]
    with pytest.raises(IntegrityError):
        worker.run("synthetic-user", eid)
    assert worker.provider.calls == 0


def test_recovery_paging_and_cursor_cas(durable):
    clock, repo, app, _, publisher, dispatcher = durable
    for n in range(103):
        accept(app, key=1000 + n * 2)
    initial = repo.get_cursor(PARTITIONS[0])
    first = repo.due_candidates(PARTITIONS[0], clock.now)
    assert len(first.candidates) == 100 and first.continuation
    second = repo.due_candidates(PARTITIONS[0], clock.now, first.continuation)
    assert len(second.candidates) == 3
    assert repo.save_cursor(initial, replace(initial.cursor, after=first.candidates[49].key))
    assert not repo.save_cursor(initial, initial.cursor)
    Recovery(repo, dispatcher, clock).tick()
    assert len(publisher.events) == 53
    # Earlier due records are revisited after wrapping the fixed-cutoff sweep.
    Recovery(repo, dispatcher, clock).tick()
    assert len(publisher.events) == 103


def test_db_error_stops_partition_without_skipping(durable, monkeypatch):
    clock, repo, app, _, publisher, dispatcher = durable
    _, _, eid = accept(app)
    original = repo.recover
    monkeypatch.setattr(
        repo, "recover", lambda *args: (_ for _ in ()).throw(StorageUnavailable("db"))
    )
    Recovery(repo, dispatcher, clock).tick()
    assert not publisher.events
    assert repo.get_cursor(PARTITIONS[0]).cursor.after is None
    monkeypatch.setattr(repo, "recover", original)
    Recovery(repo, dispatcher, clock).tick()
    assert publisher.events[0]["evaluationId"] == eid


def test_invalid_result_too_large_is_fixed_failure(durable):
    _, repo, app, worker, *_ = durable
    _, _, eid = accept(app)
    worker.provider.behavior = lambda _: {
        "score": 1,
        "summary": "x" * 360000,
        "strengths": [],
        "improvements": [],
    }
    worker.run("synthetic-user", eid)
    e = repo.snapshot().evaluations[eid]
    assert e.failure_reason == "RESULT_TOO_LARGE" and e.feedback is None


@pytest.mark.parametrize("partition", PARTITIONS)
def test_all_partitions_page_more_than_100_and_same_key_owners(partition):
    clock = Clock()
    repo = MemoryRepository(clock)
    from interview_backend.models.internal import Attempt, Dispatch, Evaluation, Session

    questions = load_questions()[:3]
    # Fixture construction only: no emulation of transactions or CAS behavior.
    for n in range(102):
        owner = f"owner-{n:03d}"
        eid = uid(1)  # Deliberately identical SK and work_sk under distinct owners.
        session = Session(owner, uid(3), questions, created_at=clock.now, updated_at=clock.now)
        attempt = Attempt(owner, uid(2), uid(3), eid, questions[0], 1, "synthetic", clock.now)
        evaluation = Evaluation(
            owner, eid, uid(2), created_at=clock.now, deadline_at=clock.now + 900000
        )
        dispatch = Dispatch(owner, eid, clock.now + 900000, created_at=clock.now, next_at=clock.now)
        if partition == PARTITIONS[1]:
            dispatch.status, dispatch.queued_at, dispatch.claim_due_at = (
                "QUEUED",
                clock.now,
                clock.now + 120000,
            )
        elif partition == PARTITIONS[2]:
            evaluation.worker_state = "running"
            evaluation.lock_owner, evaluation.lock_expires_at = uid(800), clock.now + 90000
            evaluation.lease_version = 1
            evaluation.execution_config = ExecutionConfig(prompt_version=PROMPT_VERSION)
            dispatch.status = "CLAIMED"
        repo._state.sessions[(owner, uid(3))] = session
        repo._state.attempts[(owner, uid(2))] = attempt
        repo._state.evaluations[(owner, eid)] = evaluation
        repo._state.dispatches[(owner, eid)] = dispatch
    cutoff = clock.now + 120000
    page = repo.due_candidates(partition, cutoff)
    following = repo.due_candidates(partition, cutoff, page.continuation)
    assert len(page.candidates) == 100 and len(following.candidates) == 2
    assert len({candidate.owner for candidate in (*page.candidates, *following.candidates)}) == 102


def test_recovery_mid_page_budget_resumes(durable):
    clock, repo, app, _, publisher, dispatcher = durable
    for n in range(4):
        accept(app, key=1000 + n * 2)
    recovery = Recovery(repo, dispatcher, clock)
    recovery.tick(remaining_ms=lambda: 30000 if len(publisher.events) < 2 else 5000)
    assert len(publisher.events) == 2
    assert repo.get_cursor(PARTITIONS[0]).cursor.after is not None
    recovery.tick()
    assert len(publisher.events) == 4


def test_owner_scoped_identical_ids():
    repo = MemoryRepository(Clock())
    for owner in ("one", "two"):
        ids = iter([uid(1), uid(2), uid(3)])
        app = Application(repo, load_questions(), ids.__next__)
        accept(app, owner=owner)
        assert app.evaluation(owner, uid(3)).body["evaluationId"] == uid(3)
    assert len(repo.snapshot().sessions) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("worker_state", "unknown"),
        ("lease_version", True),
        ("call_phase", "started"),
        ("status", "completed"),
    ],
)
def test_invalid_state_combinations_are_rejected(durable, field, value):
    _, repo, app, *_ = durable
    _, _, eid = accept(app)
    invalid = replace(repo.snapshot().evaluations[eid], **{field: value})
    with pytest.raises((StorageFormatError, IntegrityError)):
        encode("Evaluation", invalid, 0)


def test_crash_during_provider_is_never_recalled(durable):
    clock, repo, app, worker, *_ = durable
    _, _, eid = accept(app)

    class ProcessStopped(BaseException):
        pass

    def stopped(_):
        raise ProcessStopped

    worker.provider.behavior = stopped
    with pytest.raises(ProcessStopped):
        worker.run("synthetic-user", eid)
    assert worker.provider.calls == 1
    clock.now += 90000
    repo.recover("synthetic-user", eid)
    assert repo.snapshot().evaluations[eid].failure_reason == "OUTCOME_UNKNOWN"
    assert not worker.run("synthetic-user", eid)
    assert worker.provider.calls == 1


def test_missing_source_and_connection_configuration(runtime, monkeypatch):
    import interview_backend.repositories.dynamodb as dynamodb
    from interview_backend.bootstrap import build_runtime

    def unexpected(*args, **kwargs):
        raise AssertionError("AWS must not be contacted")

    monkeypatch.setattr(dynamodb, "client_for", unexpected)
    for config in ({"mode": "local"}, {"mode": "aws"}, {"mode": "aws", "region": "us-east-1"}):
        with pytest.raises(ValueError):
            build_runtime(**config)


def test_delayed_delivery_acquire_does_not_send_after_deadline(durable, monkeypatch):
    clock, repo, app, _, publisher, dispatcher = durable
    _, _, eid = accept(app)
    clock.now += 899999
    original = repo.acquire_delivery

    def delayed(*args):
        acquired = original(*args)
        clock.now += 1
        return acquired

    monkeypatch.setattr(repo, "acquire_delivery", delayed)
    assert dispatcher.dispatch("synthetic-user", eid, 1) == "obsolete"
    assert not publisher.events


def test_exact_350kib_boundary(durable):
    _, repo, app, *_ = durable
    sid, _, _ = accept(app)
    session = repo.snapshot().sessions[sid]
    question = session.questions[0].model_copy(update={"question": "q"})
    session = replace(session, questions=(question,))
    baseline = encode("Session", session, 0)
    room = 350 * 1024 - len(canonical(baseline).encode("ascii"))
    question.question = "q" + "x" * room
    assert len(canonical(encode("Session", session, 0)).encode("ascii")) == 350 * 1024
    question.question += "x"
    with pytest.raises(ItemTooLarge):
        encode("Session", session, 0)


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_finish_and_send_confirmation_expiry_boundaries(durable, offset):
    clock, repo, app, worker, *_ = durable
    _, _, eid = accept(app)
    delivery = repo.acquire_delivery("synthetic-user", eid, 1, uid(801)).delivery
    clock.now = delivery.expires_at + offset
    assert repo.confirm_delivery(delivery).status == ("applied" if offset < 0 else "obsolete")
    lease = repo.claim("synthetic-user", eid, 1, uid(800), worker.config).lease
    clock.now = lease.expires_at + offset
    assert repo.finish(lease, reason="PREPARATION_FAILED").status == (
        "applied" if offset < 0 else "lost_lease"
    )
