"""Separate, approval-bound maintenance of canonical S3 bootstrap State.

inspect performs only AWS reads. plan/apply require distinct hash-approved private
descriptors and a clean main. No bootstrap creation, migration, retry or repair path.
"""

import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from bootstrap_state import (
    S3_BACKEND,
    bootstrap_lock,
    compare_state_snapshot,
    private_path,
)
from deployment_guards import approved_json
from maintenance_aws import BootstrapAWS
from maintenance_contract import (
    TF_VERSION,
    audit_plan,
    backend,
    check_applied,
    check_snapshot,
    encoded,
    hashed,
    require,
    validate_approval,
    validate_inputs,
)
from offline_terraform import parse_lock
from recovery_migration import backend_hcl

from interview_backend.deployment import (
    account_settings,
    checked_session,
    credential_environment,
    read_local_settings,
)

PROJECT = Path(__file__).resolve().parents[3]
REPOSITORY = "yonegen0/ai_interview"


def git(root, *args):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=30)
    require(result.returncode == 0, "MaintenanceGitUnavailable")
    return result.stdout


def home_repository(root):
    common = Path(git(root, "rev-parse", "--git-common-dir").decode().strip())
    return (root / common).resolve().parent


def protect(directory):
    """Private before the first sensitive byte; no credential material in ACL commands."""
    if os.name != "nt":
        directory.chmod(0o700)
        return
    user = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True)
    require(user.returncode == 0, "MaintenancePrivateAclUnavailable")
    sid = list(csv.reader(io.StringIO(user.stdout.decode(errors="replace"))))[0][-1]
    require(bool(re.fullmatch(r"S-1-[0-9-]+", sid)), "MaintenancePrivateAclUnavailable")
    allowed = {sid, "S-1-5-18", "S-1-5-32-544"}
    args = ["icacls", str(directory), "/inheritance:r", "/grant:r"]
    args += ["*" + value + ":(OI)(CI)F" for value in sorted(allowed)]
    result = subprocess.run(args, capture_output=True)
    require(result.returncode == 0, "MaintenancePrivateAclUnavailable")
    # Only a validated path is inserted; quote for PowerShell, not for a shell command line.
    quoted = str(directory).replace("'", "''")
    query = (
        "@((Get-Acl -LiteralPath '" + quoted + "').Access | ForEach-Object { "
        "$_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value "
        "}) | ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", query], capture_output=True
    )
    require(
        result.returncode == 0 and set(json.loads(result.stdout)) == allowed,
        "MaintenancePrivateAclUnavailable",
    )


def secure_directory(path):
    path.mkdir(exist_ok=False)
    protect(path)


def write_bytes(path, raw):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def write_json(path, value):
    write_bytes(path, encoded(value))


def source_files(root, approval, *, require_main):
    sha = git(root, "rev-parse", "HEAD").decode().strip()
    require(sha == approval["source_sha"], "MaintenanceGitShaMismatch")
    require(
        not git(root, "status", "--porcelain=v1", "--untracked-files=all").strip(),
        "MaintenanceCleanSourceRequired",
    )
    remote = git(root, "config", "--get", "remote.origin.url").decode().strip()
    require(
        remote
        in {
            f"https://github.com/{REPOSITORY}.git",
            f"https://github.com/{REPOSITORY}",
            f"git@github.com:{REPOSITORY}.git",
        },
        "MaintenanceRepository",
    )
    if require_main:
        require(
            git(root, "branch", "--show-current").decode().strip() == "main",
            "MaintenanceMainRequired",
        )
        require(
            git(root, "ls-remote", "origin", "refs/heads/main").decode().split()[0] == sha,
            "MaintenanceRemoteMainChanged",
        )
    return configuration_files(root, sha, approval["provider_lock_sha256"])


def configuration_files(root, sha, provider_lock_sha256):
    """Read immutable configuration blobs without rewriting an original descriptor."""
    require(bool(re.fullmatch(r"[0-9a-f]{40}", sha)), "MaintenanceSourceSha")
    names = git(root, "ls-tree", "-r", "--name-only", sha, "--", "terraform/bootstrap").decode()
    files = {}
    for name in names.splitlines():
        path = Path(name)
        if path.parent.as_posix() != "terraform/bootstrap":
            continue
        require(
            not path.name.endswith(".tf.json")
            and ".auto.tfvars" not in path.name
            and path.name not in {"terraform.tfvars", "terraform.tfvars.json"},
            "MaintenanceSourceOverlay",
        )
        if path.suffix == ".tf" or path.name == ".terraform.lock.hcl":
            require(
                path.name not in {"backend.tf", "override.tf"}
                and not path.name.endswith("_override.tf"),
                "MaintenanceSourceOverlay",
            )
            files[path.name] = git(root, "show", sha + ":" + name)
    require(files and ".terraform.lock.hcl" in files, "MaintenanceSourceFiles")
    require(
        hashed(files[".terraform.lock.hcl"]) == provider_lock_sha256,
        "MaintenanceProviderLockMismatch",
    )
    lock = parse_lock(files[".terraform.lock.hcl"].decode())
    require(
        set(lock) == {"registry.terraform.io/hashicorp/aws"}
        and lock["registry.terraform.io/hashicorp/aws"]["version"] == "6.64.0",
        "MaintenanceProviderSelection",
    )
    return files


def load_evidence(approval, private):
    _, values = approved_json(approval["inputs_path"], approval["inputs_sha256"], private)
    _, adoption = approved_json(approval["adoption_path"], approval["adoption_sha256"], private)
    _, receipt = approved_json(approval["receipt_path"], approval["receipt_sha256"], private)
    require(
        adoption["destination"] == approval["backend"]
        and adoption.get("workspace") == "default"
        and adoption["destination_identity"]["lineage"] == approval["state_identity"]["lineage"]
        and adoption["destination_identity"]["serial"] == approval["state_identity"]["serial"],
        "MaintenanceCanonicalAdoptionMismatch",
    )
    require(
        receipt["identity"] == approval["state_identity"]
        and receipt["resources"] == 32
        and receipt["state_key"] == approval["backend"]["key"]
        and receipt["canonical_adoption_lineage_matches"] is True
        and receipt["active_lock"] is False,
        "MaintenancePriorReceiptMismatch",
    )
    return values


def check_configuration(run, files):
    directory = run / "configuration"
    expected = files | {"backend.tf": S3_BACKEND.encode()}
    require(
        {p.name for p in directory.iterdir()} == expected.keys(),
        "MaintenanceConfigurationExtrasOrLocalState",
    )
    for name, raw in expected.items():
        target = private_path(directory / name, run)
        require(target.is_file() and target.read_bytes() == raw, "MaintenanceConfigurationChanged")
    require(
        not any(
            (run / name).exists() for name in ("terraform.tfstate", "terraform.tfstate.backup")
        ),
        "MaintenanceLocalStateForbidden",
    )
    require(
        (run / "terraform.rc").read_bytes() == b"provider_installation { direct {} }\n"
        and (run / "empty-aws-config").read_bytes() == b"",
        "MaintenanceExecutionConfigChanged",
    )


def check_backend(run, expected):
    metadata = json.loads(private_path(run / "data/terraform.tfstate", run).read_bytes())
    require(
        metadata.get("backend", {}).get("type") == "s3" and not metadata.get("resources"),
        "MaintenanceBackendMetadata",
    )
    config = metadata["backend"]["config"]
    require(
        all(encoded(config.get(k)) == encoded(v) for k, v in expected.items()),
        "MaintenanceBackendMismatch",
    )
    for key, value in config.items():
        if key in expected:
            continue
        require(
            encoded(value) in {b"null", b'""', b"false", b"0", b"[]", b"{}"}
            or key == "workspace_key_prefix"
            and value == "env:/",
            "MaintenanceUnexpectedBackendOption",
        )
    workspace = private_path(run / "data/environment", run)
    require(
        not workspace.exists() or workspace.read_text().strip() == "default", "MaintenanceWorkspace"
    )


def execution_environment(run, parent, session, values):
    require(
        not any(
            k.startswith("AWS_ENDPOINT_URL") or k.startswith("TF_") or k.startswith("TERRAFORM_")
            for k in parent
        ),
        "MaintenanceHiddenEnvironment",
    )
    env = {k: v for k, v in parent.items() if not k.startswith(("AWS_", "P4_"))}
    env = credential_environment(session, env)
    env.update(
        AWS_REGION=values["region"],
        AWS_DEFAULT_REGION=values["region"],
        TF_DATA_DIR=str(run / "data"),
        TF_WORKSPACE="default",
        TF_INPUT="0",
        TF_IN_AUTOMATION="true",
        TF_CLI_CONFIG_FILE=str(run / "terraform.rc"),
        AWS_CONFIG_FILE=str(run / "empty-aws-config"),
        AWS_SHARED_CREDENTIALS_FILE=str(run / "empty-aws-config"),
    )
    for key, value in values.items():
        env["TF_VAR_" + key] = value if isinstance(value, str) else json.dumps(value)
    return env


def terraform(run, env, stage, args):
    """Output is private and exclusive; failure and timeout never call Terraform again."""
    try:
        result = subprocess.run(
            ["terraform", *args],
            cwd=run / "configuration",
            env=env,
            capture_output=True,
            timeout=1200,
        )
    except subprocess.TimeoutExpired as error:
        write_bytes(run / (stage + "-timeout.stdout.private.log"), error.stdout or b"")
        write_bytes(run / (stage + "-timeout.stderr.private.log"), error.stderr or b"")
        write_json(run / (stage + "-timeout.private.json"), {"status": "RESULT_UNKNOWN"})
        require(False, "MaintenanceTerraformResultUnknown")
    write_bytes(run / (stage + ".stdout.private.log"), result.stdout)
    write_bytes(run / (stage + ".stderr.private.log"), result.stderr)
    require(result.returncode == 0, "MaintenanceTerraformFailed")
    return result.stdout


def verify_backend_state(run, env, expected, snapshot, stage):
    check_backend(run, expected)
    raw = terraform(run, env, stage, ["state", "pull"])
    compare_state_snapshot(encoded(snapshot["state"]), raw)


def validate_saved(run, approval, files, values, claim):
    require(str(run) == approval["run_path"], "MaintenanceWrongApplyTarget")
    for name in (
        "binding.private.json",
        "plan-approval.private.json",
        "bootstrap.tfplan",
        "inputs.private.json",
        "backend.private.hcl",
        "review.private.json",
        "snapshot-before.private.json",
    ):
        require(private_path(run / name, run).is_file(), "MaintenanceSavedArtifactUnavailable")
    raw_binding = (run / "binding.private.json").read_bytes()
    require(hashed(raw_binding) == approval["binding_sha256"], "MaintenanceBindingHashMismatch")
    binding = json.loads(raw_binding)
    original_raw = (run / "plan-approval.private.json").read_bytes()
    require(
        hashed(original_raw) == approval["plan_approval_sha256"] == binding["plan_approval_sha256"],
        "MaintenancePlanApprovalMismatch",
    )
    original = json.loads(original_raw)
    excluded = {
        "kind",
        "expires_at",
        "run_path",
        "plan_sha256",
        "binding_sha256",
        "plan_approval_sha256",
        "canonical_state_writes_approved",
        "iam_policy_updates_approved",
    }
    require(
        original["approved"] is True
        and all(original.get(k) == v for k, v in approval.items() if k not in excluded),
        "MaintenanceApplyApprovalTarget",
    )
    require(
        hashed((run / "bootstrap.tfplan").read_bytes())
        == approval["plan_sha256"]
        == binding["plan_sha256"],
        "MaintenancePlanHashMismatch",
    )
    require(
        binding["source_sha"] == approval["source_sha"]
        and binding["state_identity"] == approval["state_identity"]
        and binding["backend"] == approval["backend"]
        and binding["source_files"] == {k: hashed(v) for k, v in files.items()}
        and binding["inputs_sha256"] == approval["inputs_sha256"]
        and binding["run_path"] == str(run),
        "MaintenanceSavedBindingMismatch",
    )
    require(
        hashed((run / "inputs.private.json").read_bytes()) == approval["inputs_sha256"]
        and json.loads((run / "inputs.private.json").read_bytes()) == values,
        "MaintenanceSavedInputsChanged",
    )
    require(
        hashed((run / "backend.private.hcl").read_bytes()) == binding["backend_hcl_sha256"]
        and (run / "backend.private.hcl").read_text() == backend_hcl(approval["backend"]),
        "MaintenanceSavedBackendChanged",
    )
    review_raw = (run / "review.private.json").read_bytes()
    require(hashed(review_raw) == binding["review_sha256"], "MaintenanceSavedReviewChanged")
    state = json.loads((run / "snapshot-before.private.json").read_bytes())
    check_snapshot(state, approval)
    audit_plan(
        json.loads(review_raw), state["state"], values, approval["account_id"], approval["region"]
    )
    completed = json.loads((claim / "plan-completed.private.json").read_bytes())
    require(
        completed
        == {
            "run_path": str(run),
            "binding_sha256": approval["binding_sha256"],
            "plan_sha256": approval["plan_sha256"],
        },
        "MaintenancePlanNotCompleted",
    )
    require(not (claim / "apply-started.private.json").exists(), "MaintenanceApplyAlreadyAttempted")
    check_configuration(run, files)
    return binding


def execute(
    operation, approval_path, approval_hash, directory, *, repository=PROJECT, environment=None
):
    require(operation in {"inspect", "plan", "apply"}, "MaintenanceOperation")
    root = Path(repository).resolve()
    home = home_repository(root)
    private = home / ".p4-artifacts"
    require(
        private.is_dir() and not (private / "bootstrap-operation.lock").exists(),
        "MaintenanceOperationLocked",
    )
    parent = dict(os.environ if environment is None else environment)
    require(
        not any(
            k.startswith("AWS_ENDPOINT_URL") or k.startswith("TF_") or k.startswith("TERRAFORM_")
            for k in parent
        ),
        "MaintenanceHiddenEnvironment",
    )
    require(
        parent.get("GITHUB_ACTIONS") != "true" and parent.get("CI", "").lower() != "true",
        "MaintenanceLocalOperatorRequired",
    )
    account, region = account_settings(home)
    raw, approval = approved_json(approval_path, approval_hash, private)
    kind = "apply" if operation == "apply" else "plan"
    validate_approval(approval, kind, account, region)
    if operation != "inspect":
        require(
            approval["approved"] is True
            and parent.get("P4_BOOTSTRAP_MAINTENANCE_EXECUTION_READY") == "true",
            "MaintenanceSeparateExplicitApprovalRequired",
        )
    values = load_evidence(approval, private)
    files = source_files(root, approval, require_main=operation != "inspect")
    run = private_path(directory, private)
    require(run.parent.is_dir(), "MaintenanceRunParentRequired")
    session = checked_session(
        account,
        region,
        environment=dict(parent, AWS_PROFILE=read_local_settings(home)["AWS_PROFILE"]),
    )
    reader = BootstrapAWS(session, account, region)
    actor = reader.actor(approval["principal_role_arn"])
    snapshot = reader.snapshot()
    check_snapshot(snapshot, approval)
    validate_inputs(values, snapshot["state"], account, region)
    reader.verify_resources(snapshot["state"], values)
    if operation == "inspect":
        secure_directory(run)
        write_json(
            run / "inspection.private.json",
            {
                "snapshot": snapshot,
                "actor": actor,
                "source_sha": approval["source_sha"],
                "source_files": {k: hashed(v) for k, v in files.items()},
                "simulation": reader.simulate_addition(),
                "aws_writes": 0,
            },
        )
        return {"status": "BOOTSTRAP_MAINTENANCE_INSPECT_PASS", "aws_writes": 0}
    namespace = hashed(encoded(backend(account, region)))
    ledger = private / "bootstrap-maintenance-ledger"
    if not ledger.exists():
        secure_directory(ledger)
    claim = private_path(ledger / namespace, private)
    if operation == "plan":
        require(not claim.exists() and not run.exists(), "MaintenancePlanAlreadyAttempted")
    else:
        validate_saved(run, approval, files, values, claim)
    with bootstrap_lock(private):
        # Re-read after acquiring the local operation lock; never adopt a newer version.
        latest = reader.snapshot()
        check_snapshot(latest, approval)
        require(
            latest["versions"] == snapshot["versions"], "MaintenanceStateVersionInventoryChanged"
        )
        reader.verify_resources(latest["state"], values)
        if operation == "plan":
            secure_directory(claim)
            write_json(
                claim / "plan-started.private.json",
                {
                    "run_path": str(run),
                    "approval_sha256": approval_hash,
                    "state_identity": snapshot["identity"],
                    "started_at": datetime.now(UTC).isoformat(),
                },
            )
            secure_directory(run)
            secure_directory(run / "configuration")
            secure_directory(run / "data")
            for name, content in files.items():
                write_bytes(run / "configuration" / name, content)
            write_bytes(run / "configuration/backend.tf", S3_BACKEND.encode())
            write_bytes(run / "backend.private.hcl", backend_hcl(approval["backend"]).encode())
            input_raw = private_path(approval["inputs_path"], private).read_bytes()
            require(hashed(input_raw) == approval["inputs_sha256"], "MaintenanceInputsChanged")
            write_bytes(run / "inputs.private.json", input_raw)
            write_bytes(run / "plan-approval.private.json", raw)
            write_json(run / "snapshot-before.private.json", snapshot)
            write_bytes(run / "terraform.rc", b"provider_installation { direct {} }\n")
            write_bytes(run / "empty-aws-config", b"")
        env = execution_environment(run, parent, session, values)
        check_configuration(run, files)
        try:
            version = json.loads(terraform(run, env, operation + "-version", ["version", "-json"]))
            require(version["terraform_version"] == TF_VERSION, "MaintenanceTerraformVersion")
            if operation == "plan":
                # Fresh data/configuration contain no local State. reconfigure never migrates State.
                terraform(
                    run,
                    env,
                    "init",
                    [
                        "init",
                        "-input=false",
                        "-reconfigure",
                        "-lockfile=readonly",
                        "-lock=true",
                        "-lock-timeout=0s",
                        "-backend-config=" + str(run / "backend.private.hcl"),
                    ],
                )
                check_configuration(run, files)
                verify_backend_state(run, env, approval["backend"], snapshot, "post-init-pull")
                initialized = reader.snapshot()
                check_snapshot(initialized, approval)
                require(
                    initialized["versions"] == snapshot["versions"],
                    "MaintenanceInitWroteCanonicalState",
                )
                reader.verify_resources(initialized["state"], values)
                terraform(
                    run,
                    env,
                    "plan",
                    [
                        "plan",
                        "-input=false",
                        "-lock=true",
                        "-lock-timeout=0s",
                        "-out=" + str(run / "bootstrap.tfplan"),
                    ],
                )
                review_raw = terraform(
                    run, env, "show", ["show", "-json", str(run / "bootstrap.tfplan")]
                )
                summary = audit_plan(
                    json.loads(review_raw), snapshot["state"], values, account, region
                )
                after = reader.snapshot()
                check_snapshot(after, approval)
                require(
                    after["versions"] == snapshot["versions"], "MaintenancePlanWroteCanonicalState"
                )
                reader.verify_resources(after["state"], values)
                check_configuration(run, files)
                check_backend(run, approval["backend"])
                write_bytes(run / "review.private.json", review_raw)
                write_json(run / "snapshot-after-plan.private.json", after)
                write_json(run / "summary.private.json", summary)
                binding = {
                    "schema_version": 1,
                    "run_path": str(run),
                    "source_sha": approval["source_sha"],
                    "source_files": {k: hashed(v) for k, v in files.items()},
                    "state_identity": snapshot["identity"],
                    "versions": snapshot["versions"],
                    "backend": approval["backend"],
                    "inputs_sha256": approval["inputs_sha256"],
                    "backend_hcl_sha256": hashed((run / "backend.private.hcl").read_bytes()),
                    "plan_approval_sha256": approval_hash,
                    "plan_sha256": hashed((run / "bootstrap.tfplan").read_bytes()),
                    "review_sha256": hashed(review_raw),
                    "actor": actor,
                }
                write_json(run / "binding.private.json", binding)
                write_json(
                    claim / "plan-completed.private.json",
                    {
                        "run_path": str(run),
                        "plan_sha256": binding["plan_sha256"],
                        "binding_sha256": hashed((run / "binding.private.json").read_bytes()),
                    },
                )
                return {
                    "status": "BOOTSTRAP_MAINTENANCE_PLAN_REVIEWED_WAITING_APPLY_APPROVAL",
                    "plan_sha256": binding["plan_sha256"],
                    **summary,
                }
            binding = validate_saved(run, approval, files, values, claim)
            require(
                latest["versions"] == binding["versions"], "MaintenanceApplyStateVersionsChanged"
            )
            verify_backend_state(run, env, approval["backend"], latest, "pre-apply-pull")
            regenerated = terraform(
                run, env, "pre-apply-show", ["show", "-json", str(run / "bootstrap.tfplan")]
            )
            audit_plan(json.loads(regenerated), latest["state"], values, account, region)
            immediate = reader.snapshot()
            check_snapshot(immediate, approval)
            require(
                immediate["versions"] == binding["versions"], "MaintenanceApplyStateVersionsChanged"
            )
            reader.verify_resources(immediate["state"], values)
            validate_saved(run, approval, files, values, claim)
            final_raw, final_approval = approved_json(approval_path, approval_hash, private)
            require(final_raw == raw and final_approval == approval, "MaintenanceApprovalChanged")
            validate_approval(final_approval, "apply", account, region)
            write_json(
                claim / "apply-started.private.json",
                {
                    "run_path": str(run),
                    "plan_sha256": approval["plan_sha256"],
                    "approval_sha256": approval_hash,
                    "started_at": datetime.now(UTC).isoformat(),
                },
            )
            # Journal fsync/ACL work must not consume the remaining approval lifetime.
            final_raw, final_approval = approved_json(approval_path, approval_hash, private)
            require(final_raw == raw and final_approval == approval, "MaintenanceApprovalChanged")
            validate_approval(final_approval, "apply", account, region)
            terraform(
                run,
                env,
                "apply",
                [
                    "apply",
                    "-input=false",
                    "-lock=true",
                    "-lock-timeout=0s",
                    str(run / "bootstrap.tfplan"),
                ],
            )
            after = reader.snapshot()
            check_applied(snapshot["state"], after["state"], account, region)
            require(
                all(x in after["versions"] for x in snapshot["versions"])
                and all(
                    x["kind"] == "Versions"
                    for x in after["versions"]
                    if x not in snapshot["versions"]
                ),
                "MaintenanceApplyVersionInventory",
            )
            reader.verify_resources(after["state"], values)
            verify_backend_state(run, env, approval["backend"], after, "post-apply-pull")
            check_configuration(run, files)
            write_json(run / "snapshot-after-apply.private.json", after)
            write_json(
                claim / "apply-completed.private.json",
                {
                    "run_path": str(run),
                    "plan_sha256": approval["plan_sha256"],
                    "state_identity": after["identity"],
                    "iam_readback": "PASS",
                },
            )
            return {"status": "BOOTSTRAP_MAINTENANCE_APPLY_VERIFIED", "updated": 2}
        except Exception:
            try:
                diagnosis = reader.diagnose()
            except Exception:
                diagnosis = {"status": "READ_ONLY_DIAGNOSIS_UNAVAILABLE", "repair_attempted": False}
            write_json(
                run / (operation + "-failure.private.json"),
                {
                    "status": "READ_ONLY_DIAGNOSIS_REQUIRED",
                    "retry_allowed": False,
                    "diagnosis": diagnosis,
                },
            )
            raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("inspect", "plan", "apply"))
    parser.add_argument("--approval", required=True)
    parser.add_argument("--approval-sha256", required=True)
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()
    try:
        result = execute(args.operation, args.approval, args.approval_sha256, args.directory)
    except Exception:
        # AWS/Terraform exceptions and file paths can carry private data; do not print them.
        print(
            json.dumps(
                {
                    "status": "BOOTSTRAP_MAINTENANCE_STOPPED",
                    "next": "READ_ONLY_DIAGNOSIS",
                    "retry_allowed": False,
                }
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
