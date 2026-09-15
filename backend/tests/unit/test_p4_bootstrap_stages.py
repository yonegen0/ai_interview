"""Offline staged bootstrap: reviewed plan, immutable attempt records, no blind retry."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_p4_tools import tool


@pytest.fixture
def staged(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "skills/p4"))
    module = tool("bootstrap_state")
    monkeypatch.setattr(module, "PROJECT", tmp_path)
    source = tmp_path / "terraform/bootstrap"
    source.mkdir(parents=True)
    (source / "main.tf").write_text("terraform {}", encoding="utf-8")
    (source / ".terraform.lock.hcl").write_text("synthetic", encoding="utf-8")
    private = tmp_path / ".p4-artifacts"
    private.mkdir()
    inputs = private / "inputs.json"
    inputs.write_text("{}", encoding="utf-8")
    values = {"account_id": "123456789012", "region": "ap-northeast-1"}
    monkeypatch.setattr(module, "inputs", lambda *a: dict(values))
    monkeypatch.setattr(module, "account_settings", lambda *a: tuple(values.values()))
    monkeypatch.setattr(module, "checked_source", lambda *a: "a" * 40)
    monkeypatch.setattr(module, "checked_session", lambda *a, **kw: None)
    monkeypatch.setattr(module, "read_local_settings", lambda *a: {})
    monkeypatch.setattr(module, "credential_environment", lambda session, env: env)
    monkeypatch.setattr(module, "verify_created_resources", lambda *a: None)
    calls = []

    def run(command, *, cwd, env):
        calls.append(command)
        if command[1] == "version":
            return b'{"terraform_version":"1.14.9"}'
        if command[1] == "plan":
            Path(next(c[5:] for c in command if c.startswith("-out="))).write_bytes(
                b"synthetic-plan"
            )
        if command[1] == "apply":
            (cwd / "terraform.tfstate").write_text(
                '{"lineage":"run","serial":1,"resources":[],"outputs":{}}', encoding="utf-8"
            )
        return b"{}"

    monkeypatch.setattr(module, "run", run)
    env = {"P4_AWS_EXECUTION_READY": "true", "P4_BOOTSTRAP_STATE_READY": "true"}
    return module, inputs, private / "run", env, calls


def test_plan_does_not_apply_and_apply_requires_reviewed_hash(staged):
    module, inputs, directory, env, calls = staged
    result = module.execute(inputs, directory, env)
    assert result["status"] == "bootstrap_planned"
    assert not any(c[1] == "apply" for c in calls)
    with pytest.raises(ValueError, match="ApprovedPlanHashRequired"):
        module.execute(inputs, directory, env, operation="apply", approved_hash="wrong")
    assert not (directory / "apply-attempt.json").exists()
    assert (
        module.execute(
            inputs, directory, env, operation="apply", approved_hash=result["plan_sha256"]
        )["status"]
        == "bootstrap_resources_verified"
    )
    with pytest.raises(ValueError, match="BootstrapApplyAlreadyAttempted"):
        module.execute(
            inputs, directory, env, operation="apply", approved_hash=result["plan_sha256"]
        )
    assert sum(c[1] == "apply" for c in calls) == 1


def test_apply_response_loss_preserves_attempt_and_rejects_retry(staged, monkeypatch):
    module, inputs, directory, env, calls = staged
    result = module.execute(inputs, directory, env)
    previous = module.run

    def fail(command, **kwargs):
        if command[1] == "apply":
            raise ValueError("TerraformOperationFailed")
        return previous(command, **kwargs)

    monkeypatch.setattr(module, "run", fail)
    with pytest.raises(ValueError, match="TerraformOperationFailed"):
        module.execute(
            inputs, directory, env, operation="apply", approved_hash=result["plan_sha256"]
        )
    assert (directory / "apply-attempt.json").exists()
    assert not (directory / "apply-completed.json").exists()
    with pytest.raises(ValueError, match="BootstrapApplyAlreadyAttempted"):
        module.execute(
            inputs, directory, env, operation="apply", approved_hash=result["plan_sha256"]
        )


@pytest.mark.parametrize(
    "target", ["bootstrap.tfplan", "main.tf", "binding.json", "review.private.json"]
)
def test_plan_or_configuration_tampering_prevents_apply(staged, target):
    module, inputs, directory, env, calls = staged
    result = module.execute(inputs, directory, env)
    (directory / target).write_text(json.dumps({"changed": True}), encoding="utf-8")
    with pytest.raises(ValueError):
        module.execute(
            inputs, directory, env, operation="apply", approved_hash=result["plan_sha256"]
        )
    assert not any(c[1] == "apply" for c in calls)


def test_migration_and_verification_require_previous_stage(tmp_path):
    module = tool("bootstrap_state")
    with pytest.raises(ValueError, match="BootstrapApplyConfirmationRequired"):
        module.operation_allowed(tmp_path, "migrate")
    with pytest.raises(ValueError, match="BootstrapMigrationAttemptRequired"):
        module.operation_allowed(tmp_path, "verify")
    module.write_record(tmp_path / "apply-completed.json", {})
    module.operation_allowed(tmp_path, "migrate")
    module.write_record(tmp_path / "migration-attempt.json", {})
    with pytest.raises(ValueError, match="BootstrapMigrationAlreadyAttempted"):
        module.operation_allowed(tmp_path, "migrate")
    module.operation_allowed(tmp_path, "verify")


def test_bootstrap_lock_rejects_other_run_and_releases_after_failure(tmp_path):
    module = tool("bootstrap_state")
    with pytest.raises(RuntimeError):
        with module.bootstrap_lock(tmp_path):
            with pytest.raises(ValueError, match="BootstrapOperationLocked"):
                with module.bootstrap_lock(tmp_path):
                    pytest.fail("parallel operation entered")
            raise RuntimeError("synthetic interruption")
    assert not (tmp_path / "bootstrap-operation.lock").exists()
    with module.bootstrap_lock(tmp_path):
        pass


def test_crash_lock_is_not_removed_automatically(tmp_path):
    module = tool("bootstrap_state")
    lock = tmp_path / "bootstrap-operation.lock"
    lock.write_text("prior interrupted operation", encoding="utf-8")
    with pytest.raises(ValueError, match="BootstrapOperationLocked"):
        with module.bootstrap_lock(tmp_path):
            pytest.fail("stale lock ignored")
    assert lock.read_text(encoding="utf-8") == "prior interrupted operation"


def test_primary_and_lock_release_failures_are_both_recorded(monkeypatch, tmp_path):
    module = tool("bootstrap_state")
    original = Path.unlink

    def unlink(path, *args, **kwargs):
        if path.name == "bootstrap-operation.lock":
            raise PermissionError("synthetic")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(ValueError, match="BootstrapOperationAndLockReleaseFailed"):
        with module.bootstrap_lock(tmp_path):
            raise RuntimeError("private-error-detail")
    record = json.loads(
        (tmp_path / "bootstrap-lock-release-failed.json").read_text(encoding="utf-8")
    )
    assert record == {"primary": "failed", "lock_release": "failed"}
    assert (tmp_path / "bootstrap-operation.lock").exists()


@pytest.mark.parametrize(
    "name",
    [
        "extra.tf.json",
        "override.tf",
        "x_override.tf",
        "terraform.tfvars",
        "hidden.auto.tfvars.json",
    ],
)
def test_source_hidden_configuration_rejected_before_copy(staged, name):
    module, inputs, directory, env, calls = staged
    (module.PROJECT / "terraform/bootstrap" / name).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="BootstrapConfigurationInvalid"):
        module.execute(inputs, directory, env)
    assert not directory.exists()
    assert not calls


def test_conflicting_input_rejected_before_copy(staged):
    module, inputs, directory, env, calls = staged
    env["TF_VAR_region"] = "us-east-1"
    with pytest.raises(ValueError, match="TerraformSettingConflict"):
        module.execute(inputs, directory, env)
    assert not directory.exists()
    assert not calls


def test_migrate_then_verify_does_not_reapply_and_verify_is_repeatable(staged, monkeypatch):
    module, inputs, directory, env, calls = staged
    planned = module.execute(inputs, directory, env)
    module.execute(inputs, directory, env, operation="apply", approved_hash=planned["plan_sha256"])
    observed = {"state_bucket": "synthetic"}
    monkeypatch.setattr(module, "_output_values", lambda *a: observed)
    monkeypatch.setattr(module, "verify_created_resources", lambda *a: None)
    monkeypatch.setattr(module, "migration_target", lambda *a, **kw: None)
    state = b'{"lineage":"run","serial":1,"resources":[],"outputs":{}}'

    def migrate(*args, **kwargs):
        (directory / "pre-migration.tfstate").write_bytes(state)
        (directory / "backend.tf").write_text(module.S3_BACKEND, encoding="utf-8")
        return state, state

    monkeypatch.setattr(module, "migrate_state", migrate)
    monkeypatch.setattr(module, "verify_state_version", lambda *a: ("v1", state))
    assert module.execute(inputs, directory, env, operation="migrate")["status"] == (
        "bootstrap_migration_verification_pending"
    )
    for _ in range(2):
        assert module.execute(inputs, directory, env, operation="verify")["status"] == (
            "bootstrap_state_migrated"
        )
    assert sum(c[1] == "apply" for c in calls) == 1


def test_partial_apply_replan_keeps_prior_attempt(staged, monkeypatch):
    from botocore.exceptions import ClientError

    module, inputs, directory, env, calls = staged
    first = module.execute(inputs, directory, env)
    module.write_record(directory / "apply-attempt.json", {"plan_sha256": first["plan_sha256"]})
    (directory / "terraform.tfstate").write_text(
        '{"lineage":"run","serial":1,"resources":[]}', encoding="utf-8"
    )

    def absent(**kwargs):
        raise ClientError({"Error": {"Code": "NoSuchKey"}}, "HeadObject")

    session = SimpleNamespace(client=lambda *a, **kw: SimpleNamespace(head_object=absent))
    monkeypatch.setattr(module, "checked_session", lambda *a, **kw: session)
    assert module.execute(inputs, directory, env, operation="inspect")["next_operation"] == "replan"
    second = module.execute(inputs, directory, env, operation="replan", attempt=2)
    assert second["attempt"] == 2
    assert (directory / "binding.json").is_file()
    assert (directory / "attempts/0002/binding.json").is_file()
    assert not any(c[1] == "apply" for c in calls)
    with pytest.raises(ValueError, match="NewBootstrapAttemptRequired"):
        module.execute(inputs, directory, env, operation="replan", attempt=2)


def test_generated_s3_backend_is_valid_hcl(tmp_path):
    import shutil
    import subprocess

    executable = shutil.which("terraform")
    if executable is None:
        pytest.skip("Terraform executable unavailable")
    module = tool("bootstrap_state")
    (tmp_path / "backend.tf").write_text(module.S3_BACKEND, encoding="utf-8")
    result = subprocess.run([executable, "fmt", "-check"], cwd=tmp_path, capture_output=True)
    assert result.returncode == 0, "GeneratedBackendInvalid"


def test_real_terraform_local_plan_apply_state(tmp_path):
    import os
    import shutil
    import subprocess

    executable = shutil.which("terraform")
    if executable is None:
        pytest.skip("Terraform executable unavailable")
    (tmp_path / "main.tf").write_text(
        'terraform {\n  backend "local" {}\n}\n'
        'resource "terraform_data" "probe" {\n  input = "synthetic"\n}\n'
        'output "probe" {\n  value = terraform_data.probe.output\n}\n',
        encoding="utf-8",
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AWS_", "TF_"))}
    env["CHECKPOINT_DISABLE"] = "1"
    for command in (
        ["init", "-input=false"],
        ["validate"],
        ["plan", "-input=false", "-out=probe.tfplan"],
        ["apply", "-input=false", "probe.tfplan"],
    ):
        result = subprocess.run([executable, *command], cwd=tmp_path, env=env, capture_output=True)
        assert result.returncode == 0, "LocalTerraformProbeFailed"
    state = (tmp_path / "terraform.tfstate").read_bytes()
    lineage, serial, resources, outputs = tool("bootstrap_state")._state_identity(state)
    assert lineage and serial >= 1 and len(resources) == 1
    assert outputs["probe"]["value"] == "synthetic"
