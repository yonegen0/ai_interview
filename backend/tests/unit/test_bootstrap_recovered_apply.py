"""Synthetic FakeProvider coverage. All real SDK/network boundaries are forbidden."""

import copy
import importlib
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import boto3.session
import botocore.client
import pytest
import test_bootstrap_audit_recovery as recovery_tests


@pytest.fixture(autouse=True)
def no_live_access(monkeypatch):
    import socket

    counts = {"sdk": 0, "network": 0}

    def sdk(*args, **kwargs):
        counts["sdk"] += 1
        pytest.fail("Real AWS access forbidden")

    def network(*args, **kwargs):
        counts["network"] += 1
        pytest.fail("Real network access forbidden")

    monkeypatch.setattr(boto3.session.Session, "__init__", sdk)
    monkeypatch.setattr(boto3.session.Session, "client", sdk)
    monkeypatch.setattr(botocore.client.BaseClient, "_make_api_call", sdk)
    monkeypatch.setattr(socket.socket, "connect", network)
    monkeypatch.setattr(socket.socket, "connect_ex", network)
    monkeypatch.setattr(socket, "create_connection", network)
    yield counts
    assert counts == {"sdk": 0, "network": 0}


@pytest.fixture
def tools(monkeypatch):
    return recovery_tests.tools.__wrapped__(monkeypatch)


@pytest.fixture
def fixture(tools):
    return recovery_tests.fixture.__wrapped__(tools)


@pytest.fixture
def recovery_tools(tools):
    return recovery_tests.recovery_tools.__wrapped__(tools)


@pytest.fixture
def harness(tools, recovery_tools, fixture, monkeypatch, tmp_path):
    h = recovery_tests.recovery_harness.__wrapped__(
        tools, recovery_tools, fixture, monkeypatch, tmp_path
    )
    recovery_tests.recover(h)
    c = importlib.import_module("bootstrap_recovered_apply")
    apply = recovery_tests.recovered_apply_inputs(h)[0]
    apply_path = h.private / "apply.json"
    apply_path.write_bytes(h.contract.encoded(apply))
    controller = h.private / "controller"
    controller.mkdir()
    audit = h.private / "audit"
    audit.mkdir()
    binary = h.private / "terraform"
    binary.write_bytes(b"synthetic terraform executable")
    platform = "windows_amd64" if os.name == "nt" else "linux_amd64"
    name = "terraform-provider-aws_v6.64.0_x5" + (".exe" if os.name == "nt" else "")
    provider = f"providers/registry.terraform.io/hashicorp/aws/6.64.0/{platform}/{name}"
    provider_path = h.original / "data" / provider
    provider_path.parent.mkdir(parents=True)
    provider_path.write_bytes(b"synthetic provider executable")
    envelope = {
        "schema_version": 1,
        "kind": "p4-bootstrap-recovered-apply-controller",
        "approved": True,
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "cost_cap_usd": "0.05",
        "controller_source_sha": "e" * 40,
        "controller_code_sha256": "f" * 64,
        "controller_repository": str(controller),
        "audit_repository": str(audit),
        "apply_approval_sha256": h.contract.hashed(apply_path.read_bytes()),
        "apply_run_path": str(h.private / "apply-output"),
        "terraform_path": str(binary),
        "terraform_sha256": h.contract.hashed(binary.read_bytes()),
        "provider_files": {provider: h.contract.hashed(provider_path.read_bytes())},
    }
    envelope_path = h.private / "controller.json"
    envelope_path.write_bytes(h.contract.encoded(envelope))
    monkeypatch.setattr(c, "controller_identity", lambda *a: None)
    commands = []
    events = []
    after = copy.deepcopy(h.snapshot)
    after["state"]["serial"] += 1
    for address, attrs in h.contract.state_instances(after["state"]).items():
        if address in h.contract.UPDATES:
            attrs["policy"] = json.dumps(
                h.contract.policy_after(
                    attrs["policy"], recovery_tests.ACCOUNT, recovery_tests.REGION
                )
            )
    after["identity"] = h.contract.identity(h.contract.encoded(after["state"]), "v2")
    after["versions"].append(
        {"kind": "Versions", "version_id": "v2", "size": len(h.contract.encoded(after["state"]))}
    )
    after["versions_sha256"] = h.contract.hashed(h.contract.encoded(after["versions"]))
    applied = [False]
    reader = SimpleNamespace(
        actor=lambda arn: copy.deepcopy(h.actor),
        snapshot=lambda: copy.deepcopy(after if applied[0] else h.snapshot),
        verify_resources=lambda *a: events.append("verify"),
        operations=["GetObject"],
        session=object(),
        diagnose=lambda: {"repair_attempted": False},
    )
    monkeypatch.setattr(h.recovery, "reader_for", lambda *a: events.append("reader") or reader)
    monkeypatch.setattr(
        h.normal,
        "execution_environment",
        lambda *a: {"TF_DATA_DIR": str(h.private / "apply-output/data")},
    )

    def fake(output, env, value, stage, args, plan):
        commands.append((stage, args))
        if stage == "version":
            return b'{"terraform_version":"1.14.9"}'
        if stage in {"pre-pull", "post-pull"}:
            return h.contract.encoded(after["state"] if applied[0] else h.snapshot["state"])
        if stage == "pre-show":
            return h.artifacts["show.stdout.private.log"]
        assert stage == "apply"
        applied[0] = True
        return b"Synthetic Apply successful"

    monkeypatch.setattr(c, "terraform", fake)
    return SimpleNamespace(
        c=c,
        h=h,
        envelope=envelope,
        envelope_path=envelope_path,
        apply=apply,
        apply_path=apply_path,
        controller=controller,
        commands=commands,
        events=events,
        after=after,
        fake=fake,
    )


def rewrite(h):
    h.apply_path.write_bytes(h.h.contract.encoded(h.apply))
    h.envelope["apply_approval_sha256"] = h.h.contract.hashed(h.apply_path.read_bytes())
    h.envelope_path.write_bytes(h.h.contract.encoded(h.envelope))


def execute(h, ready="true"):
    return h.c.execute(
        str(h.envelope_path),
        h.h.contract.hashed(h.envelope_path.read_bytes()),
        str(h.apply_path),
        h.h.contract.hashed(h.apply_path.read_bytes()),
        repository=h.controller,
        environment={"P4_BOOTSTRAP_RECOVERED_APPLY_READY": ready},
    )


def test_one_saved_plan_apply_preserves_old_evidence_and_claims(harness):
    h = harness
    originals = {name: (h.h.original / name).read_bytes() for name in h.h.artifacts}
    assert execute(h) == {"status": "BOOTSTRAP_RECOVERED_APPLY_VERIFIED", "updated": 2}
    apply = [args for stage, args in h.commands if stage == "apply"]
    assert apply == [
        [
            "apply",
            "-input=false",
            "-lock=true",
            "-lock-timeout=0s",
            str(h.h.original / "bootstrap.tfplan"),
        ]
    ]
    assert all(stage not in {"init", "plan", "destroy"} for stage, _ in h.commands)
    assert originals == {name: (h.h.original / name).read_bytes() for name in originals}
    namespace = h.h.contract.hashed(h.h.contract.encoded(h.h.value["backend"]))
    claim = h.h.private / "bootstrap-audit-recovery-ledger" / namespace
    output = h.h.private / "apply-output"
    assert (claim / "apply-completed.private.json").read_bytes() == (
        output / "apply-completed.private.json"
    ).read_bytes()
    assert not (h.h.private / "bootstrap-operation.lock").exists()
    h.envelope["apply_run_path"] = str(h.h.private / "different-run")
    rewrite(h)
    with pytest.raises(Exception, match="AlreadyAttempted"):
        execute(h)
    assert len([x for x in h.commands if x[0] == "apply"]) == 1


@pytest.mark.parametrize(
    "field,bad",
    [
        ("approved", False),
        ("schema_version", True),
        ("schema_version", 1.0),
        ("cost_cap_usd", "0.06"),
        ("kind", "p4-bootstrap-audit-recovery"),
        ("expires_at", "2000-01-01T00:00:00+00:00"),
        ("apply_approval_sha256", "x"),
        ("controller_code_sha256", "x"),
        ("controller_source_sha", "x"),
        ("terraform_sha256", "0" * 64),
        ("provider_files", {}),
    ],
)
def test_invalid_controller_stops_before_reader_or_process(harness, field, bad):
    h = harness
    h.envelope[field] = bad
    h.envelope_path.write_bytes(h.h.contract.encoded(h.envelope))
    with pytest.raises((ValueError, KeyError, TypeError)):
        execute(h)
    assert h.events == h.commands == []


@pytest.mark.parametrize(
    "field,bad",
    [
        ("approved", False),
        ("schema_version", True),
        ("schema_version", 1.0),
        ("normal_lockfile_writes_approved", False),
        ("canonical_state_writes_approved", False),
        ("iam_policy_updates_approved", False),
        ("binding_sha256", "a" * 64),
        ("plan_sha256", "a" * 64),
        ("audit_source_sha", "a" * 40),
        ("expires_at", "2000-01-01T00:00:00+00:00"),
    ],
)
def test_invalid_apply_stops_before_reader_or_process(harness, field, bad):
    h = harness
    h.apply[field] = bad
    rewrite(h)
    with pytest.raises((ValueError, KeyError, TypeError)):
        execute(h)
    assert h.events == h.commands == []


def test_missing_ready_flag_stops_before_reader(harness):
    with pytest.raises(Exception, match="ExecutionDisabled"):
        execute(harness, "false")
    assert harness.events == harness.commands == []


@pytest.mark.parametrize(
    "failure", ["timeout", "partial", "foreign-journal", "post-state", "lock-release"]
)
def test_uncertainty_keeps_claim_and_never_retries(harness, monkeypatch, failure):
    h = harness
    original = h.fake

    def failing(output, env, envelope, stage, args, plan):
        if stage == "pre-show" and failure == "foreign-journal":
            namespace = h.h.contract.hashed(h.h.contract.encoded(h.h.value["backend"]))
            (
                h.h.private
                / "bootstrap-audit-recovery-ledger"
                / namespace
                / "apply-started.private.json"
            ).write_bytes(b"foreign-owner")
        if stage == "apply" and failure in {"timeout", "partial"}:
            h.commands.append((stage, args))
            if failure == "timeout":
                raise subprocess.TimeoutExpired("synthetic terraform", 1200)
            raise ValueError("SyntheticPartialFailure")
        result = original(output, env, envelope, stage, args, plan)
        if stage == "apply" and failure == "post-state":
            h.after["state"]["lineage"] = "foreign-lineage"
        return result

    monkeypatch.setattr(h.c, "terraform", failing)
    if failure == "lock-release":
        from contextlib import contextmanager

        @contextmanager
        def failed_release(private):
            yield
            raise ValueError("SyntheticLockReleaseFailed")

        monkeypatch.setattr(h.c, "bootstrap_lock", failed_release)
    expected = {
        "timeout": "synthetic terraform",
        "partial": "SyntheticPartialFailure",
        "foreign-journal": "AttemptOwnershipChanged",
        "post-state": "MaintenanceApplyStateIdentity",
        "lock-release": "SyntheticLockReleaseFailed",
    }[failure]
    with pytest.raises((ValueError, subprocess.TimeoutExpired), match=expected):
        execute(h)
    namespace = h.h.contract.hashed(h.h.contract.encoded(h.h.value["backend"]))
    claim = h.h.private / "bootstrap-audit-recovery-ledger" / namespace
    assert (claim / "apply-started.private.json").exists()
    assert json.loads((claim / "apply-failed.private.json").read_bytes())["retry_allowed"] is False
    command_count = len(h.commands)
    h.envelope["apply_run_path"] = str(h.h.private / "retry-run")
    rewrite(h)
    with pytest.raises(ValueError):
        execute(h)
    assert len(h.commands) == command_count


@pytest.mark.parametrize("stage", ["init", "plan", "destroy", "force-unlock"])
def test_process_boundary_rejects_every_unlisted_operation(harness, stage):
    h = harness
    from bootstrap_recovered_apply import terraform

    # Restore the actual boundary rather than the FakeProvider adapter.
    real = importlib.reload(h.c).terraform
    with pytest.raises(Exception, match="OperationForbidden"):
        real(h.h.private, {}, h.envelope, stage, [stage], h.h.original / "bootstrap.tfplan")
    assert terraform is not None


@pytest.mark.parametrize(
    "name", ["apply-completed.private.json", "apply-failed.private.json", "foreign.json"]
)
def test_inconsistent_namespace_is_rejected_before_reader(harness, name):
    h = harness
    namespace = h.h.contract.hashed(h.h.contract.encoded(h.h.value["backend"]))
    claim = h.h.private / "bootstrap-audit-recovery-ledger" / namespace
    (claim / name).write_bytes(b"foreign-record")
    with pytest.raises(ValueError, match="AlreadyAttempted"):
        execute(h)
    assert h.events == h.commands == []


def test_one_sided_completion_retains_failure_and_blocks_retry(harness, monkeypatch):
    h = harness
    namespace = h.h.contract.hashed(h.h.contract.encoded(h.h.value["backend"]))
    claim = h.h.private / "bootstrap-audit-recovery-ledger" / namespace
    original = h.h.normal.write_json

    def fail_claim(path, data):
        if path == claim / "apply-completed.private.json":
            raise ValueError("SyntheticJournalFailure")
        return original(path, data)

    monkeypatch.setattr(h.h.normal, "write_json", fail_claim)
    with pytest.raises(ValueError, match="SyntheticJournalFailure"):
        execute(h)
    assert (h.h.private / "apply-output/apply-completed.private.json").exists()
    assert not (claim / "apply-completed.private.json").exists()
    assert (claim / "apply-failed.private.json").exists()
    assert len([x for x in h.commands if x[0] == "apply"]) == 1
    h.envelope["apply_run_path"] = str(h.h.private / "another-output")
    rewrite(h)
    with pytest.raises(ValueError, match="AlreadyAttempted"):
        execute(h)
    assert len([x for x in h.commands if x[0] == "apply"]) == 1


@pytest.mark.parametrize("failure", ["working-copy", "digest", "dirty", "revision"])
def test_real_controller_identity_rejects_unreviewed_code(harness, monkeypatch, failure):
    h = harness
    real = importlib.reload(h.c).controller_identity
    raw = Path(h.c.__file__).read_bytes().replace(b"\r\n", b"\n")
    h.envelope["controller_code_sha256"] = h.h.contract.hashed(raw)

    def git(root, *args):
        if args[0] == "rev-parse":
            return (
                ("0" * 40 if failure == "revision" else h.envelope["controller_source_sha"]) + "\n"
            ).encode()
        if args[0] == "status":
            return b" M modified" if failure == "dirty" else b""
        assert args[0] == "show"
        return b"foreign-code" if failure == "working-copy" else raw

    monkeypatch.setattr(h.h.normal, "git", git)
    if failure == "digest":
        h.envelope["controller_code_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="CleanControllerRequired|LoadedControllerChanged"):
        real(h.controller, h.envelope, h.h.private)


@pytest.mark.parametrize("case", ["wrong-lock", "timeout", "nonzero", "success"])
def test_real_process_adapter_logs_and_enforces_exact_command(harness, monkeypatch, case):
    h = harness
    real = importlib.reload(h.c).terraform
    output = h.h.private / "adapter-output"
    h.c.prepare_run(output, h.h.original, h.h.artifacts, h.h.files, h.envelope)
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        assert kwargs["cwd"] == output / "configuration"
        assert command[0] == h.envelope["terraform_path"]
        assert kwargs["timeout"] == 1200
        if case == "timeout":
            raise subprocess.TimeoutExpired(command, 1200, output=b"partial", stderr=b"unknown")
        return SimpleNamespace(
            returncode=1 if case == "nonzero" else 0, stdout=b"synthetic", stderr=b""
        )

    monkeypatch.setattr(h.c.subprocess, "run", fake_run)
    plan = h.h.original / "bootstrap.tfplan"
    args = ["apply", "-input=false", "-lock=true", "-lock-timeout=0s", str(plan)]
    if case == "wrong-lock":
        args[2] = "-lock=false"
        with pytest.raises(ValueError, match="OperationForbidden"):
            real(output, {}, h.envelope, "apply", args, plan)
        assert not calls
        return
    if case == "success":
        assert real(output, {}, h.envelope, "apply", args, plan) == b"synthetic"
    else:
        with pytest.raises(ValueError, match="ResultUnknown|TerraformFailed"):
            real(output, {}, h.envelope, "apply", args, plan)
    assert len(calls) == 1
    assert (output / "apply.stdout.private.log").exists()
    assert (output / "apply.stderr.private.log").exists()
