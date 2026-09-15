"""P4 execution suite: real transactions, independent processes, persistence and GSI."""

import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from time import monotonic, sleep
from uuid import uuid4

import pytest
from botocore.exceptions import EndpointConnectionError

from interview_backend.application.service import Application
from interview_backend.assets import load_questions
from interview_backend.evaluation.provider import PROMPT_VERSION, FakeProvider
from interview_backend.evaluation.worker import Worker
from interview_backend.models.internal import BusinessError, ExecutionConfig, RetryExhausted
from interview_backend.repositories.codec import PARTITIONS, key, to_wire
from interview_backend.repositories.dynamodb import DynamoDBRepository, client_for

pytestmark = pytest.mark.dynamodb
OWNER = "synthetic-p4-user"


def application(region, table):
    repo = DynamoDBRepository(client_for(region), table)
    return Application(repo, load_questions(), lambda: str(uuid4()))


def child_submit(region, table, sid, payload, key, gate):
    app = application(region, table)
    gate.wait(timeout=30)
    try:
        return app.submit(OWNER, key, sid, payload)
    except BusinessError as error:
        return error.status


def child_feedback(region, table, aid):
    return application(region, table).feedback(OWNER, aid)


def child_run(region, table, eid, gate):
    repo = application(region, table).repository
    provider = FakeProvider()
    gate.wait(timeout=30)
    Worker(repo, provider).run(OWNER, eid, 1)
    return provider.calls


def child_finish_or_recover(region, table, lease, action, gate):
    now = lease.expires_at - 1 if action == "finish" else lease.expires_at
    repo = DynamoDBRepository(client_for(region), table, clock=lambda: now)
    gate.wait(timeout=30)
    if action == "finish":
        return repo.finish(lease).status
    return repo.recover(OWNER, lease.evaluation_id).status


def setup_session(region, table):
    app = application(region, table)
    sid = app.create(OWNER, str(uuid4()), {"category": "career", "difficulty": "standard"}).body[
        "sessionId"
    ]
    payload = {
        "questionId": app.question(OWNER, sid).body["question"]["id"],
        "answer": "synthetic answer",
    }
    return app, sid, payload


@pytest.mark.parametrize("same_key", [True, False])
def test_independent_process_acceptance_and_single_provider(dynamodb_table, same_key):
    region, table = dynamodb_table
    app, sid, payload = setup_session(region, table)
    keys = [str(uuid4()), str(uuid4())]
    if same_key:
        keys[1] = keys[0]
    ctx = multiprocessing.get_context("spawn")
    with ctx.Manager() as manager, ProcessPoolExecutor(2, mp_context=ctx) as pool:
        gate = manager.Barrier(2)
        futures = [
            pool.submit(child_submit, region, table, sid, payload, key, gate) for key in keys
        ]
        replies = [f.result(timeout=60) for f in futures]
        if same_key:
            assert replies[0] == replies[1]
        else:
            assert sum(reply == 409 for reply in replies) == 1
        accepted = next(reply for reply in replies if reply != 409)
        eid = accepted.body["evaluationId"]
        gate = manager.Barrier(2)
        futures = [pool.submit(child_run, region, table, eid, gate) for _ in range(2)]
        assert sum(f.result(timeout=60) for f in futures) == 1
        # A different process reads exactly the stored result after the original workers exit.
    with ProcessPoolExecutor(1, mp_context=ctx) as pool:
        saved = pool.submit(child_feedback, region, table, accepted.body["attemptId"]).result(
            timeout=60
        )
    assert saved == app.feedback(OWNER, accepted.body["attemptId"])


class LoseReply:
    def __init__(self, client):
        self.client = client
        self.lost = False

    def __getattr__(self, name):
        return getattr(self.client, name)

    def transact_write_items(self, **request):
        result = self.client.transact_write_items(**request)
        if not self.lost:
            self.lost = True
            raise EndpointConnectionError(endpoint_url="synthetic-response-loss")
        return result


def test_real_commit_response_loss_and_replay_after_restart(dynamodb_table):
    region, table = dynamodb_table
    app, sid, payload = setup_session(region, table)
    proxy = LoseReply(client_for(region))
    app.repository = DynamoDBRepository(proxy, table)
    key = str(uuid4())
    reply = app.submit(OWNER, key, sid, payload)
    assert proxy.lost
    restarted = application(region, table)
    assert restarted.submit(OWNER, key, sid, payload) == reply
    assert restarted.repository.dispatch_event(OWNER, reply.body["evaluationId"])


def test_real_rejected_transaction_leaves_no_partial_acceptance(dynamodb_table):
    region, table = dynamodb_table
    app, sid, payload = setup_session(region, table)
    existing = app.submit(OWNER, str(uuid4()), sid, payload)
    app, second_sid, second_payload = setup_session(region, table)
    aid, request_key = str(uuid4()), str(uuid4())
    ids = iter([aid, existing.body["evaluationId"]])
    app.new_id = lambda: next(ids)
    with pytest.raises(RetryExhausted):
        app.submit(OWNER, request_key, second_sid, second_payload)
    client = client_for(region)
    for kind, identifier in (("Attempt", aid), ("IdempotencyRecord", request_key)):
        assert "Item" not in client.get_item(
            TableName=table, Key=to_wire(key(kind, OWNER, identifier)), ConsistentRead=True
        )
    assert app.question(OWNER, second_sid).body["activeAttempt"] is None
    assert app.evaluation(OWNER, existing.body["evaluationId"]).body["status"] == "processing"


def test_real_gsi_pagination_and_cursor_checkpoint(dynamodb_table):
    region, table = dynamodb_table
    app = application(region, table)
    for _ in range(101):
        _, sid, payload = setup_session(region, table)
        app.submit(OWNER, str(uuid4()), sid, payload)
    deadline = monotonic() + 60
    while True:
        cutoff = app.repository.clock()
        first = app.repository.due_candidates(PARTITIONS[0], cutoff)
        second = (
            app.repository.due_candidates(PARTITIONS[0], cutoff, first.continuation)
            if first.continuation
            else None
        )
        if second and len(first.candidates) + len(second.candidates) == 101:
            break
        assert monotonic() < deadline, "GSI did not converge"
        sleep(1)
    assert len(first.candidates) == 100
    assert len({(c.owner, c.evaluation_id) for c in (*first.candidates, *second.candidates)}) == 101


def test_started_marker_survives_new_repository_and_never_restarts(dynamodb_table):
    region, table = dynamodb_table
    app, sid, payload = setup_session(region, table)
    eid = app.submit(OWNER, str(uuid4()), sid, payload).body["evaluationId"]
    lease = app.repository.claim(
        OWNER, eid, 1, str(uuid4()), ExecutionConfig(prompt_version=PROMPT_VERSION)
    ).lease
    app.repository.mark_call_started(lease)
    restarted = DynamoDBRepository(client_for(region), table, clock=lambda: lease.expires_at)
    assert restarted.recover(OWNER, eid).status == "failed"
    provider = FakeProvider()
    assert not Worker(restarted, provider, clock=lambda: lease.expires_at).run(OWNER, eid)
    assert provider.calls == 0


def test_independent_finish_recovery_race_keeps_one_terminal(dynamodb_table):
    region, table = dynamodb_table
    app, sid, payload = setup_session(region, table)
    eid = app.submit(OWNER, str(uuid4()), sid, payload).body["evaluationId"]
    lease = app.repository.claim(
        OWNER, eid, 1, str(uuid4()), ExecutionConfig(prompt_version=PROMPT_VERSION)
    ).lease
    app.repository.mark_call_started(lease)
    ctx = multiprocessing.get_context("spawn")
    with ctx.Manager() as manager, ProcessPoolExecutor(2, mp_context=ctx) as pool:
        gate = manager.Barrier(2)
        futures = [
            pool.submit(child_finish_or_recover, region, table, lease, action, gate)
            for action in ("finish", "recover")
        ]
        statuses = [f.result(timeout=60) for f in futures]
    assert statuses in (["applied", "unchanged"], ["already_terminal", "failed"])
    assert app.evaluation(OWNER, eid).body["status"] == "failed"
    assert app.question(OWNER, sid).body["activeAttempt"]["status"] == "failed"
