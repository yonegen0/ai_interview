"""Guarded CI dev Terraform plan/apply; no implicit credentials or input files.

Outputs stay in an explicitly selected private directory. Raw Terraform output is
never logged: saved plans can contain emails. CI transport is a separate boundary.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path

from cloud_toolchain import NEW_EXECUTION_TERRAFORM_VERSION as TF_VERSION
from plan_authorization import active_guard, required_guard
from standard_diagnostics import checkpoint

from interview_backend.deployment import (
    DeploymentError,
    account_settings,
    checked_session,
    credential_environment,
    monthly_budget,
    require_aws_execution,
    terraform_environment,
)

PROJECT = Path(__file__).resolve().parents[3]
REPOSITORY = "yonegen0/ai_interview"
INPUT_KEYS = frozenset(
    {
        "log_usage",
        "boundary_arn",
        "artifact_bucket",
        "artifact_key",
        "artifact_version",
        "artifact_sha256_base64",
        "ses_email",
        "ses_identity_arn",
        "alarm_email",
        "jpy_per_usd",
        "budget_rate_date",
        "worker_enabled",
        "streams_enabled",
        "scheduler_enabled",
        "api_enabled",
    }
)
USD_INPUT_KEYS = (INPUT_KEYS - {"jpy_per_usd", "budget_rate_date"}) | {"monthly_budget_usd"}


def valid_input_keys(keys, *, without_artifact=False):
    package = {"artifact_bucket", "artifact_key", "artifact_version", "artifact_sha256_base64"}
    omitted = package if without_artifact else set()
    return set(keys) in (INPUT_KEYS - omitted, USD_INPUT_KEYS - omitted)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, *, cwd, env, accepted=(0,)):
    if os.environ.get("P4_STANDARD_ACTIVE") == "true":
        from ci_identity import standard_context

        standard_context(os.environ, reserve=120)
    guard = active_guard()
    if guard:
        return guard.process(command, cwd=cwd, env=env, accepted=accepted)
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, check=False)
    if result.returncode not in accepted:
        raise DeploymentError("TerraformOperationFailed")
    return result.stdout


def checked_git(root, env):
    if env.get("GITHUB_ACTIONS") != "true":
        raise DeploymentError("ManualGitHubWorkflowRequired")
    if env.get("P4_AWS_EXECUTION_READY") != "true":
        raise DeploymentError("AwsExecutionPrerequisitesUnconfirmed")
    sha = run(["git", "rev-parse", "HEAD"], cwd=root, env=env).decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise DeploymentError("InvalidSourceRevision")
    remote = (
        run(["git", "config", "--get", "remote.origin.url"], cwd=root, env=env).decode().strip()
    )
    if remote not in {
        f"https://github.com/{REPOSITORY}.git",
        f"git@github.com:{REPOSITORY}.git",
        f"https://github.com/{REPOSITORY}",
    }:
        raise DeploymentError("RepositoryMismatch")
    if run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, env=env).strip():
        raise DeploymentError("CleanCommittedSourceRequired")
    if env.get("GITHUB_ACTIONS") == "true":
        if env.get("GITHUB_REF") != "refs/heads/main" or env.get("GITHUB_SHA") != sha:
            raise DeploymentError("MainRevisionRequired")
        if env.get("GITHUB_REPOSITORY") != REPOSITORY:
            raise DeploymentError("RepositoryMismatch")
    else:
        branch = run(["git", "branch", "--show-current"], cwd=root, env=env).decode().strip()
        if branch != "main":
            raise DeploymentError("MainRevisionRequired")
    from github_control import github_json, verify_dev_environment

    verify_dev_environment(env)
    remote_main = github_json("git/ref/heads/main", env)
    if remote_main["object"]["sha"] != sha:
        raise DeploymentError("CurrentMainRevisionRequired")
    return sha


def inputs(path, account, region):
    values = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_inputs(values, account, region)


def validate_inputs(
    values, account, region, *, previous_configuration=None, shortening_approval_hash=None
):
    if not isinstance(values, dict) or not valid_input_keys(values):
        raise DeploymentError("ExplicitDeploymentInputsRequired")
    if values["log_usage"] not in ("developer", "customer"):
        raise DeploymentError("ExplicitLogUsageRequired")
    if (
        previous_configuration
        and previous_configuration.get("log_usage") == "customer"
        and values["log_usage"] == "developer"
        and not re.fullmatch(r"[0-9a-f]{64}", shortening_approval_hash or "")
    ):
        raise DeploymentError("ApprovedRetentionShorteningRequired")
    result = dict(values)
    if "monthly_budget_usd" in result:
        amount = result["monthly_budget_usd"]
        if (
            not isinstance(amount, str)
            or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", amount)
            or Decimal(amount) <= 0
        ):
            raise DeploymentError("InvalidMonthlyBudget")
        result["monthly_budget_usd"] = format(Decimal(amount), ".2f")
    else:
        result["monthly_budget_usd"] = monthly_budget(
            result.pop("jpy_per_usd"), result.pop("budget_rate_date")
        )
    if result["artifact_bucket"] != f"ai-interview-artifacts-{account}-{region}":
        raise DeploymentError("ArtifactBucketMismatch")
    if (
        not isinstance(result["artifact_key"], str)
        or not re.fullmatch(r"lambda/[A-Za-z0-9/_-]+[.]zip", result["artifact_key"])
        or "REPLACE_ME" in result["artifact_key"]
    ):
        raise DeploymentError("InvalidArtifactKey")
    if (
        not isinstance(result["artifact_version"], str)
        or result["artifact_version"] in {"", "null"}
        or result["artifact_version"].strip() != result["artifact_version"]
        or "REPLACE_ME" in result["artifact_version"]
    ):
        raise DeploymentError("VersionedArtifactRequired")
    if not isinstance(result["artifact_sha256_base64"], str) or not re.fullmatch(
        r"[A-Za-z0-9+/]{43}=", result["artifact_sha256_base64"]
    ):
        raise DeploymentError("InvalidArtifactDigest")
    if result["boundary_arn"] != f"arn:aws:iam::{account}:policy/ai-interview-runtime-boundary":
        raise DeploymentError("BoundaryMismatch")
    if not result["ses_identity_arn"].startswith(f"arn:aws:ses:{region}:{account}:identity/"):
        raise DeploymentError("SenderIdentityMismatch")
    for key in ("ses_email", "alarm_email"):
        if not isinstance(result[key], str) or not re.fullmatch(r"[^@\s]+@[^@\s]+", result[key]):
            raise DeploymentError("InvalidEmailSetting")
    for key in ("worker_enabled", "streams_enabled", "scheduler_enabled", "api_enabled"):
        if type(result[key]) is not bool:
            raise DeploymentError("ExplicitActivationFlagsRequired")
    result.update(account_id=account, region=region, cors_origins=["http://localhost:3000"])
    return result


def bind_plan(root, account, region, sha, input_path):
    return {
        "schema_version": 1,
        "repository": REPOSITORY,
        "code_sha": sha,
        "account_id": account,
        "region": region,
        "terraform_version": TF_VERSION,
        "lock_sha256": digest(root / ".terraform.lock.hcl"),
        "inputs_sha256": digest(input_path),
        "state_bucket": f"ai-interview-state-{account}-{region}",
        "state_key": "dev/terraform.tfstate",
    }


def assert_binding(actual, expected, plan_path, approved_hash):
    if not re.fullmatch(r"[0-9a-f]{64}", approved_hash or ""):
        raise DeploymentError("ApprovedPlanHashRequired")
    if actual != expected | {"plan_sha256": approved_hash} or digest(plan_path) != approved_hash:
        raise DeploymentError("SavedPlanMismatch")


def execute(operation, input_path, directory, approved_hash=None, *, progress=None):
    require_aws_execution()
    if operation not in {"plan", "apply", "verify"}:
        raise DeploymentError("InvalidOperation")
    guard = required_guard() if operation == "plan" else None
    if guard:
        guard.check("terraform-execution", 1920)
    account, region = account_settings(PROJECT)
    root = PROJECT / "terraform" / "environments" / "dev"
    env = terraform_environment(root, os.environ, account, region)
    values = inputs(input_path, account, region)
    if operation == "apply" and any(
        values[k] for k in ("api_enabled", "worker_enabled", "streams_enabled", "scheduler_enabled")
    ):
        from closure_readiness import require_closure_ready

        require_closure_ready(
            os.environ.get("P4_CLOSURE_VALIDATION_PATH"),
            os.environ.get("P4_CLOSURE_VALIDATION_SHA256"),
        )
    for key, value in values.items():
        encoded = value if isinstance(value, str) else json.dumps(value)
        name = f"TF_VAR_{key}"
        if name in env and env[name] != encoded:
            raise DeploymentError("TerraformSettingConflict")
        env[name] = encoded
    if any(k.startswith("TF_VAR_") and k[7:] not in values for k in env):
        raise DeploymentError("UnexpectedTerraformVariable")
    directory = Path(directory).resolve()
    private = (PROJECT / ".p4-artifacts").resolve()
    if not directory.is_relative_to(private) or directory == private:
        raise DeploymentError("PrivateRunDirectoryRequired")
    sha = checked_git(PROJECT, env)
    binding = bind_plan(root, account, region, sha, input_path)
    plan = directory / "dev.tfplan"
    manifest = directory / "plan.json"
    if operation == "plan":
        directory.mkdir(parents=True, exist_ok=False)
    env["TF_DATA_DIR"] = str(directory / ".terraform")
    env["TF_WORKSPACE"] = "default"
    version = json.loads(run(["terraform", "version", "-json"], cwd=root, env=env))
    if version["terraform_version"] != TF_VERSION:
        raise DeploymentError("TerraformVersionMismatch")
    if guard:
        guard.check("terraform-identity", 25)
    checkpoint("terraform-identity")
    if os.environ.get("P4_CLOUD_ACTIVE") == "true":
        from cloud_ci import session as cloud_session

        session = cloud_session("plan", account, region, required_seconds=1920)
    else:
        session = checked_session(account, region, environment=env)
    env = credential_environment(session, env)
    from deployment_guards import audit_retention, read_state_snapshot

    checkpoint("state-read")
    snapshot = read_state_snapshot(
        session, account, region, binding["state_key"], allow_absent=True
    )
    approval_path = os.environ.get("P4_LOG_RETENTION_APPROVAL_PATH")
    approval_hash = os.environ.get("P4_LOG_RETENTION_APPROVAL_SHA256")
    binding["state_identity"] = snapshot["identity"]
    binding["log_retention_approval_sha256"] = approval_hash
    recovery = None
    if operation == "plan" and guard and "stage_recovery" in guard.package:
        from stage_recovery import from_approval

        recovery = from_approval(guard.package, os.environ)
    elif operation != "plan":
        recovery = json.loads(manifest.read_bytes()).get("stage_recovery")
        if recovery is not None:
            from ci_identity import standard_context
            from stage_recovery import validate

            standard_context(os.environ, reserve=120)
            recovery = validate(recovery, account, region)
    if recovery:
        from stage_recovery import check_live, check_state

        check_state(snapshot, recovery)
        checkpoint("live-readback")
        check_live(session, snapshot, recovery, os.environ)
        binding["stage_recovery"] = recovery
    if operation != "plan":
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        if operation == "verify":
            binding["state_identity"] = saved["state_identity"]
        assert_binding(saved, binding, plan, approved_hash)
    validate_inputs(
        json.loads(Path(input_path).read_text()),
        account,
        region,
        previous_configuration=(snapshot["manifest"] or {}).get("configuration"),
        shortening_approval_hash=approval_hash,
    )
    run(
        [
            "terraform",
            "init",
            "-input=false",
            "-lockfile=readonly",
            f"-backend-config=bucket={binding['state_bucket']}",
            f"-backend-config=key={binding['state_key']}",
            f"-backend-config=region={region}",
            '-backend-config=allowed_account_ids=["' + account + '"]',
            "-backend-config=encrypt=true",
            "-backend-config=use_lockfile=true",
            "-backend-config=max_retries=0",
        ],
        cwd=root,
        env=env,
    )
    if guard:
        guard.check("terraform-identity", 25)
    if os.environ.get("P4_CLOUD_ACTIVE") == "true":
        cloud_session("plan", account, region, required_seconds=1500)
    else:
        checked_session(account, region, environment=env)
    if operation == "plan":
        run(
            [
                "terraform",
                "plan",
                "-input=false",
                "-lock-timeout=0s",
                "-parallelism=2",
                f"-out={plan}",
            ],
            cwd=root,
            env=env,
        )
        binding["plan_sha256"] = digest(plan)
        from plan_summary import summarize

        review = json.loads(run(["terraform", "show", "-json", str(plan)], cwd=root, env=env))
        checkpoint("plan-audit")
        if recovery:
            from stage_recovery import audit_plan

            audit_plan(review, recovery, snapshot)
        audit_retention(
            review,
            snapshot["manifest"],
            snapshot,
            approval_path,
            approval_hash,
            private,
            now=int(time.time()),
        )
        if guard:
            guard.check("post-plan-state-read", 60)
        checkpoint("post-plan-state-read")
        if (
            read_state_snapshot(session, account, region, binding["state_key"], allow_absent=True)
            != snapshot
        ):
            raise DeploymentError("StateChangedDuringPlan")
        if recovery:
            check_live(session, snapshot, recovery, os.environ)
        (directory / "review.private.json").write_text(json.dumps(review), encoding="utf-8")
        summary = summarize(review)
        (directory / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        with manifest.open("x", encoding="utf-8") as stream:
            json.dump(binding, stream, indent=2)
        return {"status": "planned", "plan_sha256": binding["plan_sha256"], "summary": summary}
    from bootstrap_state import write_record

    if operation == "apply":
        review = json.loads(run(["terraform", "show", "-json", str(plan)], cwd=root, env=env))
        if recovery:
            from stage_recovery import audit_plan

            audit_plan(review, recovery, snapshot)
        audit_retention(
            review,
            snapshot["manifest"],
            snapshot,
            approval_path,
            approval_hash,
            private,
            now=int(time.time()),
        )
        if (
            read_state_snapshot(session, account, region, binding["state_key"], allow_absent=True)
            != snapshot
        ):
            raise DeploymentError("StateChangedBeforeApply")
        write_record(directory / "apply-attempt.json", {"plan_sha256": approved_hash})
        if progress:
            progress("apply_started")
        lock_timeout = "0s" if recovery else "60s"
        command = ["terraform", "apply", "-input=false", f"-lock-timeout={lock_timeout}", str(plan)]
        if recovery:
            from stage_recovery import apply_process

            apply_process(command, directory, cwd=root, env=env)
        else:
            run(command, cwd=root, env=env)
        write_record(directory / "apply-completed.json", {"plan_sha256": approved_hash})
        if progress:
            progress("apply_completed")
    elif not (directory / "apply-completed.json").is_file():
        raise DeploymentError("ConfirmedApplyRequired")
    checked_session(account, region, environment=env)
    deployed = run(["terraform", "output", "-json", "manifest"], cwd=root, env=env)
    (directory / "deployment.json").write_bytes(deployed)
    from manifest import read_manifest, wait_for_manifest

    observed = read_manifest(directory / "deployment.json", account, region)
    wait_for_manifest(
        checked_session(account, region, environment=env),
        observed,
        approved_inputs=values,
    )
    if recovery:
        final = read_state_snapshot(session, account, region, binding["state_key"])
        check_live(session, final, recovery, os.environ, applied=True)
        from stage_recovery import state_resources

        if (
            final["identity"]["lineage"] != recovery["state_identity"]["lineage"]
            or final["identity"]["serial"] <= recovery["state_identity"]["serial"]
            or final["identity"]["version_id"] == recovery["state_identity"]["version_id"]
            or final["manifest"] != snapshot["manifest"]
            or state_resources(final) != state_resources(snapshot)
        ):
            raise DeploymentError("StageRecoveryFinalStateMismatch")
    return {"status": "applied_readback_verified", "versions": observed["versions"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("plan", "apply"))
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--plan-hash")
    args = parser.parse_args()
    try:
        result = execute(args.operation, args.inputs, args.directory, args.plan_hash)
    except Exception:
        print("GuardedTerraformFailed", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
