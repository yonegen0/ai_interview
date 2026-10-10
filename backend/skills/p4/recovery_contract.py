"""Pure, hash-bound recovery of a failed audit; never plan, apply or mutate evidence."""

import json
import re
from datetime import UTC, datetime

from maintenance_contract import (
    audit_plan,
    backend,
    check_snapshot,
    encoded,
    hashed,
    require,
    validate_approval,
    validate_inputs,
)

AUDIT_FILES = (
    "backend/skills/p4/bootstrap_audit_recovery.py",
    "backend/skills/p4/recovery_contract.py",
    "backend/skills/p4/maintenance_contract.py",
    "backend/skills/p4/bootstrap_maintenance.py",
    "backend/skills/p4/maintenance_aws.py",
    "backend/skills/p4/bootstrap_state.py",
    "backend/skills/p4/bootstrap_contract.py",
    "backend/skills/p4/deployment_guards.py",
    "backend/skills/p4/offline_terraform.py",
    "backend/skills/p4/recovery_migration.py",
    "backend/src/interview_backend/deployment.py",
)
STAGES = ("plan-version", "init", "post-init-pull", "plan", "show")
ARTIFACTS = frozenset(
    {
        "bootstrap.tfplan",
        "inputs.private.json",
        "plan-approval.private.json",
        "snapshot-before.private.json",
        "plan-failure.private.json",
        "backend.private.hcl",
        "terraform.rc",
        "empty-aws-config",
        "data/terraform.tfstate",
    }
    | {
        stage + suffix
        for stage in STAGES
        for suffix in (".stdout.private.log", ".stderr.private.log")
    }
)
RECOVERY_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "approved",
        "expires_at",
        "account_id",
        "region",
        "original_source_sha",
        "audit_source_sha",
        "original_run_path",
        "recovery_run_path",
        "original_approval_sha256",
        "original_journal_sha256",
        "original_actor_path",
        "original_actor_sha256",
        "plan_sha256",
        "artifact_hashes",
        "configuration_hashes",
        "audit_code_hashes",
        "state_identity",
        "state_versions",
        "backend",
        "workspace",
        "principal_role_arn",
        "aws_writes_approved",
        "cost_cap_usd",
    }
)


def fresh(value, now=None):
    expiry = datetime.fromisoformat(value["expires_at"])
    now = datetime.now(UTC) if now is None else now
    require(
        expiry.tzinfo is not None and 0 < (expiry - now).total_seconds() <= 86400,
        "RecoveryApprovalExpired",
    )


def digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def revision(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def validate_recovery_approval(value, now=None):
    require(
        set(value) == RECOVERY_FIELDS
        and value["schema_version"] == 1
        and value["kind"] == "p4-bootstrap-audit-recovery"
        and type(value["approved"]) is bool
        and value["aws_writes_approved"] is False
        and value["cost_cap_usd"] == "0.05",
        "RecoveryApprovalSchema",
    )
    require(
        revision(value["original_source_sha"])
        and revision(value["audit_source_sha"])
        and value["original_source_sha"] != value["audit_source_sha"],
        "RecoverySeparateRevisionsRequired",
    )
    require(
        value["region"] == "ap-northeast-1"
        and value["backend"] == backend(value["account_id"], value["region"])
        and value["workspace"] == "default",
        "RecoveryNamespaceMismatch",
    )
    require(
        set(value["audit_code_hashes"]) == set(AUDIT_FILES)
        and all(digest(v) for v in value["audit_code_hashes"].values()),
        "RecoveryAuditManifest",
    )
    require(
        all(
            digest(value[k])
            for k in (
                "original_approval_sha256",
                "original_journal_sha256",
                "original_actor_sha256",
                "plan_sha256",
            )
        )
        and all(digest(v) for v in value["artifact_hashes"].values())
        and all(digest(v) for v in value["configuration_hashes"].values()),
        "RecoveryArtifactDigest",
    )
    require(
        isinstance(value["state_versions"], list) and value["state_versions"],
        "RecoveryStateVersions",
    )
    fresh(value, now)


def validate_bundle(approval, artifacts, journal_raw, actor_raw, files):
    """The human-approved hash manifest anchors all historical evidence and Git blobs."""
    required = (
        ARTIFACTS | {"configuration/" + name for name in files} | {"configuration/backend.tf"}
    )
    require(
        set(artifacts) == set(approval["artifact_hashes"]) == required, "RecoveryArtifactManifest"
    )
    require(
        all(hashed(raw) == approval["artifact_hashes"][name] for name, raw in artifacts.items()),
        "RecoveryArtifactChanged",
    )
    require(
        hashed(journal_raw) == approval["original_journal_sha256"]
        and hashed(actor_raw) == approval["original_actor_sha256"],
        "RecoveryHistoricalEvidenceChanged",
    )
    require(
        approval["configuration_hashes"] == {k: hashed(v) for k, v in files.items()}
        and all(artifacts["configuration/" + k] == v for k, v in files.items()),
        "RecoveryOriginalGitConfigurationMismatch",
    )
    require(
        hashed(artifacts["bootstrap.tfplan"]) == approval["plan_sha256"]
        and hashed(artifacts["plan-approval.private.json"]) == approval["original_approval_sha256"],
        "RecoveryOriginalPlanOrApprovalMismatch",
    )
    original = json.loads(artifacts["plan-approval.private.json"])
    journal = json.loads(journal_raw)
    require(
        set(journal) == {"run_path", "approval_sha256", "state_identity", "started_at"}
        and journal["run_path"] == approval["original_run_path"]
        and journal["approval_sha256"] == approval["original_approval_sha256"]
        and journal["state_identity"] == approval["state_identity"],
        "RecoveryOriginalJournalMismatch",
    )
    started = datetime.fromisoformat(journal["started_at"])
    require(
        started.tzinfo is not None and started <= datetime.now(UTC), "RecoveryOriginalJournalTime"
    )
    # Historical approval is evaluated at the original attempt, never renewed or rewritten.
    validate_approval(original, "plan", approval["account_id"], approval["region"], now=started)
    require(
        original["approved"] is True
        and original["source_sha"] == approval["original_source_sha"]
        and original["state_identity"] == approval["state_identity"]
        and original["backend"] == approval["backend"]
        and original["workspace"] == approval["workspace"]
        and original["principal_role_arn"] == approval["principal_role_arn"]
        and original["provider_lock_sha256"] == hashed(files[".terraform.lock.hcl"]),
        "RecoveryOriginalApprovalMismatch",
    )
    historical_actor = json.loads(actor_raw)
    require(
        historical_actor["source_sha"] == approval["original_source_sha"]
        and historical_actor["source_files"] == approval["configuration_hashes"]
        and historical_actor["actor"]["role_arn"] == approval["principal_role_arn"]
        and historical_actor["aws_writes"] == 0,
        "RecoveryOriginalActorMismatch",
    )
    values = json.loads(artifacts["inputs.private.json"])
    require(
        hashed(artifacts["inputs.private.json"]) == original["inputs_sha256"],
        "RecoveryInputsMismatch",
    )
    snapshot = json.loads(artifacts["snapshot-before.private.json"])
    check_snapshot(snapshot, original)
    require(
        snapshot["versions"] == approval["state_versions"]
        and snapshot["versions_sha256"] == hashed(encoded(snapshot["versions"]))
        and historical_actor["snapshot"]["identity"] == approval["state_identity"]
        and historical_actor["snapshot"]["versions"] == approval["state_versions"],
        "RecoveryHistoricalStateVersionsMismatch",
    )
    validate_inputs(values, snapshot["state"], original["account_id"], original["region"])
    failure = json.loads(artifacts["plan-failure.private.json"])
    require(
        failure["status"] == "READ_ONLY_DIAGNOSIS_REQUIRED" and failure["retry_allowed"] is False,
        "RecoveryFailureEvidenceRequired",
    )
    require(
        all(artifacts[stage + ".stderr.private.log"] == b"" for stage in STAGES)
        and json.loads(artifacts["plan-version.stdout.private.log"])["terraform_version"]
        == "1.14.9",
        "RecoveryOriginalTerraformStages",
    )
    review = json.loads(artifacts["show.stdout.private.log"])
    summary = audit_plan(
        review, snapshot["state"], values, original["account_id"], original["region"]
    )
    return {"original": original, "snapshot": snapshot, "inputs": values, "summary": summary}


def check_live(bundle, snapshot, actor):
    check_snapshot(snapshot, bundle["original"])
    require(
        snapshot["versions"] == bundle["snapshot"]["versions"], "RecoveryLiveStateVersionsChanged"
    )
    require(
        actor["role_arn"] == bundle["original"]["principal_role_arn"], "RecoveryLiveActorMismatch"
    )


def make_binding(approval, approval_sha, bundle, started_sha):
    """Schema 2 cannot be mistaken for the normal schema 1 Plan completion."""
    return {
        "schema_version": 2,
        "kind": "p4-bootstrap-recovered-plan-binding",
        "original_source_sha": approval["original_source_sha"],
        "audit_source_sha": approval["audit_source_sha"],
        "audit_code_hashes": approval["audit_code_hashes"],
        "configuration_hashes": approval["configuration_hashes"],
        "original_run_path": approval["original_run_path"],
        "recovery_run_path": approval["recovery_run_path"],
        "original_approval_sha256": approval["original_approval_sha256"],
        "original_journal_sha256": approval["original_journal_sha256"],
        "original_actor_sha256": approval["original_actor_sha256"],
        "artifact_hashes": approval["artifact_hashes"],
        "recovery_approval_sha256": approval_sha,
        "recovery_started_sha256": started_sha,
        "plan_sha256": approval["plan_sha256"],
        "review_sha256": approval["artifact_hashes"]["show.stdout.private.log"],
        "inputs_sha256": bundle["original"]["inputs_sha256"],
        "provider_lock_sha256": bundle["original"]["provider_lock_sha256"],
        "state_identity": approval["state_identity"],
        "state_versions": approval["state_versions"],
        "backend": approval["backend"],
        "workspace": approval["workspace"],
        "principal_role_arn": approval["principal_role_arn"],
        "summary": bundle["summary"],
    }


def validate_recovered_apply(
    value,
    binding_raw,
    recovery_raw,
    started_raw,
    completed_raw,
    artifacts,
    journal_raw,
    actor_raw,
    files,
    snapshot,
    actor,
    audit_identity,
    *,
    apply_already_started=False,
):
    """Side-effect-free future Apply gate. This function cannot invoke Terraform/AWS."""
    fields = {
        "schema_version",
        "kind",
        "approved",
        "expires_at",
        "plan_sha256",
        "binding_sha256",
        "recovery_approval_sha256",
        "original_source_sha",
        "audit_source_sha",
        "principal_role_arn",
        "original_run_path",
        "recovery_run_path",
        "normal_lockfile_writes_approved",
        "canonical_state_writes_approved",
        "iam_policy_updates_approved",
        "cost_cap_usd",
    }
    require(
        set(value) == fields
        and value["schema_version"] == 1
        and value["kind"] == "p4-bootstrap-recovered-apply"
        and value["approved"] is True
        and value["normal_lockfile_writes_approved"] is True
        and value["canonical_state_writes_approved"] is True
        and value["iam_policy_updates_approved"] is True
        and value["cost_cap_usd"] == "0.05",
        "RecoverySeparateApplyApprovalRequired",
    )
    fresh(value)
    require(not apply_already_started, "RecoveryApplyAlreadyAttempted")
    require(
        hashed(binding_raw) == value["binding_sha256"]
        and hashed(recovery_raw) == value["recovery_approval_sha256"],
        "RecoveryApplyBindingChanged",
    )
    approval, started, completed = map(json.loads, (recovery_raw, started_raw, completed_raw))
    validate_recovery_approval(approval, now=datetime.fromisoformat(started["started_at"]))
    require(approval["approved"] is True, "RecoveryNeverApproved")
    require(
        started
        == {
            "recovery_approval_sha256": hashed(recovery_raw),
            "original_run_path": approval["original_run_path"],
            "recovery_run_path": approval["recovery_run_path"],
            "plan_sha256": approval["plan_sha256"],
            "started_at": started["started_at"],
        },
        "RecoveryStartedJournalChanged",
    )
    for key in (
        "original_source_sha",
        "audit_source_sha",
        "original_run_path",
        "recovery_run_path",
        "principal_role_arn",
        "plan_sha256",
    ):
        require(value[key] == approval[key], "RecoveryApplyTargetChanged")
    require(
        audit_identity
        == {
            "source_sha": approval["audit_source_sha"],
            "code_hashes": approval["audit_code_hashes"],
        },
        "RecoveryApplyAuditCodeChanged",
    )
    bundle = validate_bundle(approval, artifacts, journal_raw, actor_raw, files)
    check_live(bundle, snapshot, actor)
    expected = make_binding(approval, hashed(recovery_raw), bundle, hashed(started_raw))
    require(
        encoded(json.loads(binding_raw)) == encoded(expected), "RecoveryApplySemanticBindingChanged"
    )
    require(
        completed
        == {
            "recovery_run_path": approval["recovery_run_path"],
            "binding_sha256": hashed(binding_raw),
            "plan_sha256": approval["plan_sha256"],
            "started_sha256": hashed(started_raw),
        },
        "RecoveryCompletionJournalChanged",
    )
    return bundle["summary"]
