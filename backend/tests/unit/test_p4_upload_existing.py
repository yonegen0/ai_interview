"""Upload-only identity, immutable provenance, and uncertain-write boundaries."""

import ast
import base64
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_p4_tools import tool


@pytest.fixture
def module():
    return tool("upload_existing")


@pytest.fixture
def sample(module):
    package = b"approved ZIP bytes"
    approval = {
        "artifact_source_sha": "a" * 40,
        "zip_sha256": module.sha256(package),
        "zip_size": len(package),
        "manifest_sha256": "b" * 64,
        "provenance_sha256": "c" * 64,
        "aws_account": "123456789012",
        "bucket": "ai-interview-artifacts-123456789012-ap-northeast-1",
        "oidc_subject": "repo:yonegen0/ai_interview:environment:dev",
    }
    proof = {
        "run_id": "456",
        "run_attempt": "1",
        "workflow_execution_sha": "d" * 40,
        "event": "workflow_dispatch",
        "ref": "refs/heads/main",
        "actor": "operator",
    }
    return approval, proof, package


class Store:
    def __init__(self, directory):
        self.directory = directory
        self.puts = []
        self.gets = []
        self.extra = []
        self.markers = []
        self.put_override = {}
        self.get_override = {}
        self.uncertain = False

    def list_object_versions(self, **kwargs):
        key = kwargs["Prefix"]
        versions = self.extra.copy()
        if self.puts:
            versions.append({"Key": key, "VersionId": "v1", "IsLatest": True})
        return {"Versions": versions, "DeleteMarkers": self.markers, "IsTruncated": False}

    def put_object(self, **kwargs):
        assert (self.directory / "attempt.private.json").is_file()
        assert kwargs["IfNoneMatch"] == "*"
        assert kwargs["ServerSideEncryption"] == "AES256"
        self.puts.append(kwargs)
        if self.uncertain:
            raise TimeoutError("synthetic uncertain result")
        return {
            "VersionId": "v1",
            "ETag": "etag",
            "ServerSideEncryption": "AES256",
        } | self.put_override

    def get_object(self, **kwargs):
        self.gets.append(kwargs)
        assert kwargs["VersionId"] == "v1"
        assert kwargs["Key"] == self.puts[0]["Key"]
        value = self.puts[0]
        return {
            "Body": io.BytesIO(value["Body"]),
            "VersionId": "v1",
            "ContentLength": len(value["Body"]),
            "ServerSideEncryption": "AES256",
            "Metadata": value["Metadata"],
        } | self.get_override


def clients(store):
    # The reader has no write method and the writer has no bucket/history methods.
    return (
        SimpleNamespace(list_object_versions=store.list_object_versions),
        SimpleNamespace(put_object=store.put_object, get_object=store.get_object),
    )


def test_success_binds_both_revisions_and_one_version(module, sample, tmp_path):
    approval, proof, package = sample
    store = Store(tmp_path)
    receipt = module.transfer(*clients(store), approval, proof, package, tmp_path)
    assert len(store.puts) == len(store.gets) == 1
    assert store.puts[0]["Body"] is package
    assert receipt["key"] == f"lambda/{approval['artifact_source_sha']}/456/1/app.zip"
    assert proof["workflow_execution_sha"] not in receipt["key"]
    assert receipt["artifact_source_sha"] != receipt["workflow_execution_sha"]
    assert receipt["status"] == "P4_LAMBDA_ARTIFACT_UPLOADED_VERIFIED"
    assert receipt["local_zip_sha256"] == receipt["retrieved_zip_sha256"]
    assert receipt["version_id"] == "v1"
    assert (tmp_path / "retrieved-app.zip").read_bytes() == package
    assert json.loads((tmp_path / "receipt.private.json").read_bytes()) == receipt
    assert module.config().retries["total_max_attempts"] == 1


def test_uncertain_put_cannot_be_retried(module, sample, tmp_path):
    store = Store(tmp_path)
    store.uncertain = True
    with pytest.raises(TimeoutError):
        module.transfer(*clients(store), *sample, tmp_path)
    assert (tmp_path / "attempt.private.json").exists()
    assert not (tmp_path / "receipt.private.json").exists()
    with pytest.raises(module.UploadError, match="UploadAlreadyAttempted"):
        module.transfer(*clients(store), *sample, tmp_path)
    assert len(store.puts) == 1


def test_real_sdk_request_shapes_and_single_attempt(module, sample, tmp_path):
    import boto3
    from botocore.stub import Stubber

    approval, proof, package = sample
    client = boto3.Session(region_name=module.REGION).client(
        "s3",
        aws_access_key_id="synthetic",
        aws_secret_access_key="synthetic",
        config=module.config(),
    )
    assert client.meta.config.retries["total_max_attempts"] == 1
    key = f"lambda/{approval['artifact_source_sha']}/456/1/app.zip"
    metadata = {
        "artifact-source-sha": approval["artifact_source_sha"],
        "workflow-execution-sha": proof["workflow_execution_sha"],
        "github-run-id": "456",
        "github-run-attempt": "1",
        "manifest-sha256": approval["manifest_sha256"],
        "provenance-sha256": approval["provenance_sha256"],
    }
    common = {
        "Bucket": approval["bucket"],
        "Key": key,
        "ExpectedBucketOwner": approval["aws_account"],
    }
    pages = iter(
        [
            {"IsTruncated": False},
            {"IsTruncated": False, "Versions": [{"Key": key, "VersionId": "v1", "IsLatest": True}]},
        ]
    )
    reader = SimpleNamespace(list_object_versions=lambda **kw: next(pages))
    with Stubber(client) as stub:
        stub.add_response(
            "put_object",
            {
                "VersionId": "v1",
                "ETag": "etag",
                "ServerSideEncryption": "AES256",
            },
            common
            | {
                "Body": package,
                "IfNoneMatch": "*",
                "ServerSideEncryption": "AES256",
                "ChecksumSHA256": base64.b64encode(bytes.fromhex(approval["zip_sha256"])).decode(),
                "Metadata": metadata,
            },
        )
        stub.add_response(
            "get_object",
            {
                "VersionId": "v1",
                "Body": io.BytesIO(package),
                "ContentLength": len(package),
                "ServerSideEncryption": "AES256",
                "Metadata": metadata,
            },
            common | {"VersionId": "v1"},
        )
        receipt = module.transfer(reader, client, approval, proof, package, tmp_path)
        stub.assert_no_pending_responses()
    assert receipt["upload_logical_attempts"] == 1


@pytest.mark.parametrize("kind", ["version", "delete_marker"])
def test_preexisting_history_blocks_put(module, sample, tmp_path, kind):
    approval, proof, package = sample
    store = Store(tmp_path)
    item = {"Key": f"lambda/{approval['artifact_source_sha']}/456/1/app.zip", "VersionId": "old"}
    (store.extra if kind == "version" else store.markers).append(item)
    with pytest.raises(module.UploadError, match="ArtifactKeyAlreadyUsed"):
        module.transfer(*clients(store), approval, proof, package, tmp_path)
    assert store.puts == []
    assert not (tmp_path / "attempt.private.json").exists()


@pytest.mark.parametrize("version", [None, "", "null", " v1", 123])
def test_unusable_put_version_is_not_success(module, sample, tmp_path, version):
    store = Store(tmp_path)
    store.put_override["VersionId"] = version
    with pytest.raises(module.UploadError, match="VersionIdRequired"):
        module.transfer(*clients(store), *sample, tmp_path)
    assert len(store.puts) == 1
    assert store.gets == []
    assert not (tmp_path / "receipt.private.json").exists()


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"VersionId": "v2"}, "ReadbackVersionMismatch"),
        ({"ContentLength": 0}, "ReadbackSizeMismatch"),
        ({"ServerSideEncryption": "aws:kms"}, "ReadbackEncryptionMismatch"),
        ({"Metadata": {}}, "ReadbackIdentityMismatch"),
        ({"Body": b"different ZIP byt!"}, "ReadbackHashMismatch"),
    ],
)
def test_readback_mismatch_preserves_attempt_without_receipt(
    module, sample, tmp_path, change, expected
):
    store = Store(tmp_path)
    if "Body" in change:
        # Same length as the approved bytes, so digest verification must catch it.
        change = {"Body": io.BytesIO(b"x" * len(sample[2]))}
    store.get_override.update(change)
    with pytest.raises(module.UploadError, match=expected):
        module.transfer(*clients(store), *sample, tmp_path)
    assert len(store.puts) == 1
    assert (tmp_path / "attempt.private.json").exists()
    assert not (tmp_path / "receipt.private.json").exists()


def test_corrupt_source_never_reaches_put(module, sample, tmp_path):
    approval, proof, package = sample
    store = Store(tmp_path)
    with pytest.raises(module.UploadError, match="ArtifactHashMismatch"):
        module.transfer(*clients(store), approval, proof, b"x" + package[1:], tmp_path)
    assert not store.puts


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"IsTruncated": True},
        {"IsTruncated": True, "NextKeyMarker": "same", "NextVersionIdMarker": "same"},
    ],
)
def test_incomplete_or_cyclic_history_fails_closed(module, sample, response):
    client = SimpleNamespace(list_object_versions=lambda **kw: response)
    with pytest.raises(module.UploadError):
        module.versions(client, sample[0], "key")


@pytest.fixture
def ci(module, monkeypatch, tmp_path, sample):
    approval, proof, _ = sample
    event = tmp_path / "event.json"
    label = "p4-upload-existing-test"
    event.write_text(
        json.dumps({"inputs": {"operation": "upload-existing", "upload_runner_label": label}})
    )
    env = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": module.REPOSITORY,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REF_TYPE": "branch",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_JOB": "upload_existing",
        "P4_OPERATION": "upload-existing",
        "GITHUB_RUN_ATTEMPT": "1",
        "RUNNER_ENVIRONMENT": "self-hosted",
        "GITHUB_SHA": proof["workflow_execution_sha"],
        "GITHUB_RUN_ID": "456",
        "P4_APPROVED_EXECUTION_SHA": proof["workflow_execution_sha"],
        "P4_APPROVED_RUN_ID": "456",
        "GITHUB_WORKFLOW_SHA": proof["workflow_execution_sha"],
        "GITHUB_WORKFLOW_REF": f"{module.REPOSITORY}/{module.WORKFLOW}@refs/heads/main",
        "RUNNER_NAME": "ephemeral",
        "P4_APPROVED_RUNNER_NAME": "ephemeral",
        "GITHUB_EVENT_PATH": str(event),
        "P4_APPROVED_RUNNER_LABEL": label,
        "GITHUB_ACTOR": "operator",
        "GITHUB_TRIGGERING_ACTOR": "operator",
    }
    run = {
        "id": 456,
        "run_attempt": 1,
        "head_sha": proof["workflow_execution_sha"],
        "head_branch": "main",
        "event": "workflow_dispatch",
        "path": module.WORKFLOW,
        "repository": {"full_name": module.REPOSITORY},
        "status": "in_progress",
        "actor": {"login": "operator"},
        "triggering_actor": {"login": "operator"},
        "workflow_id": 100,
        "name": "P4",
    }

    def git(root, *args):
        if args[0] == "rev-parse":
            return proof["workflow_execution_sha"].encode()
        if args[0] == "status":
            return b""
        assert args == ("config", "--get", "remote.origin.url")
        return f"https://github.com/{module.REPOSITORY}.git".encode()

    def github(suffix, _):
        if suffix == "actions/runs/456":
            return run
        if suffix == "git/ref/heads/main":
            return {"object": {"sha": proof["workflow_execution_sha"]}}
        if suffix == "environments/dev":
            return {
                "deployment_branch_policy": {
                    "protected_branches": False,
                    "custom_branch_policies": True,
                }
            }
        return {"total_count": 1, "branch_policies": [{"name": "main", "type": "branch"}]}

    monkeypatch.setattr(module, "git", git)
    monkeypatch.setattr(module, "github", github)
    return env, run


def test_live_context_binding(module, ci, tmp_path):
    proof = module.identity(tmp_path, ci[0])
    assert proof["job"] == "upload_existing"
    assert proof["operation"] == "upload-existing"
    assert proof["run_id"] == "456"


@pytest.mark.parametrize(
    "key,value",
    [
        ("GITHUB_EVENT_NAME", "push"),
        ("GITHUB_RUN_ATTEMPT", "2"),
        ("GITHUB_JOB", "deployment"),
        ("GITHUB_REF", "refs/heads/feature"),
        ("P4_OPERATION", "plan"),
        ("P4_APPROVED_RUN_ID", "999"),
        ("P4_APPROVED_EXECUTION_SHA", "f" * 40),
        ("GITHUB_WORKFLOW_SHA", "f" * 40),
        ("RUNNER_NAME", "unexpected"),
        ("GITHUB_WORKFLOW_REF", "other/workflow@refs/heads/main"),
    ],
)
def test_wrong_ci_context_precedes_upload(module, ci, tmp_path, key, value):
    ci[0][key] = value
    with pytest.raises(module.UploadError):
        module.identity(tmp_path, ci[0])


@pytest.mark.parametrize(
    "key,value",
    [
        ("head_sha", "f" * 40),
        ("head_branch", "feature"),
        ("event", "push"),
        ("path", ".github/workflows/backend.yml"),
        ("run_attempt", 2),
        ("status", "completed"),
        ("actor", {"login": "someone_else"}),
    ],
)
def test_api_run_mismatch(module, ci, tmp_path, key, value):
    ci[1][key] = value
    with pytest.raises(module.UploadError, match="GitHubRunMismatch"):
        module.identity(tmp_path, ci[0])


def token_for(value):
    payload = base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")
    return "header." + payload + ".signature"


@pytest.fixture
def oidc(sample, module):
    approval, proof, _ = sample
    return {
        "iss": "https://token.actions.githubusercontent.com",
        "aud": "sts.amazonaws.com",
        "sub": approval["oidc_subject"],
        "repository": module.REPOSITORY,
        "environment": "dev",
        "ref": proof["ref"],
        "sha": proof["workflow_execution_sha"],
        "workflow_sha": proof["workflow_execution_sha"],
        "workflow_ref": f"{module.REPOSITORY}/{module.WORKFLOW}@refs/heads/main",
        "event_name": "workflow_dispatch",
        "run_id": "456",
        "run_attempt": "1",
        "actor": "operator",
        "iat": 900,
        "nbf": 900,
        "exp": 1600,
    }


@pytest.mark.parametrize(
    "key",
    [
        "iss",
        "aud",
        "sub",
        "repository",
        "environment",
        "ref",
        "sha",
        "workflow_sha",
        "workflow_ref",
        "event_name",
        "run_id",
        "run_attempt",
        "actor",
    ],
)
def test_every_required_oidc_claim_is_checked(module, sample, oidc, key):
    approval, proof, _ = sample
    assert module.claims(token_for(oidc), proof, approval, now=1000)[key] == oidc[key]
    oidc[key] = "wrong"
    with pytest.raises(module.UploadError, match="OidcClaimsMismatch"):
        module.claims(token_for(oidc), proof, approval, now=1000)


def test_expired_oidc_token_rejected(module, sample, oidc):
    with pytest.raises(module.UploadError, match="OidcExpired"):
        module.claims(token_for(oidc), sample[1], sample[0], now=1700)


def test_read_only_source_provenance_and_tampering(module, monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    evidence = source / "final-validation-20261003"
    evidence.mkdir()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("interview_backend/__init__.py", b"approved source")
        for i in range(2365):
            archive.writestr(f"dependency/{i}", b"data")
    package = output.getvalue()
    lock = b"synthetic locked dependencies"
    sha = "a" * 40
    manifest = {
        "code_sha": sha,
        "sha256": module.sha256(package),
        "runtime": "python3.14",
        "architecture": "x86_64",
        "lock_sha256": module.sha256(lock),
        "sha256_base64": base64.b64encode(bytes.fromhex(module.sha256(package))).decode(),
    }
    (source / "app.zip").write_bytes(package)
    (source / "package.json").write_text(json.dumps(manifest))
    binding = {
        "artifact_source_sha": sha,
        "zip_sha256": module.sha256(package),
        "zip_size": len(package),
        "manifest_sha256": module.sha256((source / "package.json").read_bytes()),
    }
    final = {
        "status": "P4_LAMBDA_ARTIFACT_READY",
        "code_sha": sha,
        "source_blob_matches": 287,
        "security": {
            "zip_sha256": binding["zip_sha256"],
            "manifest_sha256": binding["manifest_sha256"],
            "status": "LAMBDA_ARTIFACT_SECURITY_PASS",
            "unknown_findings": [],
            "entries_scanned": 2366,
            "app_head_blob_matches": 1,
        },
    }
    (evidence / "final.private.json").write_text(json.dumps(final))
    (evidence / "baseline.private.json").write_text(
        json.dumps(
            {
                "binding": {
                    "code_sha": sha,
                    "official_origin_verified": True,
                    "source_and_builder_blobs_verified": True,
                }
            }
        )
    )
    provenance = binding | {
        "evidence_files": {
            str(p.relative_to(source)).replace("\\", "/"): module.sha256(p.read_bytes())
            for p in evidence.iterdir()
        }
    }
    provenance_path = tmp_path / "provenance.json"
    provenance_path.write_text(json.dumps(provenance))
    approval = binding | {"provenance_sha256": module.sha256(provenance_path.read_bytes())}

    def git(root, *args):
        if args[0] == "ls-tree":
            return b"backend/src/interview_backend/__init__.py\n"
        return lock if args[-1].endswith("uv.lock") else b"approved source"

    monkeypatch.setattr(module, "git", git)
    assert module.artifact(tmp_path, source, provenance_path, approval) == package
    (evidence / "final.private.json").write_text("{}")
    with pytest.raises(module.UploadError, match="EvidenceHashMismatch"):
        module.artifact(tmp_path, source, provenance_path, approval)


def test_upload_driver_cannot_import_build_or_terraform(module):
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [
        node.module if isinstance(node, ast.ImportFrom) else item.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for item in (node.names if isinstance(node, ast.Import) else [None])
    ]
    assert not any(
        name and any(x in name for x in ("ci_deploy", "build_lambda", "terraform"))
        for name in imports
    )
    calls = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert calls.count("put_object") == 1
    assert not {"delete_object", "copy_object", "upload_file", "upload_fileobj"} & set(calls)


def test_workflow_upload_job_is_independent_and_skips_normal_jobs():
    root = Path(__file__).resolve().parents[3]
    workflow = (root / ".github/workflows/p4-deploy.yml").read_text(encoding="utf-8")
    assert "options: [plan, apply, upload-existing]" in workflow
    for name in ("backend", "offline", "deployment"):
        assert f"  {name}:\n    if: inputs.operation != 'upload-existing'" in workflow
    upload = workflow.split("  upload_existing:\n", 1)[1]
    assert "needs:" not in upload
    assert "id-token: write" in upload
    assert "environment: dev" in upload
    assert "upload_existing.py" in upload
    assert not any(value in upload for value in ("terraform", "ci_deploy", "setup-uv", "uv sync"))


def test_failure_record_never_contains_exception_secrets(module, monkeypatch, tmp_path):
    monkeypatch.setenv("P4_UPLOAD_RECEIPT_DIR", str(tmp_path))
    monkeypatch.setattr(
        module, "identity", lambda *args: (_ for _ in ()).throw(RuntimeError("SECRET_TOKEN"))
    )
    assert module.main() == 1
    raw = (tmp_path / "failure.private.json").read_text()
    assert "SECRET_TOKEN" not in raw
    assert json.loads(raw)["stage"] == "ci_identity"
