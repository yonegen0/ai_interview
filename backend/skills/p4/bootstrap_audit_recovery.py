"""Separately approved read-only audit recovery. No Terraform or Apply entry point."""

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import bootstrap_maintenance as normal
from bootstrap_state import bootstrap_lock, private_path
from deployment_guards import approved_json
from maintenance_aws import BootstrapAWS
from maintenance_contract import backend, encoded, hashed, require
from recovery_contract import (
    ARTIFACTS,
    AUDIT_FILES,
    check_live,
    make_binding,
    validate_bundle,
    validate_recovered_apply,
    validate_recovery_approval,
)

from interview_backend.deployment import (
    account_settings,
    checked_session,
    read_local_settings,
)

PROJECT = Path(__file__).resolve().parents[3]


def code_identity(root, value):
    """The new full Git revision and every executing audit dependency are explicit trust anchors."""
    sha = normal.git(root, "rev-parse", "HEAD").decode().strip()
    require(sha == value["audit_source_sha"], "RecoveryAuditRevisionMismatch")
    require(
        not normal.git(root, "status", "--porcelain=v1", "--untracked-files=all").strip()
        and normal.git(root, "branch", "--show-current").decode().strip() == "main"
        and normal.git(root, "ls-remote", "origin", "refs/heads/main").decode().split()[0] == sha,
        "RecoveryCleanRemoteMainRequired",
    )
    require(
        normal.git(root, "config", "--get", "remote.origin.url").decode().strip()
        in {
            "https://github.com/yonegen0/ai_interview.git",
            "https://github.com/yonegen0/ai_interview",
            "git@github.com:yonegen0/ai_interview.git",
        },
        "RecoveryRepositoryMismatch",
    )
    hashes = {}
    for name in AUDIT_FILES:
        raw = normal.git(root, "show", sha + ":" + name)
        require(
            (root / name).read_bytes().replace(b"\r\n", b"\n") == raw.replace(b"\r\n", b"\n"),
            "RecoveryAuditWorkingCopyChanged",
        )
        module_name = (
            "interview_backend.deployment" if name.startswith("backend/src/") else Path(name).stem
        )
        module = sys.modules.get(module_name)
        if module is None and module_name == "bootstrap_audit_recovery":
            module = sys.modules.get("__main__")
        require(
            module is not None
            and Path(module.__file__).read_bytes().replace(b"\r\n", b"\n")
            == raw.replace(b"\r\n", b"\n"),
            "RecoveryLoadedAuditCodeChanged",
        )
        hashes[name] = hashed(raw)
    require(hashes == value["audit_code_hashes"], "RecoveryAuditCodeManifestMismatch")
    # The old configuration is read at its unchanged revision; no descriptor rebinding.
    original = json.loads(
        private_path(
            Path(value["original_run_path"]) / "plan-approval.private.json",
            normal.home_repository(root) / ".p4-artifacts",
        ).read_bytes()
    )
    files = normal.configuration_files(
        root, value["original_source_sha"], original["provider_lock_sha256"]
    )
    require(
        files == normal.configuration_files(root, sha, original["provider_lock_sha256"]),
        "RecoveryTerraformConfigurationRevisionChanged",
    )
    return {"source_sha": sha, "code_hashes": hashes}, files


def paths(root, value, *, local_lock_held=False):
    private = normal.home_repository(root) / ".p4-artifacts"
    original = private_path(value["original_run_path"], private)
    recovery = private_path(value["recovery_run_path"], private)
    require(
        not recovery.is_relative_to(original)
        and not original.is_relative_to(recovery)
        and recovery.parent.is_dir(),
        "RecoverySeparateRunRequired",
    )
    namespace = hashed(encoded(backend(value["account_id"], value["region"])))
    original_claim = private_path(
        original.parent / "bootstrap-maintenance-ledger" / namespace, private
    )
    require(
        {p.name for p in original_claim.iterdir()} == {"plan-started.private.json"}
        and not (original / "binding.private.json").exists()
        and (
            not (original.parent / "bootstrap-operation.lock").exists()
            or local_lock_held
            and original.parent == private
        ),
        "RecoveryOriginalAttemptNotStopped",
    )
    ledger = private_path(private / "bootstrap-audit-recovery-ledger", private)
    claim = private_path(ledger / namespace, private)
    return private, original, recovery, original_claim, ledger, claim


def bundle_from_disk(root, value, files, *, local_lock_held=False):
    private, original, _, original_claim, _, _ = paths(root, value, local_lock_held=local_lock_held)
    required = (
        ARTIFACTS | {"configuration/" + name for name in files} | {"configuration/backend.tf"}
    )
    require(set(value["artifact_hashes"]) == required, "RecoveryArtifactManifest")
    artifacts = {name: private_path(original / name, original).read_bytes() for name in required}
    journal = private_path(original_claim / "plan-started.private.json", private).read_bytes()
    actor = private_path(value["original_actor_path"], private).read_bytes()
    validated = validate_bundle(value, artifacts, journal, actor, files)
    require(
        normal.load_evidence(validated["original"], private) == validated["inputs"],
        "RecoveryAdoptionReceiptInputsChanged",
    )
    normal.check_configuration(original, files)
    normal.check_backend(original, value["backend"])
    return validated, artifacts, journal, actor


def read_environment(root, environment):
    parent = dict(os.environ if environment is None else environment)
    require(
        not any(k.startswith(("TF_", "TERRAFORM_", "AWS_ENDPOINT_URL")) for k in parent)
        and parent.get("GITHUB_ACTIONS") != "true"
        and parent.get("CI", "").lower() != "true",
        "RecoveryLocalUnmodifiedEnvironmentRequired",
    )
    private = normal.home_repository(root) / ".p4-artifacts"
    account, region = account_settings(private.parent)
    require(region == "ap-northeast-1", "RecoveryAccountRegion")
    return parent, private, account, region


def reader_for(private, account, region, parent):
    session = checked_session(
        account,
        region,
        environment=dict(parent, AWS_PROFILE=read_local_settings(private.parent)["AWS_PROFILE"]),
    )
    return BootstrapAWS(session, account, region)


def execute(approval_path, approval_sha, *, repository=PROJECT, environment=None):
    root = Path(repository).resolve()
    parent, private, account, region = read_environment(root, environment)
    raw, value = approved_json(approval_path, approval_sha, private)
    validate_recovery_approval(value)
    require(
        value["approved"] is True and parent.get("P4_BOOTSTRAP_AUDIT_RECOVERY_READY") == "true",
        "RecoverySeparateExplicitApprovalRequired",
    )
    require((account, region) == (value["account_id"], value["region"]), "RecoveryAccountRegion")
    identity, files = code_identity(root, value)
    _, original, recovery, _, ledger, claim = paths(root, value)
    require(not recovery.exists() and not claim.exists(), "RecoveryAlreadyAttempted")
    require(not (private / "bootstrap-operation.lock").exists(), "RecoveryOperationLocked")
    reader = None
    with bootstrap_lock(private):
        require(not claim.exists() and not recovery.exists(), "RecoveryAlreadyAttempted")
        if not ledger.exists():
            normal.secure_directory(ledger)
        normal.secure_directory(claim)
        started = {
            "recovery_approval_sha256": approval_sha,
            "original_run_path": str(original),
            "recovery_run_path": str(recovery),
            "plan_sha256": value["plan_sha256"],
            "started_at": datetime.now(UTC).isoformat(),
        }
        started_raw = encoded(started)
        normal.write_bytes(claim / "recovery-started.private.json", started_raw)
        try:
            normal.secure_directory(recovery)
            normal.write_bytes(recovery / "recovery-started.private.json", started_raw)
            normal.write_bytes(recovery / "recovery-approval.private.json", raw)
            bundle, artifacts, _, _ = bundle_from_disk(root, value, files, local_lock_held=True)
            reader = reader_for(private, account, region, parent)
            actor = reader.actor(value["principal_role_arn"])
            before = reader.snapshot()
            check_live(bundle, before, actor)
            reader.verify_resources(before["state"], bundle["inputs"])
            after = reader.snapshot()
            check_live(bundle, after, reader.actor(value["principal_role_arn"]))
            reader.verify_resources(after["state"], bundle["inputs"])
            # Re-read every original artifact and Git anchor immediately before completion.
            repeated, _, _, _ = bundle_from_disk(root, value, files, local_lock_held=True)
            require(encoded(repeated) == encoded(bundle), "RecoveryEvidenceChangedDuringAudit")
            require(code_identity(root, value)[0] == identity, "RecoveryAuditRevisionChanged")
            binding = make_binding(value, approval_sha, bundle, hashed(started_raw))
            normal.write_bytes(
                recovery / "review.private.json", artifacts["show.stdout.private.log"]
            )
            normal.write_json(
                recovery / "readback.private.json",
                {
                    "before": before,
                    "after": after,
                    "actor": actor,
                    "operations": reader.operations,
                    "aws_writes": 0,
                },
            )
            normal.write_json(recovery / "binding.private.json", binding)
            completed = {
                "recovery_run_path": str(recovery),
                "binding_sha256": hashed((recovery / "binding.private.json").read_bytes()),
                "plan_sha256": value["plan_sha256"],
                "started_sha256": hashed(started_raw),
            }
            normal.write_json(claim / "recovery-completed.private.json", completed)
            normal.write_json(recovery / "recovery-completed.private.json", completed)
            return {
                "status": "BOOTSTRAP_AUDIT_RECOVERED_WAITING_APPLY_APPROVAL",
                "plan_sha256": value["plan_sha256"],
                "binding_sha256": completed["binding_sha256"],
                "aws_writes": 0,
                **bundle["summary"],
            }
        except Exception as error:
            diagnosis = {"repair_attempted": False}
            if reader is not None:
                try:
                    diagnosis = reader.diagnose()
                except Exception:
                    diagnosis = {"read_only_diagnosis_available": False, "repair_attempted": False}
            code = str(error)
            normal.write_json(
                claim / "recovery-failed.private.json",
                {
                    "status": "BOOTSTRAP_AUDIT_RECOVERY_STOPPED",
                    "retry_allowed": False,
                    "error_class": type(error).__name__,
                    "error_code": code if re.fullmatch(r"[A-Za-z]+", code) else "PrivateError",
                    "diagnosis": diagnosis,
                },
            )
            raise


def verify_apply(approval_path, approval_sha, *, repository=PROJECT, environment=None):
    """Read-only integration gate for a future separate Apply controller, never an Apply."""
    root = Path(repository).resolve()
    parent, private, account, region = read_environment(root, environment)
    _, apply_value = approved_json(approval_path, approval_sha, private)
    recovery = private_path(apply_value["recovery_run_path"], private)
    recovery_raw = (recovery / "recovery-approval.private.json").read_bytes()
    value = json.loads(recovery_raw)
    require((account, region) == (value["account_id"], value["region"]), "RecoveryAccountRegion")
    identity, files = code_identity(root, value)
    _, _, _, _, _, claim = paths(root, value)
    require(not (claim / "recovery-failed.private.json").exists(), "RecoveryFailedAttempt")
    started = private_path(claim / "recovery-started.private.json", private).read_bytes()
    completed = private_path(claim / "recovery-completed.private.json", private).read_bytes()
    require(
        started == (recovery / "recovery-started.private.json").read_bytes()
        and completed == (recovery / "recovery-completed.private.json").read_bytes(),
        "RecoveryJournalCopiesChanged",
    )
    bundle, artifacts, journal, original_actor = bundle_from_disk(root, value, files)
    require(
        (recovery / "review.private.json").read_bytes() == artifacts["show.stdout.private.log"],
        "RecoveryCopiedReviewChanged",
    )
    binding_raw = (recovery / "binding.private.json").read_bytes()
    # Validate authorization and all historical bindings before any paid/live AWS read.
    # Historical snapshot acceptance here does not replace the fresh readback below.
    validate_recovered_apply(
        apply_value,
        binding_raw,
        recovery_raw,
        started,
        completed,
        artifacts,
        journal,
        original_actor,
        files,
        bundle["snapshot"],
        json.loads(original_actor)["actor"],
        identity,
        apply_already_started=(claim / "apply-started.private.json").exists(),
    )
    reader = reader_for(private, account, region, parent)
    actor = reader.actor(value["principal_role_arn"])
    snapshot = reader.snapshot()
    reader.verify_resources(snapshot["state"], bundle["inputs"])
    return validate_recovered_apply(
        apply_value,
        (recovery / "binding.private.json").read_bytes(),
        recovery_raw,
        started,
        completed,
        artifacts,
        journal,
        original_actor,
        files,
        snapshot,
        actor,
        identity,
        apply_already_started=(claim / "apply-started.private.json").exists(),
    )


def main():
    parser = argparse.ArgumentParser()
    # Deliberately no plan/apply/destroy/repair/force-unlock subcommands.
    parser.add_argument("operation", choices=("recover",))
    parser.add_argument("--approval", required=True)
    parser.add_argument("--approval-sha256", required=True)
    args = parser.parse_args()
    try:
        result = execute(args.approval, args.approval_sha256)
    except Exception:
        print(
            json.dumps({"status": "BOOTSTRAP_AUDIT_RECOVERY_STOPPED", "retry_allowed": False}),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
