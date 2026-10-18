"""Standard bootstrap inputs and readback carry the optional Bedrock boundary flag."""

import importlib
import json
from pathlib import Path

import pytest

from interview_backend.deployment import DeploymentError

ACCOUNT = "123456789012"
REGION = "ap-northeast-1"
SUBJECT = "repo:yonegen0/ai_interview:environment:dev"


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "skills/p4"))
    return importlib.import_module("bootstrap_state"), importlib.import_module("bootstrap_contract")


def values():
    return {
        "oidc_provider_arn": (
            f"arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"
        ),
        "oidc_subjects": {role: SUBJECT for role in ("artifact", "plan", "deploy", "test")},
        "ses_identity_type": "domain",
        "ses_from_email": "sender@example.invalid",
        "ses_domain": "example.invalid",
    }


@pytest.mark.parametrize("flag", [False, True])
def test_optional_flag_roundtrips_standard_inputs(modules, tmp_path, flag):
    state, contract = modules
    document = values() | {"worker_bedrock_enabled": flag}
    path = tmp_path / "inputs.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    parsed = state.inputs(path, ACCOUNT, REGION)
    assert parsed["worker_bedrock_enabled"] is flag
    assert len(
        contract.boundary_policy(ACCOUNT, REGION, worker_bedrock_enabled=flag)["Statement"]
    ) == (7 if flag else 5)


@pytest.mark.parametrize("value", ["false", 0, None, [], {}])
def test_optional_flag_rejects_non_boolean(modules, tmp_path, value):
    state, _ = modules
    path = tmp_path / "inputs.json"
    path.write_text(json.dumps(values() | {"worker_bedrock_enabled": value}), encoding="utf-8")
    with pytest.raises(DeploymentError, match="ExplicitWorkerBedrockFlagRequired"):
        state.inputs(path, ACCOUNT, REGION)


@pytest.mark.parametrize("flag", [False, True])
def test_readback_uses_same_boundary_flag(modules, monkeypatch, flag):
    state, contract = modules
    monkeypatch.setattr(state, "_bucket_hardened", lambda *args: True)
    document = values() | {"worker_bedrock_enabled": flag}
    outputs = {
        "state_bucket": f"ai-interview-state-{ACCOUNT}-{REGION}",
        "artifact_bucket": f"ai-interview-artifacts-{ACCOUNT}-{REGION}",
        "boundary_arn": f"arn:aws:iam::{ACCOUNT}:policy/ai-interview-runtime-boundary",
        "oidc_provider_arn": document["oidc_provider_arn"],
        "roles": {
            role: f"arn:aws:iam::{ACCOUNT}:role/ai-interview-ci-{role}"
            for role in document["oidc_subjects"]
        },
        "ses_identity_arn": f"arn:aws:ses:{REGION}:{ACCOUNT}:identity/example.invalid",
    }

    class S3:
        def head_bucket(self, **kwargs):
            return {}

        def get_bucket_location(self, **kwargs):
            return {"LocationConstraint": REGION}

    class IAM:
        def get_policy(self, **kwargs):
            return {"Policy": {"Arn": outputs["boundary_arn"], "DefaultVersionId": "v1"}}

        def get_policy_version(self, **kwargs):
            return {
                "PolicyVersion": {
                    "IsDefaultVersion": True,
                    "Document": contract.boundary_policy(
                        ACCOUNT, REGION, worker_bedrock_enabled=flag
                    ),
                }
            }

        def get_open_id_connect_provider(self, **kwargs):
            return {
                "Url": "token.actions.githubusercontent.com",
                "ClientIDList": ["sts.amazonaws.com"],
            }

        def get_role(self, RoleName):
            role = RoleName.removeprefix("ai-interview-ci-")
            return {
                "Role": {
                    "Arn": outputs["roles"][role],
                    "MaxSessionDuration": 7200,
                    "AssumeRolePolicyDocument": contract.trust_policy(
                        outputs["oidc_provider_arn"], SUBJECT
                    ),
                }
            }

    class SES:
        def get_identity_verification_attributes(self, Identities):
            return {"VerificationAttributes": {Identities[0]: {"VerificationStatus": "Success"}}}

    class Session:
        def client(self, name, **kwargs):
            return {"s3": S3(), "iam": IAM(), "ses": SES()}[name]

    assert state.verify_created_resources(Session(), outputs, ACCOUNT, REGION, document)[
        "ses_identity_exists"
    ]
