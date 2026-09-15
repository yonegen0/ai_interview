"""Bootstrap IAM/SES/S3 contracts and interrupted migration classification."""

import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_p4_tools import tool


@pytest.fixture
def resources(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "skills/p4"))
    module, contract = tool("bootstrap_state"), tool("bootstrap_contract")
    a, r = "123456789012", "ap-northeast-1"
    values = {
        "oidc_subjects": {
            name: "repo:yonegen0/ai_interview:environment:dev" for name in module.ROLE_NAMES
        },
        "ses_identity_type": "domain",
        "ses_domain": "example.invalid",
        "ses_from_email": "sender@example.invalid",
    }
    outputs = {
        "state_bucket": f"ai-interview-state-{a}-{r}",
        "artifact_bucket": f"ai-interview-artifacts-{a}-{r}",
        "boundary_arn": f"arn:aws:iam::{a}:policy/ai-interview-runtime-boundary",
        "oidc_provider_arn": f"arn:aws:iam::{a}:oidc-provider/token.actions.githubusercontent.com",
        "roles": {
            name: f"arn:aws:iam::{a}:role/ai-interview-ci-{name}" for name in module.ROLE_NAMES
        },
        "ses_identity_arn": f"arn:aws:ses:{r}:{a}:identity/example.invalid",
    }
    provider = {"Url": "token.actions.githubusercontent.com", "ClientIDList": ["sts.amazonaws.com"]}
    policy = contract.boundary_policy(a, r)
    roles = {
        name: {
            "Arn": arn,
            "MaxSessionDuration": 7200,
            "AssumeRolePolicyDocument": contract.trust_policy(
                outputs["oidc_provider_arn"], values["oidc_subjects"][name]
            ),
        }
        for name, arn in outputs["roles"].items()
    }
    policies = {
        bucket: {
            "Statement": [
                {
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:*",
                    "Resource": [f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"],
                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                }
            ]
        }
        for bucket in (outputs["state_bucket"], outputs["artifact_bucket"])
    }
    s3 = SimpleNamespace(
        head_bucket=lambda **kw: {},
        get_bucket_location=lambda **kw: {"LocationConstraint": r},
        get_bucket_versioning=lambda **kw: {"Status": "Enabled"},
        get_bucket_policy=lambda **kw: {"Policy": json.dumps(policies[kw["Bucket"]])},
        get_bucket_encryption=lambda **kw: {
            "ServerSideEncryptionConfiguration": {
                "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
            }
        },
        get_public_access_block=lambda **kw: {
            "PublicAccessBlockConfiguration": {
                key: True
                for key in (
                    "BlockPublicAcls",
                    "IgnorePublicAcls",
                    "BlockPublicPolicy",
                    "RestrictPublicBuckets",
                )
            }
        },
    )
    iam = SimpleNamespace(
        get_policy=lambda **kw: {
            "Policy": {"Arn": outputs["boundary_arn"], "DefaultVersionId": "v1"}
        },
        get_policy_version=lambda **kw: {
            "PolicyVersion": {"IsDefaultVersion": True, "Document": policy}
        },
        get_open_id_connect_provider=lambda **kw: provider,
        get_role=lambda **kw: {"Role": roles[kw["RoleName"].removeprefix("ai-interview-ci-")]},
    )
    ses = SimpleNamespace(
        get_identity_verification_attributes=lambda **kw: {
            "VerificationAttributes": {"example.invalid": {"VerificationStatus": "Pending"}}
        }
    )
    session = SimpleNamespace(client=lambda name, **kw: {"s3": s3, "iam": iam, "ses": ses}[name])
    return module, session, outputs, values, provider, policy, roles, policies


def test_pending_ses_is_not_sending_evidence(resources):
    module, session, outputs, values, *_ = resources
    result = module.verify_created_resources(
        session, outputs, "123456789012", "ap-northeast-1", values
    )
    assert result == {
        "ses_identity_exists": True,
        "ses_verification": "Pending",
        "ses_sending": "not_run",
    }


@pytest.mark.parametrize("change", ["aud", "url", "trust", "boundary", "tls_object", "ses"])
def test_bootstrap_configuration_mismatch_fails(resources, change):
    module, session, outputs, values, provider, policy, roles, policies = resources
    if change == "aud":
        provider["ClientIDList"].append("other")
    elif change == "url":
        provider["Url"] = "other.invalid"
    elif change == "trust":
        roles["deploy"]["AssumeRolePolicyDocument"]["Statement"][0]["Condition"] = {}
    elif change == "boundary":
        policy["Statement"][0]["Action"].append("dynamodb:DeleteTable")
    elif change == "tls_object":
        policies[outputs["state_bucket"]]["Statement"][0]["Resource"].pop()
    else:
        values["ses_domain"] = "other.invalid"
    with pytest.raises(ValueError, match="BootstrapReadbackFailed"):
        module.verify_created_resources(session, outputs, "123456789012", "ap-northeast-1", values)


@pytest.mark.parametrize("remote", ["absent", "same", "different", "denied"])
def test_migration_inspection_preserves_backup(tmp_path, remote):
    from botocore.exceptions import ClientError

    module = tool("bootstrap_state")
    raw = b'{"lineage":"run","serial":1,"resources":[],"outputs":{}}'
    (tmp_path / "terraform.tfstate").write_bytes(raw)
    (tmp_path / "pre-migration.tfstate").write_bytes(raw)
    module.write_record(tmp_path / "migration-attempt.json", {})

    def head(**kw):
        if remote in {"absent", "denied"}:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey" if remote == "absent" else "AccessDenied"}},
                "HeadObject",
            )
        return {"VersionId": "v1"}

    s3 = SimpleNamespace(
        head_object=head,
        get_object=lambda **kw: {
            "VersionId": "v1",
            "ServerSideEncryption": "AES256",
            "Body": BytesIO(raw if remote == "same" else raw.replace(b'"serial":1', b'"serial":2')),
        },
    )
    session = SimpleNamespace(client=lambda *a, **kw: s3)
    if remote in {"different", "denied"}:
        with pytest.raises(ValueError):
            module.inspect_state(tmp_path, session, "123456789012", "ap-northeast-1", tmp_path)
    else:
        result = module.inspect_state(tmp_path, session, "123456789012", "ap-northeast-1", tmp_path)
        assert result["next_operation"] == ("verify" if remote == "same" else "migrate_resume")
    assert (tmp_path / "pre-migration.tfstate").read_bytes() == raw


def test_explicit_resume_reinitializes_local_metadata_before_copy(monkeypatch, tmp_path):
    module = tool("bootstrap_state")
    raw = b'{"lineage":"run","serial":1,"resources":[],"outputs":{}}'
    state = tmp_path / "terraform.tfstate"
    state.write_bytes(raw)
    (tmp_path / "pre-migration.tfstate").write_bytes(raw)
    (tmp_path / "backend.tf").write_text(module.S3_BACKEND, encoding="utf-8")
    calls = []
    monkeypatch.setattr(module, "migration_target", lambda *a, **kw: calls.append("absent"))

    def run(command, **kwargs):
        if "-reconfigure" in command:
            assert not (tmp_path / "backend.tf").exists()
            calls.append("local_init")
        elif "-migrate-state" in command:
            assert (tmp_path / "backend.tf").read_text(encoding="utf-8") == module.S3_BACKEND
            calls.append("copy")
        return raw

    monkeypatch.setattr(module, "run", run)
    module.migrate_state(
        tmp_path, {}, state, "bucket", "123456789012", "ap-northeast-1", resume=True
    )
    assert calls == ["absent", "local_init", "absent", "copy"]
    assert (tmp_path / "pre-migration.tfstate").read_bytes() == raw
