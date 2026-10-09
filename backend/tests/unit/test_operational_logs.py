"""End-to-end evaluation correlation, privacy, retention reuse, and fault signals offline."""

import json
from types import SimpleNamespace

import pytest
from conftest import uid
from test_durable import accept
from test_durable import durable as durable
from test_events import accepted, handlers, sqs

from interview_backend.aws_runtime import ApiEntry
from interview_backend.evaluation.dispatch import Dispatcher, FakePublisher, Recovery
from interview_backend.evaluation.provider import FakeProvider
from interview_backend.evaluation.worker import Worker
from interview_backend.models.internal import StorageUnavailable
from interview_backend.observability import Metrics, ObservedRepository
from interview_backend.operational_logs import invocation_context, log_event
from interview_backend.repositories.codec import decode, encode
from interview_backend.support_history import summarize_evaluation


def invocation(component="api", gateway="gateway-id", request="lambda-id"):
    return invocation_context(
        component,
        "dev",
        {"requestContext": {"requestId": gateway}},
        SimpleNamespace(aws_request_id=request),
    )


def test_privacy_allowlist_never_serializes_secrets_or_arbitrary_objects():
    rows = []
    with invocation():
        log_event(
            "evaluation_terminal",
            sink=rows.append,
            evaluationId=uid(1),
            ownerSub="private@example.invalid",
            answer="secret-answer",
            jwt="secret-jwt",
            token="secret-token",
            exception=RuntimeError("secret-exception"),
            status={"secret": "secret-status"},
            elapsedMs=float("nan"),
            provider=["secret-provider"],
        )
    assert len(rows) == 1
    value = json.loads(rows[0])
    assert value["evaluationId"] == uid(1)
    assert not any(marker in rows[0] for marker in ("secret", "private@", "nan"))
    assert value["gatewayRequestId"] == "gateway-id" and value["lambdaRequestId"] == "lambda-id"
    assert "_aws" not in value


def test_logging_sink_failure_and_warm_context_isolation(capsys):
    with invocation(request="first-id"):
        log_event(
            "evaluation_accepted",
            sink=lambda _: (_ for _ in ()).throw(RuntimeError("secret")),
            evaluationId=uid(1),
        )
    log_event("evaluation_accepted", evaluationId=uid(1))
    with invocation(request="second-id", gateway=None):
        log_event("evaluation_accepted", evaluationId=uid(2))
    rows = capsys.readouterr().out.strip().splitlines()
    assert len(rows) == 1 and "first-id" not in rows[0] and "gatewayRequestId" not in rows[0]


@pytest.mark.parametrize("fails", [False, True])
def test_api_to_streams_sqs_worker_terminal_correlation(runtime, capsys, fails):
    emitted = []
    repo = ObservedRepository(runtime.repository, Metrics("api", sink=emitted.append))
    runtime.application.repository = repo
    with invocation("api"):
        message = accepted(runtime)
        replay_count = len(runtime.repository.snapshot().evaluations)
    repo.metrics = Metrics("dispatcher", sink=emitted.append)
    publisher = FakePublisher()
    dispatcher = Dispatcher(repo, publisher, clock=runtime.repository.clock)
    with invocation("dispatcher", request="streams-id"):
        dispatcher.dispatch(message["ownerSub"], message["evaluationId"], 1)
    assert publisher.events[0] == message  # No new envelope fields or idempotency changes.
    repo.metrics = Metrics("worker", sink=emitted.append)
    provider = FakeProvider(
        behavior=(lambda _: (_ for _ in ()).throw(RuntimeError("secret-provider")))
        if fails
        else None
    )
    worker = Worker(repo, provider, clock=runtime.repository.clock)
    internal = handlers(runtime)
    internal.worker = worker
    with invocation("worker", request="worker-id"):
        assert internal.sqs(
            sqs(message), SimpleNamespace(get_remaining_time_in_millis=lambda: 60000)
        ) == {"batchItemFailures": []}
        internal.sqs(sqs(message), SimpleNamespace(get_remaining_time_in_millis=lambda: 60000))
    logs = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("{") and '"_aws"' not in line
    ]
    events = {r["event"] for r in logs}
    assert {
        "evaluation_accepted",
        "dispatch_confirmed",
        "worker_claimed",
        "evaluation_terminal",
    } <= events
    assert all(r.get("evaluationId") == message["evaluationId"] for r in logs)
    terminal = [r for r in logs if r["event"] == "evaluation_terminal"]
    assert len(terminal) == 1 and terminal[0]["lambdaRequestId"] == "worker-id"
    assert terminal[0]["status"] == ("failed" if fails else "completed")
    assert "secret-provider" not in json.dumps(logs)
    assert len(runtime.repository.snapshot().evaluations) == replay_count
    assert all(
        json.loads(e)["_aws"]["CloudWatchMetrics"][0]["Dimensions"]
        == [["Project", "Environment", "Component"]]
        for e in emitted
    )
    assert any('"EvaluationFailed"' in e for e in emitted) == fails


def test_support_summary_120_days_later_has_no_duplicate_record_or_ttl(runtime):
    message = accepted(runtime)
    runtime.worker.run(message["ownerSub"], message["evaluationId"], 1)
    snapshot = runtime.repository.snapshot()
    evaluation = next(iter(snapshot.evaluations.values()))
    record = encode("Evaluation", evaluation, 0)
    restored, _ = decode(record)
    summary = summarize_evaluation(
        restored, owner=message["ownerSub"], evaluation_id=message["evaluationId"]
    )
    assert summary["status"] == "completed" and summary["providerId"] == "fake"
    assert summary["elapsedMs"] >= 0
    assert not any(key in summary for key in ("answer", "feedback", "coachingHistory", "ttl"))
    with pytest.raises(ValueError, match="ExactOwner"):
        summarize_evaluation(
            restored, owner="different-user", evaluation_id=message["evaluationId"]
        )
    assert "ttl" not in record
    assert restored.created_at + 120 * 86400000 > restored.deadline_at
    assert runtime.repository.snapshot() == snapshot


def test_unknown_provider_is_not_inferred(runtime):
    message = accepted(runtime)
    evaluation = next(iter(runtime.repository.snapshot().evaluations.values()))
    summary = summarize_evaluation(
        evaluation, owner=message["ownerSub"], evaluation_id=message["evaluationId"]
    )
    assert summary["providerId"] == "unknown" and summary["elapsedMs"] is None


def test_configuration_failure_is_attributed_to_actual_test_function(monkeypatch, capsys):
    from interview_backend import aws_runtime

    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "ai-interview-test-synthetic-api")
    monkeypatch.setattr(
        aws_runtime, "build_entry", lambda _: (_ for _ in ()).throw(RuntimeError("secret-init"))
    )
    assert (
        aws_runtime.api_handler({}, SimpleNamespace(aws_request_id="init-id"))["statusCode"] == 500
    )
    output = capsys.readouterr().out
    assert '"Environment":"test"' in output and '"InvalidConfiguration"' in output
    assert "secret-init" not in output


@pytest.mark.parametrize("reason", ["started_lease", "deadline"])
def test_recovery_terminal_failures_emit_failed_and_unknown_when_required(durable, capsys, reason):
    clock, repository, app, worker, *_ = durable
    _, _, eid = accept(app)
    rows = []
    observed = ObservedRepository(repository, Metrics("dispatcher", sink=rows.append))
    if reason == "started_lease":
        lease = repository.claim("synthetic-user", eid, 1, uid(880), worker.config).lease
        repository.mark_call_started(lease)
        clock.now = lease.expires_at
    else:
        clock.now += 900000
    with invocation("dispatcher", request="recovery-id"):
        observed.recover("synthetic-user", eid)
    values = [json.loads(r) for r in rows]
    assert any(r.get("EvaluationFailed") == 1 for r in values)
    assert any(r.get("OutcomeUnknown") == 1 for r in values) == (reason == "started_lease")
    line = json.loads(capsys.readouterr().out)
    assert line["evaluationId"] == eid and line["status"] == "failed"
    assert line["failureReason"] == (
        "OUTCOME_UNKNOWN" if reason == "started_lease" else "DEADLINE_EXCEEDED"
    )


def test_pending_work_is_detected_even_when_queue_is_empty(durable):
    clock, repo, app, *_ = durable
    _, _, eid = accept(app)
    assert repo.work_observation("synthetic-user", eid) == (("PendingAge", 0),)
    clock.now += 121000
    assert ("PendingAge", 121) in repo.work_observation("synthetic-user", eid)
    # Queue age cannot substitute: no publisher has ever sent this evaluation.
    assert durable[4].events == []


def test_recovery_failure_never_emits_a_success_heartbeat(durable, monkeypatch):
    clock, repo, _, _, _, dispatcher = durable
    rows = []
    metrics = Metrics("dispatcher", sink=rows.append)
    recovery = Recovery(
        repo, dispatcher, clock=clock, metric=metrics.classification, observe=metrics.emit
    )
    recovery.tick(lambda: 30000)
    assert any(json.loads(r).get("RecoveryHeartbeat") == 1 for r in rows)
    rows.clear()
    monkeypatch.setattr(repo, "get_cursor", lambda _: (_ for _ in ()).throw(StorageUnavailable()))
    recovery.tick(lambda: 30000)
    assert not any("RecoveryHeartbeat" in json.loads(r) for r in rows)
    assert any(json.loads(r).get("RecoveryPartitionBlocked") == 3 for r in rows)


def test_caught_api_500_is_returned_and_emits_business_failure(capsys):
    from test_p4_runtime import context, environment, event

    from interview_backend.aws_settings import AwsSettings

    rows = []
    metrics = Metrics("api", sink=rows.append)
    entry = ApiEntry(
        AwsSettings.load(environment("api"), "api"), lambda _: {"statusCode": 500}, metrics
    )
    with invocation():
        assert entry(event(), context())["statusCode"] == 500
    assert any(json.loads(r).get("ApiFailure") == 1 for r in rows)
    assert json.loads(capsys.readouterr().out)["statusCode"] == 500


def test_120_day_support_reads_existing_record_with_owner_isolation(durable):
    clock, repo, app, worker, *_ = durable
    _, _, eid = accept(app)
    worker.run("synthetic-user", eid)
    before = repo.snapshot()
    clock.now += 120 * 86400000
    assert app.evaluation("synthetic-user", eid).body["status"] == "completed"
    record, _ = decode(encode("Evaluation", repo.snapshot().evaluations[eid], 0))
    summary = summarize_evaluation(record, owner="synthetic-user", evaluation_id=eid)
    assert summary["providerId"] == "fake"
    assert repo.snapshot() == before


def test_healthy_api_poll_does_not_duplicate_access_logs_or_drop_emf(capsys):
    from test_p4_runtime import context, environment, event

    from interview_backend.aws_settings import AwsSettings

    rows = []
    metrics = Metrics("api", sink=rows.append)
    entry = ApiEntry(
        AwsSettings.load(environment("api"), "api"), lambda _: {"statusCode": 200}, metrics
    )
    with invocation():
        entry(event(), context())
    assert capsys.readouterr().out == ""
    assert any("ApiRequest" in json.loads(r) for r in rows)
    assert any("ApiDuration" in json.loads(r) for r in rows)


@pytest.mark.parametrize("wrong_owner", [False, True])
def test_private_support_cli_decodes_existing_wire_item(
    runtime, monkeypatch, tmp_path, wrong_owner
):
    import sys
    from pathlib import Path

    from test_provider_validation_tools import tool

    from interview_backend.repositories.codec import to_wire

    message = accepted(runtime)
    runtime.worker.run(message["ownerSub"], message["evaluationId"], 1)
    evaluation = next(iter(runtime.repository.snapshot().evaluations.values()))
    raw = tmp_path / "exact-item.json"
    raw.write_text(json.dumps({"Item": to_wire(encode("Evaluation", evaluation, 0))}))
    private = Path(__file__).parents[2] / ".p4-artifacts"
    private.mkdir(exist_ok=True)
    output = private / ("support-offline-" + uid(981 if wrong_owner else 982) + ".json")
    output.unlink(missing_ok=True)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "support_history",
            "--record",
            str(raw),
            "--owner",
            "other-owner" if wrong_owner else message["ownerSub"],
            "--evaluation-id",
            message["evaluationId"],
            "--output",
            str(output),
        ],
    )
    try:
        if wrong_owner:
            with pytest.raises(ValueError, match="ExactOwner"):
                tool("support_history").main()
            assert not output.exists()
        else:
            tool("support_history").main()
            summary = json.loads(output.read_text())
            assert summary["evaluationId"] == message["evaluationId"]
            assert summary["status"] == "completed"
            assert not any(k in summary for k in ("answer", "feedback", "ttl"))
            with pytest.raises(FileExistsError):
                tool("support_history").main()
    finally:
        output.unlink(missing_ok=True)
