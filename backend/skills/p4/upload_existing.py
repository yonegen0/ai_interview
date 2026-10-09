"""Transfer one approved ZIP under a real CI identity; never build or run Terraform.

A one-job runner reads the existing local artifact. Its SSO profile is used only
for read-only preflight/history queries. The sole write uses GitHub OIDC and the
artifact role. A durable local attempt record prevents an uncertain retry.
"""

import base64
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

REPOSITORY = "yonegen0/ai_interview"
WORKFLOW = ".github/workflows/p4-deploy.yml"
OPERATION = "upload-existing"
REGION = "ap-northeast-1"
JOB = "upload_existing"
APP_ROOT = "backend/src/interview_backend/"


class UploadError(ValueError):
    """Only fixed classifications may be persisted or printed."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def require(condition, code):
    if not condition:
        raise UploadError(code)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def timestamp():
    return datetime.now(UTC).isoformat()


def record(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def git(root, *arguments):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    result = subprocess.run(
        ["git", *arguments], cwd=root, env=env, capture_output=True, check=False
    )
    require(result.returncode == 0, "GitReadFailed")
    return result.stdout


def safe_file(root, relative):
    relative = Path(relative)
    require(not relative.is_absolute() and ".." not in relative.parts, "UnsafeEvidencePath")
    root = Path(root).resolve(strict=True)
    path = root / relative
    require(path.resolve(strict=True).is_relative_to(root), "UnsafeEvidencePath")
    require(
        not any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)),
        "UnsafeEvidencePath",
    )
    require(path.is_file(), "EvidenceFileRequired")
    return path


def artifact(root, source, provenance_path, approval):
    """Validate immutable bytes and original Git blobs; never import ZIP code."""
    package = safe_file(source, "app.zip").read_bytes()
    manifest_bytes = safe_file(source, "package.json").read_bytes()
    require(len(package) == approval["zip_size"], "ArtifactSizeMismatch")
    require(sha256(package) == approval["zip_sha256"], "ArtifactHashMismatch")
    require(sha256(manifest_bytes) == approval["manifest_sha256"], "ManifestHashMismatch")
    provenance_bytes = Path(provenance_path).read_bytes()
    require(sha256(provenance_bytes) == approval["provenance_sha256"], "ProvenanceHashMismatch")
    provenance = json.loads(provenance_bytes)
    source_sha = approval["artifact_source_sha"]
    require(re.fullmatch(r"[0-9a-f]{40}", source_sha), "InvalidArtifactSource")
    for field in ("artifact_source_sha", "zip_sha256", "zip_size", "manifest_sha256"):
        require(provenance[field] == approval[field], "ProvenanceBindingMismatch")
    for name, expected in provenance["evidence_files"].items():
        require(sha256(safe_file(source, name).read_bytes()) == expected, "EvidenceHashMismatch")
    schema = approval.get("schema_version", 1)
    require(type(schema) is int and schema in {1, 2}, "ApprovalSchemaUnsupported")
    if schema == 2:
        final_path = "validation/final.private.json"
        baseline_path = "validation/baseline.private.json"
        source_count = approval["source_blob_count"]
        entry_count = approval["zip_entry_count"]
        require(
            type(source_count) is int
            and source_count > 0
            and type(entry_count) is int
            and entry_count > 0,
            "ArtifactInventoryRequired",
        )
        all_paths = git(root, "ls-tree", "-r", "--name-only", source_sha).decode().splitlines()
        require(len(all_paths) == source_count, "SourceInventoryMismatch")
        require("reproduction.zip" in provenance["evidence_files"], "ReproductionEvidenceRequired")
        require(
            sha256(safe_file(source, "reproduction.zip").read_bytes()) == approval["zip_sha256"],
            "ReproductionHashMismatch",
        )
    else:
        final_path = "final-validation-20261003/final.private.json"
        baseline_path = "final-validation-20261003/baseline.private.json"
        source_count, entry_count = 287, 2366
    final = json.loads(safe_file(source, final_path).read_bytes())
    require(
        final["status"] == "P4_LAMBDA_ARTIFACT_READY"
        and final["code_sha"] == source_sha
        and final["source_blob_matches"] == source_count
        and final["security"]["zip_sha256"] == approval["zip_sha256"]
        and final["security"]["manifest_sha256"] == approval["manifest_sha256"]
        and final["security"]["status"] == "LAMBDA_ARTIFACT_SECURITY_PASS"
        and final["security"]["unknown_findings"] == []
        and final["security"]["entries_scanned"] == entry_count,
        "ArtifactReadinessUnproved",
    )
    require(
        final_path in provenance["evidence_files"]
        and baseline_path in provenance["evidence_files"],
        "ProvenanceEvidenceRequired",
    )
    baseline = json.loads(safe_file(source, baseline_path).read_bytes())
    require(
        baseline["binding"]["code_sha"] == source_sha
        and baseline["binding"]["official_origin_verified"] is True
        and baseline["binding"]["source_and_builder_blobs_verified"] is True,
        "SourceProvenanceUnproved",
    )
    manifest = json.loads(manifest_bytes)
    require(
        manifest["code_sha"] == source_sha
        and manifest["sha256"] == approval["zip_sha256"]
        and manifest["runtime"] == "python3.14"
        and manifest["architecture"] == "x86_64"
        and manifest["sha256_base64"] == base64.b64encode(hashlib.sha256(package).digest()).decode()
        and manifest["lock_sha256"] == sha256(git(root, "show", f"{source_sha}:backend/uv.lock")),
        "ManifestBindingMismatch",
    )
    paths = (
        git(root, "ls-tree", "-r", "--name-only", source_sha, "--", APP_ROOT).decode().splitlines()
    )
    require(len(paths) == final["security"]["app_head_blob_matches"], "SourceFileSetMismatch")
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) == entry_count, "ZipEntrySetMismatch")
        expected_names = {"interview_backend/" + path.removeprefix(APP_ROOT) for path in paths}
        require(
            {name for name in names if name.startswith("interview_backend/")} == expected_names,
            "SourceFileSetMismatch",
        )
        for path in paths:
            name = "interview_backend/" + path.removeprefix(APP_ROOT)
            require(
                archive.read(name) == git(root, "show", f"{source_sha}:{path}"),
                "SourceBlobMismatch",
            )
    return package


def approved_configuration(env):
    """A new artifact uses a separately approved, hash-pinned local descriptor."""
    if "P4_UPLOAD_APPROVAL_PATH" not in env:
        legacy = json.loads(Path(__file__).with_name("upload_existing.approval.json").read_bytes())
        require(legacy.get("schema_version") == 1, "LocalDescriptorRequired")
        return legacy
    path = Path(env["P4_UPLOAD_APPROVAL_PATH"])
    require(path.is_absolute(), "ApprovalPathRequired")
    raw = safe_file(path.parent, path.name).read_bytes()
    expected = env.get("P4_APPROVED_ARTIFACT_APPROVAL_SHA256", "")
    require(re.fullmatch(r"[0-9a-f]{64}", expected), "ApprovalDigestRequired")
    require(sha256(raw) == expected, "ApprovalDigestMismatch")
    value = json.loads(raw)
    require(
        value.get("schema_version") == 2 and value.get("approved") is True,
        "ExplicitArtifactApprovalRequired",
    )
    return value


def json_get(url, token):
    request = Request(
        url,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"},
    )
    with build_opener(NoRedirect()).open(request, timeout=20) as response:
        raw = response.read(1048577)
        require(len(raw) <= 1048576, "ControlResponseTooLarge")
        return json.loads(raw)


def github(suffix, env):
    return json_get(f"https://api.github.com/repos/{REPOSITORY}/{suffix}", env["GH_TOKEN"])


def identity(root, env):
    expected = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REF_TYPE": "branch",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_JOB": JOB,
        "P4_OPERATION": OPERATION,
        "GITHUB_RUN_ATTEMPT": "1",
        "RUNNER_ENVIRONMENT": "self-hosted",
    }
    require(all(env.get(k) == v for k, v in expected.items()), "CiContextMismatch")
    execution = env["GITHUB_SHA"]
    run_id = env["GITHUB_RUN_ID"]
    require(re.fullmatch(r"[0-9a-f]{40}", execution), "InvalidWorkflowRevision")
    require(re.fullmatch(r"[1-9][0-9]*", run_id), "InvalidRunId")
    require(
        execution == env["P4_APPROVED_EXECUTION_SHA"]
        and run_id == env["P4_APPROVED_RUN_ID"]
        and env["GITHUB_WORKFLOW_SHA"] == execution
        and env["GITHUB_WORKFLOW_REF"] == f"{REPOSITORY}/{WORKFLOW}@refs/heads/main"
        and env["RUNNER_NAME"] == env["P4_APPROVED_RUNNER_NAME"],
        "UnapprovedExecution",
    )
    event = json.loads(Path(env["GITHUB_EVENT_PATH"]).read_bytes())
    require(
        event["inputs"]["operation"] == OPERATION
        and event["inputs"]["upload_runner_label"] == env["P4_APPROVED_RUNNER_LABEL"],
        "DispatchInputMismatch",
    )
    require(git(root, "rev-parse", "HEAD").decode().strip() == execution, "CheckoutMismatch")
    require(
        not git(root, "status", "--porcelain", "--untracked-files=all").strip(), "DirtyCheckout"
    )
    require(
        git(root, "config", "--get", "remote.origin.url").decode().strip()
        in {f"https://github.com/{REPOSITORY}", f"https://github.com/{REPOSITORY}.git"},
        "RepositoryMismatch",
    )
    run = github(f"actions/runs/{run_id}", env)
    require(
        str(run["id"]) == run_id
        and run["run_attempt"] == 1
        and run["head_sha"] == execution
        and run["head_branch"] == "main"
        and run["event"] == "workflow_dispatch"
        and run["path"] == WORKFLOW
        and run["repository"]["full_name"] == REPOSITORY
        and run["status"] == "in_progress"
        and run["actor"]["login"] == env["GITHUB_ACTOR"]
        and run["triggering_actor"]["login"] == env["GITHUB_TRIGGERING_ACTOR"],
        "GitHubRunMismatch",
    )
    require(github("git/ref/heads/main", env)["object"]["sha"] == execution, "MainRevisionMoved")
    details = github("environments/dev", env)
    branches = github("environments/dev/deployment-branch-policies?per_page=100", env)
    require(
        details["deployment_branch_policy"]
        == {"protected_branches": False, "custom_branch_policies": True}
        and branches["total_count"] == 1
        and len(branches["branch_policies"]) == 1
        and branches["branch_policies"][0]["name"] == "main"
        and branches["branch_policies"][0]["type"] == "branch",
        "DevEnvironmentMismatch",
    )
    return {
        "repository": REPOSITORY,
        "workflow_path": WORKFLOW,
        "workflow_execution_sha": execution,
        "workflow_id": run["workflow_id"],
        "workflow_name": run["name"],
        "run_id": run_id,
        "run_attempt": "1",
        "event": "workflow_dispatch",
        "ref": "refs/heads/main",
        "branch": "main",
        "environment": "dev",
        "operation": OPERATION,
        "job": JOB,
        "actor": env["GITHUB_ACTOR"],
        "triggering_actor": env["GITHUB_TRIGGERING_ACTOR"],
        "runner_name": env["RUNNER_NAME"],
    }


def claims(token, proof, approval, now=None):
    """Decode and compare claims; STS subsequently verifies the JWT signature."""
    payload = token.split(".")[1]
    value = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    expected = {
        "iss": "https://token.actions.githubusercontent.com",
        "aud": "sts.amazonaws.com",
        "sub": approval["oidc_subject"],
        "repository": REPOSITORY,
        "environment": "dev",
        "ref": proof["ref"],
        "sha": proof["workflow_execution_sha"],
        "workflow_sha": proof["workflow_execution_sha"],
        "workflow_ref": f"{REPOSITORY}/{WORKFLOW}@refs/heads/main",
        "event_name": proof["event"],
        "run_id": proof["run_id"],
        "run_attempt": proof["run_attempt"],
        "actor": proof["actor"],
    }
    require(all(value.get(k) == v for k, v in expected.items()), "OidcClaimsMismatch")
    now = time.time() if now is None else now
    require(value["nbf"] <= now + 60 and value["iat"] <= now + 60 < value["exp"], "OidcExpired")
    return expected


def config():
    from botocore.config import Config

    return Config(retries={"total_max_attempts": 1}, connect_timeout=10, read_timeout=60)


def reader(approval, profile):
    import boto3

    require(not any(k.startswith("AWS_ENDPOINT_URL") for k in os.environ), "EndpointOverride")
    session = boto3.Session(profile_name=profile, region_name=REGION)
    pending = [session._session.full_config]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            require("endpoint_url" not in item, "EndpointOverride")
            pending.extend(item.values())
    observed = session.client("sts", config=config()).get_caller_identity()
    require(observed["Account"] == approval["aws_account"], "ReaderAccountMismatch")
    return session.client("s3", config=config()), observed["Arn"]


def oidc_client(env, proof, approval):
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    url = urlsplit(env["ACTIONS_ID_TOKEN_REQUEST_URL"])
    require(
        url.scheme == "https"
        and url.hostname
        and url.hostname.endswith(".actions.githubusercontent.com")
        and not url.username
        and not url.password,
        "OidcEndpointMismatch",
    )
    query = dict(parse_qsl(url.query)) | {"audience": "sts.amazonaws.com"}
    token = json_get(
        urlunsplit(url._replace(query=urlencode(query))), env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]
    )["value"]
    verified = claims(token, proof, approval)
    unsigned = boto3.Session(region_name=REGION).client(
        "sts", config=Config(signature_version=UNSIGNED, retries={"total_max_attempts": 1})
    )
    role_name = "ai-interview-ci-artifact"
    credentials = unsigned.assume_role_with_web_identity(
        RoleArn=f"arn:aws:iam::{approval['aws_account']}:role/{role_name}",
        RoleSessionName=f"p4-{proof['run_id']}-artifact",
        WebIdentityToken=token,
        DurationSeconds=3600,
    )["Credentials"]
    token = None
    session = boto3.Session(
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
        region_name=REGION,
    )
    credentials = None
    observed = session.client("sts", config=config()).get_caller_identity()
    expected_arn = (
        f"arn:aws:sts::{approval['aws_account']}:assumed-role/"
        f"{role_name}/p4-{proof['run_id']}-artifact"
    )
    require(
        observed["Account"] == approval["aws_account"] and observed["Arn"] == expected_arn,
        "WriterIdentityMismatch",
    )
    return session.client("s3", config=config()), verified, observed["Arn"]


def bucket_preflight(s3, approval):
    args = {"Bucket": approval["bucket"], "ExpectedBucketOwner": approval["aws_account"]}
    s3.head_bucket(**args)
    require(s3.get_bucket_location(**args)["LocationConstraint"] == REGION, "BucketRegionMismatch")
    require(s3.get_bucket_versioning(**args).get("Status") == "Enabled", "VersioningRequired")
    rules = s3.get_bucket_encryption(**args)["ServerSideEncryptionConfiguration"]["Rules"]
    require(
        len(rules) == 1
        and rules[0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256",
        "BucketEncryptionMismatch",
    )
    block = s3.get_public_access_block(**args)["PublicAccessBlockConfiguration"]
    require(
        all(
            block.get(k) is True
            for k in (
                "BlockPublicAcls",
                "IgnorePublicAcls",
                "BlockPublicPolicy",
                "RestrictPublicBuckets",
            )
        ),
        "PublicAccessBlockRequired",
    )


def versions(s3, approval, key):
    request = {
        "Bucket": approval["bucket"],
        "Prefix": key,
        "ExpectedBucketOwner": approval["aws_account"],
    }
    found, markers, seen = [], [], set()
    while True:
        response = s3.list_object_versions(**request)
        found.extend(item for item in response.get("Versions", []) if item["Key"] == key)
        markers.extend(item for item in response.get("DeleteMarkers", []) if item["Key"] == key)
        if response.get("IsTruncated") is False:
            return found, markers
        require(response.get("IsTruncated") is True, "VersionInventoryIncomplete")
        cursor = (response.get("NextKeyMarker"), response.get("NextVersionIdMarker"))
        require(
            all(isinstance(v, str) and v for v in cursor) and cursor not in seen, "BadVersionCursor"
        )
        seen.add(cursor)
        request.update(KeyMarker=cursor[0], VersionIdMarker=cursor[1])


def absent(s3, approval, key):
    found, markers = versions(s3, approval, key)
    require(not found and not markers, "ArtifactKeyAlreadyUsed")


def transfer(read_s3, write_s3, approval, proof, package, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    require(not (directory / "attempt.private.json").exists(), "UploadAlreadyAttempted")
    require(sha256(package) == approval["zip_sha256"], "ArtifactHashMismatch")
    require(len(package) == approval["zip_size"], "ArtifactSizeMismatch")
    key = (
        f"lambda/{approval['artifact_source_sha']}/{proof['run_id']}/{proof['run_attempt']}/app.zip"
    )
    absent(read_s3, approval, key)
    metadata = {
        "artifact-source-sha": approval["artifact_source_sha"],
        "workflow-execution-sha": proof["workflow_execution_sha"],
        "github-run-id": proof["run_id"],
        "github-run-attempt": proof["run_attempt"],
        "manifest-sha256": approval["manifest_sha256"],
        "provenance-sha256": approval["provenance_sha256"],
    }
    binding = proof | {
        "artifact_source_sha": approval["artifact_source_sha"],
        "aws_account": approval["aws_account"],
        "region": REGION,
        "bucket": approval["bucket"],
        "key": key,
        "local_zip_sha256": approval["zip_sha256"],
        "zip_size": approval["zip_size"],
        "manifest_sha256": approval["manifest_sha256"],
        "provenance_sha256": approval["provenance_sha256"],
    }
    # Exclusive, flushed before the only write. Never remove this marker to retry.
    record(
        directory / "attempt.private.json",
        binding | {"timestamp": timestamp(), "put_started": True},
    )
    response = write_s3.put_object(
        Bucket=approval["bucket"],
        Key=key,
        Body=package,
        ExpectedBucketOwner=approval["aws_account"],
        IfNoneMatch="*",
        ServerSideEncryption="AES256",
        ChecksumSHA256=base64.b64encode(hashlib.sha256(package).digest()).decode(),
        Metadata=metadata,
    )
    version = response.get("VersionId")
    require(
        isinstance(version, str) and version.strip() == version and version not in {"", "null"},
        "VersionIdRequired",
    )
    require(response.get("ServerSideEncryption") == "AES256", "PutEncryptionMismatch")
    require(isinstance(response.get("ETag"), str) and bool(response["ETag"]), "PutEtagRequired")
    record(
        directory / "put-response.private.json",
        {
            "version_id": version,
            "etag": response["ETag"],
            "encryption": "AES256",
            "request_id": response.get("ResponseMetadata", {}).get("RequestId"),
        },
    )
    fetched = write_s3.get_object(
        Bucket=approval["bucket"],
        Key=key,
        VersionId=version,
        ExpectedBucketOwner=approval["aws_account"],
    )
    with fetched["Body"] as stream:
        body = stream.read(approval["zip_size"] + 1)
    require(fetched.get("VersionId") == version, "ReadbackVersionMismatch")
    require(
        fetched.get("ContentLength") == len(body) == approval["zip_size"], "ReadbackSizeMismatch"
    )
    require(fetched.get("ServerSideEncryption") == "AES256", "ReadbackEncryptionMismatch")
    require(fetched.get("Metadata") == metadata, "ReadbackIdentityMismatch")
    require(sha256(body) == approval["zip_sha256"], "ReadbackHashMismatch")
    found, markers = versions(read_s3, approval, key)
    require(
        len(found) == 1
        and not markers
        and found[0]["VersionId"] == version
        and found[0].get("IsLatest") is True,
        "SingleVersionUnproved",
    )
    with (directory / "retrieved-app.zip").open("xb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    receipt = binding | {
        "status": "P4_LAMBDA_ARTIFACT_UPLOADED_VERIFIED",
        "timestamp": timestamp(),
        "version_id": version,
        "etag": response["ETag"],
        "encryption": "AES256",
        "retrieved_zip_sha256": sha256(body),
        "version_pinned_get": True,
        "upload_logical_attempts": 1,
        "versions_at_key": 1,
        "terraform_executed": False,
        "state_operations": False,
        "rebuild": False,
    }
    record(directory / "receipt.private.json", receipt)
    return receipt


def main():
    stage, directory = "configuration", None
    try:
        env = dict(os.environ)
        root = Path(__file__).resolve().parents[3]
        approval = approved_configuration(env)
        require(approval["region"] == REGION, "ApprovalRegionMismatch")
        require(
            approval["bucket"] == f"ai-interview-artifacts-{approval['aws_account']}-{REGION}",
            "ApprovalBucketMismatch",
        )
        directory = Path(env["P4_UPLOAD_RECEIPT_DIR"]).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        require(not (directory / "attempt.private.json").exists(), "UploadAlreadyAttempted")
        stage = "ci_identity"
        proof = identity(root, env)
        stage = "artifact_provenance"
        package = artifact(root, env["P4_UPLOAD_SOURCE_DIR"], env["P4_UPLOAD_PROVENANCE"], approval)
        stage = "read_only_preflight"
        read_s3, read_arn = reader(approval, env["P4_UPLOAD_READ_PROFILE"])
        bucket_preflight(read_s3, approval)
        stage = "oidc"
        write_s3, oidc, write_arn = oidc_client(env, proof, approval)
        proof.update(oidc=oidc, reader_arn=read_arn, writer_arn=write_arn)
        record(directory / "identity.private.json", proof | {"timestamp": timestamp()})
        stage = "single_upload_and_readback"
        result = transfer(read_s3, write_s3, approval, proof, package, directory)
        print(result["status"])
        return 0
    except Exception as error:
        failure = {
            "status": "P4_LAMBDA_ARTIFACT_UPLOAD_STOPPED",
            "stage": stage,
            "reason": str(error) if isinstance(error, UploadError) else type(error).__name__,
            "timestamp": timestamp(),
        }
        if directory is not None and not (directory / "failure.private.json").exists():
            record(directory / "failure.private.json", failure)
        print(failure["status"] + ":" + stage, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
