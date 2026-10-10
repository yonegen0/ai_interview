"""Synthetic evidence only. No credentials, production State or live recovery execution."""

import copy
import importlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_bootstrap_maintenance as maintenance_tests
from test_bootstrap_maintenance import (
    ACCOUNT,
    REGION,
    approval_for,
    review_for,
)


@pytest.fixture
def tools(monkeypatch):
    return maintenance_tests.tools.__wrapped__(monkeypatch)


@pytest.fixture
def fixture(tools):
    return maintenance_tests.fixture.__wrapped__(tools)


@pytest.fixture
def recovery_tools(tools):
    return importlib.import_module("bootstrap_audit_recovery"), importlib.import_module(
        "recovery_contract"
    )


def real_shape(contract, fixture):
    shape = json.loads(
        (
            Path(__file__).parents[1] / "fixtures/p4/terraform-1.14.9-maintenance-shape.json"
        ).read_bytes()
    )
    review = review_for(contract, fixture)
    review["format_version"] = shape["format_version"]
    review["variables"]["worker_wif_enabled"] = shape["worker_wif_enabled_variable"]
    review["planned_values"]["outputs"]["ses_domain_verification"] = shape[
        "ses_domain_verification_output"
    ]
    review["output_changes"]["ses_domain_verification"] = shape["ses_domain_verification_change"]
    review["output_changes"]["synthetic"] = shape["existing_output_change"]
    return review


@pytest.mark.parametrize("flag", [False, "false"])
def test_only_known_disabled_flag_representations_pass(tools, fixture, flag):
    _, contract, _ = tools
    review = real_shape(contract, fixture)
    review["variables"]["worker_wif_enabled"]["value"] = flag
    assert (
        contract.audit_plan(review, fixture.state, fixture.values, ACCOUNT, REGION)["update"] == 2
    )


@pytest.mark.parametrize(
    "flag", [True, "true", "False", "FALSE", " false", "false ", "0", 0, 1, None, [], {}, "", "no"]
)
def test_boolean_normalization_is_not_general_coercion(tools, fixture, flag):
    _, contract, _ = tools
    review = real_shape(contract, fixture)
    review["variables"]["worker_wif_enabled"]["value"] = flag
    with pytest.raises(ValueError, match="PlanInputs"):
        contract.audit_plan(review, fixture.state, fixture.values, ACCOUNT, REGION)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("account_id", 123456789012),
        ("region", False),
        ("ses_domain", None),
        ("oidc_subjects", "{}"),
        ("ses_identity_type", "domain"),
    ],
)
def test_no_other_variable_is_normalized(tools, fixture, field, bad):
    _, contract, _ = tools
    review = real_shape(contract, fixture)
    review["variables"][field]["value"] = bad
    with pytest.raises(ValueError, match="PlanInputs"):
        contract.audit_plan(review, fixture.state, fixture.values, ACCOUNT, REGION)


@pytest.mark.parametrize(
    "mutation",
    [
        "ses-non-null",
        "other-null",
        "ses-domain-mode",
        "ses-missing-change",
        "missing-action",
        "nested-change",
        "missing-before",
        "missing-after",
        "missing-unknown",
        "update",
        "create",
        "delete",
        "before-changed",
        "after-changed",
        "known-false-number",
        "unknown",
        "extra-change",
        "missing-existing",
        "equal-but-wrong-before-after",
        "prior-output-changed",
    ],
)
def test_outputs_require_exact_known_no_ops(tools, fixture, mutation):
    _, contract, _ = tools
    review = real_shape(contract, fixture)
    ses = review["output_changes"]["ses_domain_verification"]
    if mutation == "ses-non-null":
        review["planned_values"]["outputs"]["ses_domain_verification"]["value"] = "changed"
    elif mutation == "other-null":
        review["planned_values"]["outputs"]["other"] = {"value": None}
    elif mutation == "ses-domain-mode":
        fixture.values["ses_identity_type"] = "domain"
        review["variables"]["ses_identity_type"]["value"] = "domain"
    elif mutation == "ses-missing-change":
        del review["output_changes"]["ses_domain_verification"]
    elif mutation.startswith("missing-") and mutation != "missing-existing":
        del ses[
            {
                "missing-action": "actions",
                "missing-before": "before",
                "missing-after": "after",
                "missing-unknown": "after_unknown",
            }[mutation]
        ]
    elif mutation == "nested-change":
        review["output_changes"]["ses_domain_verification"] = {"change": ses}
    elif mutation in ("update", "create", "delete"):
        ses["actions"] = [mutation]
    elif mutation == "before-changed":
        ses["before"] = "changed"
    elif mutation == "after-changed":
        ses["after"] = "changed"
    elif mutation == "known-false-number":
        ses["after_unknown"] = 0
    elif mutation == "unknown":
        ses["after_unknown"] = True
    elif mutation == "extra-change":
        review["output_changes"]["other"] = copy.deepcopy(ses)
    elif mutation == "missing-existing":
        del review["output_changes"]["synthetic"]
    elif mutation == "equal-but-wrong-before-after":
        review["output_changes"]["synthetic"].update(before="wrong", after="wrong")
    else:
        review["prior_state"]["values"]["outputs"]["synthetic"]["value"] = "wrong"
    with pytest.raises((ValueError, KeyError), match="OutputsChanged|before|after|actions"):
        contract.audit_plan(review, fixture.state, fixture.values, ACCOUNT, REGION)


@pytest.mark.parametrize(
    "mask", [True, 0, 1, None, "false", {"tags": {"unexpected": True}}, {"tags": None}]
)
def test_unknown_or_malformed_masks_remain_rejected(tools, fixture, mask):
    _, contract, _ = tools
    review = real_shape(contract, fixture)
    review["resource_changes"][-1]["change"]["after_unknown"] = mask
    with pytest.raises(ValueError, match="UnapprovedChange"):
        contract.audit_plan(review, fixture.state, fixture.values, ACCOUNT, REGION)


@pytest.fixture
def recovery_harness(tools, recovery_tools, fixture, monkeypatch, tmp_path):
    normal, contract, _ = tools
    recovery, pure = recovery_tools
    private = tmp_path / "home/.p4-artifacts"
    private.mkdir(parents=True)
    original = private / "original"
    original.mkdir()
    (original / "configuration").mkdir()
    (original / "data").mkdir()
    source = private.parent
    files = {"main.tf": b"terraform {}", ".terraform.lock.hcl": b"synthetic-provider-lock"}
    plan_approval = approval_for(contract, fixture, private)
    plan_approval["provider_lock_sha256"] = contract.hashed(files[".terraform.lock.hcl"])
    plan_approval["expires_at"] = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    snapshot = copy.deepcopy(fixture.snapshot)
    snapshot["versions_sha256"] = contract.hashed(contract.encoded(snapshot["versions"]))
    artifacts = {
        "bootstrap.tfplan": b"synthetic-saved-plan",
        "inputs.private.json": Path(plan_approval["inputs_path"]).read_bytes(),
        "plan-approval.private.json": contract.encoded(plan_approval),
        "snapshot-before.private.json": contract.encoded(snapshot),
        "plan-failure.private.json": contract.encoded(
            {"status": "READ_ONLY_DIAGNOSIS_REQUIRED", "retry_allowed": False, "diagnosis": {}}
        ),
        "backend.private.hcl": normal.backend_hcl(plan_approval["backend"]).encode(),
        "terraform.rc": b"provider_installation { direct {} }\n",
        "empty-aws-config": b"",
        "data/terraform.tfstate": contract.encoded(
            {"backend": {"type": "s3", "config": plan_approval["backend"]}}
        ),
        "configuration/backend.tf": normal.S3_BACKEND.encode(),
        **{"configuration/" + k: v for k, v in files.items()},
    }
    for stage in pure.STAGES:
        artifacts[stage + ".stderr.private.log"] = b""
        artifacts[stage + ".stdout.private.log"] = b"synthetic successful stage"
    artifacts["plan-version.stdout.private.log"] = contract.encoded({"terraform_version": "1.14.9"})
    artifacts["show.stdout.private.log"] = contract.encoded(real_shape(contract, fixture))
    for name, raw in artifacts.items():
        (original / name).write_bytes(raw)
    namespace = contract.hashed(contract.encoded(plan_approval["backend"]))
    oldclaim = private / "bootstrap-maintenance-ledger" / namespace
    oldclaim.mkdir(parents=True)
    journal = {
        "run_path": str(original),
        "approval_sha256": contract.hashed(artifacts["plan-approval.private.json"]),
        "state_identity": snapshot["identity"],
        "started_at": datetime.now(UTC).isoformat(),
    }
    journal_raw = contract.encoded(journal)
    (oldclaim / "plan-started.private.json").write_bytes(journal_raw)
    actor_path = private / "original-actor.json"
    actor_raw = contract.encoded(
        {
            "source_sha": plan_approval["source_sha"],
            "source_files": {k: contract.hashed(v) for k, v in files.items()},
            "actor": {"role_arn": plan_approval["principal_role_arn"]},
            "aws_writes": 0,
            "snapshot": snapshot,
        }
    )
    actor_path.write_bytes(actor_raw)
    value = {
        "schema_version": 1,
        "kind": "p4-bootstrap-audit-recovery",
        "approved": True,
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "account_id": ACCOUNT,
        "region": REGION,
        "original_source_sha": "a" * 40,
        "audit_source_sha": "c" * 40,
        "original_run_path": str(original),
        "recovery_run_path": str(private / "recovered"),
        "original_approval_sha256": journal["approval_sha256"],
        "original_journal_sha256": contract.hashed(journal_raw),
        "original_actor_path": str(actor_path),
        "original_actor_sha256": contract.hashed(actor_raw),
        "plan_sha256": contract.hashed(artifacts["bootstrap.tfplan"]),
        "artifact_hashes": {k: contract.hashed(v) for k, v in artifacts.items()},
        "configuration_hashes": {k: contract.hashed(v) for k, v in files.items()},
        "audit_code_hashes": {k: "d" * 64 for k in pure.AUDIT_FILES},
        "state_identity": snapshot["identity"],
        "state_versions": snapshot["versions"],
        "backend": snapshot["backend"],
        "workspace": "default",
        "principal_role_arn": plan_approval["principal_role_arn"],
        "aws_writes_approved": False,
        "cost_cap_usd": "0.05",
    }
    request = private / "recovery-request.json"
    request.write_bytes(contract.encoded(value))
    calls = []
    actor = {"role_arn": value["principal_role_arn"]}
    reader = SimpleNamespace(
        actor=lambda arn: copy.deepcopy(actor),
        snapshot=lambda: copy.deepcopy(snapshot),
        verify_resources=lambda *args: calls.append("resource-readback"),
        operations=["GetObject"],
        diagnose=lambda: {"repair_attempted": False},
    )
    monkeypatch.setattr(normal, "home_repository", lambda root: source)
    monkeypatch.setattr(normal, "protect", lambda path: None)
    monkeypatch.setattr(recovery, "account_settings", lambda root: (ACCOUNT, REGION))
    monkeypatch.setattr(recovery, "reader_for", lambda *args: reader)
    identity = {"source_sha": value["audit_source_sha"], "code_hashes": value["audit_code_hashes"]}
    monkeypatch.setattr(recovery, "code_identity", lambda *args: (identity, files))

    def forbidden(*args, **kwargs):
        pytest.fail("Recovery must never invoke Terraform, Plan, Apply or AWS write")

    monkeypatch.setattr(normal, "terraform", forbidden)
    return SimpleNamespace(
        normal=normal,
        contract=contract,
        recovery=recovery,
        pure=pure,
        private=private,
        source=source,
        original=original,
        oldclaim=oldclaim,
        files=files,
        artifacts=artifacts,
        journal_raw=journal_raw,
        actor_raw=actor_raw,
        value=value,
        request=request,
        snapshot=snapshot,
        actor=actor,
        identity=identity,
        calls=calls,
        reader=reader,
        env={"P4_BOOTSTRAP_AUDIT_RECOVERY_READY": "true"},
    )


def recover(h):
    return h.recovery.execute(
        h.request, h.contract.hashed(h.request.read_bytes()), repository=h.source, environment=h.env
    )


def rewritten_request(h):
    h.request.write_bytes(h.contract.encoded(h.value))


def recovered_apply_inputs(h):
    recovery = Path(h.value["recovery_run_path"])
    binding_raw = (recovery / "binding.private.json").read_bytes()
    recovery_raw = (recovery / "recovery-approval.private.json").read_bytes()
    started_raw = (recovery / "recovery-started.private.json").read_bytes()
    completed_raw = (recovery / "recovery-completed.private.json").read_bytes()
    apply_value = {
        "schema_version": 1,
        "kind": "p4-bootstrap-recovered-apply",
        "approved": True,
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "plan_sha256": h.value["plan_sha256"],
        "binding_sha256": h.contract.hashed(binding_raw),
        "recovery_approval_sha256": h.contract.hashed(recovery_raw),
        **{
            k: h.value[k]
            for k in (
                "original_source_sha",
                "audit_source_sha",
                "principal_role_arn",
                "original_run_path",
                "recovery_run_path",
            )
        },
        "normal_lockfile_writes_approved": True,
        "canonical_state_writes_approved": True,
        "iam_policy_updates_approved": True,
        "cost_cap_usd": "0.05",
    }
    return [
        apply_value,
        binding_raw,
        recovery_raw,
        started_raw,
        completed_raw,
        copy.deepcopy(h.artifacts),
        h.journal_raw,
        h.actor_raw,
        h.files,
        copy.deepcopy(h.snapshot),
        h.actor,
        h.identity,
    ]


def test_recovery_preserves_old_plan_logs_and_failed_journal(recovery_harness):
    h = recovery_harness
    before = {str(p): p.read_bytes() for p in h.original.rglob("*") if p.is_file()}
    journal_before = (h.oldclaim / "plan-started.private.json").read_bytes()
    assert recover(h)["status"] == "BOOTSTRAP_AUDIT_RECOVERED_WAITING_APPLY_APPROVAL"
    assert before == {str(p): p.read_bytes() for p in h.original.rglob("*") if p.is_file()}
    assert (h.oldclaim / "plan-started.private.json").read_bytes() == journal_before
    assert {p.name for p in h.oldclaim.iterdir()} == {"plan-started.private.json"}
    assert h.calls == ["resource-readback", "resource-readback"]
    args = recovered_apply_inputs(h)
    assert h.pure.validate_recovered_apply(*args)["update"] == 2
    # The future integration path also validates without executing an Apply.
    apply_path = h.private / "future-apply.json"
    apply_path.write_bytes(h.contract.encoded(args[0]))
    assert (
        h.recovery.verify_apply(
            apply_path,
            h.contract.hashed(apply_path.read_bytes()),
            repository=h.source,
            environment={},
        )["no_op"]
        == 30
    )


@pytest.mark.parametrize(
    "tamper",
    [
        "plan",
        "original-approval",
        "journal",
        "missing-journal",
        "source",
        "state-lineage",
        "state-version",
        "live-version-inventory",
        "actor",
        "audit-source",
        "original-failure",
        "configuration",
        "review",
        "provider-lock",
        "completed-old-journal",
    ],
)
def test_recovery_rejects_tampered_or_mismatched_original(recovery_harness, monkeypatch, tamper):
    h = recovery_harness
    if tamper == "plan":
        (h.original / "bootstrap.tfplan").write_bytes(b"changed")
    elif tamper == "original-approval":
        (h.original / "plan-approval.private.json").write_bytes(b"{}")
    elif tamper == "journal":
        (h.oldclaim / "plan-started.private.json").write_bytes(b"{}")
    elif tamper == "missing-journal":
        (h.oldclaim / "plan-started.private.json").unlink()
    elif tamper == "source":
        h.value["original_source_sha"] = "f" * 40
        rewritten_request(h)
    elif tamper in ("state-lineage", "state-version"):
        h.value["state_identity"][
            {"state-lineage": "lineage", "state-version": "version_id"}[tamper]
        ] = "unexpected"
        rewritten_request(h)
    elif tamper == "live-version-inventory":
        h.snapshot["versions"].append({"kind": "Versions", "version_id": "v2", "size": 100})
    elif tamper == "actor":
        h.actor["role_arn"] = "unexpected"
    elif tamper == "audit-source":
        monkeypatch.setattr(
            h.recovery,
            "code_identity",
            lambda *args: (_ for _ in ()).throw(ValueError("RecoveryAuditRevisionMismatch")),
        )
    elif tamper == "original-failure":
        (h.original / "plan-failure.private.json").write_bytes(b"{}")
    elif tamper == "configuration":
        (h.original / "configuration/main.tf").write_bytes(b"changed")
    elif tamper == "review":
        (h.original / "show.stdout.private.log").write_bytes(b"{}")
    elif tamper == "provider-lock":
        (h.original / "configuration/.terraform.lock.hcl").write_bytes(b"changed")
    else:
        (h.oldclaim / "plan-completed.private.json").write_bytes(b"{}")
    with pytest.raises((ValueError, FileNotFoundError)):
        recover(h)
    assert not (Path(h.value["recovery_run_path"]) / "binding.private.json").exists()


def test_recovery_one_attempt_survives_failure_and_run_switch(recovery_harness, monkeypatch):
    h = recovery_harness
    monkeypatch.setattr(
        h.reader, "snapshot", lambda: (_ for _ in ()).throw(ValueError("SyntheticReadFailure"))
    )
    with pytest.raises(ValueError):
        recover(h)
    h.value["recovery_run_path"] = str(h.private / "different-recovery-run")
    rewritten_request(h)
    with pytest.raises(ValueError, match="AlreadyAttempted"):
        recover(h)
    assert not (h.private / "different-recovery-run").exists()
    failed = list(
        (h.private / "bootstrap-audit-recovery-ledger").rglob("recovery-failed.private.json")
    )
    assert len(failed) == 1 and json.loads(failed[0].read_bytes())["retry_allowed"] is False


def test_successful_recovery_is_not_repeatable(recovery_harness):
    h = recovery_harness
    recover(h)
    with pytest.raises(ValueError, match="AlreadyAttempted"):
        recover(h)


@pytest.mark.parametrize(
    "gate", ["approval-false", "gate-missing", "write-permission", "hidden-env", "same-source"]
)
def test_recovery_requires_its_own_explicit_readonly_approval(recovery_harness, gate):
    h = recovery_harness
    if gate == "approval-false":
        h.value["approved"] = False
    elif gate == "gate-missing":
        h.env = {}
    elif gate == "write-permission":
        h.value["aws_writes_approved"] = True
    elif gate == "hidden-env":
        h.env["TF_CLI_ARGS"] = "untrusted"
    else:
        h.value["audit_source_sha"] = h.value["original_source_sha"]
    rewritten_request(h)
    with pytest.raises(ValueError):
        recover(h)
    assert not (h.private / "bootstrap-audit-recovery-ledger").exists()


@pytest.mark.parametrize(
    "tamper",
    [
        "plan",
        "original-approval",
        "journal",
        "snapshot",
        "source",
        "audit-code",
        "binding",
        "completed",
        "started",
        "state-live",
        "actor",
        "inputs",
        "apply-approval-false",
        "apply-already-started",
        "write-approval-false",
    ],
)
def test_future_apply_revalidates_both_revisions_and_every_artifact(recovery_harness, tamper):
    h = recovery_harness
    recover(h)
    args = recovered_apply_inputs(h)
    options = {}
    if tamper == "plan":
        args[5]["bootstrap.tfplan"] = b"changed"
    elif tamper == "original-approval":
        args[5]["plan-approval.private.json"] = b"{}"
    elif tamper == "journal":
        args[6] = b"{}"
    elif tamper == "snapshot":
        args[5]["snapshot-before.private.json"] = b"{}"
    elif tamper == "source":
        args[0]["original_source_sha"] = "e" * 40
    elif tamper == "audit-code":
        args[11] = dict(args[11], source_sha="e" * 40)
    elif tamper == "binding":
        args[1] = b"{}"
    elif tamper == "completed":
        args[4] = b"{}"
    elif tamper == "started":
        args[3] = b"{}"
    elif tamper == "state-live":
        args[9]["identity"]["lineage"] = "new"
    elif tamper == "actor":
        args[10] = {"role_arn": "unexpected"}
    elif tamper == "inputs":
        args[5]["inputs.private.json"] = b"{}"
    elif tamper == "apply-approval-false":
        args[0]["approved"] = False
    elif tamper == "apply-already-started":
        options["apply_already_started"] = True
    else:
        args[0]["canonical_state_writes_approved"] = False
    with pytest.raises((ValueError, KeyError)):
        h.pure.validate_recovered_apply(*args, **options)


def test_old_normal_apply_cannot_accept_recovery_binding(recovery_harness):
    h = recovery_harness
    recover(h)
    assert not (h.original / "binding.private.json").exists()
    with pytest.raises((ValueError, FileNotFoundError)):
        h.normal.validate_saved(h.original, {"run_path": str(h.original)}, h.files, {}, h.oldclaim)


def test_cli_has_no_apply_plan_or_destroy(recovery_tools, monkeypatch):
    recovery, _ = recovery_tools
    for operation in ("plan", "apply", "destroy", "force-unlock"):
        monkeypatch.setattr("sys.argv", ["recovery", operation])
        with pytest.raises(SystemExit) as error:
            recovery.main()
        assert error.value.code == 2


@pytest.mark.parametrize(
    "mutation",
    [
        "trust",
        "boundary",
        "oidc",
        "bucket",
        "artifact-role",
        "test-role",
        "create",
        "replace",
        "destroy",
        "drift",
        "deferred",
    ],
)
def test_corrected_audit_still_rejects_unapproved_iam_and_resources(tools, fixture, mutation):
    _, contract, _ = tools
    review = real_shape(contract, fixture)
    if mutation in ("drift", "deferred"):
        review[{"drift": "resource_drift", "deferred": "deferred_changes"}[mutation]] = [{}]
    else:
        address = {
            "trust": 'aws_iam_role.ci["deploy"]',
            "boundary": 'aws_iam_role.ci["plan"]',
            "oidc": "aws_iam_openid_connect_provider.github[0]",
            "artifact-role": 'aws_iam_role.ci["artifact"]',
            "test-role": 'aws_iam_role.ci["test"]',
        }.get(mutation, "aws_s3_bucket.synthetic0")
        row = next(x for x in review["resource_changes"] if x["address"] == address)
        if mutation in ("create", "replace", "destroy"):
            row["change"]["actions"] = {
                "create": ["create"],
                "replace": ["delete", "create"],
                "destroy": ["delete"],
            }[mutation]
        else:
            field = "permissions_boundary" if mutation == "boundary" else "unapproved"
            row["change"]["after"][field] = "changed"
    with pytest.raises(ValueError):
        contract.audit_plan(review, fixture.state, fixture.values, ACCOUNT, REGION)


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "head",
        "remote",
        "branch",
        "dirty",
        "repository",
        "working-file",
        "loaded-module",
        "manifest",
        "terraform-config",
    ],
)
def test_git_code_identity_checks_original_and_new_revisions(
    recovery_harness, monkeypatch, tmp_path, mutation
):
    h = recovery_harness
    real_identity = importlib.reload(h.recovery).code_identity
    repository = Path(h.recovery.__file__).resolve().parents[3]
    raw_files = {name: (repository / name).read_bytes() for name in h.pure.AUDIT_FILES}
    h.value["audit_code_hashes"] = {k: h.contract.hashed(v) for k, v in raw_files.items()}
    if mutation == "manifest":
        h.value["audit_code_hashes"][h.pure.AUDIT_FILES[0]] = "f" * 64
    if mutation == "loaded-module":
        bad = tmp_path / "fake.py"
        bad.write_bytes(b"changed")
        monkeypatch.setitem(
            h.recovery.sys.modules, "maintenance_contract", SimpleNamespace(__file__=str(bad))
        )

    def git(root, *args):
        if args[0] == "rev-parse":
            return ("f" * 40 if mutation == "head" else "c" * 40).encode()
        if args[0] == "status":
            return b" M changed" if mutation == "dirty" else b""
        if args[0] == "branch":
            return b"feature" if mutation == "branch" else b"main"
        if args[0] == "ls-remote":
            return (("f" * 40 if mutation == "remote" else "c" * 40) + "\trefs/heads/main").encode()
        if args[0] == "config":
            return (
                b"https://example.invalid/other"
                if mutation == "repository"
                else b"https://github.com/yonegen0/ai_interview.git"
            )
        name = args[1].split(":", 1)[1]
        return raw_files[name] + (b"# changed" if mutation == "working-file" else b"")

    monkeypatch.setattr(h.normal, "git", git)
    monkeypatch.setattr(
        h.normal,
        "configuration_files",
        lambda root, sha, lock: dict(
            h.files,
            **(
                {"main.tf": b"changed"}
                if mutation == "terraform-config" and sha == "c" * 40
                else {}
            ),
        ),
    )
    if mutation == "none":
        identity, files = real_identity(repository, h.value)
        assert identity["source_sha"] == "c" * 40 and files == h.files
    else:
        with pytest.raises(ValueError):
            real_identity(repository, h.value)


@pytest.mark.parametrize("path", ["same", "inside-original", "ancestor", "outside"])
def test_recovery_output_cannot_overlap_or_escape_original(recovery_harness, path):
    h = recovery_harness
    h.value["recovery_run_path"] = str(
        {
            "same": h.original,
            "inside-original": h.original / "nested",
            "ancestor": h.private,
            "outside": h.private.parent / "outside",
        }[path]
    )
    rewritten_request(h)
    with pytest.raises(ValueError):
        recover(h)


def test_expired_original_approval_is_validated_at_original_attempt(recovery_harness):
    h = recovery_harness
    old = json.loads(h.artifacts["plan-approval.private.json"])
    old["expires_at"] = (datetime.now(UTC) - timedelta(days=1) + timedelta(hours=1)).isoformat()
    h.artifacts["plan-approval.private.json"] = h.contract.encoded(old)
    h.value["artifact_hashes"]["plan-approval.private.json"] = h.contract.hashed(
        h.artifacts["plan-approval.private.json"]
    )
    h.value["original_approval_sha256"] = h.value["artifact_hashes"]["plan-approval.private.json"]
    journal = json.loads(h.journal_raw)
    journal["started_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    journal["approval_sha256"] = h.value["original_approval_sha256"]
    h.journal_raw = h.contract.encoded(journal)
    h.value["original_journal_sha256"] = h.contract.hashed(h.journal_raw)
    assert (
        h.pure.validate_bundle(h.value, h.artifacts, h.journal_raw, h.actor_raw, h.files)[
            "summary"
        ]["no_op"]
        == 30
    )
