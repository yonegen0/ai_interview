"""P4 deployment boundaries, with no credential lookup or AWS requests."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from interview_backend.aws_runtime import ApiEntry, DispatcherEntry, WorkerEntry
from interview_backend.aws_settings import AwsSettings, ConfigurationError
from interview_backend.evaluation.dispatch import Dispatcher, Recovery
from interview_backend.observability import Metrics
from interview_backend.repositories.budget import remaining_budget

ACCOUNT = "123456789012"
REGION = "ap-northeast-1"
PREFIX = f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:ai-interview-dev"


def environment(role):
    return {
        "INTERVIEW_COMPONENT": role,
        "INTERVIEW_ACCOUNT_ID": ACCOUNT,
        "INTERVIEW_REGION": REGION,
        "INTERVIEW_TABLE_NAME": "ai-interview-dev-main",
        "INTERVIEW_FUNCTION_NAME": f"ai-interview-dev-{role}",
        "INTERVIEW_QUEUE_ARN": f"arn:aws:sqs:{REGION}:{ACCOUNT}:ai-interview-dev-main",
        "INTERVIEW_QUEUE_URL": f"https://sqs.{REGION}.amazonaws.com/{ACCOUNT}/ai-interview-dev-main",
        "INTERVIEW_STREAM_ARN": (
            f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/ai-interview-dev-main/"
            "stream/2026-09-13T00:00:00.000"
        ),
        "INTERVIEW_SCHEDULE_ARN": (
            f"arn:aws:scheduler:{REGION}:{ACCOUNT}:schedule/ai-interview-dev/recovery"
        ),
        "INTERVIEW_CLIENT_ID": "testclient123",
        "INTERVIEW_USER_POOL_ID": f"{REGION}_test123",
        "INTERVIEW_API_ID": "testapi123",
        "INTERVIEW_STAGE": "dev",
    }


def context(role="api", alias="live", remaining=60000):
    return SimpleNamespace(
        invoked_function_arn=f"{PREFIX}-{role}:{alias}",
        get_remaining_time_in_millis=lambda: remaining,
    )


def event(owner="synthetic-a", token_use="access"):
    return {
        "version": "2.0",
        "rawPath": "/sessions",
        "requestContext": {
            "accountId": ACCOUNT,
            "apiId": "testapi123",
            "stage": "dev",
            "http": {"method": "POST"},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": owner,
                        "token_use": token_use,
                        "client_id": "testclient123",
                        "iss": f"https://cognito-idp.{REGION}.amazonaws.com/{REGION}_test123",
                    }
                }
            },
        },
    }


@pytest.mark.parametrize("role", ["api", "worker", "dispatcher"])
def test_settings_explicit_and_no_aws_fallback(role):
    values = environment(role)
    assert AwsSettings.load(values, role).table == "ai-interview-dev-main"
    for name in ("INTERVIEW_ACCOUNT_ID", "INTERVIEW_REGION", "INTERVIEW_TABLE_NAME"):
        missing = values.copy()
        missing.pop(name)
        with pytest.raises(ConfigurationError, match="InvalidConfiguration"):
            AwsSettings.load(missing, role)


@pytest.mark.parametrize(
    "name,value",
    [
        ("INTERVIEW_TABLE_NAME", "ai-interview-test-other-main"),
        ("INTERVIEW_QUEUE_ARN", f"arn:aws:sqs:{REGION}:{ACCOUNT}:ai-interview-test-other-main"),
        (
            "INTERVIEW_SCHEDULE_ARN",
            f"arn:aws:scheduler:{REGION}:{ACCOUNT}:schedule/ai-interview-test-other/recovery",
        ),
    ],
)
def test_settings_reject_other_run_in_same_account(name, value):
    values = environment("dispatcher")
    values[name] = value
    if name == "INTERVIEW_QUEUE_ARN":
        values["INTERVIEW_QUEUE_URL"] = (
            f"https://sqs.{REGION}.amazonaws.com/{ACCOUNT}/ai-interview-test-other-main"
        )
    if name == "INTERVIEW_TABLE_NAME":
        values["INTERVIEW_STREAM_ARN"] = (
            f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/{value}/stream/2026-09-13T00:00:00.000"
        )
    with pytest.raises(ConfigurationError):
        AwsSettings.load(values, "dispatcher")


@pytest.mark.parametrize(
    "name,value",
    [
        ("INTERVIEW_QUEUE_ARN", "arn:aws:sqs:us-east-1:123456789012:ai-interview-dev-main"),
        ("INTERVIEW_QUEUE_URL", "https://attacker.invalid/123456789012/ai-interview-dev-main"),
        (
            "INTERVIEW_STREAM_ARN",
            "arn:aws:dynamodb:ap-northeast-1:999999999999:table/other/stream/x",
        ),
        (
            "INTERVIEW_SCHEDULE_ARN",
            "arn:aws:scheduler:ap-northeast-1:123456789012:schedule/other/recovery",
        ),
    ],
)
def test_settings_reject_cross_source(name, value):
    values = environment("dispatcher")
    values[name] = value
    with pytest.raises(ConfigurationError):
        AwsSettings.load(values, "dispatcher")


def test_api_rejects_bad_identity_before_handler():
    seen = []
    entry = ApiEntry(AwsSettings.load(environment("api"), "api"), lambda e: seen.append(e))
    for token_use in ("id", None, "", "Access"):
        assert entry(event(token_use=token_use), context())["statusCode"] == 401
    for field in ("client_id", "iss", "sub"):
        invalid = event()
        invalid["requestContext"]["authorizer"]["jwt"]["claims"][field] = ""
        assert entry(invalid, context())["statusCode"] == 401
    assert seen == []


def test_api_warm_identity_and_budget_isolation():
    seen = []

    def handler(value):
        seen.append(
            (
                value["requestContext"]["authorizer"]["jwt"]["claims"]["sub"],
                remaining_budget.get()(),
            )
        )
        return {"statusCode": 200}

    entry = ApiEntry(AwsSettings.load(environment("api"), "api"), handler)
    assert entry(event(), context(remaining=399))["statusCode"] == 200
    assert remaining_budget.get() is None
    assert entry(event("synthetic-b"), context(remaining=9000))["statusCode"] == 200
    assert seen == [("synthetic-a", 399), ("synthetic-b", 9000)]


def test_api_rejects_wrong_gateway_and_lambda_context():
    entry = ApiEntry(AwsSettings.load(environment("api"), "api"), lambda _: pytest.fail("called"))
    bad = event()
    bad["requestContext"]["apiId"] = "other"
    assert entry(bad, context())["statusCode"] == 401
    assert entry(event(), context(alias="unknown"))["statusCode"] == 500


def test_worker_entry_passes_budget_and_reports_failures():
    class Worker:
        def run(self, owner, eid, generation, remaining):
            assert remaining() == 51000
            raise ValueError("SECRET")

    settings = AwsSettings.load(environment("worker"), "worker")
    entry = WorkerEntry(settings, Worker())
    record = {
        "eventSource": "aws:sqs",
        "eventSourceARN": settings.queue_arn,
        "messageId": "m1",
        "body": json.dumps(
            {
                "eventVersion": 1,
                "type": "EvaluationRequested",
                "ownerSub": "synthetic-a",
                "evaluationId": "10000000-0000-4000-8000-000000000001",
                "dispatchVersion": 1,
            }
        ),
    }
    assert entry({"Records": [record]}, context("worker", remaining=51000)) == {
        "batchItemFailures": [{"itemIdentifier": "m1"}]
    }


def test_dispatcher_alias_cannot_cross_event_types():
    entry = DispatcherEntry(AwsSettings.load(environment("dispatcher"), "dispatcher"), None, None)
    with pytest.raises(RuntimeError, match="InternalInvocationFailed"):
        entry({"eventVersion": 1, "type": "RecoveryTick"}, context("dispatcher", "streams"))
    with pytest.raises(RuntimeError, match="InternalInvocationFailed"):
        entry({"Records": []}, context("dispatcher", "recovery"))


def test_metrics_allowlist_and_sink_failure(capsys):
    rows = []
    metric = Metrics("api", sink=rows.append)
    metric.emit("ApiDuration", 12.5)
    parsed = json.loads(rows[0])
    assert parsed["ApiDuration"] == 12.5
    for name, value in (("SECRET", 1), ("ApiDuration", float("nan")), ("ApiDuration", True)):
        with pytest.raises(ValueError):
            metric.emit(name, value)
    Metrics("worker", sink=lambda _: (_ for _ in ()).throw(OSError("SECRET"))).emit("DBError")
    assert "SECRET" not in capsys.readouterr().out


def test_recovery_heartbeat_only_after_checkpoints(runtime, monkeypatch):
    rows = []
    recovery = Recovery(
        runtime.repository,
        Dispatcher(runtime.repository, runtime.publisher),
        observe=lambda name, value: rows.append((name, value)),
    )
    recovery.tick()
    assert ("RecoveryHeartbeat", 1) in rows
    rows.clear()
    monkeypatch.setattr(runtime.repository, "save_cursor", lambda *_: False)
    recovery.tick()
    assert ("RecoveryHeartbeat", 1) not in rows


def test_aws_get_keeps_storage_and_provider_pure(runtime):
    sid = runtime.application.create(
        "synthetic-a",
        "10000000-0000-4000-8000-000000000001",
        {"category": "career", "difficulty": "standard"},
    ).body["sessionId"]
    before = deepcopy(runtime.repository.snapshot())
    entry = ApiEntry(AwsSettings.load(environment("api"), "api"), runtime.handler)
    request = event()
    request["rawPath"] = f"/sessions/{sid}/question"
    request["requestContext"]["http"]["method"] = "GET"
    for _ in range(3):
        assert entry(request, context())["statusCode"] == 200
    assert runtime.repository.snapshot() == before
    assert runtime.provider.calls == 0
    assert runtime.publisher.events == []
