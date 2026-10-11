"""Separately approved saved-Plan Apply controller. Never replan or repair.

The historical recovery audit stays at its approved clean-main revision. This
controller has a separate reviewed Git/code/runtime envelope and attempt journal.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import bootstrap_audit_recovery as recovery
import bootstrap_maintenance as normal
import recovery_contract as pure
from bootstrap_state import bootstrap_lock, private_path
from deployment_guards import approved_json
from maintenance_contract import UPDATES, check_applied, encoded, hashed, require, state_instances

PROJECT = Path(__file__).resolve().parents[3]
CODE = "backend/skills/p4/bootstrap_recovered_apply.py"
CONTROLLER_REF = "refs/heads/codex/bootstrap-recovered-apply-controller-20261011"
FIELDS = {
    "schema_version",
    "kind",
    "approved",
    "expires_at",
    "cost_cap_usd",
    "controller_source_sha",
    "controller_ref",
    "controller_code_sha256",
    "controller_repository",
    "audit_repository",
    "apply_approval_sha256",
    "apply_run_path",
    "terraform_path",
    "terraform_sha256",
    "provider_files",
}


def validate_envelope(value):
    require(
        set(value) == FIELDS
        and type(value["schema_version"]) is int
        and value["schema_version"] == 1
        and value["kind"] == "p4-bootstrap-recovered-apply-controller"
        and value["approved"] is True
        and value["cost_cap_usd"] == "0.05",
        "RecoveredApplyControllerApprovalRequired",
    )
    pure.fresh(value)
    require(value["controller_ref"] == CONTROLLER_REF, "RecoveredApplyIndependentBranchRequired")
    require(
        pure.revision(value["controller_source_sha"])
        and all(
            pure.digest(value[key])
            for key in ("controller_code_sha256", "apply_approval_sha256", "terraform_sha256")
        ),
        "RecoveredApplyControllerManifest",
    )
    require(
        all(
            isinstance(value[key], str) and Path(value[key]).is_absolute()
            for key in (
                "controller_repository",
                "audit_repository",
                "apply_run_path",
                "terraform_path",
            )
        ),
        "RecoveredApplyAbsolutePathsRequired",
    )
    providers = value["provider_files"]
    require(isinstance(providers, dict) and bool(providers), "RecoveredApplyProviderManifest")
    platform = "windows_amd64" if os.name == "nt" else "linux_amd64"
    prefix = f"providers/registry.terraform.io/hashicorp/aws/6.64.0/{platform}/"
    expected = "terraform-provider-aws_v6.64.0_x5" + (".exe" if os.name == "nt" else "")
    require(
        all(
            isinstance(name, str)
            and name in {prefix + expected, prefix + "LICENSE.txt"}
            and pure.digest(digest)
            for name, digest in providers.items()
        )
        and prefix + expected in providers,
        "RecoveredApplyProviderManifest",
    )


def controller_identity(root, value, private):
    require(
        root == private_path(value["controller_repository"], private),
        "RecoveredApplyControllerPath",
    )
    require(normal.home_repository(root) == private.parent, "RecoveredApplyCommonRepository")
    sha = normal.git(root, "rev-parse", "HEAD").decode().strip()
    require(
        sha == value["controller_source_sha"]
        and not normal.git(root, "status", "--porcelain=v1", "--untracked-files=all").strip(),
        "RecoveredApplyCleanControllerRequired",
    )
    require(
        normal.git(root, "branch", "--show-current").decode().strip()
        == CONTROLLER_REF.removeprefix("refs/heads/")
        and normal.git(root, "ls-remote", "origin", CONTROLLER_REF).decode().split()[0] == sha,
        "RecoveredApplyIndependentBranchChanged",
    )
    raw = normal.git(root, "show", sha + ":" + CODE)
    require(
        hashed(raw) == value["controller_code_sha256"]
        and Path(__file__).read_bytes().replace(b"\r\n", b"\n") == raw.replace(b"\r\n", b"\n"),
        "RecoveredApplyLoadedControllerChanged",
    )


def provider_inventory(original):
    base = original / "data"
    directory = private_path(base / "providers", original)
    require(directory.is_dir(), "RecoveredApplyProviderCacheUnavailable")
    observed = {}
    for item in directory.rglob("*"):
        safe = private_path(item, original)
        if safe.is_file():
            observed[safe.relative_to(base).as_posix()] = hashed(safe.read_bytes())
    return observed


def runtime_gate(value, original):
    binary = Path(value["terraform_path"])
    require(
        not any(p.is_symlink() or p.is_junction() for p in (binary, *binary.parents))
        and binary.is_file()
        and hashed(binary.read_bytes()) == value["terraform_sha256"],
        "RecoveredApplyTerraformBinaryChanged",
    )
    require(
        provider_inventory(original) == value["provider_files"],
        "RecoveredApplyProviderCacheChanged",
    )


def apply_permissions(reader, request, bundle):
    """Simulate only the approved State write and two inline-policy writes.

    Simulation is an additional fail-closed gate, never a live authorization
    guarantee or an actual PutObject/PutRolePolicy invocation.
    """
    account = request["account_id"]
    resources = state_instances(bundle["snapshot"]["state"])
    roles = {resources[address]["role"] for address in UPDATES}
    require(
        roles == {"ai-interview-ci-plan", "ai-interview-ci-deploy"},
        "RecoveredApplyWriteTargetsChanged",
    )
    backend = request["backend"]
    requests = [
        ("s3:PutObject", f"arn:aws:s3:::{backend['bucket']}/{backend['key']}", request["region"]),
        *[
            ("iam:PutRolePolicy", f"arn:aws:iam::{account}:role/{role}", "us-east-1")
            for role in sorted(roles)
        ],
    ]
    observed = []
    for action, arn, region in requests:
        context = [
            {
                "ContextKeyName": "aws:SecureTransport",
                "ContextKeyValues": ["true"],
                "ContextKeyType": "boolean",
            },
            {
                "ContextKeyName": "aws:RequestedRegion",
                "ContextKeyValues": [region],
                "ContextKeyType": "string",
            },
            {
                "ContextKeyName": "aws:PrincipalArn",
                "ContextKeyValues": [request["principal_role_arn"]],
                "ContextKeyType": "string",
            },
        ]
        if action == "s3:PutObject":
            context.append(
                {
                    "ContextKeyName": "s3:x-amz-server-side-encryption",
                    "ContextKeyValues": ["AES256"],
                    "ContextKeyType": "string",
                }
            )
        result = reader.iam.simulate_principal_policy(
            PolicySourceArn=request["principal_role_arn"],
            ActionNames=[action],
            ResourceArns=[arn],
            ContextEntries=context,
        )
        evaluations = result.get("EvaluationResults", [])
        require(
            len(evaluations) == 1
            and result.get("IsTruncated") is False
            and "Marker" not in result
            and evaluations[0].get("EvalActionName") == action
            and evaluations[0].get("EvalResourceName") == arn
            and evaluations[0].get("EvalDecision") == "allowed"
            and not evaluations[0].get("MissingContextValues"),
            "RecoveredApplyWritePermissionsDenied",
        )
        observed.append({"action": action, "resource": arn, "decision": "allowed"})
    return observed


def local_binding(audit, value, files, claim, run, owned=None):
    request = json.loads((run / "recovery-approval.private.json").read_bytes())
    require(not (claim / "recovery-failed.private.json").exists(), "RecoveredApplyRecoveryFailed")
    for name in ("recovery-started.private.json", "recovery-completed.private.json"):
        require(
            (claim / name).read_bytes() == (run / name).read_bytes(), "RecoveryJournalCopiesChanged"
        )
    if owned is None:
        require(
            {p.name for p in claim.iterdir()}
            == {"recovery-started.private.json", "recovery-completed.private.json"},
            "RecoveryApplyAlreadyAttempted",
        )
    else:
        # Only the current lock owner may perform its final recheck after claiming
        # the attempt. Never delete, replace or ignore a foreign start journal.
        require(
            (claim / "apply-started.private.json").read_bytes() == owned
            and {p.name for p in claim.iterdir()}
            == {
                "recovery-started.private.json",
                "recovery-completed.private.json",
                "apply-started.private.json",
            },
            "RecoveredApplyAttemptOwnershipChanged",
        )
    bundle, artifacts, journal, old_actor = recovery.bundle_from_disk(
        audit, request, files, local_lock_held=True
    )
    require(
        (run / "review.private.json").read_bytes() == artifacts["show.stdout.private.log"],
        "RecoveryCopiedReviewChanged",
    )
    identity = recovery.code_identity(audit, request)[0]
    args = (
        value,
        (run / "binding.private.json").read_bytes(),
        (run / "recovery-approval.private.json").read_bytes(),
        (claim / "recovery-started.private.json").read_bytes(),
        (claim / "recovery-completed.private.json").read_bytes(),
        artifacts,
        journal,
        old_actor,
        files,
    )
    pure.validate_recovered_apply(
        *args,
        bundle["snapshot"],
        json.loads(old_actor)["actor"],
        identity,
        apply_already_started=False,
    )
    return request, bundle, args, identity


def prepare_run(output, original, artifacts, files, envelope):
    normal.secure_directory(output)
    normal.secure_directory(output / "configuration")
    normal.secure_directory(output / "data")
    for name, raw in files.items():
        normal.write_bytes(output / "configuration" / name, raw)
    for source, destination in (
        ("configuration/backend.tf", "configuration/backend.tf"),
        ("backend.private.hcl", "backend.private.hcl"),
        ("data/terraform.tfstate", "data/terraform.tfstate"),
        ("terraform.rc", "terraform.rc"),
        ("empty-aws-config", "empty-aws-config"),
    ):
        normal.write_bytes(output / destination, artifacts[source])
    for name, digest in envelope["provider_files"].items():
        path = private_path(original / "data" / name, original)
        raw = path.read_bytes()
        require(hashed(raw) == digest, "RecoveredApplyProviderCacheChanged")
        target = output / "data" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        normal.write_bytes(target, raw)
        if os.name != "nt":
            target.chmod(path.stat().st_mode & 0o777)
    normal.check_configuration(output, files)


def terraform(output, env, envelope, stage, args, plan, *, authorization=None):
    allowed = {
        "version": ["version", "-json"],
        "pre-pull": ["state", "pull"],
        "pre-show": ["show", "-json", str(plan)],
        "apply": ["apply", "-input=false", "-lock=true", "-lock-timeout=0s", str(plan)],
        "post-pull": ["state", "pull"],
    }
    require(
        stage in allowed and args == allowed[stage], "RecoveredApplyTerraformOperationForbidden"
    )
    binary = Path(envelope["terraform_path"])
    require(
        hashed(binary.read_bytes()) == envelope["terraform_sha256"],
        "RecoveredApplyTerraformBinaryChanged",
    )
    require(
        provider_inventory(output) == envelope["provider_files"],
        "RecoveredApplyProviderCacheChanged",
    )
    if stage == "apply":
        require(callable(authorization), "RecoveredApplyFinalAuthorizationRequired")
        authorization()
    try:
        result = subprocess.run(
            [str(binary), *args],
            cwd=output / "configuration",
            env=env,
            capture_output=True,
            timeout=1200,
        )
    except subprocess.TimeoutExpired as error:
        normal.write_bytes(output / (stage + ".stdout.private.log"), error.stdout or b"")
        normal.write_bytes(output / (stage + ".stderr.private.log"), error.stderr or b"")
        require(False, "RecoveredApplyResultUnknown")
    normal.write_bytes(output / (stage + ".stdout.private.log"), result.stdout)
    normal.write_bytes(output / (stage + ".stderr.private.log"), result.stderr)
    require(result.returncode == 0, "RecoveredApplyTerraformFailed")
    return result.stdout


def execute(
    controller_path, controller_sha, apply_path, apply_sha, *, repository=PROJECT, environment=None
):
    root = Path(repository).resolve()
    parent, private, account, region = recovery.read_environment(root, environment)
    raw, envelope = approved_json(controller_path, controller_sha, private)
    validate_envelope(envelope)
    require(
        parent.get("P4_BOOTSTRAP_RECOVERED_APPLY_READY") == "true",
        "RecoveredApplyExecutionDisabled",
    )
    require(apply_sha == envelope["apply_approval_sha256"], "RecoveredApplyApprovalHashChanged")
    apply_raw, value = approved_json(apply_path, apply_sha, private)
    require(
        type(value.get("schema_version")) is int and value["schema_version"] == 1,
        "RecoveredApplyStrictSchemaRequired",
    )
    controller_identity(root, envelope, private)
    audit = private_path(envelope["audit_repository"], private)
    require(normal.home_repository(audit) == private.parent, "RecoveredApplyCommonRepository")
    run = private_path(value["recovery_run_path"], private)
    request = json.loads((run / "recovery-approval.private.json").read_bytes())
    require(
        (account, region) == (request["account_id"], request["region"]), "RecoveryAccountRegion"
    )
    identity, files = recovery.code_identity(audit, request)
    _, original, _, _, _, claim = recovery.paths(audit, request)
    output = private_path(envelope["apply_run_path"], private)
    require(
        output.parent.is_dir()
        and not output.exists()
        and all(
            not output.is_relative_to(p) and not p.is_relative_to(output)
            for p in (original, run, claim)
        ),
        "RecoveredApplySeparateRunRequired",
    )
    require(not (private / "bootstrap-operation.lock").exists(), "RecoveryOperationLocked")
    _, bundle, args, identity = local_binding(audit, value, files, claim, run)
    runtime_gate(envelope, original)
    reader = None
    owned = None
    try:
        with bootstrap_lock(private):
            # All local authorization and historical validation precedes SDK or
            # Terraform access. The durable claim prohibits retries across runs.
            _, bundle, args, identity = local_binding(audit, value, files, claim, run)
            runtime_gate(envelope, original)
            started = {
                "controller_approval_sha256": controller_sha,
                "apply_approval_sha256": apply_sha,
                "apply_run_path": str(output),
                "plan_sha256": value["plan_sha256"],
                "binding_sha256": value["binding_sha256"],
            }
            owned = encoded(started)
            normal.write_bytes(claim / "apply-started.private.json", owned)
            artifacts = args[5]
            prepare_run(output, original, artifacts, files, envelope)
            normal.write_bytes(output / "apply-started.private.json", owned)
            normal.write_bytes(output / "controller-approval.private.json", raw)
            normal.write_bytes(output / "apply-approval.private.json", apply_raw)
            reader = recovery.reader_for(private, account, region, parent)
            actor = reader.actor(value["principal_role_arn"])
            before = reader.snapshot()
            reader.verify_resources(before["state"], bundle["inputs"])
            pure.validate_recovered_apply(*args, before, actor, identity)
            permissions_before = apply_permissions(reader, request, bundle)
            env = normal.execution_environment(output, parent, reader.session, bundle["inputs"])
            env["CHECKPOINT_DISABLE"] = "1"
            plan = original / "bootstrap.tfplan"
            require(
                json.loads(terraform(output, env, envelope, "version", ["version", "-json"], plan))[
                    "terraform_version"
                ]
                == "1.14.9",
                "RecoveredApplyTerraformVersion",
            )
            normal.check_backend(output, request["backend"])
            pulled = terraform(output, env, envelope, "pre-pull", ["state", "pull"], plan)
            normal.compare_state_snapshot(encoded(before["state"]), pulled)
            shown = terraform(output, env, envelope, "pre-show", ["show", "-json", str(plan)], plan)
            normal.audit_plan(json.loads(shown), before["state"], bundle["inputs"], account, region)
            immediate = reader.snapshot()
            reader.verify_resources(immediate["state"], bundle["inputs"])
            _, repeated, args, identity = local_binding(audit, value, files, claim, run, owned)
            require(encoded(repeated) == encoded(bundle), "RecoveredApplyEvidenceChanged")
            pure.validate_recovered_apply(
                *args, immediate, reader.actor(value["principal_role_arn"]), identity
            )
            permissions_immediate = apply_permissions(reader, request, bundle)
            pure.fresh(envelope)
            controller_identity(root, envelope, private)
            require(
                (output / "apply-started.private.json").read_bytes() == owned,
                "RecoveredApplyAttemptOwnershipChanged",
            )
            require(hashed(plan.read_bytes()) == value["plan_sha256"], "RecoveredApplyPlanChanged")
            normal.check_configuration(output, files)
            normal.check_backend(output, request["backend"])

            def final_authorization():
                # After potentially expensive runtime hashing, immediately before
                # subprocess invocation, re-read both exact approved descriptors.
                _, current_controller = approved_json(controller_path, controller_sha, private)
                _, current_apply = approved_json(apply_path, apply_sha, private)
                validate_envelope(current_controller)
                require(encoded(current_apply) == encoded(value), "RecoveredApplyApprovalChanged")
                pure.fresh(current_apply)
                require(
                    (claim / "apply-started.private.json").read_bytes() == owned
                    and (output / "apply-started.private.json").read_bytes() == owned,
                    "RecoveredApplyAttemptOwnershipChanged",
                )

            terraform(
                output,
                env,
                envelope,
                "apply",
                ["apply", "-input=false", "-lock=true", "-lock-timeout=0s", str(plan)],
                plan,
                authorization=final_authorization,
            )
            after = reader.snapshot()
            check_applied(before["state"], after["state"], account, region)
            require(
                all(x in after["versions"] for x in before["versions"])
                and bool([x for x in after["versions"] if x not in before["versions"]])
                and all(
                    x["kind"] == "Versions"
                    for x in after["versions"]
                    if x not in before["versions"]
                ),
                "RecoveredApplyVersionInventory",
            )
            reader.actor(value["principal_role_arn"])
            reader.verify_resources(after["state"], bundle["inputs"])
            permissions_after = apply_permissions(reader, request, bundle)
            pulled = terraform(output, env, envelope, "post-pull", ["state", "pull"], plan)
            normal.compare_state_snapshot(encoded(after["state"]), pulled)
            again = reader.snapshot()
            require(encoded(again) == encoded(after), "RecoveredApplyPostStateChanged")
            reader.verify_resources(again["state"], bundle["inputs"])
            recovery.bundle_from_disk(audit, request, files, local_lock_held=True)
            normal.check_configuration(output, files)
            normal.check_backend(output, request["backend"])
            normal.write_json(
                output / "apply-readback.private.json",
                {
                    "before": before,
                    "after": after,
                    "operations": reader.operations,
                    "write_permission_simulations": {
                        "before": permissions_before,
                        "immediate": permissions_immediate,
                        "after": permissions_after,
                    },
                },
            )
            finished = {**started, "state_identity": after["identity"], "verified_updates": 2}
            normal.write_json(output / "apply-completed.private.json", finished)
            normal.write_json(claim / "apply-completed.private.json", finished)
        return {"status": "BOOTSTRAP_RECOVERED_APPLY_VERIFIED", "updated": 2}
    except Exception as error:
        if owned is not None:
            diagnosis = {"repair_attempted": False}
            if reader is not None:
                try:
                    diagnosis = reader.diagnose()
                except Exception:
                    diagnosis = {"repair_attempted": False, "available": False}
            failed = {
                "status": "READ_ONLY_DIAGNOSIS_REQUIRED",
                "retry_allowed": False,
                "error_class": type(error).__name__,
                "diagnosis": diagnosis,
            }
            normal.write_json(claim / "apply-failed.private.json", failed)
            if output.is_dir():
                normal.write_json(output / "apply-failed.private.json", failed)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("apply",))
    parser.add_argument("--controller-approval", required=True)
    parser.add_argument("--controller-approval-sha256", required=True)
    parser.add_argument("--apply-approval", required=True)
    parser.add_argument("--apply-approval-sha256", required=True)
    args = parser.parse_args()
    try:
        result = execute(
            args.controller_approval,
            args.controller_approval_sha256,
            args.apply_approval,
            args.apply_approval_sha256,
        )
    except Exception:
        print(
            json.dumps({"status": "BOOTSTRAP_RECOVERED_APPLY_STOPPED", "retry_allowed": False}),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
