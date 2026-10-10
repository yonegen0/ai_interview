"""Synthetic State and AWS/Terraform boundaries; never touch private production evidence."""

import copy
import importlib
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

ACCOUNT = "123456789012"
REGION = "ap-northeast-1"


@pytest.fixture
def tools(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "skills/p4"))
    return (
        importlib.import_module("bootstrap_maintenance"),
        importlib.import_module("maintenance_contract"),
        importlib.import_module("maintenance_aws"),
    )


@pytest.fixture
def fixture(tools):
    _, contract, _ = tools
    subjects = {
        role: "repo:yonegen0/ai_interview:environment:dev"
        for role in ("plan", "deploy", "test", "artifact")
    }
    values = {
        "account_id": ACCOUNT,
        "region": REGION,
        "oidc_provider_arn": "",
        "oidc_subjects": subjects,
        "ses_identity_type": "email",
        "ses_from_email": "synthetic@example.invalid",
        "ses_domain": "",
        "worker_wif_enabled": False,
    }
    resources = []

    def add(kind, name, attrs, index=None):
        item = {"attributes": attrs, "schema_version": 0}
        if index is not None:
            item["index_key"] = index
        resources.append({"type": kind, "name": name, "mode": "managed", "instances": [item]})

    policy = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": ["synthetic"]}
            ],
        }
    )
    for role in ("plan", "deploy"):
        add(
            "aws_iam_role_policy",
            "state",
            {
                "id": role,
                "name": "state-and-artifacts",
                "role": "ai-interview-ci-" + role,
                "policy": policy,
            },
            role,
        )
    for role in subjects:
        trust = {
            "Statement": [
                {
                    "Condition": {
                        "StringEquals": {"token.actions.githubusercontent.com:sub": subjects[role]}
                    }
                }
            ]
        }
        add("aws_iam_role", "ci", {"id": role, "assume_role_policy": json.dumps(trust)}, role)
    add("aws_iam_openid_connect_provider", "github", {"id": "synthetic"}, 0)
    add(
        "aws_ses_email_identity",
        "sender",
        {"id": "synthetic", "email": values["ses_from_email"]},
        0,
    )
    for index in range(24):
        add("aws_s3_bucket", "synthetic" + str(index), {"id": str(index), "tags": {}})
    state = {
        "version": 4,
        "terraform_version": "1.14.9",
        "lineage": "synthetic-lineage",
        "serial": 1,
        "resources": resources,
        "outputs": {"synthetic": {"value": "constant"}},
        "check_results": [],
    }
    snapshot = {
        "identity": contract.identity(contract.encoded(state), "v1"),
        "state": state,
        "backend": contract.backend(ACCOUNT, REGION),
        "versions": [{"kind": "Versions", "version_id": "v1", "size": 100}],
    }
    return SimpleNamespace(values=values, state=state, snapshot=snapshot)


def review_for(contract, fixture):
    old = contract.state_instances(fixture.state)
    changes, planned = [], []
    for address, attrs in old.items():
        after = copy.deepcopy(attrs)
        actions = ["no-op"]
        if address in contract.UPDATES:
            actions = ["update"]
            after["policy"] = json.dumps(contract.policy_after(attrs["policy"], ACCOUNT, REGION))
        changes.append(
            {
                "address": address,
                "mode": "managed",
                "change": {
                    "actions": actions,
                    "before": attrs,
                    "after": after,
                    "after_unknown": {},
                },
            }
        )
        planned.append({"address": address, "mode": "managed", "values": after})
    return {
        "terraform_version": "1.14.9",
        "applyable": True,
        "complete": True,
        "variables": {k: {"value": v} for k, v in fixture.values.items()},
        "resource_changes": changes,
        "prior_state": {
            "values": {
                "root_module": {
                    "resources": [
                        {"address": a, "mode": "managed", "values": v} for a, v in old.items()
                    ]
                }
            }
        },
        "planned_values": {
            "root_module": {"resources": planned},
            "outputs": copy.deepcopy(fixture.state["outputs"]),
        },
        "output_changes": {
            "synthetic": {
                "actions": ["no-op"],
                "before": "constant",
                "after": "constant",
                "after_unknown": False,
            }
        },
        "checks": [{"status": "pass"}],
    }


def approval_for(contract, fixture, private):
    def save(name, value):
        p = private / name
        raw = contract.encoded(value)
        p.write_bytes(raw)
        return str(p), contract.hashed(raw)

    inputs_path, inputs_hash = save("inputs.json", fixture.values)
    adoption_path, adoption_hash = save(
        "adoption.json",
        {
            "workspace": "default",
            "destination": fixture.snapshot["backend"],
            "destination_identity": {"lineage": fixture.state["lineage"], "serial": 1},
        },
    )
    receipt_path, receipt_hash = save(
        "receipt.json",
        {
            "identity": fixture.snapshot["identity"],
            "resources": 32,
            "state_key": "bootstrap/terraform.tfstate",
            "canonical_adoption_lineage_matches": True,
            "active_lock": False,
        },
    )
    return {
        "schema_version": 1,
        "kind": "p4-bootstrap-maintenance-plan",
        "approved": True,
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "account_id": ACCOUNT,
        "region": REGION,
        "source_sha": "a" * 40,
        "backend": fixture.snapshot["backend"],
        "workspace": "default",
        "state_identity": fixture.snapshot["identity"],
        "addresses": sorted(contract.state_instances(fixture.state)),
        "inputs_path": inputs_path,
        "inputs_sha256": inputs_hash,
        "provider_lock_sha256": "b" * 64,
        "adoption_path": adoption_path,
        "adoption_sha256": adoption_hash,
        "receipt_path": receipt_path,
        "receipt_sha256": receipt_hash,
        "principal_role_arn": f"arn:aws:iam::{ACCOUNT}:role/test",
        "normal_lockfile_writes_approved": True,
        "canonical_state_writes_approved": False,
        "iam_policy_updates_approved": False,
        "cost_cap_usd": "0.05",
    }


def test_canonical_snapshot_and_two_update_plan(tools, fixture):
    _, contract, _ = tools
    approval = {
        "state_identity": fixture.snapshot["identity"],
        "backend": fixture.snapshot["backend"],
        "addresses": sorted(contract.state_instances(fixture.state)),
    }
    assert len(contract.check_snapshot(fixture.snapshot, approval)) == 32
    contract.validate_inputs(fixture.values, fixture.state, ACCOUNT, REGION)
    assert contract.audit_plan(
        review_for(contract, fixture), fixture.state, fixture.values, ACCOUNT, REGION
    ) == {"create": 0, "update": 2, "replace": 0, "destroy": 0, "no_op": 30}


@pytest.mark.parametrize(
    "field,value",
    [
        ("lineage", "old-local"),
        ("serial", 0),
        ("serial", 2),
        ("sha256", "0" * 64),
        ("version_id", "old-version"),
    ],
)
def test_snapshot_identity_is_not_adopted_from_live(tools, fixture, field, value):
    _, contract, _ = tools
    expected = copy.deepcopy(fixture.snapshot)
    fixture.snapshot["identity"][field] = value
    with pytest.raises(ValueError, match="MaintenanceStateChanged"):
        contract.check_snapshot(fixture.snapshot, {"state_identity": expected["identity"]})


@pytest.mark.parametrize(
    "change", ["empty", "removed", "renamed", "module", "deposed", "duplicate"]
)
def test_state_addresses_and_nonempty_managed_namespace(tools, fixture, change):
    _, contract, _ = tools
    expected = sorted(contract.state_instances(fixture.state))
    if change == "empty":
        fixture.state["resources"] = []
    elif change == "removed":
        fixture.state["resources"].pop()
    elif change == "renamed":
        fixture.state["resources"][-1]["name"] = "unapproved"
    elif change == "module":
        fixture.state["resources"][-1]["module"] = "module.new"
    elif change == "deposed":
        fixture.state["resources"][-1]["instances"][0]["deposed"] = "old"
    else:
        fixture.state["resources"][-1] = fixture.state["resources"][-2]
    with pytest.raises(ValueError):
        contract.check_snapshot(
            fixture.snapshot,
            {"state_identity": fixture.snapshot["identity"], "addresses": expected},
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("oidc_provider_arn", "external"),
        ("worker_wif_enabled", True),
        ("ses_from_email", "changed@example.invalid"),
        ("region", "us-east-1"),
        ("account_id", "000000000000"),
    ],
)
def test_input_values_preserve_owned_provider_and_baseline(tools, fixture, field, value):
    _, contract, _ = tools
    fixture.values[field] = value
    with pytest.raises(ValueError):
        contract.validate_inputs(fixture.values, fixture.state, ACCOUNT, REGION)


@pytest.mark.parametrize(
    "change",
    [
        "create",
        "replace",
        "destroy",
        "read",
        "wrong-policy",
        "trust",
        "boundary",
        "missing",
        "unknown",
        "drift",
        "output",
        "incomplete",
        "variable",
        "check",
        "module",
        "before",
    ],
)
def test_every_saved_plan_difference_is_audited(tools, fixture, change):
    _, contract, _ = tools
    review = review_for(contract, fixture)
    row = review["resource_changes"][0]
    if change in {"create", "replace", "destroy", "read"}:
        row["change"]["actions"] = {"replace": ["delete", "create"], "destroy": ["delete"]}.get(
            change, [change]
        )
    elif change == "wrong-policy":
        doc = json.loads(row["change"]["after"]["policy"])
        doc["Statement"][-1]["Resource"] = ["*"]
        row["change"]["after"]["policy"] = json.dumps(doc)
    elif change in {"trust", "boundary"}:
        row["change"]["after"][change] = "unapproved"
    elif change == "missing":
        review["resource_changes"].pop()
    elif change == "unknown":
        row["change"]["after_unknown"] = {"policy": True}
    elif change == "drift":
        review["resource_drift"] = [row]
    elif change == "output":
        review["planned_values"]["outputs"]["synthetic"]["value"] = "new"
    elif change == "incomplete":
        review["complete"] = False
    elif change == "variable":
        review["variables"]["worker_wif_enabled"]["value"] = True
    elif change == "check":
        review["checks"][0]["status"] = "fail"
    elif change == "module":
        review["planned_values"]["root_module"]["child_modules"] = [{}]
    else:
        row["change"]["before"] = dict(row["change"]["before"], id="other")
    with pytest.raises(ValueError):
        contract.audit_plan(review, fixture.state, fixture.values, ACCOUNT, REGION)


@pytest.mark.parametrize(
    "mutation",
    ["key", "bucket", "account", "workspace", "expiry", "provider-lock", "unknown-field"],
)
def test_descriptor_namespace_and_hash_fields(tools, fixture, tmp_path, mutation):
    _, contract, _ = tools
    value = approval_for(contract, fixture, tmp_path)
    if mutation == "key":
        value["backend"]["key"] = "dev/terraform.tfstate"
    elif mutation == "bucket":
        value["backend"]["bucket"] = "other"
    elif mutation == "account":
        value["account_id"] = "000000000000"
    elif mutation == "workspace":
        value["workspace"] = "test"
    elif mutation == "expiry":
        value["expires_at"] = datetime.now(UTC).isoformat()
    elif mutation == "provider-lock":
        value["provider_lock_sha256"] = "bad"
    else:
        value["force_copy"] = True
    with pytest.raises(ValueError):
        contract.validate_approval(value, "plan", ACCOUNT, REGION)


@pytest.fixture
def harness(tools, fixture, tmp_path, monkeypatch):
    runner, contract, _ = tools
    home = tmp_path / "home"
    home.mkdir()
    private = home / ".p4-artifacts"
    private.mkdir()
    approval = approval_for(contract, fixture, private)
    request = private / "approval.json"
    request.write_bytes(contract.encoded(approval))
    run = private / "run"
    files = {
        "main.tf": b'terraform { required_version = "= 1.14.9" }\n',
        ".terraform.lock.hcl": b"synthetic-provider-lock",
    }
    calls = []

    class Reader:
        def __init__(self, *args):
            self.current = copy.deepcopy(fixture.snapshot)
            self.operations = []

        def actor(self, expected):
            return {"role_arn": expected}

        def snapshot(self):
            return copy.deepcopy(self.current)

        def verify_resources(self, state, values):
            assert contract.state_instances(state)

        def simulate_addition(self):
            return {"plan": "allowed", "deploy": "allowed"}

    reader = Reader()
    monkeypatch.setattr(runner, "home_repository", lambda root: home)
    monkeypatch.setattr(runner, "account_settings", lambda root: (ACCOUNT, REGION))
    monkeypatch.setattr(runner, "read_local_settings", lambda root: {"AWS_PROFILE": "synthetic"})
    monkeypatch.setattr(runner, "source_files", lambda *a, **kw: files)
    monkeypatch.setattr(runner, "checked_session", lambda *a, **kw: SimpleNamespace())
    monkeypatch.setattr(runner, "BootstrapAWS", lambda *args: reader)
    monkeypatch.setattr(runner, "credential_environment", lambda session, env: dict(env))
    # ACL behavior has its own tests. Synthetic orchestration does not run OS permission tools.
    monkeypatch.setattr(runner, "protect", lambda path: None)

    def terraform(directory, env, stage, args):
        calls.append((stage, list(args)))
        assert (
            "-lock=false" not in args and "-migrate-state" not in args and "-force-copy" not in args
        )
        assert "TF_LOG" not in env and env["TF_WORKSPACE"] == "default"
        if args[0] == "version":
            return contract.encoded({"terraform_version": "1.14.9"})
        if args[0] == "init":
            assert "-reconfigure" in args and "-lockfile=readonly" in args
            (directory / "data/terraform.tfstate").write_bytes(
                contract.encoded({"backend": {"type": "s3", "config": approval["backend"]}})
            )
            return b""
        if args[:2] == ["state", "pull"]:
            return contract.encoded(reader.current["state"])
        if args[0] == "plan":
            (directory / "bootstrap.tfplan").write_bytes(b"synthetic-saved-plan")
            return b""
        if args[0] == "show":
            return contract.encoded(review_for(contract, fixture))
        assert args[0] == "apply" and "-lock=true" in args
        state = copy.deepcopy(fixture.state)
        state["serial"] = 2
        for r in state["resources"]:
            if r["type"] == "aws_iam_role_policy":
                a = r["instances"][0]["attributes"]
                a["policy"] = json.dumps(contract.policy_after(a["policy"], ACCOUNT, REGION))
        reader.current["state"] = state
        reader.current["identity"] = contract.identity(contract.encoded(state), "v2")
        reader.current["versions"].append({"kind": "Versions", "version_id": "v2", "size": 101})
        return b""

    monkeypatch.setattr(runner, "terraform", terraform)
    return SimpleNamespace(
        runner=runner,
        contract=contract,
        approval=approval,
        request=request,
        run=run,
        private=private,
        reader=reader,
        files=files,
        calls=calls,
        env={"P4_BOOTSTRAP_MAINTENANCE_EXECUTION_READY": "true"},
        tf=terraform,
    )


def plan(h):
    return h.runner.execute(
        "plan",
        h.request,
        h.contract.hashed(h.request.read_bytes()),
        h.run,
        repository=h.private.parent,
        environment=h.env,
    )


def apply_request(h):
    value = copy.deepcopy(h.approval)
    value.update(
        kind="p4-bootstrap-maintenance-apply",
        canonical_state_writes_approved=True,
        iam_policy_updates_approved=True,
        run_path=str(h.run),
        plan_sha256=h.contract.hashed((h.run / "bootstrap.tfplan").read_bytes()),
        binding_sha256=h.contract.hashed((h.run / "binding.private.json").read_bytes()),
        plan_approval_sha256=h.contract.hashed(h.request.read_bytes()),
    )
    path = h.private / "apply-approval.json"
    path.write_bytes(h.contract.encoded(value))
    return path


def apply(h, path):
    return h.runner.execute(
        "apply",
        path,
        h.contract.hashed(path.read_bytes()),
        h.run,
        repository=h.private.parent,
        environment=h.env,
    )


def test_full_plan_apply_and_replay_is_blocked(harness):
    h = harness
    assert plan(h)["update"] == 2
    assert (h.run / "configuration/backend.tf").read_bytes() == h.runner.S3_BACKEND.encode()
    path = apply_request(h)
    assert apply(h, path)["status"] == "BOOTSTRAP_MAINTENANCE_APPLY_VERIFIED"
    with pytest.raises(ValueError):
        apply(h, path)
    assert len([args for _, args in h.calls if args[0] == "apply"]) == 1


@pytest.mark.parametrize(
    "failure",
    [
        "plan-failed",
        "plan-timeout",
        "after-state",
        "after-init",
        "unknown-review",
        "apply-failed",
        "apply-timeout",
    ],
)
def test_failure_journals_forbid_new_run_and_retry(harness, monkeypatch, failure):
    h = harness

    def fail(directory, env, stage, args):
        if stage == "plan" and failure.startswith("plan-"):
            raise ValueError("SyntheticResultUnknown")
        if stage == "apply" and failure.startswith("apply-"):
            h.calls.append((stage, args))
            raise ValueError("SyntheticResultUnknown")
        result = h.tf(directory, env, stage, args)
        if (
            failure == "after-state"
            and stage == "plan"
            or failure == "after-init"
            and stage == "init"
        ):
            h.reader.current["identity"]["version_id"] = "unexpected"
        if failure == "unknown-review" and stage == "show":
            value = json.loads(result)
            value["complete"] = False
            return h.contract.encoded(value)
        return result

    if failure.startswith("apply-"):
        plan(h)
        path = apply_request(h)
    monkeypatch.setattr(h.runner, "terraform", fail)
    with pytest.raises(ValueError):
        if failure.startswith("apply-"):
            apply(h, path)
        else:
            plan(h)
    with pytest.raises(ValueError):
        if failure.startswith("apply-"):
            apply(h, path)
        else:
            h.run = h.private / "another-run"
            plan(h)
    assert len([x for x in h.calls if x[0] == "apply"]) <= 1
    assert not (h.private / "bootstrap-operation.lock").exists()


@pytest.mark.parametrize(
    "tamper",
    [
        "plan",
        "binding",
        "inputs",
        "backend",
        "local-state",
        "extra-tf",
        "workspace",
        "wrong-run",
        "state-before",
        "state-at-last-read",
        "provider-lock",
    ],
)
def test_apply_binding_and_immediate_state_guard(harness, monkeypatch, tamper):
    h = harness
    plan(h)
    path = apply_request(h)
    if tamper == "plan":
        (h.run / "bootstrap.tfplan").write_bytes(b"changed")
    elif tamper == "binding":
        (h.run / "binding.private.json").write_bytes(b"{}")
    elif tamper == "inputs":
        (h.run / "inputs.private.json").write_bytes(b"{}")
    elif tamper == "backend":
        (h.run / "backend.private.hcl").write_bytes(b'key="dev/terraform.tfstate"')
    elif tamper == "local-state":
        (h.run / "configuration/terraform.tfstate").write_bytes(b"old")
    elif tamper == "extra-tf":
        (h.run / "configuration/unapproved.tf").write_bytes(b"bad")
    elif tamper == "workspace":
        (h.run / "data/environment").write_text("test")
    elif tamper == "wrong-run":
        h.run = h.private / "wrong"
    elif tamper == "provider-lock":
        (h.run / "configuration/.terraform.lock.hcl").write_bytes(b"changed")
    elif tamper == "state-before":
        h.reader.current["identity"]["serial"] = 2
    else:

        def state_after_show(directory, env, stage, args):
            result = h.tf(directory, env, stage, args)
            if stage == "pre-apply-show":
                h.reader.current["identity"]["version_id"] = "changed"
            return result

        monkeypatch.setattr(h.runner, "terraform", state_after_show)
    with pytest.raises((ValueError, FileNotFoundError)):
        apply(h, path)
    assert not any(args[0] == "apply" for _, args in h.calls)


def test_false_approval_and_unready_gate_do_not_run_terraform(harness):
    h = harness
    h.env = {}
    with pytest.raises(ValueError, match="SeparateExplicitApproval"):
        plan(h)
    h.env = {"P4_BOOTSTRAP_MAINTENANCE_EXECUTION_READY": "true"}
    h.approval["approved"] = False
    h.request.write_bytes(h.contract.encoded(h.approval))
    with pytest.raises(ValueError, match="SeparateExplicitApproval"):
        plan(h)
    assert not h.calls


def test_readonly_inspection_never_initializes_backend(harness):
    h = harness
    h.approval["approved"] = False
    h.request.write_bytes(h.contract.encoded(h.approval))
    result = h.runner.execute(
        "inspect",
        h.request,
        h.contract.hashed(h.request.read_bytes()),
        h.run,
        repository=h.private.parent,
        environment={},
    )
    assert result["aws_writes"] == 0 and not h.calls


@pytest.mark.parametrize("bad", ["key", "type", "credential", "workspace", "encrypt"])
def test_backend_metadata_rejects_hidden_reconfiguration(harness, bad):
    h = harness
    plan(h)
    p = h.run / "data/terraform.tfstate"
    metadata = json.loads(p.read_bytes())
    if bad == "type":
        metadata["backend"]["type"] = "local"
    elif bad == "workspace":
        (h.run / "data/environment").write_text("other")
    else:
        metadata["backend"]["config"].update(
            {
                "key": {"key": "dev/terraform.tfstate"},
                "credential": {"access_key": "synthetic"},
                "encrypt": {"encrypt": False},
            }[bad]
        )
    p.write_bytes(h.contract.encoded(metadata))
    with pytest.raises(ValueError):
        h.runner.check_backend(h.run, h.approval["backend"])


def test_git_revision_and_provider_lock_guard(tools, monkeypatch, tmp_path):
    runner, _, _ = tools
    monkeypatch.setattr(runner, "git", lambda root, *args: b"b" * 40)
    with pytest.raises(ValueError, match="GitShaMismatch"):
        runner.source_files(tmp_path, {"source_sha": "a" * 40}, require_main=True)


@pytest.mark.parametrize("mismatch", ["lock", "branch", "remote", "overlay"])
def test_source_manifest_is_from_exact_git_blobs(tools, monkeypatch, tmp_path, mismatch):
    runner, contract, _ = tools
    lock = b"""provider "registry.terraform.io/hashicorp/aws" {
 version = "6.64.0"
 constraints = "~> 6.0"
 hashes = ["zh:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]
}"""

    def git(root, *args):
        if args == ("rev-parse", "HEAD"):
            return b"a" * 40
        if args[0] == "status":
            return b""
        if args[0] == "config":
            return b"https://github.com/yonegen0/ai_interview.git"
        if args[0] == "branch":
            return b"feature" if mismatch == "branch" else b"main"
        if args[0] == "ls-remote":
            return (b"b" if mismatch == "remote" else b"a") * 40 + b"\trefs/heads/main"
        if args[0] == "ls-tree":
            return b"terraform/bootstrap/.terraform.lock.hcl\nterraform/bootstrap/" + (
                b"backend.tf" if mismatch == "overlay" else b"main.tf"
            )
        return lock if args[-1].endswith(".terraform.lock.hcl") else b"terraform {}"

    monkeypatch.setattr(runner, "git", git)
    with pytest.raises(ValueError):
        runner.source_files(
            tmp_path,
            {
                "source_sha": "a" * 40,
                "provider_lock_sha256": "0" * 64 if mismatch == "lock" else contract.hashed(lock),
            },
            require_main=True,
        )


def test_privacy_gate_refuses_symlink(tools, tmp_path):
    runner, _, _ = tools
    link = tmp_path / "link"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Windows symlink privilege unavailable")
    with pytest.raises(ValueError):
        runner.private_path(link / "evidence", tmp_path)


def test_acl_failure_occurs_before_sensitive_write(tools, tmp_path, monkeypatch):
    runner, _, _ = tools

    def fail(directory):
        raise ValueError("MaintenancePrivateAclUnavailable")

    monkeypatch.setattr(runner, "protect", fail)
    with pytest.raises(ValueError):
        runner.secure_directory(tmp_path / "private")
    assert not list((tmp_path / "private").iterdir())


def test_sdk_guard_refuses_iam_and_state_writes(tools):
    _, _, aws = tools
    hooks = []
    session = SimpleNamespace(
        events=SimpleNamespace(register=lambda name, fn: hooks.append(fn)),
        client=lambda *a, **kw: SimpleNamespace(),
    )
    reader = aws.BootstrapAWS(session, ACCOUNT, REGION)
    for operation in ("PutObject", "DeleteObject", "PutRolePolicy", "UpdateAssumeRolePolicy"):
        with pytest.raises(ValueError, match="SdkWriteForbidden"):
            hooks[0](SimpleNamespace(name=operation))
    hooks[0](SimpleNamespace(name="GetObject"))
    assert reader.operations == ["GetObject"]


@pytest.mark.parametrize("mutation", ["lineage", "serial", "trust", "address", "output"])
def test_apply_readback_rejects_partial_or_unapproved_changes(tools, fixture, mutation):
    _, contract, _ = tools
    after = copy.deepcopy(fixture.state)
    after["serial"] = 2
    for resource in after["resources"]:
        if resource["type"] == "aws_iam_role_policy":
            attrs = resource["instances"][0]["attributes"]
            attrs["policy"] = json.dumps(contract.policy_after(attrs["policy"], ACCOUNT, REGION))
    if mutation == "lineage":
        after["lineage"] = "replacement"
    elif mutation == "serial":
        after["serial"] = 1
    elif mutation == "trust":
        after["resources"][2]["instances"][0]["attributes"]["assume_role_policy"] = "{}"
    elif mutation == "address":
        after["resources"][-1]["name"] = "changed"
    else:
        after["outputs"]["synthetic"]["value"] = "changed"
    with pytest.raises(ValueError):
        contract.check_applied(fixture.state, after, ACCOUNT, REGION)


@pytest.mark.parametrize(
    "name",
    ["TF_WORKSPACE", "TF_CLI_ARGS_plan", "TF_VAR_account_id", "TF_LOG", "AWS_ENDPOINT_URL_S3"],
)
def test_hidden_environment_never_reaches_child(harness, name):
    h = harness
    h.env[name] = "untrusted"
    with pytest.raises(ValueError, match="HiddenEnvironment"):
        plan(h)
    assert not h.calls


def test_subprocess_timeout_stops_without_exposing_output(tools, tmp_path, monkeypatch):
    runner, _, _ = tools
    (tmp_path / "configuration").mkdir()

    def timeout(*args, **kw):
        raise subprocess.TimeoutExpired(args[0], 1200, output=b"synthetic-private-output")

    monkeypatch.setattr(runner.subprocess, "run", timeout)
    with pytest.raises(ValueError, match="ResultUnknown") as caught:
        runner.terraform(tmp_path, {}, "plan", ["plan", "-lock=true"])
    assert "synthetic-private-output" not in str(caught.value)
    assert (
        json.loads((tmp_path / "plan-timeout.private.json").read_bytes())["status"]
        == "RESULT_UNKNOWN"
    )


def test_exclusive_private_records_and_path_escape(tools, tmp_path):
    runner, _, _ = tools
    p = tmp_path / "record"
    runner.write_json(p, {"synthetic": True})
    with pytest.raises(FileExistsError):
        runner.write_json(p, {})
    with pytest.raises(ValueError):
        runner.private_path(tmp_path.parent / "outside", tmp_path)
    if os.name != "nt":
        assert p.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "code,present",
    [("404", False), ("403", False), ("403", True), ("AccessDenied", True), ("500", False)],
)
def test_exact_lock_absence_never_infers_from_403(tools, code, present):
    _, contract, aws = tools
    reader = aws.BootstrapAWS.__new__(aws.BootstrapAWS)
    reader.account, reader.backend = ACCOUNT, contract.backend(ACCOUNT, REGION)

    def head(**kw):
        raise ClientError({"Error": {"Code": code}}, "HeadObject")

    reader.s3 = SimpleNamespace(
        head_object=head,
        list_objects_v2=lambda **kw: {
            "IsTruncated": False,
            "Contents": [{"Key": kw["Prefix"]}] if present else [],
        },
    )
    if present or code == "500":
        with pytest.raises(ValueError):
            reader.absent_lock()
    else:
        reader.absent_lock()


@pytest.mark.parametrize("mutation", ["none", "version", "size", "encryption", "empty-state"])
def test_version_pinned_s3_snapshot(tools, fixture, mutation):
    _, contract, aws = tools
    reader = aws.BootstrapAWS.__new__(aws.BootstrapAWS)
    reader.account, reader.region = ACCOUNT, REGION
    reader.backend = contract.backend(ACCOUNT, REGION)
    raw = contract.encoded(
        fixture.state if mutation != "empty-state" else dict(fixture.state, resources=[])
    )
    calls = []

    def head(**kw):
        if kw["Key"].endswith(".tflock"):
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"VersionId": "v1", "ContentLength": len(raw), "ServerSideEncryption": "AES256"}

    def get(**kw):
        calls.append(kw)
        assert kw["VersionId"] == "v1" and kw["ExpectedBucketOwner"] == ACCOUNT
        return {
            "Body": BytesIO(raw),
            "VersionId": "v2" if mutation == "version" else "v1",
            "ContentLength": len(raw) + (1 if mutation == "size" else 0),
            "ServerSideEncryption": "aws:kms" if mutation == "encryption" else "AES256",
        }

    reader.s3 = SimpleNamespace(
        head_object=head,
        get_object=get,
        head_bucket=lambda **kw: None,
        get_bucket_location=lambda **kw: {"LocationConstraint": REGION},
        get_bucket_versioning=lambda **kw: {"Status": "Enabled"},
        get_bucket_encryption=lambda **kw: {
            "ServerSideEncryptionConfiguration": {
                "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
            }
        },
        list_object_versions=lambda **kw: {
            "IsTruncated": False,
            "Versions": [{"Key": kw["Prefix"], "VersionId": "v1", "Size": len(raw)}],
        },
    )
    if mutation == "none":
        assert reader.snapshot()["identity"] == fixture.snapshot["identity"]
    else:
        with pytest.raises(ValueError):
            reader.snapshot()
    assert len(calls) == 1
