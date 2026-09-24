"""Read-only recovery handoff verification; reuse the bootstrap migration engine.

No ordinary bootstrap journal is synthesized. A separately reviewed, hash-pinned
handoff binds the actual recovery evidence and the exact operational State path.
"""

import argparse
import json
import os
from pathlib import Path

import bootstrap_state as bootstrap

from interview_backend.deployment import DeploymentError


def require(condition, code="RecoveryHandoffMismatch"):
    if not condition:
        raise DeploymentError(code)


def read(path):
    return json.loads(Path(path).read_bytes())


def hashed(path):
    return bootstrap.digest_bytes(Path(path).read_bytes())


def canonical_backend(account, region, state):
    bucket = state["outputs"]["state_bucket"]["value"]
    require(bucket == f"ai-interview-state-{account}-{region}")
    managed = [
        i["attributes"]["id"]
        for r in state["resources"]
        if r["type"] == "aws_s3_bucket" and r["name"] == "storage"
        for i in r["instances"]
        if i.get("index_key") == "state"
    ]
    require(managed == [bucket])
    return {
        "bucket": bucket,
        "key": "dev/terraform.tfstate",
        "region": region,
        "encrypt": True,
        "use_lockfile": True,
        "allowed_account_ids": [account],
    }


def backend_hcl(settings):
    return "".join(f"{key} = {json.dumps(value)}\n" for key, value in settings.items())


def validate_handoff(path, approved_hash, account, region, *, migrated=False):
    private = (bootstrap.PROJECT / ".p4-artifacts").resolve()
    path = bootstrap.private_path(path, private)
    require(hashed(path) == approved_hash, "ApprovedRecoveryHandoffRequired")
    binding = read(path)
    require(binding["schema_version"] == 1 and binding["kind"] == "recovery-migration")
    require(binding["account_id"] == account and binding["region"] == region)
    require(binding["workspace"] == "default")

    def checked(name):
        item = binding["evidence"][name]
        target = bootstrap.private_path(item["path"], private)
        require(hashed(target) == item["sha256"])
        return target

    state_path = bootstrap.private_path(binding["source_state"], private)
    require(str(state_path) == binding["source_state"])
    run = state_path.parent
    require(state_path.name == "terraform.tfstate" and run.name == "run")
    require(run.parent == checked("start").parent)
    raw = checked("backup").read_bytes()
    require(bootstrap.digest_bytes(raw) == binding["state_sha256"])
    if not migrated:
        require(state_path.read_bytes() == raw)
    lineage, serial, resources, _ = bootstrap._state_identity(raw)
    count = sum(len(r["instances"]) for r in resources)
    require(lineage == binding["lineage"] and serial == binding["serial"] == 34)
    require(count == binding["instance_count"] == 32)
    state = json.loads(raw)
    destination = canonical_backend(account, region, state) | {"key": bootstrap.STATE_KEY}
    require(binding["destination"] == destination)
    require(read(checked("preflight"))["state"]["lineage"] == lineage)
    pre = read(checked("preflight"))
    require(pre["state"]["serial"] == 33 and pre["state"]["instance_count"] == 32)
    require(hashed(checked("inputs")) == pre["new_input_sha256"])
    require(
        checked("dev_backend").read_text(encoding="utf-8")
        == backend_hcl(canonical_backend(account, region, state))
    )
    require(pre["four_way_subject_match"] is True)
    require(pre["unchanged_account_region_ses_buckets_repository_environment"] is True)
    bootstrap.validate_configuration(run)
    expected_tf = {name for name in pre["configuration_sha256"] if name.endswith(".tf")}
    require(
        {p.name for p in run.glob("*.tf")} == expected_tf | ({"backend.tf"} if migrated else set())
    )
    for name, digest in pre["configuration_sha256"].items():
        require(Path(name).name == name)
        require(hashed(run / name) == digest)
        require(hashed(bootstrap.PROJECT / "terraform/bootstrap" / name) == digest)
    start, done = read(checked("start")), read(checked("apply"))
    require(
        (checked("start").parent / start["execution_directory"]).resolve()
        == checked("apply").parent
    )
    require(checked("readback").parent == checked("normal").parent == checked("apply").parent)
    require(
        checked("inputs").parent == checked("refresh_plan").parent == checked("preflight").parent
    )
    require(start["plan_sha256"] == done["plan_sha256"] == hashed(checked("refresh_plan")))
    require(start["plan_sha256"] == binding["refresh_plan_sha256"])
    rb = read(checked("readback"))
    require(rb["state_sha256"] == binding["state_sha256"])
    require(rb["state"]["lineage"] == lineage and rb["state"]["serial"] == serial)
    require(rb["state"]["instance_count"] == count)
    require(rb["normalized_six_differences_resolved"] and rb["aws_snapshot_unchanged"])
    require(
        all(
            rb[k] == 0
            for k in ("resource_id_changes", "apply_added", "apply_changed", "apply_destroyed")
        )
    )
    normal = read(checked("normal"))
    require(normal["complete_no_op"] and normal["normal_plan_success"])
    require(normal["addresses_retained"] and normal["planned_instances"] == 32)
    require(
        all(
            normal[k] == 0
            for k in ("add", "change", "destroy", "replace", "outputs_changed", "drift_count")
        )
    )
    require(not normal["normal_apply_executed"] and not normal["s3_migration_executed"])
    require(hashed(checked("normal_plan")) == normal["normal_plan_sha256"])
    require(read(checked("normal_exit"))["return_code"] == 0)
    require(not (run / ".terraform.tfstate.lock.info").exists(), "RecoveryLocked")
    workspace = run / ".terraform/environment"
    require(not workspace.exists() or workspace.read_text().strip() == "default")
    if not migrated:
        require(
            not any(
                (run / n).exists()
                for n in (
                    "backend.tf",
                    "migration-attempt.json",
                    "migration-receipt.json",
                    "pre-migration.tfstate",
                )
            ),
            "RecoveryMigrationAlreadyStarted",
        )
        metadata = run / ".terraform/terraform.tfstate"
        if metadata.exists():
            require(read(metadata).get("backend", {}).get("type", "local") == "local")
    else:
        require((run / "backend.tf").read_text(encoding="utf-8") == bootstrap.S3_BACKEND)
        metadata = read(run / ".terraform/terraform.tfstate")["backend"]
        require(metadata["type"] == "s3")
        require(all(metadata["config"].get(k) == v for k, v in destination.items()))
    return binding, state, checked("inputs"), run


def vacant_destination(session, destination, account):
    """Reject history, delete markers and locks, not just the current HEAD."""
    bootstrap.migration_target(
        account, destination["region"], destination["bucket"], session=session
    )
    s3 = session.client("s3", region_name=destination["region"])
    for key in (bootstrap.STATE_KEY, "dev/terraform.tfstate"):
        for page in s3.get_paginator("list_object_versions").paginate(
            Bucket=destination["bucket"], Prefix=key, ExpectedBucketOwner=account
        ):
            require(
                not any(
                    item["Key"] in {key, key + ".tflock"}
                    for field in ("Versions", "DeleteMarkers")
                    for item in page.get(field, [])
                ),
                "RecoveryDestinationOccupied",
            )


def inspect(path, approved_hash, environment=None, *, migrated=False):
    parent = dict(os.environ if environment is None else environment)
    account, region = bootstrap.account_settings(bootstrap.PROJECT, parent)
    require(
        not (bootstrap.PROJECT / ".p4-artifacts/bootstrap-operation.lock").exists(),
        "RecoveryLocked",
    )
    binding, state, inputs_path, run = validate_handoff(
        path, approved_hash, account, region, migrated=migrated
    )
    backend_path = bootstrap.PROJECT / "terraform/environments/dev/backend-dev.hcl"
    public_lines = [
        line.strip()
        for line in backend_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    public_expected = backend_hcl(
        {
            k: v
            for k, v in canonical_backend(account, region, state).items()
            if k not in {"bucket", "allowed_account_ids"}
        }
    )
    require(public_lines == public_expected.splitlines(), "DevBackendConfigurationMismatch")
    values = bootstrap.inputs(inputs_path, account, region)
    env = bootstrap.input_environment(run, parent, account, region, values)
    profile = bootstrap.read_local_settings(bootstrap.PROJECT).get("AWS_PROFILE")
    if profile and not env.get("AWS_ACCESS_KEY_ID"):
        require(env.get("AWS_PROFILE", profile) == profile)
        env["AWS_PROFILE"] = profile
    session = bootstrap.checked_session(account, region, environment=env)
    env = bootstrap.credential_environment(session, env)
    env["TF_DATA_DIR"] = str(run / ".terraform")
    env["TF_WORKSPACE"] = "default"
    version = json.loads(bootstrap.run(["terraform", "version", "-json"], cwd=run, env=env))
    require(version["terraform_version"] == bootstrap.TF_VERSION)
    require(
        version.get("provider_selections", {}).get("registry.terraform.io/hashicorp/aws")
        == "6.64.0"
    )
    if not migrated:
        vacant_destination(session, binding["destination"], account)
    bootstrap.verify_created_resources(
        session, {k: v["value"] for k, v in state["outputs"].items()}, account, region, values
    )
    return binding, state, run, env, session


def execute(operation, path, approved_hash, *, approve_force_copy=False):
    require(operation in {"inspect", "migrate", "verify"})
    binding, state, run, env, session = inspect(path, approved_hash, migrated=operation == "verify")
    if operation == "inspect":
        return {
            "status": "recovery_preconditions_passed",
            "readiness": "approval_and_clean_ci_required",
        }
    bootstrap.prerequisites(env)
    sha = bootstrap.checked_source(bootstrap.PROJECT, env)
    require(
        bootstrap.run(["git", "rev-parse", "origin/main"], cwd=bootstrap.PROJECT, env=env)
        .decode()
        .strip()
        == sha
    )
    private = bootstrap.PROJECT / ".p4-artifacts"
    with bootstrap.bootstrap_lock(private):
        # Revalidate the exact State under the same lock used by normal bootstrap.
        validate_handoff(
            path,
            approved_hash,
            binding["account_id"],
            binding["region"],
            migrated=operation == "verify",
        )
        if operation == "migrate":
            require(approve_force_copy, "ExplicitForceCopyApprovalRequired")
            vacant_destination(session, binding["destination"], binding["account_id"])
            bootstrap.write_record(
                run / "migration-attempt.json", {"recovery_handoff_sha256": approved_hash}
            )
            bootstrap.migrate_state(
                run,
                env,
                run / "terraform.tfstate",
                binding["destination"]["bucket"],
                binding["account_id"],
                binding["region"],
                session=session,
            )
            return {"status": "bootstrap_migration_verification_pending"}
        require(read(run / "migration-attempt.json") == {"recovery_handoff_sha256": approved_hash})
        original = (run / "pre-migration.tfstate").read_bytes()
        require(bootstrap.digest_bytes(original) == binding["state_sha256"])
        version, remote = bootstrap.verify_state_version(
            session, binding["destination"]["bucket"], binding["account_id"], original
        )
        pulled = bootstrap.run(["terraform", "state", "pull"], cwd=run, env=env)
        require(bootstrap._state_identity(pulled) == bootstrap._state_identity(original))
        plan = run / "migration-normal.tfplan"
        require(not plan.exists() and not (run / "migration-receipt.json").exists())
        bootstrap.run(
            ["terraform", "plan", "-input=false", "-detailed-exitcode", f"-out={plan}"],
            cwd=run,
            env=env,
        )
        review = json.loads(
            bootstrap.run(["terraform", "show", "-json", str(plan)], cwd=run, env=env)
        )
        bootstrap.write_record(run / "migration-normal-review.private.json", review)
        require(not review.get("resource_drift"))
        require(
            all(r["change"]["actions"] == ["no-op"] for r in review.get("resource_changes", []))
        )
        require(all(r["actions"] == ["no-op"] for r in review.get("output_changes", {}).values()))
        later_version, later_remote = bootstrap.verify_state_version(
            session, binding["destination"]["bucket"], binding["account_id"], original
        )
        require(later_version == version and later_remote == remote)
        require((run / "pre-migration.tfstate").read_bytes() == original)
        bootstrap.write_record(
            run / "migration-receipt.json",
            {
                "schema_version": 1,
                "source_sha": bootstrap.checked_source(bootstrap.PROJECT, env),
                "state_key": bootstrap.STATE_KEY,
                "state_version_id": version,
                "local_state_sha256": bootstrap.digest_bytes(original),
                "remote_state_sha256": bootstrap.digest_bytes(remote),
                "backup_preserved": True,
                "recovery_handoff_sha256": approved_hash,
                "normal_plan_sha256": hashed(plan),
            },
        )
        return {"status": "bootstrap_state_migrated"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("inspect", "migrate", "verify"))
    parser.add_argument("--handoff", required=True)
    parser.add_argument("--handoff-sha256", required=True)
    parser.add_argument("--approve-force-copy", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(
            args.operation,
            args.handoff,
            args.handoff_sha256,
            approve_force_copy=args.approve_force_copy,
        )
    except Exception:
        print(json.dumps({"status": "failed", "reason": "RecoveryMigrationChecksFailed"}))
        raise SystemExit(1) from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
