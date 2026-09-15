"""OIDC fixture checks are not JWT signature verification evidence."""

import base64
import importlib.util
import json
from pathlib import Path

import pytest


def module():
    path = Path(__file__).resolve().parents[2] / "skills/p4/ci_identity.py"
    spec = importlib.util.spec_from_file_location("ci_identity", path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.mark.parametrize(
    "changed",
    [
        {},
        {"sub": "repo:other:environment:dev"},
        {"ref": "refs/heads/feature"},
        {"repository": "other/repo"},
        {"aud": "other"},
        {"iss": "https://other.invalid"},
        {"environment": "prod"},
        {"sha": "b" * 40},
    ],
)
def test_exact_oidc_claims(changed):
    subject = "repo:yonegen0/ai_interview:environment:dev"
    claims = {
        "iss": "https://token.actions.githubusercontent.com",
        "aud": "sts.amazonaws.com",
        "sub": subject,
        "repository": "yonegen0/ai_interview",
        "environment": "dev",
        "ref": "refs/heads/main",
        "sha": "a" * 40,
    } | changed
    token = (
        "header." + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode() + ".signature"
    )
    env = {
        "GITHUB_SHA": "a" * 40,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REPOSITORY": "yonegen0/ai_interview",
    }
    if changed:
        with pytest.raises(ValueError, match="OidcClaimsMismatch"):
            module().validated_claims(token, subject, env)
    else:
        assert module().validated_claims(token, subject, env) == claims


@pytest.mark.parametrize(
    "policies",
    [
        {"total_count": 1, "branch_policies": [{"name": "main", "type": "branch"}]},
        {"total_count": 1, "branch_policies": [{"name": "main", "type": "tag"}]},
        {"total_count": 1, "branch_policies": [{"name": "*", "type": "branch"}]},
        {"total_count": 0, "branch_policies": []},
        {"total_count": 2, "branch_policies": [{"name": "main", "type": "branch"}]},
    ],
)
def test_dev_environment_requires_exact_main_branch(monkeypatch, policies):
    directory = Path(__file__).resolve().parents[2] / "skills/p4"
    monkeypatch.syspath_prepend(str(directory))
    import github_control

    details = {
        "deployment_branch_policy": {
            "protected_branches": False,
            "custom_branch_policies": True,
        }
    }
    if policies == {"total_count": 1, "branch_policies": [{"name": "main", "type": "branch"}]}:
        github_control.validate_branch_rules(details, policies)
        with pytest.raises(ValueError):
            github_control.validate_branch_rules({"deployment_branch_policy": None}, policies)
    else:
        with pytest.raises(ValueError, match="MainOnlyDevEnvironmentRequired"):
            github_control.validate_branch_rules(details, policies)
