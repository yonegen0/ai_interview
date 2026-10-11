"""Synthetic approval packages, clock, processes and APIs; no live AWS."""

import hashlib
import json
import signal
import subprocess
import textwrap
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest


def environment(configuration=None, artifact_digest="a" * 64, run_id="123"):
    import plan_authorization as module

    config = configuration or {}
    descriptor = {
        "schema_version": 1,
        "operation": "plan",
        "execution_ready": True,
        "repository": "yonegen0/ai_interview",
        "source_sha": "a" * 40,
        "account_id": "123456789012",
        "region": "ap-northeast-1",
        "oidc_subject": "subject",
        "expires_at_utc": "2099-01-01T00:00:00Z",
        "oidc_limits": dict(module.LIMITS),
        "sts_limits": dict(module.LIMITS),
        "duration_seconds": 3600,
        "artifact_sha256": artifact_digest,
        "configuration_sha256": module.canonical_hash(config),
        "s3_put_limit": 6,
        "cleanup_seconds": 120,
        "deadline_policy": "no-new-operations;inflight-normal-unlock-only",
        "operation_budgets_seconds": dict(module.BUDGETS),
    }
    env = {
        "GITHUB_SHA": "a" * 40,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_RUN_ID": run_id,
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_REPOSITORY": "yonegen0/ai_interview",
        "AWS_DEV_ACCOUNT_ID": "123456789012",
        "AWS_REGION": "ap-northeast-1",
        "P4_OIDC_SUBJECT": "subject",
        "P4_PACKAGE_SHA256": artifact_digest,
        "P4_DEPLOY_INPUTS": json.dumps(config),
        "P4_OPERATION": "plan",
        "P4_PLAN_JOB_STARTED_MONOTONIC": str(time.monotonic()),
    }
    bind(env, descriptor)
    return env, descriptor


def bind(env, descriptor):
    import plan_authorization as module

    raw = "# Synthetic approval\n" + module.START + json.dumps(descriptor) + module.END + "\n"
    env.update(
        P4_PLAN_APPROVAL_PACKAGE=raw,
        P4_PLAN_APPROVAL_SHA256=hashlib.sha256(raw.encode()).hexdigest(),
        P4_PLAN_APPROVAL_EXPIRES_AT=descriptor.get("expires_at_utc", ""),
    )


def run_record(env, **changes):
    return {
        "id": int(env["GITHUB_RUN_ID"]),
        "run_attempt": 1,
        "head_sha": env["GITHUB_SHA"],
        "head_branch": "main",
        "event": "workflow_dispatch",
        "path": ".github/workflows/p4-deploy.yml",
        "repository": {"full_name": "yonegen0/ai_interview"},
        "display_title": "P4 plan approval-" + env["P4_PLAN_APPROVAL_SHA256"],
        **changes,
    }


def install_transport_approval(monkeypatch, configuration=None):
    """Real Guard with synthetic durable GitHub history for existing transports."""
    import os

    import github_control

    env, _ = environment(
        configuration,
        os.environ.get("P4_PACKAGE_SHA256", "a" * 64),
        os.environ.get("GITHUB_RUN_ID", "123"),
    )
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(
        github_control,
        "github_json",
        lambda suffix, env: {"total_count": 1, "workflow_runs": [run_record(env)]},
    )


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 11, tzinfo=UTC)
        self.tick = 0

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)
        self.tick += seconds


def guard(tmp_path, *, seconds=7200, history=None):
    import plan_authorization as module

    env, descriptor = environment()
    clock = Clock()
    env["P4_PLAN_JOB_STARTED_MONOTONIC"] = "0"
    descriptor["expires_at_utc"] = (clock.now + timedelta(seconds=seconds)).isoformat()
    bind(env, descriptor)
    history = history or {"total_count": 1, "workflow_runs": [run_record(env)]}
    instance = module.Guard(
        env,
        tmp_path / "journal",
        clock=lambda: clock.now,
        monotonic=lambda: clock.tick,
        github_get=lambda *a: history,
    )
    return instance, env, descriptor, clock


@pytest.mark.parametrize("seconds", [1, 0, -1])
def test_deadline_before_equal_after(tmp_path, seconds):
    if seconds > 0:
        instance, *_ = guard(tmp_path, seconds=seconds)
        instance.check("offline", 0)
    else:
        with pytest.raises(ValueError, match="ExpiredOrInsufficientTime"):
            guard(tmp_path, seconds=seconds)


@pytest.mark.parametrize(
    "expiry",
    [
        None,
        "",
        "tomorrow",
        "2026-02-30T00:00:00Z",
        "2026-10-11T00:00:00",
        "2026-10-11T09:00:00+09:00",
    ],
)
def test_invalid_missing_and_non_utc_deadline(expiry):
    import plan_authorization as module

    env, descriptor = environment()
    descriptor["expires_at_utc"] = expiry
    bind(env, descriptor)
    with pytest.raises(ValueError):
        module.load(env)


@pytest.mark.parametrize(
    "fault",
    [
        "missing-package",
        "missing-deadline",
        "deadline",
        "hash",
        "source",
        "configuration",
        "role-limits",
        "not-ready",
    ],
)
def test_package_ci_binding_fail_closed(fault):
    import plan_authorization as module

    env, descriptor = environment()
    if fault == "missing-package":
        del env["P4_PLAN_APPROVAL_PACKAGE"]
    elif fault == "missing-deadline":
        del env["P4_PLAN_APPROVAL_EXPIRES_AT"]
    elif fault == "deadline":
        env["P4_PLAN_APPROVAL_EXPIRES_AT"] = "2099-01-02T00:00:00Z"
    elif fault == "hash":
        env["P4_PLAN_APPROVAL_SHA256"] = "b" * 64
    elif fault == "source":
        env["GITHUB_SHA"] = "b" * 40
    elif fault == "configuration":
        env["P4_DEPLOY_INPUTS"] = '{"api_enabled":true}'
    else:
        descriptor["oidc_limits" if fault == "role-limits" else "execution_ready"] = (
            {"plan": 4, "artifact": 2} if fault == "role-limits" else False
        )
        bind(env, descriptor)
    with pytest.raises(ValueError):
        module.load(env)


def test_expiry_midway_blocks_every_later_operation_and_clock_rollback(tmp_path):
    instance, _, _, clock = guard(tmp_path, seconds=100)
    assert instance.authenticate("oidc", "plan", lambda: "token") == "token"
    clock.advance(100)
    clock.now -= timedelta(hours=1)  # Monotonic time prevents deadline extension.
    calls = []
    with pytest.raises(ValueError):
        instance.authenticate("sts", "plan", lambda: calls.append("AWS"))
    with pytest.raises(ValueError, match="Stopped"):
        instance.check("put", 0)
    assert calls == []


@pytest.mark.parametrize(
    "kind,role,limit",
    [(k, r, n) for k in ("oidc", "sts") for r, n in (("plan", 3), ("artifact", 2))],
)
def test_separate_authentication_limits(tmp_path, kind, role, limit):
    instance, *_ = guard(tmp_path)
    calls = []
    for _ in range(limit):
        instance.authenticate(kind, role, lambda: calls.append(kind))
    with pytest.raises(ValueError, match="LimitExceeded"):
        instance.authenticate(kind, role, lambda: calls.append("excess"))
    assert len(calls) == limit
    assert instance.counts[kind][role] == limit
    assert instance.counts["sts" if kind == "oidc" else "oidc"][role] == 0


@pytest.mark.parametrize("kind", ["oidc", "sts"])
def test_failed_authentication_consumes_attempt_and_stops_before_retry(tmp_path, kind):
    instance, *_ = guard(tmp_path)
    calls = []

    def failed():
        calls.append("attempt")
        raise TimeoutError("SECRET synthetic-token")

    with pytest.raises(TimeoutError):
        instance.authenticate(kind, "plan", failed)
    for _ in range(4):
        with pytest.raises(ValueError, match="Stopped"):
            instance.authenticate(kind, "plan", failed)
    assert calls == ["attempt"] and instance.counts[kind]["plan"] == 1
    evidence = "".join(path.read_text() for path in instance.directory.iterdir())
    assert (
        "TimeoutError" in evidence
        and "SECRET" not in evidence
        and "synthetic-token" not in evidence
    )


@pytest.mark.parametrize("role", ["deploy", "test", "other"])
def test_unapproved_roles_refused_without_external_call(tmp_path, role):
    instance, *_ = guard(tmp_path)
    with pytest.raises(ValueError):
        instance.authenticate("oidc", role, lambda: pytest.fail("token requested"))


def test_replay_failed_run_and_new_attempt_are_rejected(tmp_path):
    import plan_authorization as module

    env, descriptor = environment(run_id="124")
    rows = [run_record(env, id=123, status="completed", conclusion="failure"), run_record(env)]
    with pytest.raises(ValueError, match="AlreadyConsumed"):
        module.verify_run_history(
            env["P4_PLAN_APPROVAL_SHA256"],
            env,
            lambda *a: {"total_count": 2, "workflow_runs": rows},
        )
    env["GITHUB_RUN_ATTEMPT"] = "2"
    with pytest.raises(ValueError, match="ScopeMismatch"):
        module.load(env)
    instance, env, _, clock = guard(tmp_path)
    with pytest.raises(FileExistsError):
        module.Guard(env, instance.directory, clock=lambda: clock.now)


@pytest.mark.parametrize("total,rows", [(1000, []), (2, []), (1, [])])
def test_incomplete_history_is_not_authorization(total, rows):
    import plan_authorization as module

    env, _ = environment()
    with pytest.raises(ValueError):
        module.verify_run_history(
            env["P4_PLAN_APPROVAL_SHA256"],
            env,
            lambda *a: {"total_count": total, "workflow_runs": rows},
        )


def test_partial_put_unknown_preserves_journal_and_never_resends(tmp_path):
    instance, env, _, clock = guard(tmp_path)
    calls = []
    bucket = "ai-interview-artifacts-123456789012-ap-northeast-1"
    key = f"lambda/{env['GITHUB_SHA']}/123/1/app.zip"

    def partial():
        calls.append(key)
        clock.advance(7200)
        return "may-have-written"

    with pytest.raises(ValueError):
        instance.put(bucket, key, partial)
    with pytest.raises(ValueError, match="Stopped"):
        instance.put(bucket, key, partial)
    assert calls == [key] and key in instance.puts
    assert any("outcome-not-success" in p.read_text() for p in instance.directory.iterdir())


def test_s3_scope_count_envelope_last_and_deadline(tmp_path):
    instance, env, _, clock = guard(tmp_path)
    bucket = "ai-interview-artifacts-123456789012-ap-northeast-1"
    keys = [f"lambda/{env['GITHUB_SHA']}/123/1/app.zip"] + [
        "plans/123/1/" + name
        for name in (
            "dev.tfplan",
            "plan.json",
            "summary.json",
            "review.private.json",
            "envelope.json",
        )
    ]
    calls = []
    for key in keys:
        instance.put(bucket, key, lambda key=key: calls.append(key))
    with pytest.raises(ValueError):
        instance.put(bucket, keys[-1], lambda: pytest.fail("seventh Put"))
    assert calls == keys


@pytest.mark.parametrize("unknown", [False, True])
def test_terraform_deadline_interrupts_once_without_force_unlock_or_retry(
    tmp_path, monkeypatch, unknown
):
    import plan_authorization as module

    instance, _, _, clock = guard(tmp_path)
    commands, signals = [], []
    calls = 0

    def communicate(timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            clock.advance(1200)
            raise subprocess.TimeoutExpired("terraform", timeout)
        if unknown:
            raise subprocess.TimeoutExpired("terraform", timeout)
        return b"private output", b"private token"

    fake = SimpleNamespace(
        communicate=communicate, poll=lambda: None, send_signal=signals.append, returncode=1
    )
    monkeypatch.setattr(
        module.subprocess, "Popen", lambda command, **kw: commands.append(command) or fake
    )
    with pytest.raises(ValueError, match="DeadlineStop"):
        instance.process(["terraform", "plan"], cwd=tmp_path, env={})
    with pytest.raises(ValueError, match="Stopped"):
        instance.process(["terraform", "plan"], cwd=tmp_path, env={})
    assert commands == [["terraform", "plan"]] and signals == [signal.SIGINT]
    evidence = "".join(p.read_text() for p in instance.directory.iterdir())
    assert "private token" not in evidence and "private output" not in evidence
    assert ("lock-outcome-unknown" in evidence) == unknown


def test_insufficient_operation_budget_refuses_before_process(tmp_path, monkeypatch):
    import plan_authorization as module

    instance, *_ = guard(tmp_path, seconds=1320)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **kw: pytest.fail("process started"))
    with pytest.raises(ValueError):
        instance.process(["terraform", "plan"], cwd=tmp_path, env={})


def test_workflow_checks_deadline_before_checkout_and_preserves_journal():
    workflow = (Path(__file__).parents[3] / ".github/workflows/p4-deploy.yml").read_text()
    assert workflow.index("Check absolute approval deadline at job start") < workflow.index(
        "actions/checkout@"
    )
    assert "timeout-minutes: 55" in workflow
    assert "if: always() && inputs.operation == 'plan'" in workflow


def test_direct_terraform_plan_requires_initialized_authorization(monkeypatch, tmp_path):
    from test_p4_tools import tool

    module = tool("terraform_dev")
    monkeypatch.setattr(module, "require_aws_execution", lambda: None)
    monkeypatch.setattr(module, "account_settings", lambda *a: pytest.fail("AWS setup"))
    with pytest.raises(ValueError, match="NotInitialized"):
        module.execute("plan", tmp_path / "inputs", tmp_path)


@pytest.mark.parametrize(
    "source",
    [
        "AWS_PROFILE",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        "AWS_ACCESS_KEY_ID",
        "AWS_ENDPOINT_URL_STS",
    ],
)
def test_conflicting_credential_provider_refused_before_github_or_auth(tmp_path, source):
    import plan_authorization as module

    env, _ = environment()
    env[source] = "synthetic-private-provider"
    with pytest.raises(ValueError, match="CredentialSourceConflict"):
        module.Guard(env, tmp_path / "journal", github_get=lambda *a: pytest.fail("API called"))


@pytest.mark.parametrize("fault", [None, "oidc-timeout", "sts-timeout", "wrong-role", "expired"])
def test_ci_identity_wires_real_guard_to_separate_requests_and_stops(tmp_path, monkeypatch, fault):
    import base64
    from io import BytesIO

    import boto3
    import plan_authorization as module
    from test_p4_tools import tool

    instance, env, _, clock = guard(tmp_path)
    monkeypatch.setattr(module, "CURRENT", instance)
    identity = tool("ci_identity")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("P4_AWS_EXECUTION_READY", "true")
    monkeypatch.setenv(
        "ACTIONS_ID_TOKEN_REQUEST_URL", "https://test.actions.githubusercontent.com/token"
    )
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "SECRET-request-token")
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(key, "synthetic")  # Restore SDK-written environment after this test.
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
    claims = {
        "iss": "https://token.actions.githubusercontent.com",
        "aud": "sts.amazonaws.com",
        "sub": "subject",
        "repository": env["GITHUB_REPOSITORY"],
        "environment": "dev",
        "sha": env["GITHUB_SHA"],
        "ref": env["GITHUB_REF"],
    }
    token = (
        "SECRET." + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode() + ".signature"
    )
    calls = {"oidc": 0, "sts": 0, "identity": 0}

    def request_token(*args, **kwargs):
        calls["oidc"] += 1
        if fault == "oidc-timeout":
            raise TimeoutError("SECRET token request failed")
        assert kwargs["timeout"] == 15
        return BytesIO(json.dumps({"value": token}).encode())

    def exchange(**kwargs):
        calls["sts"] += 1
        if fault == "sts-timeout":
            raise TimeoutError("SECRET credentials unknown")
        role = kwargs["RoleArn"].split("-")[-1]
        assert kwargs["DurationSeconds"] == 3600 and kwargs["WebIdentityToken"] == token
        return {
            "AssumedRoleUser": {
                "Arn": (
                    f"arn:aws:sts::123456789012:assumed-role/ai-interview-ci-{role}/p4-123-{role}"
                    if fault != "wrong-role"
                    else "arn:aws:sts::123456789012:assumed-role/other/session"
                )
            },
            "ResponseMetadata": {"RequestId": "synthetic-request-id"},
            "Credentials": {
                "AccessKeyId": "synthetic",
                "SecretAccessKey": "synthetic",
                "SessionToken": "synthetic",
                "Expiration": clock.now + timedelta(seconds=-1 if fault == "expired" else 3600),
            },
        }

    def client(name, **kwargs):
        assert name == "sts" and kwargs["config"].retries == {"total_max_attempts": 1}
        assert kwargs["endpoint_url"] == "https://sts.ap-northeast-1.amazonaws.com"
        return SimpleNamespace(assume_role_with_web_identity=exchange)

    def checked(account, region, *, environment):
        calls["identity"] += 1
        assert environment["AWS_SESSION_TOKEN"] == "synthetic"
        return "checked-session"

    monkeypatch.setattr(identity, "build_opener", lambda *a: SimpleNamespace(open=request_token))
    monkeypatch.setattr(boto3, "Session", lambda **kw: SimpleNamespace(client=client))
    monkeypatch.setattr(identity, "checked_session", checked)
    for role in ("plan", "plan", "artifact", "plan", "artifact"):
        if fault:
            with pytest.raises(ValueError):
                identity.assume(role, "123456789012", "ap-northeast-1", expected_subject="subject")
        else:
            assert (
                identity.assume(role, "123456789012", "ap-northeast-1", expected_subject="subject")
                == "checked-session"
            )
    if fault:
        assert calls == {"oidc": 1, "sts": int(fault != "oidc-timeout"), "identity": 0}
    else:
        assert calls == {"oidc": 5, "sts": 5, "identity": 5}
        assert instance.counts == {
            "oidc": {"plan": 3, "artifact": 2},
            "sts": {"plan": 3, "artifact": 2},
        }
    evidence = "".join(p.read_text() for p in instance.directory.iterdir())
    assert "SECRET" not in evidence and token not in evidence


@pytest.mark.parametrize("elapsed", [0, 3120])
def test_outer_job_budget_includes_checkout_and_setup(tmp_path, elapsed):
    instance, _, _, clock = guard(tmp_path)
    clock.advance(elapsed)
    if elapsed:
        with pytest.raises(ValueError):
            instance.check("authenticate-after-long-setup", 0)
    else:
        instance.check("authenticate", 20)


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_job_first_step_mock_clock_exact_deadline_and_evidence(tmp_path, monkeypatch, offset):
    import datetime as datetime_module
    import sys

    env, descriptor = environment()
    now = datetime(2026, 10, 11, tzinfo=UTC)
    descriptor["expires_at_utc"] = (now + timedelta(seconds=offset)).isoformat()
    bind(env, descriptor)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "github-env"))

    class MockDatetime:
        now = staticmethod(lambda zone: now)
        fromisoformat = staticmethod(datetime.fromisoformat)

    monkeypatch.setitem(
        sys.modules,
        "datetime",
        SimpleNamespace(datetime=MockDatetime, timezone=datetime_module.timezone),
    )
    workflow = (Path(__file__).parents[3] / ".github/workflows/p4-deploy.yml").read_text()
    script = textwrap.dedent(
        workflow.split("python3 - <<'PY'\n", 1)[1].split("          PY\n", 1)[0]
    )
    if offset > 0:
        exec(compile(script, "job-start-mock", "exec"), {})
    else:
        with pytest.raises(SystemExit, match="JobStartRefused"):
            exec(compile(script, "job-start-mock", "exec"), {})
    record = json.loads((tmp_path / "p4-plan-approval-job-start.private.json").read_text())
    assert record["status"] == ("passed" if offset > 0 else "refused")
