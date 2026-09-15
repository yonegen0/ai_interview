"""Manual main/dev CI transport for immutable artifacts and saved Terraform plans."""

import hashlib
import json
import os
import re
import sys
from urllib.request import Request

from ci_identity import NoRedirect, assume
from terraform_dev import (
    INPUT_KEYS,
    PROJECT,
    REPOSITORY,
    checked_git,
    execute,
    run,
    validate_inputs,
)

from interview_backend.deployment import (
    DeploymentError,
    account_settings,
    require_aws_execution,
    terraform_environment,
)

PACKAGE_KEYS = frozenset(
    {"artifact_bucket", "artifact_key", "artifact_version", "artifact_sha256_base64"}
)


def preflight(environment):
    require_aws_execution(environment)
    operation = environment.get("P4_OPERATION")
    if operation not in {"plan", "apply"}:
        raise DeploymentError("InvalidOperation")
    if operation == "apply" and (
        not re.fullmatch(r"[0-9]+", environment.get("P4_PLAN_RUN_ID", ""))
        or not re.fullmatch(r"[0-9a-f]{64}", environment.get("P4_PLAN_HASH", ""))
    ):
        raise DeploymentError("ApprovedPlanIdentityRequired")
    account, region = account_settings(PROJECT, environment)
    configuration = json.loads(environment["P4_DEPLOY_INPUTS"])
    if not isinstance(configuration, dict) or configuration.keys() != INPUT_KEYS - PACKAGE_KEYS:
        raise DeploymentError("ExplicitDeploymentInputsRequired")
    package = {
        "artifact_bucket": f"ai-interview-artifacts-{account}-{region}",
        "artifact_key": "lambda/preflight/app.zip",
        "artifact_version": "preflight",
        "artifact_sha256_base64": "A" * 43 + "=",
    }
    values = validate_inputs(configuration | package, account, region)
    if any(
        values[key]
        for key in ("worker_enabled", "streams_enabled", "scheduler_enabled", "api_enabled")
    ):
        raise DeploymentError("ClosedInitialDeploymentRequired")
    terraform_environment(PROJECT / "terraform/environments/dev", environment, account, region)
    if any(key.startswith("TF_VAR_") for key in environment):
        raise DeploymentError("UnexpectedTerraformVariable")
    return account, region, operation, configuration


def build_environment(environment):
    forbidden = ("AWS_", "TF_", "P4_", "ACTIONS_", "GH_", "GITHUB_")
    child = {key: value for key, value in environment.items() if not key.startswith(forbidden)}
    child.pop("PYTHONPATH", None)
    child.pop("PYTHONHOME", None)
    child["AWS_EC2_METADATA_DISABLED"] = "true"
    child["PYTHONNOUSERSITE"] = "1"
    return child


def github_run(run_id):
    from urllib.request import build_opener

    if not re.fullmatch(r"[0-9]+", run_id):
        raise DeploymentError("InvalidPlanRun")
    request = Request(
        f"https://api.github.com/repos/{REPOSITORY}/actions/runs/{run_id}",
        headers={
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json",
        },
    )
    with build_opener(NoRedirect()).open(request, timeout=15) as response:
        data = json.loads(response.read(1048576))
    if (
        data["conclusion"] != "success"
        or data["head_branch"] != "main"
        or data["head_sha"] != os.environ["GITHUB_SHA"]
        or data["event"] != "workflow_dispatch"
        or data["path"] != ".github/workflows/p4-deploy.yml"
        or data["repository"]["full_name"] != REPOSITORY
        or str(data["id"]) != run_id
        or data["status"] != "completed"
        or type(data["run_attempt"]) is not int
        or data["run_attempt"] < 1
    ):
        raise DeploymentError("SuccessfulMainPlanRequired")
    return str(data["run_attempt"])


def put(s3, bucket, key, body):
    response = s3.put_object(
        Bucket=bucket, Key=key, Body=body, IfNoneMatch="*", ServerSideEncryption="AES256"
    )
    version = response.get("VersionId")
    if not version or version == "null":
        raise DeploymentError("VersionedArtifactRequired")
    return version


def get(s3, bucket, key, *, version=None):
    args = {"Bucket": bucket, "Key": key}
    if version:
        args["VersionId"] = version
    response = s3.get_object(**args)
    if not response.get("VersionId") or response["VersionId"] == "null":
        response["Body"].close()
        raise DeploymentError("VersionedArtifactRequired")
    if version is not None and response["VersionId"] != version:
        response["Body"].close()
        raise DeploymentError("ArtifactVersionMismatch")
    with response["Body"] as stream:
        return stream.read()


def role_session(role, account, region):
    return assume(role, account, region, expected_subject=os.environ["P4_OIDC_SUBJECT"])


def optional_record(s3, bucket, key):
    # A prefix-conditioned ListBucket grant need not turn a missing GetObject
    # into 404. Confirm absence with the explicitly authorized exact prefix.
    request = {"Bucket": bucket, "Prefix": key}
    seen = set()
    while True:
        response = s3.list_objects_v2(**request)
        if any(item["Key"] == key for item in response.get("Contents", [])):
            return json.loads(get(s3, bucket, key))
        if response.get("IsTruncated") is False:
            return None
        token = response.get("NextContinuationToken")
        if not isinstance(token, str) or not token or token in seen:
            raise DeploymentError("ApplyJournalUnavailable")
        seen.add(token)
        request["ContinuationToken"] = token


def apply_saved_plan(account, region, bucket, prefix, approved, input_path, directory):
    """A durable per-plan journal prevents retries after an uncertain apply."""
    identity = {"plan_sha256": approved, "plan_prefix": prefix}
    s3 = role_session("artifact", account, region).client("s3")
    completed = optional_record(s3, bucket, prefix + "/apply-completed.json")
    started = optional_record(s3, bucket, prefix + "/apply-started.json")
    if completed is not None:
        if completed != identity or started != identity:
            raise DeploymentError("ApplyJournalMismatch")
        from bootstrap_state import write_record

        write_record(directory / "apply-completed.json", {"plan_sha256": approved})
        role_session("deploy", account, region)
        return execute("verify", input_path, directory, approved)
    if started is not None:
        raise DeploymentError("ApplyOutcomeUnknownNewPlanRequired")

    def progress(stage):
        record_name = {
            "apply_started": "apply-started.json",
            "apply_completed": "apply-completed.json",
        }[stage]
        journal = role_session("artifact", account, region).client("s3")
        put(journal, bucket, prefix + "/" + record_name, json.dumps(identity).encode())
        role_session("deploy", account, region)

    role_session("deploy", account, region)
    return execute("apply", input_path, directory, approved, progress=progress)


def build_package(directory, sha):
    environment = build_environment(os.environ)
    backend = PROJECT / "backend"
    requirements, dependencies = directory / "requirements.txt", directory / "dependencies"
    run(
        [
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--format",
            "requirements-txt",
            "--output-file",
            str(requirements),
        ],
        cwd=backend,
        env=environment,
    )
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            "3.14",
            "--python-platform",
            "x86_64-manylinux_2_34",
            "--target",
            str(dependencies),
            "--only-binary=:all:",
            "--require-hashes",
            "-r",
            str(requirements),
        ],
        cwd=backend,
        env=environment,
    )
    from build_lambda import build

    package = directory / "app.zip"
    info = build(backend / "src/interview_backend", dependencies, backend / "uv.lock", package, sha)
    # Verify the exact ZIP that will be uploaded, not a different earlier build.
    import zipfile

    with zipfile.ZipFile(package) as archive:
        archive.extractall(directory / "expanded")
    run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; assert sys.platform == 'linux'; "
            "import interview_backend, boto3, pydantic, pydantic_core; "
            "assert all(Path(m.__file__).resolve().is_relative_to(Path.cwd()) "
            "for m in (interview_backend,boto3,pydantic,pydantic_core)); "
            "from interview_backend.aws_runtime import api_handler, "
            "worker_handler, dispatcher_handler; from interview_backend.assets import "
            "load_questions; assert load_questions()",
        ],
        cwd=directory / "expanded",
        env=environment,
    )
    return package, info


def main():
    try:
        account, region, operation, configuration = preflight(os.environ)
        sha = checked_git(PROJECT, os.environ)
        run_id, attempt = os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"]
        if not all(re.fullmatch(r"[0-9]+", value) for value in (run_id, attempt)):
            raise DeploymentError("InvalidRunIdentity")
        directory = PROJECT / ".p4-artifacts" / f"ci-{run_id}-{attempt}"
        directory.mkdir(parents=True, exist_ok=False)
        bucket = f"ai-interview-artifacts-{account}-{region}"
        plan_prefix = f"plans/{run_id}/{attempt}"
        if operation == "plan":
            package, info = build_package(directory, sha)
            s3 = role_session("artifact", account, region).client("s3")
            key = f"lambda/{sha}/{run_id}/{attempt}/app.zip"
            version = put(s3, bucket, key, package.read_bytes())
            package_info = {
                "artifact_bucket": bucket,
                "artifact_key": key,
                "artifact_version": version,
                "artifact_sha256_base64": info["sha256_base64"],
            }
            if any(key in configuration for key in package_info):
                raise DeploymentError("ArtifactOverrideForbidden")
            configuration.update(package_info)
            input_path = directory / "inputs.json"
            input_path.write_text(json.dumps(configuration, sort_keys=True), encoding="utf-8")
            role_session("plan", account, region)
            result = execute("plan", input_path, directory / "terraform")
            s3 = role_session("artifact", account, region).client("s3")
            plan_version = put(
                s3,
                bucket,
                f"{plan_prefix}/dev.tfplan",
                (directory / "terraform/dev.tfplan").read_bytes(),
            )
            binding_version = put(
                s3,
                bucket,
                f"{plan_prefix}/plan.json",
                (directory / "terraform/plan.json").read_bytes(),
            )
            put(
                s3,
                bucket,
                f"{plan_prefix}/summary.json",
                (directory / "terraform/summary.json").read_bytes(),
            )
            review_version = put(
                s3,
                bucket,
                f"{plan_prefix}/review.private.json",
                (directory / "terraform/review.private.json").read_bytes(),
            )
            envelope = {
                "operation": "plan",
                "code_sha": sha,
                "run_id": run_id,
                "run_attempt": attempt,
                "plan_sha256": result["plan_sha256"],
                "plan_version": plan_version,
                "binding_version": binding_version,
                "package": package_info,
                "review_version": review_version,
            }
            put(s3, bucket, f"{plan_prefix}/envelope.json", json.dumps(envelope).encode())
            print(json.dumps(result | {"run_id": run_id, "run_attempt": attempt}))
        else:
            source_run = os.environ["P4_PLAN_RUN_ID"]
            source_attempt = github_run(source_run)
            plan_prefix = f"plans/{source_run}/{source_attempt}"
            s3 = role_session("deploy", account, region).client("s3")
            envelope = json.loads(get(s3, bucket, f"{plan_prefix}/envelope.json"))
            approved = os.environ["P4_PLAN_HASH"]
            if (
                envelope["operation"] != "plan"
                or envelope["code_sha"] != sha
                or envelope["run_id"] != source_run
                or envelope["run_attempt"] != source_attempt
                or envelope["plan_sha256"] != approved
                or not isinstance(envelope["package"], dict)
                or envelope["package"].keys() != PACKAGE_KEYS
                or envelope["package"]["artifact_key"]
                != f"lambda/{sha}/{source_run}/{source_attempt}/app.zip"
            ):
                raise DeploymentError("PlanEnvelopeMismatch")
            if any(key in configuration for key in envelope["package"]):
                raise DeploymentError("ArtifactOverrideForbidden")
            configuration.update(envelope["package"])
            validate_inputs(configuration, account, region)
            input_path = directory / "inputs.json"
            input_path.write_text(json.dumps(configuration, sort_keys=True), encoding="utf-8")
            tf_dir = directory / "terraform"
            tf_dir.mkdir()
            raw_plan = get(
                s3, bucket, f"{plan_prefix}/dev.tfplan", version=envelope["plan_version"]
            )
            if hashlib.sha256(raw_plan).hexdigest() != approved:
                raise DeploymentError("SavedPlanMismatch")
            (tf_dir / "dev.tfplan").write_bytes(raw_plan)
            (tf_dir / "plan.json").write_bytes(
                get(s3, bucket, f"{plan_prefix}/plan.json", version=envelope["binding_version"])
            )
            result = apply_saved_plan(
                account, region, bucket, plan_prefix, approved, input_path, tf_dir
            )
            s3 = role_session("artifact", account, region).client("s3")
            put(
                s3,
                bucket,
                f"plans/{run_id}/{attempt}/deployment.json",
                (tf_dir / "deployment.json").read_bytes(),
            )
            print(json.dumps(result))
        return 0
    except Exception:
        print("P4CiDeploymentFailed", file=sys.stderr)
        return 1
    finally:
        for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
            os.environ.pop(key, None)


if __name__ == "__main__":
    raise SystemExit(main())
