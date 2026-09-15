"""Create bootstrap resources locally, verify them, then migrate State to S3.

The command is intentionally local-only because the OIDC roles it creates do not
exist yet. It never prints Terraform output and keeps both the original local
State and an immutable pre-migration copy in a private run directory.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

from interview_backend.deployment import (
    DeploymentError,
    account_settings,
    checked_session,
    credential_environment,
    read_local_settings,
    terraform_environment,
)

PROJECT = Path(__file__).resolve().parents[3]
TF_VERSION = "1.14.9"
REPOSITORY = "yonegen0/ai_interview"
STATE_KEY = "bootstrap/terraform.tfstate"
S3_BACKEND = 'terraform {\n  backend "s3" {}\n}\n'
INPUT_KEYS = frozenset(
    {
        "oidc_provider_arn",
        "oidc_subjects",
        "ses_identity_type",
        "ses_from_email",
        "ses_domain",
    }
)
ROLE_NAMES = ("artifact", "plan", "deploy", "test")
SUBJECT = re.compile(r"repo:yonegen0(?:@[0-9]+)?/ai_interview(?:@[0-9]+)?:environment:dev")


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def run(command, *, cwd, env):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, check=False)
    if result.returncode:
        raise DeploymentError("TerraformOperationFailed")
    return result.stdout


def prerequisites(environment):
    if environment.get("GITHUB_ACTIONS") == "true" or environment.get("CI", "").lower() == "true":
        raise DeploymentError("LocalBootstrapRequired")
    if (
        environment.get("P4_AWS_EXECUTION_READY") != "true"
        or environment.get("P4_BOOTSTRAP_STATE_READY") != "true"
    ):
        raise DeploymentError("BootstrapExecutionPrerequisitesUnconfirmed")
    if any(key.startswith("AWS_ENDPOINT_URL") for key in environment):
        raise DeploymentError("AwsEndpointOverrideForbidden")


def checked_source(root, environment):
    sha = run(["git", "rev-parse", "HEAD"], cwd=root, env=environment).decode().strip()
    branch = run(["git", "branch", "--show-current"], cwd=root, env=environment).decode().strip()
    remote = (
        run(["git", "config", "--get", "remote.origin.url"], cwd=root, env=environment)
        .decode()
        .strip()
    )
    dirty = run(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, env=environment
    )
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or branch != "main" or dirty.strip():
        raise DeploymentError("CleanCommittedMainRequired")
    if remote not in {
        f"https://github.com/{REPOSITORY}.git",
        f"https://github.com/{REPOSITORY}",
        f"git@github.com:{REPOSITORY}.git",
    }:
        raise DeploymentError("RepositoryMismatch")
    return sha


def inputs(path, account, region):
    try:
        values = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError, UnicodeError, json.JSONDecodeError:
        raise DeploymentError("BootstrapInputsUnavailable") from None
    if not isinstance(values, dict) or values.keys() != INPUT_KEYS:
        raise DeploymentError("ExplicitBootstrapInputsRequired")
    subjects = values.get("oidc_subjects")
    if (
        not isinstance(subjects, dict)
        or set(subjects) != set(ROLE_NAMES)
        or any(
            not isinstance(value, str) or SUBJECT.fullmatch(value) is None
            for value in subjects.values()
        )
    ):
        raise DeploymentError("VerifiedOidcSubjectsRequired")
    provider = values.get("oidc_provider_arn")
    if not isinstance(provider, str) or provider not in {
        "",
        f"arn:aws:iam::{account}:oidc-provider/token.actions.githubusercontent.com",
    }:
        raise DeploymentError("OidcProviderMismatch")
    identity_type = values.get("ses_identity_type")
    email = values.get("ses_from_email")
    domain = values.get("ses_domain")
    if identity_type not in {"email", "domain"}:
        raise DeploymentError("InvalidSesIdentity")
    if not isinstance(email, str) or re.fullmatch(r"[^@\s]+@[^@\s]+", email) is None:
        raise DeploymentError("InvalidSesIdentity")
    if not isinstance(domain, str) or (
        identity_type == "domain"
        and (
            re.fullmatch(r"[A-Za-z0-9.-]+\.[A-Za-z]+", domain) is None
            or not email.endswith("@" + domain)
        )
    ):
        raise DeploymentError("InvalidSesIdentity")
    return dict(values) | {"account_id": account, "region": region}


def _output_values(raw):
    try:
        decoded = json.loads(raw)
        return {key: item["value"] for key, item in decoded.items()}
    except json.JSONDecodeError, TypeError, KeyError, AttributeError:
        raise DeploymentError("BootstrapOutputInvalid") from None


def _bucket_hardened(client, bucket):
    client.head_bucket(Bucket=bucket)
    if client.get_bucket_versioning(Bucket=bucket).get("Status") != "Enabled":
        return False
    encryption = client.get_bucket_encryption(Bucket=bucket)
    rules = encryption.get("ServerSideEncryptionConfiguration", {}).get("Rules", [])
    if not any(
        rule.get("ApplyServerSideEncryptionByDefault", {}).get("SSEAlgorithm") == "AES256"
        for rule in rules
    ):
        return False
    policy = json.loads(client.get_bucket_policy(Bucket=bucket)["Policy"])
    if not any(
        statement.get("Effect") == "Deny"
        and statement.get("Principal") == "*"
        and statement.get("Action") == "s3:*"
        and set(statement.get("Resource", []))
        == {f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"}
        and statement.get("Condition", {}).get("Bool", {}).get("aws:SecureTransport") == "false"
        for statement in policy.get("Statement", [])
    ):
        return False
    block = client.get_public_access_block(Bucket=bucket).get("PublicAccessBlockConfiguration", {})
    return all(
        block.get(name) is True
        for name in (
            "BlockPublicAcls",
            "IgnorePublicAcls",
            "BlockPublicPolicy",
            "RestrictPublicBuckets",
        )
    )


def verify_created_resources(session, outputs, account, region, values=None):
    expected = {
        "state_bucket": f"ai-interview-state-{account}-{region}",
        "artifact_bucket": f"ai-interview-artifacts-{account}-{region}",
        "boundary_arn": f"arn:aws:iam::{account}:policy/ai-interview-runtime-boundary",
        "oidc_provider_arn": (
            f"arn:aws:iam::{account}:oidc-provider/token.actions.githubusercontent.com"
        ),
        "roles": {
            name: f"arn:aws:iam::{account}:role/ai-interview-ci-{name}" for name in ROLE_NAMES
        },
    }
    try:
        if any(outputs.get(key) != value for key, value in expected.items()):
            raise ValueError
        identity = outputs["ses_identity_arn"]
        prefix = f"arn:aws:ses:{region}:{account}:identity/"
        if not isinstance(identity, str) or not identity.startswith(prefix):
            raise ValueError
        s3 = session.client("s3", region_name=region)
        for name in ("state_bucket", "artifact_bucket"):
            s3.head_bucket(Bucket=outputs[name], ExpectedBucketOwner=account)
            if (
                s3.get_bucket_location(Bucket=outputs[name], ExpectedBucketOwner=account).get(
                    "LocationConstraint"
                )
                != region
            ):
                raise ValueError
        if not all(
            _bucket_hardened(s3, outputs[name]) for name in ("state_bucket", "artifact_bucket")
        ):
            raise ValueError
        iam = session.client("iam", region_name=region)
        from bootstrap_contract import boundary_policy, canonical_policy, trust_policy

        policy = iam.get_policy(PolicyArn=outputs["boundary_arn"])["Policy"]
        if policy["Arn"] != expected["boundary_arn"]:
            raise ValueError
        version = iam.get_policy_version(
            PolicyArn=policy["Arn"], VersionId=policy["DefaultVersionId"]
        )["PolicyVersion"]
        if not version["IsDefaultVersion"] or canonical_policy(
            version["Document"]
        ) != canonical_policy(boundary_policy(account, region)):
            raise ValueError
        provider = iam.get_open_id_connect_provider(
            OpenIDConnectProviderArn=outputs["oidc_provider_arn"]
        )
        if provider["Url"] != "token.actions.githubusercontent.com" or provider["ClientIDList"] != [
            "sts.amazonaws.com"
        ]:
            raise ValueError
        for name in ROLE_NAMES:
            role = iam.get_role(RoleName=f"ai-interview-ci-{name}")["Role"]
            if (
                role["Arn"] != expected["roles"][name]
                or role.get("PermissionsBoundary") is not None
                or role["MaxSessionDuration"] != 7200
                or canonical_policy(role["AssumeRolePolicyDocument"])
                != canonical_policy(
                    trust_policy(expected["oidc_provider_arn"], values["oidc_subjects"][name])
                )
            ):
                raise ValueError
        ses = session.client("ses", region_name=region)
        identity_name = identity.removeprefix(prefix)
        if (
            identity_name
            != values["ses_from_email" if values["ses_identity_type"] == "email" else "ses_domain"]
        ):
            raise ValueError
        observed = ses.get_identity_verification_attributes(Identities=[identity_name])
        status = observed["VerificationAttributes"][identity_name]["VerificationStatus"]
        if status not in {"Pending", "Success", "Failed", "TemporaryFailure", "NotStarted"}:
            raise ValueError
        return {"ses_identity_exists": True, "ses_verification": status, "ses_sending": "not_run"}
    except Exception:
        raise DeploymentError("BootstrapReadbackFailed") from None


def _state_identity(raw):
    try:
        state = json.loads(raw)
        lineage = state["lineage"]
        serial = state["serial"]
        resources = state["resources"]
        if (
            not isinstance(lineage, str)
            or not lineage
            or type(serial) is not int
            or serial < 0
            or not isinstance(resources, list)
            or not isinstance(state.get("outputs", {}), dict)
        ):
            raise ValueError
        return lineage, serial, resources, state.get("outputs", {})
    except json.JSONDecodeError, KeyError, TypeError, ValueError:
        raise DeploymentError("TerraformStateInvalid") from None


def migration_target(account, region, bucket, *, session=None):
    """Reject occupied or unreadable destinations before Terraform can copy State."""
    from botocore.exceptions import ClientError

    session = session or checked_session(account, region)
    s3 = session.client("s3", region_name=region)
    if bucket != f"ai-interview-state-{account}-{region}":
        raise DeploymentError("BootstrapStateBucketMismatch")
    s3.head_bucket(Bucket=bucket, ExpectedBucketOwner=account)
    if (
        s3.get_bucket_location(Bucket=bucket, ExpectedBucketOwner=account).get("LocationConstraint")
        != region
    ):
        raise DeploymentError("BootstrapStateRegionMismatch")
    if not _bucket_hardened(s3, bucket):
        raise DeploymentError("BootstrapReadbackFailed")
    try:
        s3.head_object(Bucket=bucket, Key=STATE_KEY, ExpectedBucketOwner=account)
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") not in {"404", "NoSuchKey"}:
            raise DeploymentError("BootstrapStateDestinationUnconfirmed") from None
    else:
        raise DeploymentError("BootstrapStateAlreadyExists")


def migrate_state(
    root,
    environment,
    local_state,
    bucket,
    account,
    region,
    *,
    resume=False,
    session=None,
    backup_prepared=False,
):
    migration_target(account, region, bucket, **({"session": session} if session else {}))
    local_state = Path(local_state)
    original = local_state.read_bytes()
    _state_identity(original)
    backup = Path(root) / "pre-migration.tfstate"
    if resume or backup_prepared:
        if not backup.is_file() or backup.read_bytes() != original:
            raise DeploymentError("BootstrapBackupMismatch")
    else:
        with backup.open("xb") as stream:
            stream.write(original)
            stream.flush()
            os.fsync(stream.fileno())
    backend = Path(root) / "backend.tf"
    if resume:
        # Only after confirmed remote absence and exact local/backup equality.
        # Interrupted init may already have changed local backend metadata.
        if backend.exists():
            if backend.read_text(encoding="utf-8") != S3_BACKEND:
                raise DeploymentError("BootstrapBackendConfigurationConflict")
            saved = Path(root) / "pre-resume.backend.txt"
            if saved.exists() and saved.read_text(encoding="utf-8") != S3_BACKEND:
                raise DeploymentError("BootstrapBackendConfigurationConflict")
            backend.replace(saved)
        run(
            ["terraform", "init", "-reconfigure", "-input=false", "-lockfile=readonly"],
            cwd=root,
            env=environment,
        )
        if local_state.read_bytes() != original:
            raise DeploymentError("BootstrapBackupMismatch")
        migration_target(account, region, bucket, **({"session": session} if session else {}))
    if backend.exists():
        if backend.read_text(encoding="utf-8") != S3_BACKEND:
            raise DeploymentError("BootstrapBackendConfigurationConflict")
    else:
        with backend.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(S3_BACKEND)
    run(
        [
            "terraform",
            "init",
            "-input=false",
            "-lockfile=readonly",
            "-migrate-state",
            "-force-copy",
            f"-backend-config=bucket={bucket}",
            f"-backend-config=key={STATE_KEY}",
            f"-backend-config=region={region}",
            '-backend-config=allowed_account_ids=["' + account + '"]',
            "-backend-config=encrypt=true",
            "-backend-config=use_lockfile=true",
        ],
        cwd=root,
        env=environment,
    )
    remote = run(["terraform", "state", "pull"], cwd=root, env=environment)
    if _state_identity(remote) != _state_identity(original):
        raise DeploymentError("MigratedStateMismatch")
    return original, remote


def verify_state_version(session, bucket, account, original):
    """Verify the bytes of the exact S3 version recorded in the receipt."""
    s3 = session.client("s3")
    head = s3.head_object(Bucket=bucket, Key=STATE_KEY, ExpectedBucketOwner=account)
    version = head.get("VersionId")
    if not isinstance(version, str) or not version or version == "null":
        raise DeploymentError("VersionedStateRequired")
    response = s3.get_object(
        Bucket=bucket, Key=STATE_KEY, VersionId=version, ExpectedBucketOwner=account
    )
    with response["Body"] as stream:
        if response.get("VersionId") != version or response.get("ServerSideEncryption") != "AES256":
            raise DeploymentError("MigratedStateReadbackFailed")
        remote = stream.read()
    if _state_identity(remote) != _state_identity(original):
        raise DeploymentError("MigratedStateMismatch")
    return version, remote


def _copy_configuration(source, destination):
    validate_configuration(source)
    terraform_files = sorted(source.glob("*.tf"))
    files = terraform_files + [source / ".terraform.lock.hcl"]
    if not terraform_files or any(not path.is_file() or path.is_symlink() for path in files):
        raise DeploymentError("BootstrapConfigurationInvalid")
    destination.mkdir(parents=True, exist_ok=False)
    for path in files:
        shutil.copy2(path, destination / path.name)


def validate_configuration(directory):
    for path in Path(directory).iterdir():
        name = path.name
        if (
            path.is_symlink()
            or path.is_junction()
            or name.endswith(".tf.json")
            or name == "override.tf"
            or name.endswith("_override.tf")
            or name in {"terraform.tfvars", "terraform.tfvars.json"}
            or ".auto.tfvars" in name
        ):
            raise DeploymentError("BootstrapConfigurationInvalid")


def input_environment(directory, parent, account, region, values):
    env = terraform_environment(directory, parent, account, region)
    for key, value in values.items():
        encoded = value if isinstance(value, str) else json.dumps(value)
        if f"TF_VAR_{key}" in env and env[f"TF_VAR_{key}"] != encoded:
            raise DeploymentError("TerraformSettingConflict")
        env[f"TF_VAR_{key}"] = encoded
    if any(key.startswith("TF_VAR_") and key[7:] not in values for key in env):
        raise DeploymentError("UnexpectedTerraformVariable")
    return env


def private_path(path, private):
    candidate = Path(path).absolute()
    if any(part.is_symlink() or part.is_junction() for part in (candidate, *candidate.parents)):
        raise DeploymentError("PrivateBootstrapPathsRequired")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(private) or resolved == private:
        raise DeploymentError("PrivateBootstrapPathsRequired")
    return resolved


def write_record(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def operation_allowed(directory, operation, *, records=None, resume=False):
    """Attempt records survive crashes and prevent blind reapplication."""
    directory = Path(directory)
    records = directory if records is None else Path(records)
    if operation == "apply":
        if (records / "apply-attempt.json").exists() or any(
            (directory / name).exists() for name in ("migration-attempt.json", "backend.tf")
        ):
            raise DeploymentError("BootstrapApplyAlreadyAttempted")
    elif operation == "migrate":
        if not (records / "apply-completed.json").is_file():
            raise DeploymentError("BootstrapApplyConfirmationRequired")
        if (directory / "migration-attempt.json").exists() and not resume:
            raise DeploymentError("BootstrapMigrationAlreadyAttempted")
    elif operation == "verify":
        if (
            not (directory / "migration-attempt.json").is_file()
            and not (records / "apply-completed.json").is_file()
        ):
            raise DeploymentError("BootstrapMigrationAttemptRequired")
    elif operation not in {"plan", "inspect", "replan"}:
        raise DeploymentError("InvalidBootstrapOperation")


def inspect_state(directory, session, account, region, records):
    """No State writes; only confirmed absence permits a local continuation."""
    from botocore.exceptions import ClientError

    directory = Path(directory)
    local = directory / "terraform.tfstate"
    backup = directory / "pre-migration.tfstate"
    local_raw = local.read_bytes() if local.is_file() else None
    if local_raw is not None:
        _state_identity(local_raw)
    backup_raw = backup.read_bytes() if backup.is_file() else None
    if backup_raw is not None:
        _state_identity(backup_raw)
    bucket = f"ai-interview-state-{account}-{region}"
    s3 = session.client("s3", region_name=region)
    try:
        s3.head_object(Bucket=bucket, Key=STATE_KEY, ExpectedBucketOwner=account)
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") not in {"404", "NoSuchKey", "NoSuchBucket"}:
            raise DeploymentError("BootstrapStateDestinationUnconfirmed") from None
    else:
        if backup_raw is None:
            raise DeploymentError("BootstrapRemoteStateUnbound")
        verify_state_version(session, bucket, account, backup_raw)
        return {"status": "remote_migrated", "next_operation": "verify"}
    if (directory / "migration-receipt.json").exists():
        raise DeploymentError("BootstrapRemoteStateMissing")
    if (directory / "migration-attempt.json").exists() or backup_raw is not None:
        if backup_raw is None or local_raw != backup_raw:
            raise DeploymentError("BootstrapBackupMismatch")
        return {"status": "migration_interrupted", "next_operation": "migrate_resume"}
    if local_raw is None:
        return {"status": "apply_outcome_unknown", "next_operation": "stop"}
    if (records / "apply-completed.json").is_file():
        return {"status": "applied", "next_operation": "migrate"}
    if (records / "apply-attempt.json").is_file():
        return {"status": "partial_apply", "next_operation": "replan"}
    raise DeploymentError("BootstrapStateUnbound")


@contextmanager
def bootstrap_lock(private):
    """Serialize local bootstrap runs; crash residue requires explicit inspection."""
    path = Path(private) / "bootstrap-operation.lock"
    primary_failed = False
    try:
        stream = path.open("x", encoding="utf-8")
    except FileExistsError:
        raise DeploymentError("BootstrapOperationLocked") from None
    try:
        with stream:
            stream.write("bootstrap operation in progress\n")
            stream.flush()
            os.fsync(stream.fileno())
        yield
    except BaseException:
        primary_failed = True
        raise
    finally:
        try:
            path.unlink()
        except OSError:
            write_record(
                Path(private) / "bootstrap-lock-release-failed.json",
                {"primary": "failed" if primary_failed else "passed", "lock_release": "failed"},
            )
            raise DeploymentError(
                "BootstrapOperationAndLockReleaseFailed"
                if primary_failed
                else "BootstrapLockReleaseFailed"
            ) from None


def execute(
    input_path,
    directory,
    environment=None,
    *,
    operation="plan",
    approved_hash=None,
    attempt=1,
    resume=False,
):
    parent = dict(os.environ if environment is None else environment)
    prerequisites(parent)
    private = PROJECT / ".p4-artifacts"
    if not private.is_dir() or private.is_symlink() or private.is_junction():
        raise DeploymentError("PrivateBootstrapPathsRequired")
    private_path(directory, private.resolve())
    private_path(input_path, private.resolve())
    with bootstrap_lock(private):
        return execute_stage(
            input_path,
            directory,
            parent,
            operation=operation,
            approved_hash=approved_hash,
            attempt=attempt,
            resume=resume,
        )


def execute_stage(
    input_path,
    directory,
    environment=None,
    *,
    operation="plan",
    approved_hash=None,
    attempt=1,
    resume=False,
):
    parent = dict(os.environ if environment is None else environment)
    prerequisites(parent)
    if operation not in {"plan", "apply", "inspect", "replan", "migrate", "verify"}:
        raise DeploymentError("InvalidBootstrapOperation")
    if type(attempt) is not int or not 1 <= attempt <= 9999:
        raise DeploymentError("InvalidBootstrapAttempt")
    if resume and operation != "migrate" or operation == "plan" and attempt != 1:
        raise DeploymentError("InvalidBootstrapOperation")
    account, region = account_settings(PROJECT, parent)
    private = (PROJECT / ".p4-artifacts").resolve()
    directory = private_path(directory, private)
    input_path = private_path(input_path, private)
    values = inputs(input_path, account, region)
    local_profile = read_local_settings(PROJECT).get("AWS_PROFILE")
    if local_profile:
        if parent.get("AWS_PROFILE", local_profile) != local_profile:
            raise DeploymentError("ConflictingCredentialProfile")
        if not parent.get("AWS_ACCESS_KEY_ID"):
            parent["AWS_PROFILE"] = local_profile
    source = PROJECT / "terraform" / "bootstrap"
    validate_configuration(source)
    env = input_environment(directory, parent, account, region, values)
    source_sha = checked_source(PROJECT, parent)
    if operation == "plan":
        _copy_configuration(source, directory)
    elif not directory.is_dir():
        raise DeploymentError("BootstrapRunRequired")
    records = directory if attempt == 1 else directory / "attempts" / f"{attempt:04d}"
    private_path(records, private)
    operation_allowed(directory, operation, records=records, resume=resume)
    validate_configuration(directory)
    source_files = sorted(source.glob("*.tf")) + [source / ".terraform.lock.hcl"]
    files = {path.name: digest_bytes(path.read_bytes()) for path in source_files}
    for name, hashed in files.items():
        candidate = directory / name
        if candidate.is_symlink() or digest_bytes(candidate.read_bytes()) != hashed:
            raise DeploymentError("BootstrapConfigurationChanged")
    extras = set(path.name for path in directory.glob("*.tf")) - files.keys()
    if extras - ({"backend.tf"} if operation in {"verify", "inspect"} or resume else set()):
        raise DeploymentError("BootstrapConfigurationChanged")
    if "backend.tf" in extras:
        if (directory / "backend.tf").read_text(encoding="utf-8") != S3_BACKEND:
            raise DeploymentError("BootstrapBackendConfigurationConflict")
    env["TF_DATA_DIR"] = str(directory / ".terraform")
    env["TF_WORKSPACE"] = "default"

    def authorize():
        nonlocal env
        if not env.get("AWS_ACCESS_KEY_ID") and not env.get("AWS_PROFILE"):
            local_profile = read_local_settings(PROJECT).get("AWS_PROFILE")
            if local_profile:
                env["AWS_PROFILE"] = local_profile
        session = checked_session(account, region, environment=env)
        env = credential_environment(session, env)
        return session

    version = json.loads(run(["terraform", "version", "-json"], cwd=directory, env=env))
    if version.get("terraform_version") != TF_VERSION:
        raise DeploymentError("TerraformVersionMismatch")
    plan = records / "bootstrap.tfplan"
    binding = {
        "schema_version": 1,
        "source_sha": source_sha,
        "account_id": account,
        "region": region,
        "terraform_version": TF_VERSION,
        "files": files,
        "inputs_sha256": digest_bytes(json.dumps(values, sort_keys=True).encode()),
        "attempt": attempt,
        "backend": "local",
        "state_key": STATE_KEY,
    }
    if operation == "replan":
        previous = directory if attempt == 2 else directory / "attempts" / f"{attempt - 1:04d}"
        if attempt < 2 or records.exists():
            raise DeploymentError("NewBootstrapAttemptRequired")
        prior = json.loads((previous / "binding.json").read_text(encoding="utf-8"))
        expected_prior = binding | {
            "attempt": attempt - 1,
            "plan_sha256": digest_bytes((previous / "bootstrap.tfplan").read_bytes()),
            "review_sha256": digest_bytes((previous / "review.private.json").read_bytes()),
        }
        if prior != expected_prior:
            raise DeploymentError("BootstrapPlanBindingMismatch")
        status = inspect_state(directory, authorize(), account, region, previous)
        if status["next_operation"] != "replan":
            raise DeploymentError("BootstrapReplanNotAllowed")
        records.mkdir(parents=True, exist_ok=False)
    if operation in {"plan", "replan"}:
        authorize()
        run(["terraform", "init", "-input=false", "-lockfile=readonly"], cwd=directory, env=env)
        authorize()
        run(["terraform", "plan", "-input=false", f"-out={plan}"], cwd=directory, env=env)
        hashed = digest_bytes(plan.read_bytes())
        from plan_summary import summarize

        review = json.loads(run(["terraform", "show", "-json", str(plan)], cwd=directory, env=env))
        write_record(records / "review.private.json", review)
        write_record(records / "summary.json", summarize(review))
        write_record(
            records / "binding.json",
            binding
            | {
                "plan_sha256": hashed,
                "review_sha256": digest_bytes((records / "review.private.json").read_bytes()),
            },
        )
        return {"status": "bootstrap_planned", "plan_sha256": hashed, "attempt": attempt}
    actual = json.loads((records / "binding.json").read_text(encoding="utf-8"))
    hashed = digest_bytes(plan.read_bytes())
    if actual != binding | {
        "plan_sha256": hashed,
        "review_sha256": digest_bytes((records / "review.private.json").read_bytes()),
    }:
        raise DeploymentError("BootstrapPlanBindingMismatch")
    if operation == "apply":
        if not isinstance(approved_hash, str) or approved_hash != hashed:
            raise DeploymentError("ApprovedPlanHashRequired")
        authorize()
        if attempt > 1 and any((directory / "attempts").glob(f"{attempt + 1:04d}/binding.json")):
            raise DeploymentError("BootstrapAttemptSuperseded")
        write_record(records / "apply-attempt.json", {"plan_sha256": hashed})
        run(["terraform", "apply", "-input=false", str(plan)], cwd=directory, env=env)
        write_record(records / "apply-completed.json", {"plan_sha256": hashed})
        observed = _output_values(run(["terraform", "output", "-json"], cwd=directory, env=env))
        readback = verify_created_resources(authorize(), observed, account, region, values)
        write_record(
            records / "readback-completed.json", {"plan_sha256": hashed, "readback": readback}
        )
        return {"status": "bootstrap_resources_verified"}
    if operation == "inspect" or resume:
        status = inspect_state(directory, authorize(), account, region, records)
        if operation == "inspect":
            return status
        if status["next_operation"] == "verify":
            operation = "verify"
        elif status["next_operation"] != "migrate_resume":
            raise DeploymentError("BootstrapMigrationResumeNotAllowed")
    authorize()
    backup = directory / "pre-migration.tfstate"
    if (directory / "migration-attempt.json").exists() and backup.is_file():
        observed = _output_values(json.dumps(json.loads(backup.read_bytes())["outputs"]))
    else:
        observed = _output_values(run(["terraform", "output", "-json"], cwd=directory, env=env))
    session = authorize()
    readback = verify_created_resources(session, observed, account, region, values)
    if operation == "verify" and not (directory / "migration-attempt.json").exists():
        if not (records / "readback-completed.json").exists():
            write_record(
                records / "readback-completed.json", {"plan_sha256": hashed, "readback": readback}
            )
        return {"status": "bootstrap_resources_verified"}
    local_state = directory / "terraform.tfstate"
    if operation == "migrate":
        migration_target(account, region, observed["state_bucket"], session=session)
        if not resume:
            original = local_state.read_bytes()
            _state_identity(original)
            with (directory / "pre-migration.tfstate").open("xb") as stream:
                stream.write(original)
                stream.flush()
                os.fsync(stream.fileno())
        if not (directory / "migration-attempt.json").exists():
            write_record(directory / "migration-attempt.json", {"plan_sha256": hashed})
        migrate_state(
            directory,
            env,
            local_state,
            observed["state_bucket"],
            account,
            region,
            resume=resume,
            backup_prepared=True,
            session=session,
        )
        return {"status": "bootstrap_migration_verification_pending"}
    original = (directory / "pre-migration.tfstate").read_bytes()
    session = authorize()
    try:
        version_id, remote = verify_state_version(
            session, observed["state_bucket"], account, original
        )
    except Exception:
        raise DeploymentError("MigratedStateReadbackFailed") from None
    receipt = {
        "schema_version": 1,
        "source_sha": source_sha,
        "state_key": STATE_KEY,
        "state_version_id": version_id,
        "local_state_sha256": digest_bytes(original),
        "remote_state_sha256": digest_bytes(remote),
        "backup_preserved": True,
    }
    receipt_path = directory / "migration-receipt.json"
    if receipt_path.exists():
        if json.loads(receipt_path.read_text(encoding="utf-8")) != receipt:
            raise DeploymentError("BootstrapReceiptMismatch")
    else:
        write_record(receipt_path, receipt)
    return {"status": "bootstrap_state_migrated", "receipt": "migration-receipt.json"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "operation", choices=("plan", "apply", "inspect", "replan", "migrate", "verify")
    )
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--plan-hash")
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(
            args.inputs,
            args.directory,
            operation=args.operation,
            approved_hash=args.plan_hash,
            attempt=args.attempt,
            resume=args.resume,
        )
    except DeploymentError as error:
        allowed = {
            "BootstrapApplyAlreadyAttempted": "inspect",
            "BootstrapMigrationAlreadyAttempted": "inspect",
            "BootstrapOperationLocked": "stop",
            "TerraformOperationFailed": "inspect",
            "BootstrapReadbackFailed": "verify",
            "MigratedStateReadbackFailed": "inspect",
            "BootstrapBackupMismatch": "stop",
            "BootstrapStateDestinationUnconfirmed": "inspect",
        }
        failure = str(error) if str(error) in allowed else "BootstrapStateMigrationFailed"
        print(
            json.dumps(
                {
                    "status": "failed",
                    "failure": failure,
                    "next_operation": allowed.get(failure, "stop"),
                }
            ),
            file=sys.stderr,
        )
        return 1
    except Exception:
        print("BootstrapStateMigrationFailed", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
