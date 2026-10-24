"""Standard dispatch/role separation and saved-plan reuse; no live credentials."""

import base64
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


@pytest.mark.parametrize("operation", ["plan", "apply"])
def test_standard_dispatch_passes_explicit_package_base_to_offline(operation):
    workflows = Path(__file__).resolve().parents[3] / ".github/workflows"
    workflow = (workflows / f"p4-standard-{operation}.yml").read_text()
    inputs = workflow.split("    inputs:\n", 1)[1].split("\npermissions:", 1)[0]
    base_input = re.search(r"^      package_base_sha:\n((?:        .*\n)+)", inputs, re.M)
    assert base_input is not None, "Manual package comparison requires an explicit ancestor"
    assert "        type: string\n" in base_input[1]
    assert "        required: true\n" in base_input[1]
    assert "default:" not in base_input[1]
    offline = workflow.split("  offline:\n", 1)[1].split(f"\n  {operation}:\n", 1)[0]
    assert "    uses: ./.github/workflows/p4-static.yml\n" in offline
    assert "    with:\n      package_base_sha: ${{ inputs.package_base_sha }}" in offline
    static = (workflows / "p4-static.yml").read_text()
    assert "          PACKAGE_BASE_SHA: ${{ inputs.package_base_sha }}\n" in static
    assert "run: python3 backend/skills/p4/package_changes.py\n" in static


def context(operation="plan"):
    from ci_identity import STANDARD_SUBJECT

    return {
        "P4_STANDARD_ACTIVE": "true",
        "P4_OPERATION": operation,
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": "yonegen0/ai_interview",
        "GITHUB_REPOSITORY_ID": "1361325921",
        "GITHUB_REPOSITORY_OWNER_ID": "76547980",
        "GITHUB_ACTOR_ID": "76547980",
        "GITHUB_ACTOR": "yonegen0",
        "GITHUB_TRIGGERING_ACTOR": "yonegen0",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_RUN_ID": "123",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_WORKFLOW_SHA": "a" * 40,
        "GITHUB_WORKFLOW_REF": (
            f"yonegen0/ai_interview/.github/workflows/p4-standard-{operation}.yml@refs/heads/main"
        ),
        "P4_STANDARD_READY": "true",
        "P4_STANDARD_REVIEW_MODE": "manual",
        "P4_APPROVED_SOURCE_SHA": "a" * 40,
        "P4_OIDC_SUBJECT": STANDARD_SUBJECT + "dev-" + operation,
        "P4_APPROVED_AT_UTC": "2026-10-21T00:00:00Z",
        "P4_APPROVAL_EXPIRES_AT": "2026-10-24T00:00:00Z",
        "P4_PLAN_RUN_ID": "100",
    }


@pytest.mark.parametrize("operation", ["plan", "apply"])
def test_standard_dispatch_identity_and_absolute_deadline(operation):
    from ci_identity import standard_context

    env = context(operation)
    issued = datetime(2026, 10, 21, tzinfo=UTC)
    assert standard_context(env, now=issued) == "dev-" + operation
    for now in (issued - timedelta(seconds=1), issued + timedelta(hours=72)):
        with pytest.raises(ValueError, match="ExpiredOrNotIssued"):
            standard_context(env, now=now)
    with pytest.raises(ValueError, match="ExpiredOrNotIssued"):
        standard_context(env, now=issued + timedelta(hours=71), reserve=3600)


@pytest.mark.parametrize(
    "change",
    [
        {"GITHUB_REPOSITORY_ID": "1"},
        {"GITHUB_REPOSITORY_OWNER_ID": "1"},
        {"GITHUB_ACTOR_ID": "1"},
        {"GITHUB_TRIGGERING_ACTOR": "other"},
        {"GITHUB_RUN_ATTEMPT": "2"},
        {"GITHUB_EVENT_NAME": "push"},
        {"GITHUB_REF": "refs/tags/main"},
        {"GITHUB_WORKFLOW_SHA": "b" * 40},
        {"GITHUB_WORKFLOW_REF": "other"},
        {"P4_APPROVED_SOURCE_SHA": "b" * 40},
        {"P4_STANDARD_READY": "false"},
        {"P4_STANDARD_REVIEW_MODE": "unknown"},
        {"P4_OIDC_SUBJECT": "repo:yonegen0/ai_interview:environment:dev"},
        {"P4_OPERATION": "upload-existing"},
        {"P4_CLOUD_ACTIVE": "true"},
    ],
)
def test_standard_dispatch_rejects_mismatched_scope(change):
    from ci_identity import standard_context

    with pytest.raises(ValueError, match="IdentityMismatch"):
        standard_context(context() | change, now=datetime(2026, 10, 21, tzinfo=UTC))


def history(env, digest, **changes):
    operation = env["P4_OPERATION"]
    title = f"P4 plan approval-{digest}" if operation == "plan" else f"P4 apply plan-100-{digest}"
    return {
        "id": 123,
        "run_attempt": 1,
        "head_sha": "a" * 40,
        "head_branch": "main",
        "event": "workflow_dispatch",
        "path": f".github/workflows/p4-standard-{operation}.yml",
        "repository": {"full_name": "yonegen0/ai_interview"},
        "display_title": title,
        "actor": {"id": 76547980},
        "triggering_actor": {"id": 76547980},
        **changes,
    }


@pytest.mark.parametrize("operation", ["plan", "apply"])
def test_first_dispatch_consumes_even_failed_or_queued_run(operation):
    from plan_authorization import verify_run_history

    env, digest = context(operation), "b" * 64
    run = history(env, digest, status="queued", conclusion=None)

    def getter(*a):
        return {"total_count": 1, "workflow_runs": [run]}

    assert verify_run_history(digest, env, getter) == "123"
    env["GITHUB_RUN_ID"] = "124"
    with pytest.raises(ValueError, match="AlreadyConsumed"):
        verify_run_history(digest, env, getter)


def test_apply_cannot_use_non_operator_history():
    from plan_authorization import verify_run_history

    env, digest = context("apply"), "b" * 64
    run = history(env, digest, triggering_actor={"id": 1})
    with pytest.raises(ValueError, match="AlreadyConsumed"):
        verify_run_history(digest, env, lambda *a: {"total_count": 1, "workflow_runs": [run]})


def test_oidc_payload_binds_workflow_run_and_environment(monkeypatch):
    import ci_identity

    env = context()
    monkeypatch.setattr(ci_identity, "standard_context", lambda e: "dev-plan")
    claims = {
        "iss": "https://token.actions.githubusercontent.com",
        "aud": "sts.amazonaws.com",
        "sub": env["P4_OIDC_SUBJECT"],
        "repository": env["GITHUB_REPOSITORY"],
        "environment": "dev-plan",
        "ref": env["GITHUB_REF"],
        "sha": env["GITHUB_SHA"],
        "repository_id": env["GITHUB_REPOSITORY_ID"],
        "repository_owner_id": env["GITHUB_REPOSITORY_OWNER_ID"],
        "actor_id": env["GITHUB_ACTOR_ID"],
        "run_id": env["GITHUB_RUN_ID"],
        "run_attempt": "1",
        "workflow_ref": env["GITHUB_WORKFLOW_REF"],
        "workflow_sha": env["GITHUB_WORKFLOW_SHA"],
        "event_name": env["GITHUB_EVENT_NAME"],
    }

    def token(value):
        return "header." + base64.urlsafe_b64encode(json.dumps(value).encode()).decode() + ".sig"

    assert ci_identity.validated_claims(token(claims), claims["sub"], env)["sub"] == claims["sub"]
    for change in ({"environment": "dev-apply"}, {"run_id": "124"}, {"workflow_sha": "b" * 40}):
        with pytest.raises(ValueError, match="OidcClaimsMismatch"):
            ci_identity.validated_claims(token(claims | change), claims["sub"], env)


@pytest.mark.parametrize("operation,role", [("plan", "deploy"), ("apply", "plan")])
def test_wrong_role_is_rejected_before_oidc(monkeypatch, operation, role):
    import ci_identity

    for key, value in context(operation).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(ci_identity, "require_aws_execution", lambda: None)
    monkeypatch.setattr(ci_identity, "validate_target", lambda *a: None)
    monkeypatch.setattr(ci_identity, "standard_context", lambda *a, **k: "dev-" + operation)
    with pytest.raises(ValueError, match="RolePurposeMismatch"):
        ci_identity.assume(role, "123456789012", "ap-northeast-1", expected_subject="unused")


@pytest.mark.parametrize(
    "operation,role,suffix",
    [
        ("plan", "plan", "plan"),
        ("plan", "artifact", "artifact-plan"),
        ("apply", "deploy", "deploy"),
        ("apply", "artifact", "artifact-apply"),
    ],
)
def test_standard_sts_uses_only_purpose_specific_role(monkeypatch, operation, role, suffix):
    from types import SimpleNamespace

    import boto3
    import ci_identity

    env = context(operation)
    env["ACTIONS_ID_TOKEN_REQUEST_URL"] = "https://example.actions.githubusercontent.com/token"
    env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"] = "synthetic"
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    # assume() intentionally writes ephemeral credentials to the process mapping.
    # Register those keys with monkeypatch so a synthetic success cannot leak them
    # into the next test's credential-source checks.
    for key in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
    ):
        monkeypatch.setenv(key, "synthetic")
    monkeypatch.setattr(ci_identity, "require_aws_execution", lambda: None)
    monkeypatch.setattr(ci_identity, "validate_target", lambda *a: None)
    monkeypatch.setattr(ci_identity, "standard_context", lambda *a, **k: "dev-" + operation)
    monkeypatch.setattr(ci_identity, "active_guard", lambda: None)
    monkeypatch.setattr(ci_identity, "validated_claims", lambda *a: {})
    monkeypatch.setattr(ci_identity, "checked_session", lambda *a, **k: "synthetic-session")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, count):
            return b'{"value":"synthetic-jwt"}'

    monkeypatch.setattr(
        ci_identity, "build_opener", lambda *a: SimpleNamespace(open=lambda *a, **k: Response())
    )

    def assume(**kwargs):
        assert kwargs["RoleArn"].endswith(":role/ai-interview-standard-ci-" + suffix)
        assert kwargs["DurationSeconds"] == 3600
        policy = json.loads(kwargs["Policy"])
        assert (
            policy["Statement"][1]["Condition"]["DateGreaterThanEquals"]["aws:CurrentTime"]
            == (env["P4_APPROVAL_EXPIRES_AT"])
        )
        return {
            "AssumedRoleUser": {
                "Arn": (
                    f"arn:aws:sts::123456789012:assumed-role/ai-interview-standard-ci-{suffix}"
                    f"/p4-123-{role}"
                )
            },
            "Credentials": {
                "AccessKeyId": "synthetic",
                "SecretAccessKey": "synthetic",
                "SessionToken": "synthetic",
                "Expiration": datetime.now(UTC) + timedelta(hours=1),
            },
        }

    monkeypatch.setattr(
        boto3,
        "Session",
        lambda **k: SimpleNamespace(
            client=lambda *a, **k: SimpleNamespace(assume_role_with_web_identity=assume)
        ),
    )
    assert (
        ci_identity.assume(
            role, "123456789012", "ap-northeast-1", expected_subject=env["P4_OIDC_SUBJECT"]
        )
        == "synthetic-session"
    )


def test_standard_environment_needs_main_restriction_and_protection(monkeypatch):
    import ci_identity
    import github_control

    monkeypatch.setattr(ci_identity, "standard_context", lambda e: "dev-apply")
    env = context("apply")
    details = {
        "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True},
        "can_admins_bypass": False,
        "protection_rules": [],
    }
    branch = {"protected": True}
    policies = {"total_count": 1, "branch_policies": [{"name": "main", "type": "branch"}]}

    def get(suffix, _):
        if "policies?" in suffix:
            return policies
        return branch if suffix == "branches/main" else details

    monkeypatch.setattr(github_control, "github_json", get)
    github_control.verify_dev_environment(env)
    env["P4_STANDARD_REVIEW_MODE"] = "reviewers"
    with pytest.raises(ValueError, match="ReviewerMissing"):
        github_control.verify_dev_environment(env)
    details["protection_rules"] = [
        {
            "type": "required_reviewers",
            "reviewers": [{"type": "User", "reviewer": {"id": 76547980}}],
        }
    ]
    github_control.verify_dev_environment(env)
    branch["protected"] = False
    with pytest.raises(ValueError, match="ProtectedMainRequired"):
        github_control.verify_dev_environment(env)
