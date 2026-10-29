"""Public standard-CI diagnostics with synthetic failures and forbidden sockets."""

import json
from types import SimpleNamespace

import pytest

from interview_backend.deployment import DeploymentError


@pytest.fixture
def diagnostic():
    import standard_diagnostics as m

    instance = m.Diagnostic()
    token = m.CURRENT.set(instance)
    try:
        yield m, instance
    finally:
        m.CURRENT.reset(token)


@pytest.mark.parametrize(
    "error,reason",
    [
        (
            DeploymentError("private-token", reason_code="StageRecoveryScopeMismatch"),
            "StageRecoveryScopeMismatch",
        ),
        (ValueError("StateReadbackChanged"), "StateReadbackChanged"),
        (RuntimeError("private-token"), "ExternalOrScopeFailure"),
        (DeploymentError("private-token"), "ExternalOrScopeFailure"),
    ],
)
def test_finite_projection_never_stringifies_exceptions(diagnostic, capsys, error, reason):
    m, instance = diagnostic
    m.checkpoint("state-preflight")
    instance.emit(error)
    output = capsys.readouterr().out
    value = json.loads(output.removeprefix("P4_STANDARD_FAILURE "))
    assert "private-token" not in output
    assert value["reason_code"] == reason
    assert value["failure_stage"] == "state-preflight"
    assert value["process_started"] is value["process_exit_observed"] is False
    assert value["terraform_command_kind"] == "unknown"


def test_hostile_exception_property_and_broken_sink_do_not_leak(diagnostic, monkeypatch):
    _, instance = diagnostic

    class Hostile(Exception):
        @property
        def reason_code(self):
            raise RuntimeError("private-token")

        def __str__(self):
            pytest.fail("private exception was stringified")

    assert instance.projection(Hostile())["reason_code"] == "ExternalOrScopeFailure"
    monkeypatch.setattr(
        "builtins.print", lambda *a, **k: (_ for _ in ()).throw(OSError("private-token"))
    )
    instance.emit(Hostile())


@pytest.mark.parametrize("kind", ["init", "plan", "show", "version"])
@pytest.mark.parametrize("launch_failure,returncode", [(True, None), (False, 0), (False, 1)])
def test_actual_guard_process_status_is_distinct_from_admission(
    diagnostic, monkeypatch, tmp_path, kind, launch_failure, returncode
):
    import plan_authorization as p

    m, instance = diagnostic
    guard = p.Guard.__new__(p.Guard)
    guard.environment = {}
    guard.directory = tmp_path
    guard.plan_started = False
    guard.monotonic = lambda: 0
    guard.remaining = lambda: 7200
    guard.check = lambda *a: None
    guard.record = lambda *a, **k: None
    guard.fail = lambda *a: None
    child = SimpleNamespace(
        returncode=returncode,
        poll=lambda: returncode,
        communicate=lambda **k: (b"private-token", b"private-token"),
    )

    def launch(*a, **k):
        if launch_failure:
            raise OSError("private-token")
        return child

    monkeypatch.setattr(p.subprocess, "Popen", launch)
    monkeypatch.setattr(p, "seal", lambda *a: {})
    if launch_failure or returncode:
        with pytest.raises((OSError, DeploymentError)):
            guard.process(["terraform", kind], cwd=tmp_path, env={})
    else:
        assert guard.process(["terraform", kind], cwd=tmp_path, env={}) == b"private-token"
    value = instance.projection(DeploymentError("PlanProcessFailed"))
    assert value["failure_stage"] == "terraform-" + kind
    assert value["terraform_command_kind"] == kind
    assert value["process_started"] is (not launch_failure)
    assert value["process_exit_observed"] is (not launch_failure)
    # A later command refused before launch must not inherit earlier completion.
    m.process_event("plan", "admission")
    assert instance.started is instance.exited is False


@pytest.mark.parametrize("standard", [False, True])
@pytest.mark.parametrize("operation", ["plan", "apply"])
def test_main_preflight_failure_is_observable_without_admission(
    monkeypatch, capsys, standard, operation
):
    import ci_deploy as c
    import standard_diagnostics as m

    monkeypatch.setenv("P4_STANDARD_ACTIVE", str(standard).lower())
    monkeypatch.setenv("P4_OPERATION", operation)
    monkeypatch.delenv("P4_CLOUD_ACTIVE", raising=False)
    monkeypatch.setattr(
        c,
        "preflight",
        lambda *a: (_ for _ in ()).throw(DeploymentError("PlanApprovalHashMismatch")),
    )
    monkeypatch.setattr(c, "initialize", lambda *a: pytest.fail("admission reached"))
    assert c.main() == 1
    output = capsys.readouterr()
    assert output.err == "P4CiDeploymentFailed\n"
    if standard:
        value = json.loads(output.out.removeprefix("P4_STANDARD_FAILURE "))
        assert value["failure_stage"] == "preflight"
        assert value["reason_code"] == "PlanApprovalHashMismatch"
    else:
        assert output.out == ""
    assert m.CURRENT.get() is None


@pytest.mark.parametrize("operation", ["plan", "apply"])
@pytest.mark.parametrize(
    "issued,expiry,reason",
    [
        (
            "2026-10-21T00:00:00Z",
            "2026-10-23T23:07:30Z",
            "StandardApprovalExpiredOrNotIssued",
        ),
        (
            "2026-10-17T00:00:00Z",
            "2026-10-20T00:00:00Z",
            "StandardApprovalExpiredOrNotIssued",
        ),
        (
            "2026-10-22T00:00:00Z",
            "2026-10-25T00:00:00Z",
            "StandardApprovalExpiredOrNotIssued",
        ),
        ("private-token", "2026-10-24T00:00:00Z", "AbsoluteUtcApprovalTimestampRequired"),
        ("2026-13-21T00:00:00Z", "2026-10-24T00:00:00Z", "InvalidApprovalTimestamp"),
    ],
)
def test_real_standard_preflight_refusal_is_finite_and_never_reaches_execution(
    monkeypatch, capsys, operation, issued, expiry, reason
):
    from datetime import UTC, datetime

    import ci_deploy as c
    import ci_identity
    import plan_authorization
    import standard_diagnostics as m
    from test_standard_ci import context

    for key, value in context(operation).items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("P4_CLOUD_ACTIVE", raising=False)
    monkeypatch.setenv("P4_APPROVED_AT_UTC", issued)
    monkeypatch.setenv("P4_APPROVAL_EXPIRES_AT", expiry)
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "private-token")
    monkeypatch.setenv("P4_DEPLOY_INPUTS", "private-email@example.invalid")
    monkeypatch.setattr(
        ci_identity,
        "datetime",
        SimpleNamespace(now=lambda tz: datetime(2026, 10, 21, 1, tzinfo=UTC)),
    )

    def forbidden(*args, **kwargs):
        pytest.fail("Rejected preflight reached execution or remote history")

    monkeypatch.setattr(c, "initialize", forbidden)
    monkeypatch.setattr(c, "checked_git", forbidden)
    monkeypatch.setattr(c, "role_session", forbidden)
    monkeypatch.setattr(c, "execute", forbidden)
    monkeypatch.setattr(plan_authorization, "verify_run_history", forbidden)
    assert c.main() == 1
    output = capsys.readouterr()
    assert output.err == "P4CiDeploymentFailed\n"
    value = json.loads(output.out.removeprefix("P4_STANDARD_FAILURE "))
    assert value["reason_code"] == reason
    assert value["failure_stage"] == "preflight"
    assert value["process_started"] is value["process_exit_observed"] is False
    assert value["terraform_command_kind"] == "unknown"
    assert all(
        private not in output.out + output.err
        for private in (issued, expiry, "private-token", "private-email@example.invalid", "a" * 40)
    )
    assert m.CURRENT.get() is None


def test_apply_after_preflight_does_not_claim_unobserved_process_state(monkeypatch, capsys):
    import ci_deploy as c
    import plan_authorization
    import standard_diagnostics as m

    monkeypatch.setenv("P4_STANDARD_ACTIVE", "true")
    monkeypatch.setenv("P4_OPERATION", "apply")
    monkeypatch.setenv("P4_PLAN_HASH", "private-plan-hash")
    monkeypatch.delenv("P4_CLOUD_ACTIVE", raising=False)
    monkeypatch.setattr(c, "preflight", lambda *a: ("123456789012", "ap-northeast-1", "apply", {}))
    monkeypatch.setattr(
        plan_authorization,
        "verify_run_history",
        lambda *a: (_ for _ in ()).throw(
            DeploymentError("private-token", reason_code="PlanApprovalAlreadyConsumed")
        ),
    )
    assert c.main() == 1
    output = capsys.readouterr()
    value = json.loads(output.out.removeprefix("P4_STANDARD_FAILURE "))
    assert value["reason_code"] == "PlanApprovalAlreadyConsumed"
    assert value["failure_stage"] == "authorization"
    assert value["process_started"] is value["process_exit_observed"] is None
    assert "private" not in output.out + output.err
    assert m.CURRENT.get() is None


def test_unknown_stage_and_command_cannot_publish_arbitrary_values(diagnostic):
    m, instance = diagnostic
    m.checkpoint("private-token")
    m.process_event("private-token", "admission")
    value = instance.projection(ValueError("private-token"))
    assert value["failure_stage"] == value["terraform_command_kind"] == "unknown"
    assert "private-token" not in json.dumps(value)


@pytest.mark.parametrize(
    "field,value", [("audit_rule", "private-token"), ("audit_resource_index", "private-token")]
)
def test_stage_audit_fields_cannot_publish_arbitrary_values(diagnostic, field, value):
    _, instance = diagnostic
    error = DeploymentError("StageRecoveryPlanRejected")
    error.audit_rule = "plan-shape"
    error.audit_resource_index = 1
    setattr(error, field, value)
    result = instance.projection(error)
    assert "private-token" not in json.dumps(result)
    if field == "audit_rule":
        assert "stage_audit" not in result
    else:
        assert result["stage_audit"] == {"rule": "plan-shape"}


@pytest.mark.parametrize(
    "suffix,status,reason",
    [
        (
            "environments/dev-plan/variables?per_page=30&page=1",
            403,
            "GitHubEnvironmentHttpRejected",
        ),
        (
            "environments/dev-apply/variables?per_page=30&page=2",
            403,
            "GitHubEnvironmentHttpRejected",
        ),
        (
            "environments/dev-plan/variables?per_page=30&page=1",
            500,
            "GitHubEnvironmentServiceUnavailable",
        ),
        ("git/ref/heads/main", 403, "GitHubControlPlaneUnavailable"),
    ],
)
def test_environment_variable_http_refusal_remains_fail_closed(
    diagnostic, monkeypatch, capsys, suffix, status, reason
):
    import io
    from urllib.error import HTTPError

    import github_control as g

    m, instance = diagnostic
    requests = []

    def open_request(request, **kwargs):
        requests.append(request)
        raise HTTPError(
            "https://private.invalid/private-token",
            status,
            "private-token",
            {"private": "private-token"},
            io.BytesIO(b"private-token"),
        )

    monkeypatch.setattr(g, "build_opener", lambda *a: SimpleNamespace(open=open_request))
    monkeypatch.setattr(g.time, "time", lambda: 1000)
    m.checkpoint("readiness-readback")
    with pytest.raises(DeploymentError, match="^GitHubControlPlaneUnavailable$") as failure:
        g.github_json(
            suffix,
            {
                "GH_TOKEN": "private-token",
                "GITHUB_REPOSITORY": g.REPOSITORY,
                "GITHUB_REPOSITORY_ID": "1361325921",
                "P4_ENV_READ_TOKEN": "private_token",
                "P4_ENV_TOKEN_STARTED_AT": "1000",
            },
        )
    assert len(requests) == 1  # No alternate token, endpoint or retry.
    assert failure.value.reason_code == reason
    instance.emit(failure.value)
    output = capsys.readouterr().out
    assert "private-token" not in output and suffix not in output
    assert json.loads(output.removeprefix("P4_STANDARD_FAILURE "))["reason_code"] == reason


def test_exit_observation_survives_private_journal_write_failure(diagnostic, monkeypatch, tmp_path):
    import plan_authorization as p

    _, instance = diagnostic
    guard = p.Guard.__new__(p.Guard)
    guard.environment = {}
    guard.directory = tmp_path
    guard.plan_started = False
    guard.monotonic = lambda: 0
    guard.remaining = lambda: 7200
    guard.check = lambda *a: None
    guard.fail = lambda *a: None

    def record(stage, **kwargs):
        if stage == "process-exit-observed":
            raise OSError("private-journal-path")

    guard.record = record
    monkeypatch.setattr(
        p.subprocess,
        "Popen",
        lambda *a, **k: SimpleNamespace(
            returncode=0,
            poll=lambda: 0,
            communicate=lambda **k: (b"", b""),
        ),
    )
    with pytest.raises(OSError):
        guard.process(["terraform", "init"], cwd=tmp_path, env={})
    assert instance.started is instance.exited is True


def test_stage_update_denial_has_specific_hint_without_private_output(diagnostic):
    from plan_process_diagnostics import summarize_failure

    _, instance = diagnostic
    error = DeploymentError("StageRecoveryApplyProcessFailed")
    error.process_diagnostic = summarize_failure(
        1, b"private stdout", b"BadRequestException private arn logs:UpdateLogDelivery"
    )
    result = instance.projection(error)
    assert result["diagnostic_hints"] == ["api-bad-request-marker", "update-log-delivery-marker"]
    assert result["hints_are_root_cause_proof"] is False
    assert "private" not in json.dumps(result)
