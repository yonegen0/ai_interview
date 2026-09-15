"""Deployment tools are tested offline; fixture files contain synthetic values only."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def tool(name):
    location = Path(__file__).resolve().parents[2] / "skills" / "p4" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, location)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest():
    account, region, prefix = "123456789012", "ap-northeast-1", "ai-interview-dev"
    queue = f"https://sqs.{region}.amazonaws.com/{account}/{prefix}"
    return {
        "schema_version": 2,
        "configuration": {
            "boundary_arn": f"arn:aws:iam::{account}:policy/ai-interview-runtime-boundary",
            "ses_email": "sender@example.invalid",
            "ses_identity_arn": f"arn:aws:ses:{region}:{account}:identity/example.invalid",
            "alarm_email": "alarms@example.invalid",
            "monthly_budget_usd": "20.00",
            "cors_origins": ["http://localhost:3000"],
            "worker_enabled": False,
            "streams_enabled": False,
            "scheduler_enabled": False,
            "api_enabled": False,
        },
        "account_id": account,
        "region": region,
        "environment": "dev",
        "run_id": "",
        "table_name": prefix + "-main",
        "api_id": "synthetic",
        "api_endpoint": f"https://synthetic.execute-api.{region}.amazonaws.com/dev",
        "queue_arn": f"arn:aws:sqs:{region}:{account}:{prefix}-main",
        "queue_url": queue + "-main",
        "worker_dlq_url": queue + "-worker-dlq",
        "stream_failure_url": queue + "-stream-failure",
        "user_pool_id": region + "_synthetic",
        "client_id": "synthetic",
        "versions": {k: "1" for k in ("api", "worker", "dispatcher")},
        "aliases": {
            k: f"arn:aws:lambda:{region}:{account}:function:{prefix}-{role}:{alias}"
            for k, role, alias in (
                ("api", "api", "live"),
                ("worker", "worker", "live"),
                ("streams", "dispatcher", "streams"),
                ("recovery", "dispatcher", "recovery"),
            )
        },
        "artifact": {"sha256_base64": "synthetic-hash"},
    }


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"account_id": "999999999999"},
        {"region": "us-east-1"},
        {"environment": "test"},
        {"run_id": "other"},
        {"aliases": {}},
        {"api_endpoint": "https://attacker.invalid"},
        {"versions": {}},
    ],
)
def test_manifest_validation(tmp_path, change):
    module = tool("manifest")
    data = manifest() | change
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    if change:
        with pytest.raises(ValueError, match="InvalidDeploymentManifest"):
            module.read_manifest(path, "123456789012", "ap-northeast-1")
    else:
        assert module.read_manifest(path, "123456789012", "ap-northeast-1") == data
        with pytest.raises(ValueError):
            module.read_manifest(path, "123456789012", "ap-northeast-1", require_test=True)


@pytest.mark.parametrize("data", [None, [], 1, {"versions": []}])
def test_malformed_manifest_redacted(tmp_path, data):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="InvalidDeploymentManifest"):
        tool("manifest").read_manifest(path, "123456789012", "ap-northeast-1")


def test_readback_rejects_before_api_or_tokens():
    calls = []

    def client(name, **kwargs):
        calls.append(name)
        return SimpleNamespace(get_caller_identity=lambda: {"Account": "999999999999"})

    with pytest.raises(ValueError, match="DeploymentReadbackFailed"):
        tool("manifest").verify_live_manifest(SimpleNamespace(client=client), manifest())
    assert calls == ["sts"]


def test_package_rejects_missing_sha_without_reading_files():
    with pytest.raises(ValueError, match="FullCodeShaRequired"):
        tool("build_lambda").build("missing", "missing", "missing", "missing", "main")


def test_package_rejects_output_inside_source(tmp_path):
    with pytest.raises(ValueError, match="FreshSeparateOutputRequired"):
        tool("build_lambda").build(tmp_path, tmp_path, "missing", tmp_path / "app.zip", "a" * 40)


def test_saved_plan_binding_rejects_changes(tmp_path):
    module = tool("terraform_dev")
    plan = tmp_path / "dev.tfplan"
    plan.write_bytes(b"synthetic-plan")
    hashed = module.digest(plan)
    expected = {"account_id": "123456789012", "code_sha": "a" * 40}
    actual = expected | {"plan_sha256": hashed}
    module.assert_binding(actual, expected, plan, hashed)
    for changed in (actual | {"code_sha": "b" * 40}, actual | {"account_id": "999999999999"}):
        with pytest.raises(ValueError, match="SavedPlanMismatch"):
            module.assert_binding(changed, expected, plan, hashed)
    plan.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SavedPlanMismatch"):
        module.assert_binding(actual, expected, plan, hashed)


def test_local_terraform_apply_rejected_before_aws(tmp_path):
    with pytest.raises(ValueError, match="ManualGitHubWorkflowRequired"):
        tool("terraform_dev").checked_git(tmp_path, {})


def test_bootstrap_rejects_without_two_explicit_gates_before_commands(monkeypatch, tmp_path):
    module = tool("bootstrap_state")
    monkeypatch.setattr(module, "run", lambda *a, **kw: pytest.fail("unexpected command"))
    monkeypatch.setattr(
        module, "checked_session", lambda *a, **kw: pytest.fail("unexpected AWS client")
    )
    with pytest.raises(ValueError, match="BootstrapExecutionPrerequisitesUnconfirmed"):
        module.execute(tmp_path / "inputs.json", tmp_path / "run", {})


def test_bootstrap_inputs_are_exact_and_errors_are_redacted(tmp_path):
    module = tool("bootstrap_state")
    valid = {
        "oidc_provider_arn": "",
        "oidc_subjects": {
            name: "repo:yonegen0/ai_interview:environment:dev"
            for name in ("artifact", "plan", "deploy", "test")
        },
        "ses_identity_type": "email",
        "ses_from_email": "private@example.invalid",
        "ses_domain": "",
    }
    path = tmp_path / "inputs.json"
    path.write_text(json.dumps(valid), encoding="utf-8")
    result = module.inputs(path, "123456789012", "ap-northeast-1")
    assert result["account_id"] == "123456789012"
    assert result["region"] == "ap-northeast-1"
    path.write_text(json.dumps(valid | {"private-token": "secret-value"}), encoding="utf-8")
    with pytest.raises(ValueError, match="ExplicitBootstrapInputsRequired") as error:
        module.inputs(path, "123456789012", "ap-northeast-1")
    assert "private" not in str(error.value)
    assert "secret" not in str(error.value)


def test_bootstrap_migration_failure_preserves_local_state(monkeypatch, tmp_path):
    module = tool("bootstrap_state")
    monkeypatch.setattr(module, "migration_target", lambda *args: None)
    local_state = tmp_path / "terraform.tfstate"
    local_state.write_bytes(b'{"lineage":"synthetic","serial":1,"resources":[]}')

    def fail(*args, **kwargs):
        local_state.unlink()
        raise ValueError("TerraformOperationFailed")

    monkeypatch.setattr(module, "run", fail)
    with pytest.raises(ValueError, match="TerraformOperationFailed"):
        module.migrate_state(
            tmp_path,
            {},
            local_state,
            "ai-interview-state-123456789012-ap-northeast-1",
            "123456789012",
            "ap-northeast-1",
        )
    assert not local_state.exists()
    assert (tmp_path / "pre-migration.tfstate").read_bytes().startswith(b'{"lineage"')
    assert (tmp_path / "backend.tf").read_text(encoding="utf-8") == module.S3_BACKEND


def test_bootstrap_readback_requires_versioned_hardened_buckets():
    module = tool("bootstrap_state")
    account = "123456789012"
    region = "ap-northeast-1"
    outputs = {
        "state_bucket": f"ai-interview-state-{account}-{region}",
        "artifact_bucket": f"ai-interview-artifacts-{account}-{region}",
        "boundary_arn": f"arn:aws:iam::{account}:policy/ai-interview-runtime-boundary",
        "oidc_provider_arn": (
            f"arn:aws:iam::{account}:oidc-provider/token.actions.githubusercontent.com"
        ),
        "roles": {
            name: f"arn:aws:iam::{account}:role/ai-interview-ci-{name}"
            for name in ("artifact", "plan", "deploy", "test")
        },
        "ses_identity_arn": f"arn:aws:ses:{region}:{account}:identity/example.invalid",
    }
    s3 = SimpleNamespace(
        head_bucket=lambda **kw: {},
        get_bucket_versioning=lambda **kw: {"Status": "Suspended"},
        get_bucket_policy=lambda **kw: {
            "Policy": json.dumps(
                {
                    "Statement": [
                        {
                            "Effect": "Deny",
                            "Principal": "*",
                            "Action": "s3:*",
                            "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                        }
                    ]
                }
            )
        },
        get_public_access_block=lambda **kw: {
            "PublicAccessBlockConfiguration": {
                name: True
                for name in (
                    "BlockPublicAcls",
                    "IgnorePublicAcls",
                    "BlockPublicPolicy",
                    "RestrictPublicBuckets",
                )
            }
        },
        get_bucket_encryption=lambda **kw: {
            "ServerSideEncryptionConfiguration": {
                "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
            }
        },
    )
    session = SimpleNamespace(
        client=lambda name, **kw: {
            "s3": s3,
            "iam": SimpleNamespace(
                get_policy=lambda **kw: {},
                get_role=lambda **kw: {},
                get_open_id_connect_provider=lambda **kw: {},
            ),
            "ses": SimpleNamespace(
                get_identity_verification_attributes=lambda **kw: {"VerificationAttributes": {}}
            ),
        }[name]
    )
    with pytest.raises(ValueError, match="BootstrapReadbackFailed"):
        module.verify_created_resources(session, outputs, account, region)


@pytest.mark.parametrize("code", [None, "403", "404", "NoSuchKey", "SlowDown"])
def test_bootstrap_destination_distinguishes_absent_denied_and_existing(monkeypatch, code):
    from botocore.exceptions import ClientError

    module = tool("bootstrap_state")
    account, region = "123456789012", "ap-northeast-1"
    calls = []

    def head(**kwargs):
        calls.append(kwargs)
        if code:
            raise ClientError({"Error": {"Code": code}}, "HeadObject")
        return {"VersionId": "existing"}

    s3 = SimpleNamespace(
        head_bucket=lambda **kw: None,
        get_bucket_location=lambda **kw: {"LocationConstraint": region},
        head_object=head,
    )
    monkeypatch.setattr(
        module, "checked_session", lambda *a: SimpleNamespace(client=lambda *a, **kw: s3)
    )
    monkeypatch.setattr(module, "_bucket_hardened", lambda *a: True)
    if code in {"404", "NoSuchKey"}:
        module.migration_target(account, region, f"ai-interview-state-{account}-{region}")
    else:
        with pytest.raises(ValueError, match="BootstrapState"):
            module.migration_target(account, region, f"ai-interview-state-{account}-{region}")
    assert calls[0]["ExpectedBucketOwner"] == account


def test_ci_prerequisites_fail_before_any_command(monkeypatch, tmp_path):
    module = tool("terraform_dev")
    monkeypatch.setattr(module, "run", lambda *a, **kw: pytest.fail("unexpected command"))
    with pytest.raises(ValueError, match="AwsExecutionPrerequisitesUnconfirmed"):
        module.checked_git(tmp_path, {"GITHUB_ACTIONS": "true"})


@pytest.mark.parametrize("change", [{}, {"VersionId": "other"}, {"ServerSideEncryption": "none"}])
def test_bootstrap_reads_receipt_version_and_closes_body(change):
    from io import BytesIO

    module = tool("bootstrap_state")
    original = b'{"lineage":"run","serial":1,"resources":[],"outputs":{}}'
    body = BytesIO(original)
    calls = []

    def get(**kwargs):
        calls.append(kwargs)
        return {"VersionId": "v1", "ServerSideEncryption": "AES256", "Body": body} | change

    session = SimpleNamespace(
        client=lambda *a: SimpleNamespace(
            head_object=lambda **kw: {"VersionId": "v1"}, get_object=get
        )
    )
    if change:
        with pytest.raises(ValueError, match="MigratedStateReadbackFailed"):
            module.verify_state_version(session, "bucket", "123456789012", original)
    else:
        assert module.verify_state_version(session, "bucket", "123456789012", original) == (
            "v1",
            original,
        )
    assert calls[0]["VersionId"] == "v1"
    assert body.closed


def test_state_comparison_includes_outputs():
    module = tool("bootstrap_state")
    state = {"lineage": "run", "serial": 1, "resources": [], "outputs": {"x": 1}}
    changed = state | {"outputs": {"x": 2}}
    assert module._state_identity(json.dumps(state)) != module._state_identity(json.dumps(changed))


def test_terraform_subprocess_error_redacted(monkeypatch, tmp_path):
    module = tool("terraform_dev")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=1, stdout=b"private-email", stderr=b"private-token"
        ),
    )
    with pytest.raises(ValueError, match="TerraformOperationFailed") as error:
        module.run(["terraform"], cwd=tmp_path, env={})
    assert "private" not in str(error.value)


def test_ci_artifact_requires_creation_and_version(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "skills/p4"))
    module = tool("ci_deploy")
    calls = []
    client = SimpleNamespace(
        put_object=lambda **request: calls.append(request) or {"VersionId": "v1"}
    )
    assert module.put(client, "bucket", "lambda/run/app.zip", b"zip") == "v1"
    assert calls[0]["IfNoneMatch"] == "*"
    assert calls[0]["ServerSideEncryption"] == "AES256"
    for response in ({}, {"VersionId": "null"}):
        with pytest.raises(ValueError, match="VersionedArtifactRequired"):
            module.put(
                SimpleNamespace(put_object=lambda result=response, **kw: result), "b", "k", b"x"
            )


def test_ci_transport_failure_redacts_and_clears_credentials(monkeypatch, capsys):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "skills/p4"))
    module = tool("ci_deploy")

    def fail(*args):
        raise RuntimeError("private-session-token")

    monkeypatch.setattr(module, "account_settings", fail)
    monkeypatch.setenv("AWS_SESSION_TOKEN", "private-session-token")
    assert module.main() == 1
    assert capsys.readouterr().err == "P4CiDeploymentFailed\n"
    assert "AWS_SESSION_TOKEN" not in module.os.environ


def test_ci_get_rejects_different_version_before_read(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "skills/p4"))
    module = tool("ci_deploy")
    closed = []
    body = SimpleNamespace(
        close=lambda: closed.append(True),
        read=lambda: pytest.fail("mismatched object was read"),
    )
    client = SimpleNamespace(get_object=lambda **kw: {"VersionId": "other", "Body": body})
    with pytest.raises(ValueError, match="ArtifactVersionMismatch"):
        module.get(client, "bucket", "key", version="expected")
    assert closed == [True]


def test_auth_gate_runs_before_settings_or_clients(monkeypatch, capsys):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "skills/p4"))
    module = tool("auth_e2e")
    monkeypatch.delenv("P4_AWS_EXECUTION_READY", raising=False)
    monkeypatch.setattr(module.sys, "argv", ["auth_e2e.py", "--manifest", "missing"])
    monkeypatch.setattr(module, "account_settings", lambda *a: pytest.fail("settings read"))
    assert module.main() == 1
    assert capsys.readouterr().err == "AuthE2EFailed\n"


def test_auth_guard_failure_never_prompts_or_sends_token(monkeypatch, capsys):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "skills/p4"))
    module = tool("auth_e2e")
    monkeypatch.setattr(module.sys, "argv", ["auth_e2e.py", "--manifest", "missing"])

    def fail(*args):
        raise RuntimeError("private-token")

    monkeypatch.setattr(module, "account_settings", fail)
    monkeypatch.setattr(module.getpass, "getpass", lambda *a: pytest.fail("unexpected prompt"))
    monkeypatch.setattr(module.boto3, "client", lambda *a, **kw: pytest.fail("unexpected client"))
    assert module.main() == 1
    assert capsys.readouterr().err == "AuthE2EFailed\n"


def test_plan_summary_never_copies_private_data():
    module = tool("plan_summary")
    plan = {
        "resource_changes": [
            {
                "type": "aws_lambda_function",
                "address": "private-email@example.invalid",
                "change": {
                    "actions": ["update"],
                    "before": {"timeout": 15, "environment": {"Token": "private-token"}},
                    "after": {
                        "timeout": 30,
                        "email": "private-email@example.invalid",
                        "policy": "private-token",
                        "memory_size": "private-value",
                    },
                },
            }
        ]
    }
    summary = module.summarize(plan)
    assert "private" not in json.dumps(summary)
    assert summary["resource_changes"][0]["settings"] == {"timeout": {"before": 15, "after": 30}}


def test_plan_summary_rejects_unknown_action():
    with pytest.raises(ValueError, match="UnsafePlanSummary"):
        tool("plan_summary").summarize(
            {
                "resource_changes": [
                    {"type": "aws_lambda_function", "change": {"actions": ["private-value"]}}
                ]
            }
        )
