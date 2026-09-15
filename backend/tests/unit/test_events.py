"""R08/R19 input adapters, replay filtering, and safe batch failure responses."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest
from conftest import uid

from interview_backend.evaluation.events import EvaluationRequested, InternalHandlers
from interview_backend.models.internal import StorageUnavailable
from interview_backend.repositories.codec import encode, to_wire


class Context:
    def get_remaining_time_in_millis(self):
        return 60000


def accepted(runtime):
    app = runtime.application
    owner = "synthetic-user"
    sid = app.create(owner, uid(100), {"category": "career", "difficulty": "standard"}).body[
        "sessionId"
    ]
    payload = {"questionId": app.question(owner, sid).body["question"]["id"], "answer": "synthetic"}
    reply = app.submit(owner, uid(101), sid, payload)
    return runtime.repository.dispatch_event(owner, reply.body["evaluationId"])


def handlers(runtime):
    return InternalHandlers(
        runtime.worker,
        runtime.dispatcher,
        runtime.recovery,
        queue_arn="queue",
        stream_arn="stream",
        scheduler_arn="schedule",
    )


def sqs(message, arn="queue"):
    return {
        "Records": [
            {
                "eventSource": "aws:sqs",
                "eventSourceARN": arn,
                "messageId": "message",
                "body": json.dumps(message),
            }
        ]
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("eventVersion", True),
        ("eventVersion", 2),
        ("dispatchVersion", True),
        ("dispatchVersion", 0),
        ("dispatchVersion", "1"),
        ("ownerSub", ""),
        ("evaluationId", "invalid"),
        ("extra", 1),
        ("type", "Other"),
    ],
)
def test_malformed_messages_do_not_call_provider(runtime, field, value, capsys):
    event = accepted(runtime)
    event[field] = value
    before = runtime.repository.snapshot()
    assert handlers(runtime).sqs(sqs(event), Context()) == {
        "batchItemFailures": [{"itemIdentifier": "message"}]
    }
    assert runtime.provider.calls == 0
    assert runtime.repository.snapshot() == before
    assert not capsys.readouterr().out


def test_sqs_source_and_duplicates(runtime):
    event = accepted(runtime)
    handler = handlers(runtime)
    assert handler.sqs(sqs(event, "forged"), Context())["batchItemFailures"]
    assert handler.sqs(sqs(event), Context()) == {"batchItemFailures": []}
    assert handler.sqs(sqs(event), Context()) == {"batchItemFailures": []}
    assert runtime.provider.calls == 1


def test_sqs_storage_failure_is_retryable(runtime, monkeypatch):
    event = accepted(runtime)

    def fail(*args, **kwargs):
        raise StorageUnavailable("storage")

    monkeypatch.setattr(runtime.repository, "claim", fail)
    assert handlers(runtime).sqs(sqs(event), Context())["batchItemFailures"]
    assert runtime.provider.calls == 0


def stream(new, old=None, event_name="MODIFY"):
    record = {
        "eventSource": "aws:dynamodb",
        "eventSourceARN": "stream",
        "eventName": event_name,
        "dynamodb": {"SequenceNumber": "10", "NewImage": to_wire(encode("Dispatch", new, 1))},
    }
    if old is not None:
        record["dynamodb"]["OldImage"] = to_wire(encode("Dispatch", old, 0))
    return {"Records": [record]}


def test_stream_insert_sends_once_and_self_updates_do_not_recurse(runtime):
    event = accepted(runtime)
    d = runtime.repository.snapshot().dispatches[event["evaluationId"]]
    handler = handlers(runtime)
    assert not handler.streams(stream(d, event_name="INSERT"), Context())["batchItemFailures"]
    queued = runtime.repository.snapshot().dispatches[d.id]
    assert not handler.streams(stream(queued, d), Context())["batchItemFailures"]
    assert len(runtime.publisher.events) == 1
    # Even if a send-lease-only stream event arrives late, it is not another trigger.
    pending = replace(d, send_owner=uid(800), send_expires_at=d.created_at + 45000)
    assert not handler.streams(stream(pending, d), Context())["batchItemFailures"]
    assert len(runtime.publisher.events) == 1


def test_unknown_stream_schema_and_scheduler_input(runtime):
    event = accepted(runtime)
    d = runtime.repository.snapshot().dispatches[event["evaluationId"]]
    invalid = stream(d, event_name="INSERT")
    invalid["Records"][0]["dynamodb"]["NewImage"]["schema_version"] = {"N": "2"}
    assert handlers(runtime).streams(invalid, Context())["batchItemFailures"]
    assert not runtime.publisher.events
    for value in (
        {"eventVersion": True, "type": "RecoveryTick"},
        {"eventVersion": 1, "type": "RecoveryTick", "owner": "fake"},
    ):
        with pytest.raises(ValueError):
            handlers(runtime).scheduler(value, Context(), source_arn="schedule")
    with pytest.raises(ValueError):
        handlers(runtime).scheduler(
            {"eventVersion": 1, "type": "RecoveryTick"}, Context(), source_arn="forged"
        )


def test_partial_batch_only_reports_failed_record(runtime):
    good = sqs(accepted(runtime))
    bad = deepcopy(good["Records"][0])
    bad["messageId"] = "bad"
    bad["body"] = "invalid json"
    good["Records"].append(bad)
    assert handlers(runtime).sqs(good, Context()) == {
        "batchItemFailures": [{"itemIdentifier": "bad"}]
    }
    assert runtime.provider.calls == 1


def test_strict_event_success():
    parsed = EvaluationRequested(
        eventVersion=1,
        type="EvaluationRequested",
        ownerSub="owner",
        evaluationId=uid(1),
        dispatchVersion=1,
    )
    assert parsed.model_dump()["dispatchVersion"] == 1
