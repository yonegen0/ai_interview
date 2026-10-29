"""Apply lifecycle observations and secret-free failures; no real child or network."""

import json
from types import SimpleNamespace

import pytest

from interview_backend.deployment import DeploymentError


@pytest.fixture
def harness(monkeypatch):
    import ci_identity
    import stage_recovery as recovery
    import standard_diagnostics as diagnostics

    monkeypatch.setattr(ci_identity, "standard_context", lambda *a, **k: None)
    diagnostic = diagnostics.Diagnostic()
    token = diagnostics.CURRENT.set(diagnostic)
    try:
        yield recovery, diagnostics, diagnostic
    finally:
        diagnostics.CURRENT.reset(token)


def child(returncode=0):
    return SimpleNamespace(
        returncode=returncode,
        poll=lambda: returncode,
        communicate=lambda **k: (b"private stdout", b"private stderr"),
    )


def apply(recovery, tmp_path):
    return recovery.apply_process(
        ["terraform", "apply", "private-plan-path"], tmp_path, cwd=tmp_path, env={}
    )


@pytest.mark.parametrize("code", [0, 1, 2, -9])
def test_exit_is_observed_before_completion_and_raw_output_never_leaves_memory(
    harness, monkeypatch, tmp_path, capsys, code
):
    r, _, d = harness
    process = child(code)
    process.communicate = lambda **k: (
        b"private stdout",
        b"private email@example.invalid arn:private BadRequestException logs:ListLogDeliveries",
    )
    monkeypatch.setattr(r.subprocess, "Popen", lambda *a, **k: process)
    if code:
        with pytest.raises(DeploymentError, match="StageRecoveryApplyProcessFailed") as raised:
            apply(r, tmp_path)
        error = raised.value
        summary = json.loads((tmp_path / "recovery-process-failure.private.json").read_bytes())
        assert summary["raw_output_preserved"] is False
        assert summary["returncode"] == code
    else:
        assert apply(r, tmp_path) == b"private stdout"
        error = DeploymentError("StageRecoveryScopeMismatch")
    value = d.projection(error)
    assert value["failure_stage"] == "terraform-apply"
    assert value["process_started"] is value["process_exit_observed"] is True
    assert value["process_returncode"] == code
    assert value["terraform_command_kind"] == "apply"
    if code:
        assert value["diagnostic_hints"] == [
            "api-bad-request-marker",
            "list-log-deliveries-marker",
        ]
        assert value["hints_are_root_cause_proof"] is False
    d.emit(error)
    output = capsys.readouterr()
    persisted = "".join(p.read_text() for p in tmp_path.iterdir())
    for secret in ("private stdout", "private email", "email@example.invalid", "arn:private"):
        assert secret not in output.out + output.err + persisted
    assert not (tmp_path / "apply-completed.json").exists()


@pytest.mark.parametrize("failure", ["admission", "launch", "initial-journal", "exit-journal"])
def test_failures_before_and_after_launch_are_distinct(harness, monkeypatch, tmp_path, failure):
    import ci_identity

    r, m, d = harness
    m.process_event("apply", "admission")
    m.process_event("apply", "launched")
    m.process_event("apply", "exit-observed", returncode=42)
    launches = []

    def launch(*a, **k):
        launches.append(True)
        if failure == "launch":
            raise OSError("private token")
        return child()

    monkeypatch.setattr(r.subprocess, "Popen", launch)
    expected = {
        "admission": "StandardApprovalExpiredOrNotIssued",
        "launch": "StageRecoveryApplyLaunchFailed",
        "initial-journal": "StageRecoveryApplyJournalFailed",
        "exit-journal": "StageRecoveryApplyJournalFailed",
    }[failure]
    if failure == "admission":

        def refuse(*a, **k):
            raise DeploymentError(expected)

        monkeypatch.setattr(ci_identity, "standard_context", refuse)
    elif "journal" in failure:
        name = "started" if failure == "initial-journal" else "exit"
        path = tmp_path / f"recovery-process-{name}.private.json"
        path.write_text("preserved existing evidence")
    with pytest.raises(DeploymentError, match=expected) as raised:
        apply(r, tmp_path)
    value = d.projection(raised.value)
    assert value["reason_code"] == expected
    assert value["process_started"] is (failure == "exit-journal")
    assert value["process_exit_observed"] is (failure == "exit-journal")
    assert value["process_returncode"] == (0 if failure == "exit-journal" else None)
    assert len(launches) == int(failure in {"launch", "exit-journal"})
    if "journal" in failure:
        assert path.read_text() == "preserved existing evidence"


@pytest.mark.parametrize("unknown", [False, True])
def test_deadline_interrupts_once_and_records_only_observed_exit(
    harness, monkeypatch, tmp_path, unknown
):
    r, _, d = harness
    ticks = iter([0, 1201])
    monkeypatch.setattr(r.time, "monotonic", lambda: next(ticks))
    signals, launches = [], []
    process = child(-2)
    process.poll = lambda: None
    process.send_signal = signals.append

    def communicate(**k):
        if unknown:
            raise r.subprocess.TimeoutExpired("private command", k["timeout"])
        return b"private stdout", b"private stderr"

    process.communicate = communicate

    def launch(*a, **k):
        launches.append(True)
        return process

    monkeypatch.setattr(r.subprocess, "Popen", launch)
    with pytest.raises(DeploymentError, match="StageRecoveryApplyDeadlineStop") as raised:
        apply(r, tmp_path)
    value = d.projection(raised.value)
    assert value["reason_code"] == "StageRecoveryApplyDeadlineStop"
    assert value["process_started"] is True
    assert value["process_exit_observed"] is (not unknown)
    assert value["process_returncode"] == (None if unknown else -2)
    assert launches == [True] and signals == [r.signal.SIGINT]
    if unknown:
        evidence = json.loads((tmp_path / "recovery-process-unknown.private.json").read_bytes())
        assert evidence["retry_authorized"] is False


@pytest.mark.parametrize("failure", ["observation", "keyboard", "context-after-exit"])
def test_exceptions_preserve_child_observations_and_do_not_retry(
    harness, monkeypatch, tmp_path, failure
):
    import ci_identity

    r, _, d = harness
    process = child()
    calls, signals = [], []
    if failure != "context-after-exit":
        process.poll = lambda: None
        process.send_signal = signals.append

        def communicate(**k):
            calls.append(k["timeout"])
            if len(calls) == 1:
                if failure == "keyboard":
                    raise KeyboardInterrupt("private token")
                raise OSError("private token")
            return b"", b""

        process.communicate = communicate
    else:
        contexts = []

        def context(*a, **k):
            contexts.append(k["reserve"])
            if len(contexts) == 3:
                raise DeploymentError("StandardApprovalExpiredOrNotIssued")

        monkeypatch.setattr(ci_identity, "standard_context", context)
    launches = []

    def launch(*a, **k):
        launches.append(True)
        return process

    monkeypatch.setattr(r.subprocess, "Popen", launch)
    with pytest.raises(KeyboardInterrupt if failure == "keyboard" else DeploymentError) as raised:
        apply(r, tmp_path)
    value = d.projection(raised.value)
    assert value["process_started"] is value["process_exit_observed"] is True
    assert value["process_returncode"] == 0
    assert launches == [True]
    assert signals == ([] if failure == "context-after-exit" else [r.signal.SIGINT])
    assert "private token" not in json.dumps(value)
    if failure == "observation":
        assert value["reason_code"] == "StageRecoveryApplyObservationFailed"


def test_one_second_poll_timeout_is_not_an_apply_failure(harness, monkeypatch, tmp_path):
    r, _, d = harness
    process = child()
    calls = []

    def communicate(**k):
        calls.append(True)
        if len(calls) == 1:
            raise r.subprocess.TimeoutExpired("private command", 1)
        return b"ok", b""

    process.communicate = communicate
    monkeypatch.setattr(r.subprocess, "Popen", lambda *a, **k: process)
    assert apply(r, tmp_path) == b"ok"
    assert calls == [True, True] and d.returncode == 0


def test_poll_observes_exit_after_communicate_exception(harness, monkeypatch, tmp_path):
    r, _, d = harness
    process = child(2)

    def fail(**k):
        raise OSError("private observation failure")

    process.communicate = fail
    monkeypatch.setattr(r.subprocess, "Popen", lambda *a, **k: process)
    with pytest.raises(DeploymentError, match="StageRecoveryApplyObservationFailed") as raised:
        apply(r, tmp_path)
    value = d.projection(raised.value)
    assert value["process_exit_observed"] is True and value["process_returncode"] == 2


@pytest.mark.parametrize("code", [True, "private token", None, 2**40])
def test_returncode_and_hints_projection_reject_untrusted_values(harness, code):
    _, m, d = harness
    m.process_event("apply", "admission")
    m.process_event("apply", "launched")
    m.process_event("apply", "exit-observed", returncode=code)
    error = DeploymentError("StageRecoveryApplyProcessFailed")
    error.process_diagnostic = {"diagnostic_hints": ["private token"]}
    value = d.projection(error)
    assert value["process_returncode"] is None
    assert "diagnostic_hints" not in value and "private token" not in json.dumps(value)
    m.process_event("show", "admission")
    assert d.returncode is None and d.started is d.exited is False
