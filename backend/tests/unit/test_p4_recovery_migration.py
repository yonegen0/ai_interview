"""Synthetic recovery evidence only; no real State or AWS writes."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_p4_tools import tool


@pytest.fixture
def handoff(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "skills/p4"))
    m = tool("recovery_migration")
    monkeypatch.setattr(m.bootstrap, "PROJECT", tmp_path)
    root = tmp_path / ".p4-artifacts/recovery"
    run = root / "run"
    phase, execution = root / "review", root / "execution"
    for p in (run, phase, execution, tmp_path / "terraform/bootstrap"):
        p.mkdir(parents=True)
    account, region = "123456789012", "ap-northeast-1"
    bucket = f"ai-interview-state-{account}-{region}"

    def write(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    state = {
        "version": 4,
        "lineage": "synthetic-B",
        "serial": 34,
        "outputs": {"state_bucket": {"value": bucket}},
        "resources": [
            {
                "type": "aws_s3_bucket",
                "name": "storage",
                "instances": [{"index_key": "state", "attributes": {"id": bucket}}],
            },
            {
                "type": "aws_iam_role",
                "name": "synthetic",
                "instances": [
                    {"index_key": str(i), "attributes": {"id": str(i)}} for i in range(31)
                ],
            },
        ],
    }
    source = write(run / "terraform.tfstate", state)
    backup = write(root / "backup.tfstate", state)
    config = tmp_path / "terraform/bootstrap/main.tf"
    config.write_text("# synthetic\n")
    (run / "main.tf").write_bytes(config.read_bytes())
    inputs = write(phase / "inputs.json", {"synthetic": True})
    refresh = write(phase / "refresh.tfplan", {})
    normal_plan = write(execution / "normal.tfplan", {})
    files = {
        "backup": backup,
        "inputs": inputs,
        "refresh_plan": refresh,
        "normal_plan": normal_plan,
        "start": write(
            root / "start.json",
            {"execution_directory": "execution", "plan_sha256": m.hashed(refresh)},
        ),
        "apply": write(execution / "apply.json", {"plan_sha256": m.hashed(refresh)}),
        "preflight": write(
            phase / "preflight.json",
            {
                "state": {"lineage": "synthetic-B", "serial": 33, "instance_count": 32},
                "new_input_sha256": m.hashed(inputs),
                "four_way_subject_match": True,
                "unchanged_account_region_ses_buckets_repository_environment": True,
                "configuration_sha256": {"main.tf": m.hashed(config)},
            },
        ),
        "readback": write(
            execution / "readback.json",
            {
                "state_sha256": m.hashed(source),
                "state": {"lineage": "synthetic-B", "serial": 34, "instance_count": 32},
                "normalized_six_differences_resolved": True,
                "aws_snapshot_unchanged": True,
                "resource_id_changes": 0,
                "apply_added": 0,
                "apply_changed": 0,
                "apply_destroyed": 0,
            },
        ),
        "normal": write(
            execution / "normal.json",
            {
                "complete_no_op": True,
                "normal_plan_success": True,
                "addresses_retained": True,
                "planned_instances": 32,
                "normal_plan_sha256": m.hashed(normal_plan),
                "add": 0,
                "change": 0,
                "destroy": 0,
                "replace": 0,
                "outputs_changed": 0,
                "drift_count": 0,
                "normal_apply_executed": False,
                "s3_migration_executed": False,
            },
        ),
        "normal_exit": write(execution / "exit.json", {"return_code": 0}),
    }
    dev_backend = root / "backend-dev.hcl"
    dev_backend.write_text(
        m.backend_hcl(m.canonical_backend(account, region, state)), encoding="utf-8"
    )
    files["dev_backend"] = dev_backend
    binding = {
        "schema_version": 1,
        "kind": "recovery-migration",
        "account_id": account,
        "region": region,
        "workspace": "default",
        "source_state": str(source.resolve()),
        "state_sha256": m.hashed(source),
        "lineage": "synthetic-B",
        "serial": 34,
        "instance_count": 32,
        "refresh_plan_sha256": m.hashed(refresh),
        "destination": m.canonical_backend(account, region, state) | {"key": m.bootstrap.STATE_KEY},
        "evidence": {
            k: {"path": str(p.resolve()), "sha256": m.hashed(p)} for k, p in files.items()
        },
    }
    path = write(root / "handoff.json", binding)
    return SimpleNamespace(
        m=m,
        path=path,
        binding=binding,
        state=state,
        run=run,
        account=account,
        region=region,
        files=files,
        write=write,
    )


def validate(f):
    return f.m.validate_handoff(f.path, f.m.hashed(f.path), f.account, f.region)


def test_valid_handoff_is_read_only(handoff):
    f = handoff
    before = {p: p.read_bytes() for p in f.run.parent.rglob("*") if p.is_file()}
    validate(f)
    assert before == {p: p.read_bytes() for p in f.run.parent.rglob("*") if p.is_file()}


@pytest.mark.parametrize(
    "key,value",
    [
        ("serial", 33),
        ("lineage", "A"),
        ("instance_count", 31),
        ("workspace", "dev"),
        ("account_id", "000000000000"),
        ("region", "us-east-1"),
        ("state_sha256", "0" * 64),
        ("source_state", "/wrong/terraform.tfstate"),
        ("refresh_plan_sha256", "0" * 64),
    ],
)
def test_reject_wrong_binding(handoff, key, value):
    f = handoff
    f.binding[key] = value
    f.write(f.path, f.binding)
    with pytest.raises(f.m.DeploymentError):
        validate(f)


@pytest.mark.parametrize(
    "key,value",
    [
        ("bucket", "wrong"),
        ("key", "dev/terraform.tfstate"),
        ("encrypt", False),
        ("use_lockfile", False),
    ],
)
def test_reject_destination_changes(handoff, key, value):
    f = handoff
    f.binding["destination"][key] = value
    f.write(f.path, f.binding)
    with pytest.raises(f.m.DeploymentError):
        validate(f)


@pytest.mark.parametrize(
    "name", ["backup", "inputs", "apply", "readback", "normal", "normal_plan", "preflight"]
)
def test_reject_evidence_tamper(handoff, name):
    f = handoff
    f.files[name].write_bytes(b"tampered")
    with pytest.raises(f.m.DeploymentError):
        validate(f)


@pytest.mark.parametrize(
    "marker",
    [
        "backend.tf",
        "migration-attempt.json",
        "migration-receipt.json",
        "pre-migration.tfstate",
        ".terraform.tfstate.lock.info",
    ],
)
def test_reject_started_or_locked(handoff, marker):
    f = handoff
    (f.run / marker).touch()
    with pytest.raises(f.m.DeploymentError):
        validate(f)


def test_reject_unapproved_handoff(handoff):
    f = handoff
    with pytest.raises(f.m.DeploymentError):
        f.m.validate_handoff(f.path, "0" * 64, f.account, f.region)


def test_backend_matches_state_and_contains_no_credentials(handoff):
    f = handoff
    settings = f.m.canonical_backend(f.account, f.region, f.state)
    assert settings["key"] == "dev/terraform.tfstate"
    assert settings["allowed_account_ids"] == [f.account]
    assert "profile" not in settings and "access_key" not in settings
    f.state["outputs"]["state_bucket"]["value"] = "other"
    with pytest.raises(f.m.DeploymentError):
        f.m.canonical_backend(f.account, f.region, f.state)


@pytest.mark.parametrize(
    "field,key",
    [
        ("Versions", "bootstrap/terraform.tfstate"),
        ("DeleteMarkers", "bootstrap/terraform.tfstate"),
        ("Versions", "bootstrap/terraform.tfstate.tflock"),
        ("Versions", "dev/terraform.tfstate"),
    ],
)
def test_remote_history_or_lock_rejected(handoff, monkeypatch, field, key):
    f = handoff
    monkeypatch.setattr(f.m.bootstrap, "migration_target", lambda *a, **k: None)
    paginator = SimpleNamespace(paginate=lambda **kw: [{field: [{"Key": key}]}])
    session = SimpleNamespace(
        client=lambda *a, **kw: SimpleNamespace(get_paginator=lambda *a: paginator)
    )
    with pytest.raises(f.m.DeploymentError):
        f.m.vacant_destination(session, f.binding["destination"], f.account)


def test_inspect_never_enters_migration(handoff, monkeypatch):
    f = handoff
    monkeypatch.setattr(f.m, "inspect", lambda *a, **k: (f.binding, f.state, f.run, {}, None))
    monkeypatch.setattr(
        f.m.bootstrap, "migrate_state", lambda *a, **k: pytest.fail("migration called")
    )
    assert (
        f.m.execute("inspect", f.path, f.m.hashed(f.path))["status"]
        == "recovery_preconditions_passed"
    )


def test_migrate_requires_explicit_force_copy_approval(handoff, monkeypatch):
    f = handoff
    monkeypatch.setattr(f.m, "inspect", lambda *a, **k: (f.binding, f.state, f.run, {}, None))
    monkeypatch.setattr(f.m.bootstrap, "prerequisites", lambda *a: None)
    monkeypatch.setattr(f.m.bootstrap, "checked_source", lambda *a: "synthetic")
    monkeypatch.setattr(f.m.bootstrap, "run", lambda *a, **k: b"synthetic")
    monkeypatch.setattr(
        f.m.bootstrap, "migrate_state", lambda *a, **k: pytest.fail("migration called")
    )
    with pytest.raises(f.m.DeploymentError, match="ExplicitForceCopyApprovalRequired"):
        f.m.execute("migrate", f.path, f.m.hashed(f.path))
    assert not (f.run / "migration-attempt.json").exists()


@pytest.mark.parametrize("field", ["complete_no_op", "normal_plan_success", "addresses_retained"])
def test_rehashed_but_failed_normal_record_rejected(handoff, field):
    f = handoff
    record = f.m.read(f.files["normal"])
    record[field] = False
    f.write(f.files["normal"], record)
    f.binding["evidence"]["normal"]["sha256"] = f.m.hashed(f.files["normal"])
    f.write(f.path, f.binding)
    with pytest.raises(f.m.DeploymentError):
        validate(f)


def test_source_mutation_and_extra_config_rejected(handoff):
    f = handoff
    source = f.run / "terraform.tfstate"
    original = source.read_bytes()
    source.write_bytes(original + b" ")
    with pytest.raises(f.m.DeploymentError):
        validate(f)
    source.write_bytes(original)
    (f.run / "unexpected.tf").write_text("# added")
    with pytest.raises(f.m.DeploymentError):
        validate(f)


def test_unreadable_destination_not_absent(handoff, monkeypatch):
    f = handoff

    def denied(*args, **kwargs):
        raise f.m.DeploymentError("Denied")

    monkeypatch.setattr(f.m.bootstrap, "migration_target", denied)
    with pytest.raises(f.m.DeploymentError, match="Denied"):
        f.m.vacant_destination(None, f.binding["destination"], f.account)


def test_approved_migration_delegates_only_to_migration_engine(handoff, monkeypatch):
    f = handoff
    monkeypatch.setattr(f.m, "inspect", lambda *a, **k: (f.binding, f.state, f.run, {}, None))
    monkeypatch.setattr(f.m.bootstrap, "prerequisites", lambda *a: None)
    monkeypatch.setattr(f.m.bootstrap, "checked_source", lambda *a: "synthetic")
    commands = []

    def git_only(command, **kwargs):
        commands.append(command)
        assert command == ["git", "rev-parse", "origin/main"]
        return b"synthetic"

    monkeypatch.setattr(f.m.bootstrap, "run", git_only)
    monkeypatch.setattr(f.m, "vacant_destination", lambda *a: None)
    calls = []
    monkeypatch.setattr(f.m.bootstrap, "migrate_state", lambda *a, **k: calls.append((a, k)))
    result = f.m.execute("migrate", f.path, f.m.hashed(f.path), approve_force_copy=True)
    assert result["status"] == "bootstrap_migration_verification_pending"
    assert len(calls) == 1 and calls[0][0][2] == f.run / "terraform.tfstate"
    assert not (f.run / "migration-receipt.json").exists()


@pytest.mark.parametrize("changed", [False, True])
def test_postmigration_verification_no_apply(handoff, monkeypatch, changed):
    f = handoff
    original = f.files["backup"].read_bytes()
    (f.run / "pre-migration.tfstate").write_bytes(original)
    f.write(f.run / "migration-attempt.json", {"recovery_handoff_sha256": f.m.hashed(f.path)})
    monkeypatch.setattr(f.m, "inspect", lambda *a, **k: (f.binding, f.state, f.run, {}, None))
    monkeypatch.setattr(f.m, "validate_handoff", lambda *a, **k: None)
    monkeypatch.setattr(f.m.bootstrap, "prerequisites", lambda *a: None)
    monkeypatch.setattr(f.m.bootstrap, "checked_source", lambda *a: "synthetic")
    monkeypatch.setattr(f.m.bootstrap, "verify_state_version", lambda *a: ("version", original))

    def fake_run(command, **kwargs):
        assert "apply" not in command and "init" not in command
        if command[0] == "git":
            return b"synthetic"
        if command[1:3] == ["state", "pull"]:
            return original
        if command[1] == "plan":
            (f.run / "migration-normal.tfplan").write_bytes(b"synthetic-plan")
            return b""
        assert command[1] == "show"
        return json.dumps(
            {"resource_changes": [{"change": {"actions": ["update"] if changed else ["no-op"]}}]}
        ).encode()

    monkeypatch.setattr(f.m.bootstrap, "run", fake_run)
    if changed:
        with pytest.raises(f.m.DeploymentError):
            f.m.execute("verify", f.path, f.m.hashed(f.path))
        assert not (f.run / "migration-receipt.json").exists()
    else:
        assert (
            f.m.execute("verify", f.path, f.m.hashed(f.path))["status"]
            == "bootstrap_state_migrated"
        )
        assert (f.run / "migration-receipt.json").exists()
