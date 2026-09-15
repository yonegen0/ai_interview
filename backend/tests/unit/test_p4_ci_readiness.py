"""CI preflight and claim discovery must not create AWS clients."""

import base64
import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_p4_tools import tool


@pytest.fixture
def tools_path(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "skills/p4"))


def test_discovery_allowlists_claims_without_aws(tools_path):
    module = tool("oidc_discovery")
    claims = {
        "iss": "https://token.actions.githubusercontent.com",
        "aud": "sts.amazonaws.com",
        "sub": "repo:yonegen0/ai_interview:environment:dev",
        "repository": "yonegen0/ai_interview",
        "repository_id": "1234",
        "environment": "dev",
        "ref": "refs/heads/main",
        "sha": "a" * 40,
        "private": "never-display",
    }
    token = (
        "header."
        + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        + ".signature"
    )
    env = {
        "P4_OIDC_DISCOVERY_READY": "true",
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF": claims["ref"],
        "GITHUB_REPOSITORY": claims["repository"],
        "GITHUB_SHA": claims["sha"],
        "ACTIONS_ID_TOKEN_REQUEST_URL": "https://test.actions.githubusercontent.com/token",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "synthetic",
    }
    opener = SimpleNamespace(open=lambda *a, **kw: BytesIO(json.dumps({"value": token}).encode()))
    result = module.discover(env, opener=opener)
    assert set(result) == {"iss", "aud", "sub", "repository", "repository_id"}
    assert "never-display" not in json.dumps(result)
    assert token not in json.dumps(result)


def test_discovery_gate_precedes_http(tools_path):
    module = tool("oidc_discovery")
    with pytest.raises(ValueError, match="OidcDiscoveryPrerequisitesUnconfirmed"):
        module.discover(
            {}, opener=SimpleNamespace(open=lambda *a, **kw: pytest.fail("HTTP called"))
        )


def test_redirect_cannot_forward_oidc_request_token(tools_path):
    from urllib.request import Request

    redirect = tool("ci_identity").NoRedirect()
    request = Request(
        "https://test.actions.githubusercontent.com/token",
        headers={"Authorization": "Bearer synthetic"},
    )
    assert (
        redirect.redirect_request(request, None, 302, "redirect", {}, "https://other.invalid/")
        is None
    )


def test_build_environment_drops_credentials_and_import_overrides(tools_path):
    module = tool("ci_deploy")
    env = {
        "AWS_ACCESS_KEY_ID": "private",
        "AWS_PROFILE": "private",
        "AWS_SESSION_TOKEN": "private",
        "GH_TOKEN": "private",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "private",
        "P4_DEPLOY_INPUTS": "private",
        "PYTHONPATH": "other-zip",
        "PATH": "synthetic",
    }
    child = module.build_environment(env)
    assert "private" not in child.values()
    assert "PYTHONPATH" not in child
    assert child["PATH"] == "synthetic"
    assert env["AWS_PROFILE"] == "private"


@pytest.mark.parametrize("inputs", ["{}", "[]", "null", '{"artifact_key":"override"}'])
def test_ci_invalid_inputs_precede_build_and_aws(tools_path, monkeypatch, inputs):
    module = tool("ci_deploy")
    monkeypatch.setattr(module, "account_settings", lambda *a: ("123456789012", "ap-northeast-1"))
    with pytest.raises(ValueError, match="ExplicitDeploymentInputsRequired"):
        module.preflight(
            {"P4_AWS_EXECUTION_READY": "true", "P4_OPERATION": "plan", "P4_DEPLOY_INPUTS": inputs}
        )


@pytest.mark.parametrize("failure", [None, "apply", "readback"])
def test_durable_apply_receipt_controls_retry(tools_path, monkeypatch, tmp_path, failure):
    from botocore.exceptions import ClientError

    module = tool("ci_deploy")
    objects, operations = {}, []

    def put(**kw):
        if kw["Key"] in objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        objects[kw["Key"]] = kw["Body"]
        return {"VersionId": "v1"}

    def get(**kw):
        if kw["Key"] not in objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"VersionId": "v1", "Body": BytesIO(objects[kw["Key"]])}

    s3 = SimpleNamespace(
        put_object=put,
        get_object=get,
        list_objects_v2=lambda **kw: {
            "Contents": [{"Key": key} for key in objects if key.startswith(kw["Prefix"])],
            "IsTruncated": False,
        },
    )
    monkeypatch.setattr(module, "role_session", lambda *a: SimpleNamespace(client=lambda *a: s3))

    def execute(operation, *args, progress=None):
        operations.append(operation)
        if progress:
            progress("apply_started")
            if failure == "apply":
                raise ValueError("SyntheticApplyFailure")
            progress("apply_completed")
            if failure == "readback":
                raise ValueError("SyntheticReadbackFailure")
        return {"status": "applied_readback_verified"}

    monkeypatch.setattr(module, "execute", execute)
    args = (
        "123456789012",
        "ap-northeast-1",
        "bucket",
        "plans/1/1",
        "a" * 64,
        tmp_path / "inputs",
        tmp_path,
    )
    if failure:
        with pytest.raises(ValueError, match="Synthetic"):
            module.apply_saved_plan(*args)
    else:
        assert module.apply_saved_plan(*args)["status"] == "applied_readback_verified"
    if failure == "apply":
        with pytest.raises(ValueError, match="ApplyOutcomeUnknownNewPlanRequired"):
            module.apply_saved_plan(*args)
        assert operations == ["apply"]
    else:
        module.apply_saved_plan(*args)
        assert operations == ["apply", "verify"]


@pytest.mark.parametrize(
    "fail_upload", [None, "dev.tfplan", "plan.json", "summary.json", "review.private.json"]
)
def test_ci_plan_transport_commits_envelope_last(tools_path, monkeypatch, tmp_path, fail_upload):
    module = tool("ci_deploy")
    monkeypatch.setattr(module, "PROJECT", tmp_path)
    account, region, sha = "123456789012", "ap-northeast-1", "a" * 40
    monkeypatch.setattr(module, "preflight", lambda env: (account, region, "plan", {}))
    monkeypatch.setattr(module, "checked_git", lambda *a: sha)
    monkeypatch.setenv("GITHUB_RUN_ID", "1")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    uploads = []

    def put(s3, bucket, key, body):
        uploads.append(key)
        if fail_upload and key.endswith("/" + fail_upload):
            raise ValueError("SyntheticUploadFailure")
        return "v1"

    monkeypatch.setattr(module, "put", put)
    monkeypatch.setattr(module, "role_session", lambda *a: SimpleNamespace(client=lambda *a: None))

    def build(directory, sha):
        package = directory / "app.zip"
        package.write_bytes(b"same-zip")
        return package, {"sha256_base64": "A" * 43 + "="}

    monkeypatch.setattr(module, "build_package", build)

    def execute(operation, path, directory):
        assert operation == "plan"
        directory.mkdir()
        for name in ("dev.tfplan", "plan.json", "summary.json", "review.private.json"):
            (directory / name).write_bytes(b"synthetic")
        return {"plan_sha256": "b" * 64}

    monkeypatch.setattr(module, "execute", execute)
    assert module.main() == (1 if fail_upload else 0)
    if fail_upload:
        assert not any(key.endswith("envelope.json") for key in uploads)
    else:
        assert uploads[-1] == "plans/1/1/envelope.json"


@pytest.mark.parametrize(
    "field,value",
    [
        ("head_sha", "b" * 40),
        ("id", 99),
        ("head_branch", "feature"),
        ("conclusion", "failure"),
        ("event", "push"),
        ("path", ".github/workflows/other.yml"),
        ("repository", {"full_name": "other/repository"}),
        ("run_attempt", 0),
        ("status", "in_progress"),
    ],
)
def test_source_plan_run_mismatch(tools_path, monkeypatch, field, value):
    import urllib.request

    module = tool("ci_deploy")
    data = {
        "head_sha": "a" * 40,
        "id": 1,
        "head_branch": "main",
        "conclusion": "success",
        "event": "workflow_dispatch",
        "path": ".github/workflows/p4-deploy.yml",
        "repository": {"full_name": "yonegen0/ai_interview"},
        "run_attempt": 1,
        "status": "completed",
    }
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv("GH_TOKEN", "synthetic")
    monkeypatch.setattr(
        urllib.request,
        "build_opener",
        lambda *a: SimpleNamespace(open=lambda *a, **kw: BytesIO(json.dumps(data).encode())),
    )
    assert module.github_run("1") == "1"
    data[field] = value
    with pytest.raises(ValueError, match="SuccessfulMainPlanRequired"):
        module.github_run("1")


@pytest.mark.parametrize(
    "tamper",
    [None, "plan", "operation", "run_id", "run_attempt", "code_sha", "missing_plan", "version"],
)
def test_plan_to_apply_transport(tools_path, monkeypatch, tmp_path, tamper):
    import hashlib

    from botocore.exceptions import ClientError

    module = tool("ci_deploy")
    monkeypatch.setattr(module, "PROJECT", tmp_path)
    account, region, sha = "123456789012", "ap-northeast-1", "a" * 40
    config = {
        "boundary_arn": f"arn:aws:iam::{account}:policy/ai-interview-runtime-boundary",
        "ses_email": "sender@example.invalid",
        "ses_identity_arn": f"arn:aws:ses:{region}:{account}:identity/example.invalid",
        "alarm_email": "alarm@example.invalid",
        "jpy_per_usd": "150",
        "budget_rate_date": "2026-09-14",
        "worker_enabled": False,
        "streams_enabled": False,
        "scheduler_enabled": False,
        "api_enabled": False,
    }
    monkeypatch.setattr(
        module, "preflight", lambda env: (account, region, env["P4_OPERATION"], dict(config))
    )
    monkeypatch.setattr(module, "checked_git", lambda *a: sha)
    monkeypatch.setattr(module, "github_run", lambda *a: "1")
    objects, operations = {}, []

    def put(**kw):
        if kw["Key"] in objects:
            raise ValueError("ImmutableObjectConflict")
        objects[kw["Key"]] = kw["Body"]
        return {"VersionId": "v1"}

    def get(**kw):
        if kw["Key"] not in objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {
            "VersionId": "different"
            if tamper == "version" and kw["Key"].endswith("dev.tfplan")
            else "v1",
            "Body": BytesIO(objects[kw["Key"]]),
        }

    s3 = SimpleNamespace(
        put_object=put,
        get_object=get,
        list_objects_v2=lambda **kw: {
            "Contents": [{"Key": key} for key in objects if key.startswith(kw["Prefix"])],
            "IsTruncated": False,
        },
    )
    monkeypatch.setattr(module, "role_session", lambda *a: SimpleNamespace(client=lambda *a: s3))

    def build(directory, sha):
        path = directory / "app.zip"
        path.write_bytes(b"same-zip")
        return path, {"sha256_base64": "A" * 43 + "="}

    monkeypatch.setattr(module, "build_package", build)
    hashed = hashlib.sha256(b"plan").hexdigest()

    def execute(operation, inputs, directory, approved=None, *, progress=None):
        operations.append(operation)
        if operation == "plan":
            directory.mkdir()
            (directory / "dev.tfplan").write_bytes(b"plan")
            for name in ("plan.json", "summary.json", "review.private.json"):
                (directory / name).write_text("{}", encoding="utf-8")
            return {"plan_sha256": hashed}
        assert approved == hashed
        assert (directory / "dev.tfplan").read_bytes() == b"plan"
        progress("apply_started")
        progress("apply_completed")
        (directory / "deployment.json").write_text("{}", encoding="utf-8")
        return {"status": "applied_readback_verified"}

    monkeypatch.setattr(module, "execute", execute)
    for key, value in {
        "P4_OPERATION": "plan",
        "GITHUB_RUN_ID": "1",
        "GITHUB_RUN_ATTEMPT": "1",
        "P4_PLAN_HASH": hashed,
        "P4_PLAN_RUN_ID": "1",
    }.items():
        monkeypatch.setenv(key, value)
    assert module.main() == 0
    if tamper == "plan":
        objects["plans/1/1/dev.tfplan"] = b"altered"
    elif tamper == "missing_plan":
        del objects["plans/1/1/dev.tfplan"]
    elif tamper in {"operation", "run_id", "run_attempt", "code_sha"}:
        envelope = json.loads(objects["plans/1/1/envelope.json"])
        envelope[tamper] = "other"
        objects["plans/1/1/envelope.json"] = json.dumps(envelope).encode()
    monkeypatch.setenv("P4_OPERATION", "apply")
    monkeypatch.setenv("GITHUB_RUN_ID", "2")
    assert module.main() == (1 if tamper else 0)
    assert operations == (["plan"] if tamper else ["plan", "apply"])


@pytest.mark.parametrize("failure", [None, "expired", "switch"])
def test_oidc_role_exchange_failure_is_redacted(tools_path, monkeypatch, failure):
    import boto3

    module = tool("ci_identity")
    for key, value in {
        "P4_AWS_EXECUTION_READY": "true",
        "GITHUB_ACTIONS": "true",
        "GITHUB_RUN_ID": "1",
        "ACTIONS_ID_TOKEN_REQUEST_URL": "https://test.actions.githubusercontent.com/token",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "private-request-token",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(module, "validated_claims", lambda *a: {})
    monkeypatch.setattr(
        module,
        "build_opener",
        lambda *a: SimpleNamespace(open=lambda *a, **kw: BytesIO(b'{"value":"private-id-token"}')),
    )

    def exchange(**kwargs):
        if failure == "expired":
            raise RuntimeError("private-id-token expired")
        return {
            "Credentials": {
                "AccessKeyId": "synthetic",
                "SecretAccessKey": "synthetic",
                "SessionToken": "synthetic",
            }
        }

    monkeypatch.setattr(
        boto3,
        "Session",
        lambda **kw: SimpleNamespace(
            client=lambda *a, **kw: SimpleNamespace(assume_role_with_web_identity=exchange)
        ),
    )

    def checked(*args):
        if failure == "switch":
            from interview_backend.deployment import DeploymentError

            raise DeploymentError("AwsAccountMismatch")
        return "session"

    monkeypatch.setattr(module, "checked_session", checked)
    # Ensure restoration even though the production function updates os.environ.
    for key in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
    ):
        monkeypatch.setenv(key, "synthetic")
    if failure:
        with pytest.raises(ValueError) as error:
            module.assume("deploy", "123456789012", "ap-northeast-1", expected_subject="subject")
        assert "private" not in str(error.value)
    else:
        assert (
            module.assume("deploy", "123456789012", "ap-northeast-1", expected_subject="subject")
            == "session"
        )
