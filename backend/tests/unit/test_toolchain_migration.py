"""The opt-in qualification path cannot weaken normal or historical contracts."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_p4_tools import tool

AWS = "registry.terraform.io/hashicorp/aws"


def lock(version, constraint, *, hashes=None, address=AWS):
    hashes = hashes or ["h1:" + "a" * 43 + "=", "h1:" + "b" * 43 + "=", "zh:" + "c" * 64]
    return (
        f'provider "{address}" {{ version = "{version}" constraints = "{constraint}" '
        f"hashes = {json.dumps(hashes)} }}"
    ).encode()


def configurations(candidate="1.16.7"):
    m = tool("toolchain_migration")
    before = {"terraform/bootstrap/iam.tf": b'resource "aws_iam_role" "synthetic" {}'}
    for scope, (filename, version) in m.SCOPES.items():
        before[f"terraform/{scope}/{filename}"] = (
            b'terraform {\n  required_version = "= 1.14.9"\n'
            b"  required_providers {\n"
            b'    aws = { source = "hashicorp/aws", version = "~> 6.0" }\n  }\n}\n'
        )
        before[f"terraform/{scope}/.terraform.lock.hcl"] = lock(version, "~> 6.0")
    after = m.candidate_configuration(before, candidate)
    for scope in m.SCOPES:
        after[f"terraform/{scope}/.terraform.lock.hcl"] = lock("6.70.0", "6.70.0")
    return m, before, after


@pytest.mark.parametrize("candidate", ["1.16.7", "1.17.0"])
def test_explicit_six_scope_migration_does_not_relax_additive_guard(candidate):
    m, before, after = configurations(candidate)
    m.assert_migration(before, after, candidate)
    for scope in m.SCOPES:
        name = f"terraform/{scope}/.terraform.lock.hcl"
        with pytest.raises(ValueError, match="ProviderSelectionChanged"):
            tool("offline_terraform").assert_additive(before[name].decode(), after[name].decode())
    assert len(m.SCOPES) == 6


@pytest.mark.parametrize(
    "change",
    [
        "iam",
        "backend",
        "state",
        "file-delete",
        "provider-add",
        "provider-version",
        "constraint",
        "one-platform",
        "no-zip-hash",
        "different-lock",
        "old-cli",
        "baseline-provider",
        "baseline-requirement",
        "extra-scope",
        "unknown-lock-field",
    ],
)
def test_migration_rejects_unrelated_or_partial_changes(change):
    m, before, after = configurations()
    name = "terraform/bootstrap/.terraform.lock.hcl"
    if change == "iam":
        after["terraform/bootstrap/iam.tf"] = b'locals { action = "s3:*" }'
    elif change == "backend":
        after["terraform/bootstrap/main.tf"] += b'backend "s3" {}'
    elif change == "state":
        after["terraform/bootstrap/terraform.tfstate"] = b"{}"
    elif change == "file-delete":
        del after["terraform/bootstrap/iam.tf"]
    elif change == "provider-add":
        after[name] += lock("1.0.0", "1.0.0", address="registry.terraform.io/hashicorp/random")
    elif change == "provider-version":
        after[name] = lock("6.70.1", "6.70.0")
    elif change == "constraint":
        after[name] = lock("6.70.0", "~> 6.0")
    elif change == "one-platform":
        after[name] = lock("6.70.0", "6.70.0", hashes=["zh:" + "c" * 64])
    elif change == "no-zip-hash":
        after[name] = lock("6.70.0", "6.70.0", hashes=["h1:" + c * 43 + "=" for c in "ab"])
    elif change == "different-lock":
        after[name] = after[name].replace(b"zh:" + b"c" * 64, b"zh:" + b"d" * 64)
    elif change == "old-cli":
        after["terraform/bootstrap/main.tf"] = before["terraform/bootstrap/main.tf"]
    elif change == "baseline-provider":
        before[name] = lock("6.65.0", "~> 6.0")
    elif change == "baseline-requirement":
        before["terraform/bootstrap/main.tf"] = before["terraform/bootstrap/main.tf"].replace(
            b"1.14.9", b"1.14.8"
        )
    elif change == "extra-scope":
        before["terraform/extra/.terraform.lock.hcl"] = after[
            "terraform/extra/.terraform.lock.hcl"
        ] = lock("6.70.0", "6.70.0")
    else:
        after[name] += b"unknown = true"
    with pytest.raises(ValueError):
        m.assert_migration(before, after, "1.16.7")


@pytest.mark.parametrize("candidate", ["1.14.9", "1.17.1", "latest", ""])
def test_unreviewed_candidates_are_rejected(candidate):
    m, before, _ = configurations()
    with pytest.raises(ValueError, match="UnreviewedMigrationCandidate"):
        m.candidate_configuration(before, candidate)


@pytest.mark.parametrize("version", ["1.14.9", "1.16.7", "1.17.0"])
@pytest.mark.parametrize("platform", ["linux_amd64", "windows_amd64"])
def test_version_json_shapes(version, platform):
    m = tool("toolchain_migration")
    value = {"terraform_version": version, "platform": platform, "provider_selections": {}}
    if version == "1.17.0":
        value["format_version"] = "1.0"
    m.assert_version_json(value, version, platform)
    for bad in ({}, [], value | {"format_version": "2.0"}, value | {"platform": "linux_arm64"}):
        with pytest.raises(ValueError, match="MigrationTerraformVersionMismatch"):
            m.assert_version_json(bad, version, platform)
    with pytest.raises(ValueError, match="MigrationTerraformVersionMismatch"):
        m.assert_version_json(value, "0.0.0", platform)


def test_execution_pin_and_historical_evidence_remain_separate():
    repository = Path(__file__).resolve().parents[3]
    m = tool("cloud_toolchain")
    assert m.NEW_EXECUTION_TERRAFORM_VERSION == m.EXPECTED_TERRAFORM_VERSION == "1.14.9"
    for name in ("bootstrap_state", "maintenance_contract"):
        assert tool(name).TF_VERSION == "1.14.9"
    for name in ("terraform_dev", "cloud_controller_core", "test_closure_apply"):
        assert tool(name).TF_VERSION == m.NEW_EXECUTION_TERRAFORM_VERSION
    for name in ("standard-plan", "standard-apply", "cloud-plan", "compound", "deploy", "static"):
        workflow = (repository / f".github/workflows/p4-{name}.yml").read_text()
        assert f"terraform_version: {m.NEW_EXECUTION_TERRAFORM_VERSION}\n" in workflow


@pytest.mark.parametrize("candidate", ["1.16.7", "1.17.0"])
def test_future_execution_contract_does_not_reinterpret_historical_versions(monkeypatch, candidate):
    # Pure import test only; no candidate is enabled in the real execution configuration.
    monkeypatch.setitem(
        sys.modules, "cloud_toolchain", SimpleNamespace(NEW_EXECUTION_TERRAFORM_VERSION=candidate)
    )
    for name in ("terraform_dev", "cloud_controller_core", "test_closure_apply"):
        assert tool(name).TF_VERSION == candidate
    for name in ("bootstrap_state", "maintenance_contract"):
        assert tool(name).TF_VERSION == "1.14.9"


@pytest.mark.parametrize("candidate", ["1.16.7", "1.17.0"])
def test_candidate_binary_is_rejected_for_cloud_execution(monkeypatch, candidate):
    m = tool("cloud_toolchain")
    monkeypatch.setattr(m.shutil, "which", lambda name: name)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=json.dumps({"terraform_version": candidate}))

    monkeypatch.setattr(m.subprocess, "run", run)
    with pytest.raises(ValueError, match="CloudTerraformVersionMismatch"):
        m.qualify()
    assert len(calls) == 1


@pytest.mark.parametrize("version", ["1.14.9", "1.16.7", "1.17.0"])
def test_actual_synthetic_json_fixtures_are_separate_from_historical_evidence(version):
    fixtures = Path(__file__).resolve().parents[1] / "fixtures/p4"
    value = json.loads((fixtures / f"terraform-{version}-offline-json.json").read_text())
    tool("toolchain_migration").assert_version_json(value["version"], version, "windows_amd64")
    show = value["show"]
    assert show["terraform_version"] == version and show["format_version"] == "1.2"
    assert show["variables"]["worker_wif_enabled"]["value"] is False
    assert show["planned_values"]["outputs"]["null_value"] == {
        "sensitive": False,
        "type": "dynamic",
        "value": None,
    }
    assert not show.get("resource_changes") and not show["configuration"].get("provider_config")
    assert show["complete"] is True and show["errored"] is False
    historical = json.loads((fixtures / "terraform-1.14.9-maintenance-shape.json").read_text())
    # The old fixture deliberately describes its original recorded shape, never overwritten.
    assert historical["worker_wif_enabled_variable"]["value"] == "false"


@pytest.mark.parametrize("field", ["terraform_version", "lock_sha256", "code_sha", "plan_sha256"])
def test_saved_plan_binding_rejects_toolchain_or_digest_mixing(tmp_path, field):
    m = tool("terraform_dev")
    plan = tmp_path / "synthetic.tfplan"
    plan.write_bytes(b"synthetic-only-never-apply")
    hashed = m.digest(plan)
    expected = {"terraform_version": "1.16.7", "lock_sha256": "a" * 64, "code_sha": "b" * 40}
    binding = expected | {"plan_sha256": hashed}
    m.assert_binding(binding, expected, plan, hashed)
    changed = binding | {field: "1.14.9" if field == "terraform_version" else "c" * 64}
    with pytest.raises(ValueError, match="SavedPlanMismatch"):
        m.assert_binding(changed, expected, plan, hashed)
    plan.write_bytes(b"changed-synthetic-plan")
    with pytest.raises(ValueError, match="SavedPlanMismatch"):
        m.assert_binding(binding, expected, plan, hashed)


@pytest.mark.parametrize(
    "failure", [None, "command", "original", "version", "lock", "hcl", "binary"]
)
def test_qualification_is_isolated_and_never_invokes_formal_plan_apply(
    tmp_path, monkeypatch, failure
):
    m, before, after = configurations()
    repository = tmp_path / "repository"
    repository.mkdir()
    executable = tmp_path / "terraform"
    executable.touch()
    for name, raw in before.items():
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    snapshot = dict.fromkeys(before, "digest")
    reads, calls = [], []

    def tracked(path):
        reads.append(path)
        return {} if failure == "original" and len(reads) == 2 else snapshot

    def run(args, *, cwd, env, check, capture_output, timeout):
        calls.append(args[1:])
        assert not cwd.is_relative_to(repository)
        assert check is False and capture_output and timeout == 600
        assert env["AWS_EC2_METADATA_DISABLED"] == "true"
        assert "AWS_ACCESS_KEY_ID" not in env and "TF_CLI_ARGS" not in env
        assert args[1] not in {"plan", "apply", "show", "state"}
        if args[1:3] == ["version", "-json"]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=json.dumps(
                    {
                        "terraform_version": "1.14.9" if failure == "version" else "1.16.7",
                        "platform": "linux_amd64",
                    }
                ).encode(),
                stderr=b"",
            )
        if args[1:3] == ["providers", "lock"]:
            assert args[3:] == ["-platform=linux_amd64", "-platform=windows_amd64"]
            if failure == "command":
                raise subprocess.CalledProcessError(1, args)
            (cwd / ".terraform.lock.hcl").write_bytes(
                lock("6.70.0", "~> 6.0" if failure == "lock" else "6.70.0")
            )
            if failure == "hcl":
                (cwd / "main.tf").write_bytes(b'backend "s3" {}')
            if failure == "binary":
                executable.write_bytes(b"changed-during-qualification")
        if args[1] == "init":
            assert args[2:] == ["-backend=false", "-input=false", "-lockfile=readonly"]
        return subprocess.CompletedProcess(args, 0, stdout=b"synthetic mock success", stderr=b"")

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "synthetic")
    monkeypatch.setenv("TF_CLI_ARGS", "-unsafe")
    monkeypatch.setattr(m, "tracked_snapshot", tracked)
    monkeypatch.setattr(m.platform, "system", lambda: "Linux")
    monkeypatch.setattr(m.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(m.subprocess, "run", run)
    if failure:
        with pytest.raises((ValueError, subprocess.CalledProcessError)):
            m.qualify(repository, tmp_path, executable, "1.16.7")
    else:
        work = m.qualify(repository, tmp_path, executable, "1.16.7")
        report = json.loads((work / "report.json").read_text())
        assert report["aws_operations"] == 0 and report["formal_plan_apply"] is False
        assert sum(c[0] == "validate" for c in calls) == 6
        assert sum(c[0] == "test" for c in calls) == 3
    assert len(reads) == 2
    assert all((repository / name).read_bytes() == raw for name, raw in before.items())
    if failure:
        assert not list(tmp_path.glob("p4-qualify-*/report.json"))
    if failure in {"version", "command", "lock", "hcl"}:
        assert all(c[0] != "init" for c in calls)


@pytest.mark.parametrize("failure", [None, "state-version", "schema-change"])
def test_opt_in_schema_matrix_uses_empty_backend_free_baselines(tmp_path, monkeypatch, failure):
    m, before, _ = configurations()
    before["terraform/bootstrap/iam.tf"] = b'resource "aws_iam_role" "synthetic" {}'
    repository = tmp_path / "repository"
    repository.mkdir()
    executable = tmp_path / "terraform"
    executable.touch()
    for name, raw in before.items():
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    monkeypatch.setattr(m, "tracked_snapshot", lambda path: dict.fromkeys(before, "synthetic"))
    monkeypatch.setattr(m.platform, "system", lambda: "Linux")
    monkeypatch.setattr(m.platform, "machine", lambda: "x86_64")
    calls = []

    def run(args, *, cwd, env, **kwargs):
        calls.append((cwd, args[1:]))
        assert not cwd.is_relative_to(repository)
        assert "AWS_ACCESS_KEY_ID" not in env
        assert env["AWS_EC2_METADATA_DISABLED"] == "true"
        assert args[1] not in {"plan", "apply", "show", "state"}
        value = b"synthetic"
        if args[1:3] == ["version", "-json"]:
            value = json.dumps({"terraform_version": "1.16.7", "platform": "linux_amd64"}).encode()
        elif args[1:3] == ["providers", "lock"]:
            (cwd / ".terraform.lock.hcl").write_bytes(lock("6.70.0", "6.70.0"))
        elif args[1] == "init":
            assert args[2:] == ["-backend=false", "-input=false", "-lockfile=readonly"]
            if cwd.name.startswith("schema-"):
                assert set(path.name for path in cwd.iterdir()) == {
                    "main.tf",
                    ".terraform.lock.hcl",
                }
                assert b"backend" not in (cwd / "main.tf").read_bytes()
                assert b"resource " not in (cwd / "main.tf").read_bytes()
        elif args[1:3] == ["providers", "schema"]:
            row = {"version": 0, "block": {"attributes": {}}}
            if cwd.name == "bootstrap":
                if failure == "state-version":
                    row["version"] = 1
                elif failure == "schema-change":
                    row["block"]["attributes"]["unexpected"] = {"required": True}
            value = json.dumps(
                {
                    "format_version": "1.0",
                    "provider_schemas": {
                        AWS: {"resource_schemas": {"aws_iam_role": row}},
                    },
                }
            ).encode()
        return subprocess.CompletedProcess(args, 0, stdout=value, stderr=b"")

    monkeypatch.setattr(m.subprocess, "run", run)
    if failure:
        with pytest.raises(ValueError):
            m.qualify(repository, tmp_path, executable, "1.16.7", compare_provider_schemas=True)
        assert not list(tmp_path.glob("p4-qualify-*/report.json"))
    else:
        work = m.qualify(repository, tmp_path, executable, "1.16.7", compare_provider_schemas=True)
        report = json.loads((work / "report.json").read_text())
        assert set(report["provider_schema_comparisons"]) == {"6.64.0", "6.65.0"}
        assert sum(args[:2] == ["providers", "schema"] for _, args in calls) == 3


@pytest.mark.parametrize(
    "failure", [None, "source", "iam", "state", "lock", "missing-schema", "existing", "inside"]
)
def test_candidate_bundle_is_bound_non_overwriting_and_keeps_adoption_on_hold(
    tmp_path, monkeypatch, failure
):
    m, before, after = configurations()
    repository, qualification = tmp_path / "repository", tmp_path / "qualification"
    for root, config in ((repository, before), (qualification / "checkout", after)):
        for name, raw in config.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    snapshot = dict.fromkeys(before, "synthetic")
    monkeypatch.setattr(m, "tracked_snapshot", lambda path: snapshot)
    report = {
        "status": "OFFLINE_QUALIFIED_NOT_DEPLOYMENT_APPROVAL",
        "version": {"terraform_version": "1.16.7"},
        "source_configuration_sha256": {} if failure == "source" else snapshot,
        "provider_schema_comparisons": {}
        if failure == "missing-schema"
        else {
            version: {
                "resource_types": ["aws_iam_role"],
                "schema_versions": {"aws_iam_role": 0},
                "baseline_schema_sha256": "a" * 64,
                "candidate_schema_sha256": "b" * 64,
                "defaults_and_state_upgraders_proven": False,
            }
            for version in ("6.64.0", "6.65.0")
        },
    }
    (qualification / "report.json").write_text(json.dumps(report))
    if failure == "iam":
        (qualification / "checkout/terraform/bootstrap/iam.tf").write_bytes(b"changed")
    elif failure == "state":
        (qualification / "checkout/terraform/bootstrap/terraform.tfstate").write_bytes(b"{}")
    elif failure == "lock":
        (qualification / "checkout/terraform/bootstrap/.terraform.lock.hcl").write_bytes(
            lock("6.65.0", "6.65.0")
        )
    destination = repository / "bundle" if failure == "inside" else tmp_path / "bundle"
    if failure == "existing":
        destination.mkdir()
        (destination / "preserve").write_bytes(b"preserve")
    if failure:
        with pytest.raises((ValueError, FileExistsError)):
            m.export_candidate_bundle(repository, qualification, destination)
        if failure == "existing":
            assert (destination / "preserve").read_bytes() == b"preserve"
        else:
            assert not destination.exists()
    else:
        m.export_candidate_bundle(repository, qualification, destination)
        manifest = json.loads((destination / "UPGRADE_HOLD.json").read_text())
        assert manifest["status"] == "HOLD_INCOMPLETE_EXECUTION_MIGRATION_DO_NOT_MERGE"
        assert len(manifest["files"]) == 12
        assert not list(destination.rglob("*.tfstate"))
    assert all((repository / name).read_bytes() == raw for name, raw in before.items())
