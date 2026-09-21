"""Offline diagnostics, preflight and immutable source handover contracts."""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_p4_bootstrap_stages as stage_tests
from test_p4_tools import tool


@pytest.fixture
def staged(monkeypatch, tmp_path):
    return stage_tests.staged.__wrapped__(monkeypatch, tmp_path)


@pytest.fixture
def diagnostic_module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "skills/p4"))
    import bootstrap_diagnostics

    return bootstrap_diagnostics


def partial(staged, monkeypatch):
    from botocore.exceptions import ClientError

    module, inputs, directory, env, calls = staged
    first = module.execute(inputs, directory, env)
    module.write_record(directory / "apply-attempt.json", {"plan_sha256": first["plan_sha256"]})
    (directory / "terraform.tfstate").write_text(
        '{"lineage":"synthetic","serial":21,"resources":[],"outputs":{}}', encoding="utf-8"
    )

    def absent(**kwargs):
        raise ClientError({"Error": {"Code": "NoSuchKey"}}, "HeadObject")

    session = SimpleNamespace(client=lambda *a, **kw: SimpleNamespace(head_object=absent))
    monkeypatch.setattr(module, "checked_session", lambda *a, **kw: session)
    return first


def test_preflight_never_applies_and_rechecks_after_success(staged):
    module, inputs, directory, env, calls = staged
    planned = module.execute(inputs, directory, env)
    calls.clear()
    result = module.execute(
        inputs, directory, env, operation="preflight", approved_hash=planned["plan_sha256"]
    )
    assert result == {
        "status": "bootstrap_preflight_passed",
        "attempt": 1,
        "next_operation": "apply",
    }
    assert [c[1] for c in calls] == ["version"]
    assert not (directory / "apply-attempt.json").exists()
    assert not (directory / "terraform.tfstate").exists()
    (directory / "bootstrap.tfplan").write_bytes(b"changed-after-preflight")
    with pytest.raises(module.DeploymentError, match="BootstrapPlanBindingMismatch"):
        module.execute(
            inputs, directory, env, operation="apply", approved_hash=planned["plan_sha256"]
        )
    assert not any(c[1] == "apply" for c in calls)


@pytest.mark.parametrize("blocker", ["attempted", "successor", "migration"])
def test_preflight_rejects_journal_and_successor(staged, blocker):
    module, inputs, directory, env, calls = staged
    planned = module.execute(inputs, directory, env)
    if blocker == "successor":
        (directory / "attempts/0002").mkdir(parents=True)
    else:
        name = "apply-attempt.json" if blocker == "attempted" else "migration-attempt.json"
        module.write_record(directory / name, {})
    with pytest.raises(
        module.DeploymentError, match="Bootstrap(ApplyAlreadyAttempted|AttemptSuperseded)"
    ):
        module.execute(
            inputs, directory, env, operation="preflight", approved_hash=planned["plan_sha256"]
        )
    assert not any(c[1] == "apply" for c in calls)


@pytest.mark.parametrize("operation", ["init", "plan", "show", "apply"])
def test_failed_terraform_streams_private_output_without_public_leak(
    diagnostic_module, tmp_path, monkeypatch, capsys, operation
):
    d = diagnostic_module
    diagnostic = d.Diagnostics(tmp_path, "apply", 1, "a" * 40)
    secret = b"synthetic-token secret@example.invalid 123456789012"

    def fail(command, **kwargs):
        assert "capture_output" not in kwargs
        kwargs["stdout"].write(secret)
        kwargs["stderr"].write(secret)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(d.subprocess, "run", fail)
    with pytest.raises(d.BootstrapFailure) as caught:
        diagnostic.run(
            ["terraform", operation], cwd=tmp_path, env={"AWS_SESSION_TOKEN": "never-record"}
        )
    assert caught.value.stage == "terraform_" + operation
    public = json.dumps(d.public_failure(caught.value))
    assert "synthetic-token" not in public and "example.invalid" not in public
    assert caught.value.return_code == 1
    assert next(diagnostic.path.glob("*.stderr.private")).read_bytes() == secret
    assert "never-record" not in "".join(p.read_text() for p in diagnostic.path.glob("*.json"))
    assert capsys.readouterr() == ("", "")


def test_diagnostic_records_exclusive_and_private(diagnostic_module, tmp_path):
    d = diagnostic_module
    log = d.Diagnostics(tmp_path, "preflight", 1, "a" * 40)
    before = (log.path / "context.json").read_bytes()
    with pytest.raises(d.BootstrapFailure, match="DiagnosticStorageFailed"):
        log.record("context.json", {"overwrite": True})
    assert (log.path / "context.json").read_bytes() == before
    # Diagnostics construction sets and reads back the actual Windows DACL.
    if os.name != "nt":
        assert log.path.stat().st_mode & 0o777 == 0o700
        assert (log.path / "context.json").stat().st_mode & 0o777 == 0o600


def test_permissions_failure_prevents_terraform(staged, monkeypatch, diagnostic_module):
    module, inputs, directory, env, calls = staged

    def denied(path):
        raise diagnostic_module.BootstrapFailure(
            "DiagnosticPermissionsFailed", "diagnostic_storage"
        )

    monkeypatch.setattr(diagnostic_module, "secure_directory", denied)
    with pytest.raises(module.DeploymentError, match="DiagnosticPermissionsFailed"):
        module.execute(inputs, directory, env)
    assert not calls


def test_link_rejected_before_private_write(diagnostic_module, tmp_path, monkeypatch):
    target = tmp_path / "diagnostics"
    original = Path.is_junction
    monkeypatch.setattr(Path, "is_junction", lambda p: p == target or original(p))
    with pytest.raises(diagnostic_module.BootstrapFailure, match="DiagnosticPermissionsFailed"):
        diagnostic_module.Diagnostics(tmp_path, "plan", 1, "a" * 40)
    assert not target.exists()


def test_start_and_storage_errors_are_distinct(diagnostic_module, tmp_path, monkeypatch):
    d = diagnostic_module
    log = d.Diagnostics(tmp_path, "apply", 1, "a" * 40)

    def fail(*a, **k):
        raise OSError("secret-detail")

    monkeypatch.setattr(d.subprocess, "run", fail)
    with pytest.raises(d.BootstrapFailure, match="TerraformStartFailed"):
        log.run(["terraform", "apply"], cwd=tmp_path, env={})
    monkeypatch.setattr(d, "exclusive", fail)
    with pytest.raises(d.BootstrapFailure, match="DiagnosticStorageFailed"):
        log.run(["terraform", "apply"], cwd=tmp_path, env={})


def test_storage_failure_after_apply_preserves_journal(staged, monkeypatch, diagnostic_module):
    module, inputs, directory, env, calls = staged
    planned = module.execute(inputs, directory, env)
    original = module.run

    def fail(command, **kwargs):
        if command[1] == "apply":
            raise diagnostic_module.BootstrapFailure(
                "DiagnosticStorageFailed", "diagnostic_storage"
            )
        return original(command, **kwargs)

    monkeypatch.setattr(module, "run", fail)
    with pytest.raises(module.DeploymentError, match="DiagnosticStorageFailed"):
        module.execute(
            inputs, directory, env, operation="apply", approved_hash=planned["plan_sha256"]
        )
    assert (directory / "apply-attempt.json").is_file()
    with pytest.raises(module.DeploymentError, match="BootstrapApplyAlreadyAttempted"):
        module.execute(
            inputs, directory, env, operation="apply", approved_hash=planned["plan_sha256"]
        )


def test_v1_to_v2_transition_preserves_previous_bytes(staged, monkeypatch):
    module, inputs, directory, env, calls = staged
    partial(staged, monkeypatch)
    path = directory / "binding.json"
    prior = json.loads(path.read_bytes())
    prior["schema_version"] = 1
    del prior["predecessor"]
    path.write_text(json.dumps(prior), encoding="utf-8")
    before = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    monkeypatch.setattr(module, "checked_source", lambda *a: "b" * 40)
    seen = []
    monkeypatch.setattr(module, "check_source_transition", lambda *args: seen.append(args[:2]))
    module.execute(
        inputs, directory, env, operation="replan", attempt=2, previous_source_sha="a" * 40
    )
    assert seen == [("a" * 40, "b" * 40)]
    assert before == {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    current = json.loads((directory / "attempts/0002/binding.json").read_bytes())
    assert current["schema_version"] == 2 and current["source_sha"] == "b" * 40
    assert current["predecessor"]["binding_sha256"] == module.digest_bytes(before["binding.json"])
    module.execute(
        inputs,
        directory,
        env,
        operation="preflight",
        attempt=2,
        approved_hash=current["plan_sha256"],
    )
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(module.DeploymentError, match="BootstrapPlanBindingMismatch"):
        module.execute(
            inputs,
            directory,
            env,
            operation="preflight",
            attempt=2,
            approved_hash=current["plan_sha256"],
        )


@pytest.mark.parametrize("previous_sha", [None, "c" * 40])
def test_transition_requires_explicit_matching_sha(staged, monkeypatch, previous_sha):
    module, inputs, directory, env, calls = staged
    partial(staged, monkeypatch)
    monkeypatch.setattr(module, "checked_source", lambda *a: "b" * 40)
    with pytest.raises(module.DeploymentError, match="BootstrapPlanBindingMismatch"):
        module.execute(
            inputs, directory, env, operation="replan", attempt=2, previous_source_sha=previous_sha
        )
    assert not (directory / "attempts/0002").exists()


@pytest.mark.parametrize(
    "blocker",
    ["state", "remote", "403", "migration", "incomplete", "inputs", "review", "plan", "config"],
)
def test_replan_rejects_unsafe_continuation(staged, monkeypatch, blocker):
    from botocore.exceptions import ClientError

    module, inputs, directory, env, calls = staged
    partial(staged, monkeypatch)
    if blocker == "state":
        (directory / "terraform.tfstate").write_text("invalid")
    elif blocker in {"remote", "403"}:

        def head(**kwargs):
            if blocker == "403":
                raise ClientError({"Error": {"Code": "403"}}, "HeadObject")
            return {}

        monkeypatch.setattr(
            module,
            "checked_session",
            lambda *a, **kw: SimpleNamespace(
                client=lambda *a, **kw: SimpleNamespace(head_object=head)
            ),
        )
    elif blocker == "migration":
        module.write_record(directory / "migration-attempt.json", {})
    elif blocker == "incomplete":
        (directory / "attempts/0002").mkdir(parents=True)
    elif blocker == "inputs":
        monkeypatch.setattr(module, "inputs", lambda *a: {"changed": True})
    else:
        name = {"review": "review.private.json", "plan": "bootstrap.tfplan", "config": "main.tf"}[
            blocker
        ]
        (directory / name).write_bytes(b"changed")
    calls.clear()
    with pytest.raises(module.DeploymentError):
        module.execute(inputs, directory, env, operation="replan", attempt=2)
    assert not any(c[1] in {"plan", "apply"} for c in calls)


@pytest.mark.parametrize("failure", [None, "ancestry", "blob", "extra"])
def test_source_transition_checks_git_ancestry_and_blobs(monkeypatch, failure):
    module = tool("bootstrap_state")

    def git(command, **kwargs):
        if command[1] == "merge-base":
            if failure == "ancestry":
                raise module.DeploymentError("TerraformOperationFailed")
            return b""
        if command[1] == "ls-tree":
            return b"terraform/bootstrap/main.tf\n" + (
                b"terraform/bootstrap/extra.tf\n" if failure == "extra" else b""
            )
        return (
            b"different" if failure == "blob" and command[2].startswith("b") else b"terraform {}\n"
        )

    monkeypatch.setattr(module, "run", git)
    if failure:
        with pytest.raises(module.DeploymentError, match="BootstrapSourceTransitionInvalid"):
            module.check_source_transition(
                "a" * 40, "b" * 40, {"main.tf": "working-tree-crlf-hash"}, {}
            )
    else:
        module.check_source_transition(
            "a" * 40, "b" * 40, {"main.tf": "working-tree-crlf-hash"}, {}
        )


@pytest.mark.parametrize(
    "operation", ["plan", "apply", "preflight", "verify", "inspect", "migrate"]
)
def test_transition_option_is_replan_only(staged, operation):
    module, inputs, directory, env, calls = staged
    with pytest.raises(module.DeploymentError, match="BootstrapSourceTransitionInvalid"):
        module.execute(inputs, directory, env, operation=operation, previous_source_sha="a" * 40)
    assert not calls


def test_unknown_exception_never_becomes_public_detail(diagnostic_module):
    d = diagnostic_module
    failure = d.safe_failure(RuntimeError("secret@example.invalid"), {"stage": "readback"})
    assert d.public_failure(failure)["reason_code"] == "UnexpectedBootstrapFailure"
    assert "example.invalid" not in str(failure)


@pytest.mark.parametrize("known", [True, False])
def test_cli_failure_is_safe_json(diagnostic_module, monkeypatch, capsys, known):
    module = tool("bootstrap_state")

    def fail(*args, **kwargs):
        if known:
            raise diagnostic_module.BootstrapFailure(
                "TerraformNonZeroExit", "terraform_apply", return_code=1
            )
        raise RuntimeError("synthetic-token secret@example.invalid")

    monkeypatch.setattr(module, "execute", fail)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bootstrap_state.py",
            "apply",
            "--inputs",
            "synthetic",
            "--directory",
            "synthetic",
            "--attempt",
            "1",
        ],
    )
    assert module.main() == 1
    output = capsys.readouterr()
    assert not output.out
    decoded = json.loads(output.err)
    assert decoded["reason_code"] == (
        "TerraformNonZeroExit" if known else "UnexpectedBootstrapFailure"
    )
    assert "synthetic-token" not in output.err and "example.invalid" not in output.err


@pytest.mark.parametrize("version", [1, 2])
def test_binding_versions_accept_only_exact_schema(staged, version):
    module, inputs, directory, env, calls = staged
    planned = module.execute(inputs, directory, env)
    path = directory / "binding.json"
    binding = json.loads(path.read_bytes())
    binding["schema_version"] = version
    if version == 1:
        del binding["predecessor"]
    path.write_text(json.dumps(binding), encoding="utf-8")
    module.execute(
        inputs, directory, env, operation="preflight", approved_hash=planned["plan_sha256"]
    )
    binding["unexpected"] = True
    path.write_text(json.dumps(binding), encoding="utf-8")
    with pytest.raises(module.DeploymentError, match="BootstrapPlanBindingMismatch"):
        module.execute(
            inputs, directory, env, operation="preflight", approved_hash=planned["plan_sha256"]
        )


@pytest.mark.parametrize("condition", ["dirty", "version", "authentication", "short_term"])
def test_preflight_guard_failures_do_not_create_apply_record(staged, monkeypatch, condition):
    module, inputs, directory, env, calls = staged
    planned = module.execute(inputs, directory, env)
    expected = {
        "dirty": "CleanCommittedMainRequired",
        "version": "TerraformVersionMismatch",
        "authentication": "SsoTokenUnavailable",
        "short_term": "ShortTermCredentialsRequired",
    }[condition]

    def fail(*a, **kw):
        raise module.DeploymentError(expected)

    if condition == "dirty":
        monkeypatch.setattr(module, "checked_source", fail)
    elif condition == "version":
        monkeypatch.setattr(module, "run", lambda *a, **kw: b'{"terraform_version":"0.0.0"}')
    elif condition == "authentication":
        monkeypatch.setattr(module, "checked_session", fail)
    else:
        monkeypatch.setattr(module, "credential_environment", fail)
    with pytest.raises(module.DeploymentError, match=expected) as caught:
        module.execute(
            inputs, directory, env, operation="preflight", approved_hash=planned["plan_sha256"]
        )
    if condition in {"authentication", "short_term"}:
        assert caught.value.stage == "authentication"
    assert not (directory / "apply-attempt.json").exists()


def test_failed_replan_is_preserved_and_not_reused(staged, monkeypatch):
    module, inputs, directory, env, calls = staged
    partial(staged, monkeypatch)
    original = module.run

    def fail(command, **kwargs):
        if command[1] == "plan":
            raise module.DeploymentError("TerraformOperationFailed")
        return original(command, **kwargs)

    monkeypatch.setattr(module, "run", fail)
    with pytest.raises(module.DeploymentError, match="TerraformOperationFailed"):
        module.execute(inputs, directory, env, operation="replan", attempt=2)
    assert (directory / "attempts/0002").is_dir()
    assert not (directory / "attempts/0002/binding.json").exists()
    with pytest.raises(module.DeploymentError, match="NewBootstrapAttemptRequired"):
        module.execute(inputs, directory, env, operation="replan", attempt=2)
    with pytest.raises(module.DeploymentError, match="BootstrapAttemptIncomplete"):
        module.execute(inputs, directory, env, operation="replan", attempt=3)


def test_replan_rejects_mismatched_apply_journal(staged, monkeypatch):
    module, inputs, directory, env, calls = staged
    partial(staged, monkeypatch)
    (directory / "apply-attempt.json").write_text('{"plan_sha256":"wrong"}', encoding="utf-8")
    with pytest.raises(module.DeploymentError, match="BootstrapPlanBindingMismatch"):
        module.execute(inputs, directory, env, operation="replan", attempt=2)
    assert not (directory / "attempts/0002").exists()


def test_real_local_subprocess_diagnostic_transport(diagnostic_module, tmp_path, monkeypatch):
    """Exercise file handles with a local child only, without an AWS provider."""
    d = diagnostic_module
    log = d.Diagnostics(tmp_path, "preflight", 1, "a" * 40)
    original = d.subprocess.run
    monkeypatch.setattr(
        d.subprocess,
        "run",
        lambda command, **kw: original([sys.executable, "-c", "print('synthetic')"], **kw),
    )
    output = log.run(["terraform", "version"], cwd=tmp_path, env=dict(os.environ))
    assert output.strip() == b"synthetic"
