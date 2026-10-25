"""Unmerged PR B consistency; passing never releases the adoption HOLD."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from test_p4_tools import tool


def test_six_candidate_scopes_and_official_generated_locks_agree():
    root = Path(__file__).resolve().parents[3]
    migration = tool("toolchain_migration")
    expected = tool("cloud_toolchain").NEW_EXECUTION_TERRAFORM_VERSION
    locks = []
    for scope, (filename, _) in migration.SCOPES.items():
        directory = root / "terraform" / scope
        text = (directory / filename).read_text()
        assert f'required_version = "= {expected}"' in text
        assert 'aws = { source = "hashicorp/aws", version = "= 6.70.0" }' in text
        selected = tool("offline_terraform").parse_lock(
            (directory / ".terraform.lock.hcl").read_text()
        )
        assert set(selected) == {migration.AWS}
        assert selected[migration.AWS]["version"] == "6.70.0"
        assert selected[migration.AWS]["constraints"] == "6.70.0"
        assert sum(value.startswith("h1:") for value in selected[migration.AWS]["hashes"]) >= 2
        locks.append(selected)
    assert all(value == locks[0] for value in locks)


def test_candidate_workflow_qualifies_explicit_legacy_source_without_aws_permission():
    root = Path(__file__).resolve().parents[3]
    text = (root / ".github/workflows/p4-toolchain-qualification.yml").read_text()
    assert "ref: 7ec3595aa02c5315f6d7600282b428d294d3d771" in text
    assert "--repository migration-baseline" in text
    assert "--candidate-repository ." in text
    expected = tool("cloud_toolchain").NEW_EXECUTION_TERRAFORM_VERSION
    assert f"--checkout-candidate {expected}" in text
    assert "--compare-provider-schemas" in text
    assert "id-token:" not in text and "environment:" not in text
    assert "workflow_dispatch:" not in text
    assert "  push:" not in text
    assert "github.event_name == 'pull_request'" in text
    assert "github.event.pull_request.head.repo.full_name == github.repository" in text
    assert "head.ref == 'codex/issue39-upgrade-b-hold-20261025'" in text


@pytest.mark.parametrize(
    "change", ["old-cli", "other-cli", "windows", "arm64", "missing-platform", "format"]
)
def test_new_execution_contract_rejects_other_toolchains_before_authentication(change):
    m = tool("cloud_toolchain")
    value = {"terraform_version": "1.16.7", "platform": "linux_amd64"}
    m.assert_execution_version(value)
    if change == "old-cli":
        value["terraform_version"] = "1.14.9"
    elif change == "other-cli":
        value["terraform_version"] = "1.17.0"
    elif change == "windows":
        value["platform"] = "windows_amd64"
    elif change == "arm64":
        value["platform"] = "linux_arm64"
    elif change == "missing-platform":
        del value["platform"]
    else:
        value["format_version"] = "2.0"
    with pytest.raises(ValueError, match="CloudTerraformVersionMismatch"):
        m.assert_execution_version(value)


def test_fresh_plan_binding_requires_new_runtime_platform_and_rejects_legacy_binding(tmp_path):
    m = tool("terraform_dev")
    (tmp_path / ".terraform.lock.hcl").write_bytes(b"synthetic-lock-not-for-execution")
    inputs = tmp_path / "inputs.json"
    inputs.write_bytes(b"{}")
    expected = m.bind_plan(tmp_path, "123456789012", "ap-northeast-1", "a" * 40, inputs)
    assert expected["terraform_version"] == "1.16.7"
    assert expected["terraform_platform"] == "linux_amd64"
    plan = tmp_path / "synthetic-plan"
    plan.write_bytes(b"synthetic-plan-not-for-execution")
    actual = expected | {"plan_sha256": m.digest(plan)}
    m.assert_binding(actual, expected, plan, m.digest(plan))
    for changed in (
        {key: value for key, value in actual.items() if key != "terraform_platform"},
        actual | {"terraform_platform": "windows_amd64"},
        actual | {"terraform_version": "1.14.9"},
    ):
        with pytest.raises(ValueError, match="SavedPlanMismatch"):
            m.assert_binding(changed, expected, plan, m.digest(plan))


@pytest.mark.parametrize("failure", [None, "iam", "inventory", "changed-during-check"])
def test_actual_candidate_checkout_comparison_fails_closed_without_mutation(
    tmp_path, monkeypatch, failure
):
    from test_toolchain_migration import configurations

    m, before, after = configurations()
    roots = [tmp_path / "baseline", tmp_path / "candidate"]
    snapshots = [dict.fromkeys(config, "synthetic") for config in (before, after)]
    for root, config in zip(roots, (before, after), strict=True):
        for name, raw in config.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    if failure == "iam":
        (roots[1] / "terraform/bootstrap/iam.tf").write_bytes(b"unapproved change")
    elif failure == "inventory":
        snapshots[1]["terraform/bootstrap/terraform.tfstate"] = "never-read"
    reads = []

    def snapshot(root):
        reads.append(root)
        if failure == "changed-during-check" and len(reads) > 2:
            return {}
        return snapshots[roots.index(root)]

    monkeypatch.setattr(m, "tracked_snapshot", snapshot)
    if failure:
        with pytest.raises(ValueError):
            m.verify_candidate_checkout(*roots, "1.16.7")
    else:
        m.verify_candidate_checkout(*roots, "1.16.7")
        assert len(reads) == 4
    assert all((roots[0] / name).read_bytes() == raw for name, raw in before.items())


@pytest.mark.parametrize("wrong_toolchain", [True, False])
def test_test_closure_rejects_toolchain_before_sts(tmp_path, monkeypatch, wrong_toolchain):
    """Verify the real argument path and prevent any unmocked AWS session."""
    m = tool("test_closure_apply")
    run = tmp_path / ".p4-artifacts" / "synthetic-run"
    run.mkdir(parents=True)
    manifest = run / "manifest.json"
    plan = run / "plan.tfplan"
    proof = run / "proof.json"
    for path in (manifest, plan, proof):
        path.write_text("synthetic", encoding="utf-8")
    monkeypatch.setattr(m, "PROJECT", tmp_path)
    monkeypatch.setattr(
        m.sys,
        "argv",
        [
            "test_closure_apply.py",
            "preflight",
            "--manifest",
            str(manifest),
            "--account",
            "123456789012",
            "--region",
            "ap-northeast-1",
            "--directory",
            str(run),
            "--plan",
            str(plan),
            "--plan-hash",
            "a" * 64,
            "--proof",
            str(proof),
            "--proof-hash",
            "b" * 64,
            "--source-sha",
            "c" * 40,
        ],
    )
    calls = []
    monkeypatch.setattr(m, "require_aws_execution", lambda: calls.append("ready"))

    def qualify():
        calls.append("qualify")
        if wrong_toolchain:
            raise ValueError("CloudTerraformVersionMismatch")

    def checked_session(*args):
        calls.append("checked_session")
        raise ValueError("SyntheticStopBeforeAws")

    monkeypatch.setattr(m, "qualify_tools_without_credentials", qualify)
    monkeypatch.setattr(m, "read_manifest", lambda *args, **kw: {"run_id": "synthetic"})
    monkeypatch.setattr(m, "checked_session", checked_session)
    expected_error = (
        "CloudTerraformVersionMismatch" if wrong_toolchain else "SyntheticStopBeforeAws"
    )
    with pytest.raises(ValueError, match=expected_error):
        m.main()
    assert calls == (
        ["ready", "qualify"] if wrong_toolchain else ["ready", "qualify", "checked_session"]
    )


@pytest.mark.parametrize(
    "case",
    [
        "ok",
        "candidate",
        "platform",
        "format",
        "missing-platform",
        "json",
        "scalar",
        "exit",
        "timeout",
        "missing",
        "host",
    ],
)
def test_legacy_version_probe_is_credential_free_and_fails_closed(tmp_path, monkeypatch, case):
    m = tool("bootstrap_maintenance")
    binary = tmp_path / "terraform.exe"
    binary.write_bytes(b"synthetic-not-executed")

    def which(name, *, path):
        assert name == "terraform" and path == "synthetic-path"
        return None if case == "missing" else str(binary)

    monkeypatch.setattr(m.shutil, "which", which)
    monkeypatch.setattr(m.platform, "system", lambda: "Windows")
    monkeypatch.setattr(m.platform, "machine", lambda: "arm64" if case == "host" else "AMD64")
    value = {"terraform_version": "1.14.9", "platform": "windows_amd64"}
    if case == "candidate":
        value["terraform_version"] = "1.16.7"
    elif case == "platform":
        value["platform"] = "linux_amd64"
    elif case == "format":
        value["format_version"] = "2.0"
    elif case == "missing-platform":
        del value["platform"]
    calls = []

    def process(command, **kwargs):
        calls.append(kwargs)
        assert command == [str(binary), "version", "-json"]
        assert Path(kwargs["cwd"]).is_dir() and Path(kwargs["cwd"]) != tmp_path
        assert kwargs["timeout"] == 15 and kwargs["capture_output"] is True
        env = kwargs["env"]
        assert env["CHECKPOINT_DISABLE"] == "1" and env["PATH"] == "synthetic-path"
        assert env["AWS_EC2_METADATA_DISABLED"] == "true"
        assert env["AWS_CONFIG_FILE"] == env["AWS_SHARED_CREDENTIALS_FILE"] == m.os.devnull
        assert Path(env["TF_CLI_CONFIG_FILE"]).is_relative_to(kwargs["cwd"])
        assert "never-propagate" not in env.values()
        if case == "timeout":
            raise m.subprocess.TimeoutExpired(command, 15)
        raw = b"invalid" if case == "json" else m.encoded([] if case == "scalar" else value)
        return SimpleNamespace(returncode=1 if case == "exit" else 0, stdout=raw)

    monkeypatch.setattr(m.subprocess, "run", process)
    environment = dict.fromkeys(
        [
            "AWS_PROFILE",
            "aws_secret_access_key",
            "ACTIONS_TOKEN",
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "P4_READY",
            "TF_CLI_ARGS",
            "TERRAFORM_CONFIG",
        ],
        "never-propagate",
    ) | {"PATH": "synthetic-path"}
    if case == "ok":
        m.qualify_legacy_terraform(environment=environment)
    else:
        with pytest.raises(ValueError, match="MaintenanceTerraform"):
            m.qualify_legacy_terraform(environment=environment)
    assert len(calls) == (0 if case in {"missing", "host"} else 1)
    assert all(not Path(call["cwd"]).exists() for call in calls)


@pytest.mark.parametrize("case", ["legacy", "candidate-hcl", "missing-hcl", "candidate-lock"])
def test_legacy_configuration_never_rebinds_candidate_requirements(tmp_path, monkeypatch, case):
    from test_toolchain_migration import lock

    m = tool("bootstrap_maintenance")
    provider = lock("6.70.0" if case == "candidate-lock" else "6.64.0", "~> 6.0")
    version = "1.16.7" if case == "candidate-hcl" else "1.14.9"
    hcl = (
        b"terraform {}"
        if case == "missing-hcl"
        else (f'terraform {{ required_version = "= {version}" }}'.encode())
    )

    def git(root, *args):
        if args[0] == "ls-tree":
            return b"terraform/bootstrap/main.tf\nterraform/bootstrap/.terraform.lock.hcl\n"
        assert args[0] == "show"
        return provider if args[-1].endswith(".terraform.lock.hcl") else hcl

    monkeypatch.setattr(m, "git", git)
    if case == "legacy":
        assert m.configuration_files(tmp_path, "a" * 40, m.hashed(provider))["main.tf"] == hcl
    else:
        with pytest.raises(ValueError, match="MaintenanceTerraformRequirement|ProviderSelection"):
            m.configuration_files(tmp_path, "a" * 40, m.hashed(provider))
