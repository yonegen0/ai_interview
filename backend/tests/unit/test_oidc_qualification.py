"""Qualification boundaries: synthetic tokens/clients only, no external services."""

import base64
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError


def environment():
    import oidc_qualification as q

    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": q.REPOSITORY,
        "GITHUB_REPOSITORY_ID": "1361325921",
        "GITHUB_REPOSITORY_OWNER_ID": "76547980",
        "GITHUB_ACTOR": "yonegen0",
        "GITHUB_ACTOR_ID": "76547980",
        "GITHUB_TRIGGERING_ACTOR": "yonegen0",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_RUN_ID": "123",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_WORKFLOW_SHA": "a" * 40,
        "GITHUB_WORKFLOW_REF": f"{q.REPOSITORY}/{q.WORKFLOW}@refs/heads/main",
        "P4_EXPECTED_SOURCE_SHA": "a" * 40,
        "P4_QUALIFY_ENVIRONMENT": "dev-plan",
        "P4_STANDARD_READY": "false",
        "P4_AWS_EXECUTION_READY": "false",
        "P4_STANDARD_REVIEW_MODE": "manual",
        "AWS_DEV_ACCOUNT_ID": "123456789012",
        "AWS_REGION": q.REGION,
        "AWS_EC2_METADATA_DISABLED": "true",
    }


def state(tmp_path):
    import oidc_qualification as q

    env = environment()
    name, expiry = q.context(env)
    return {
        "env": env,
        "name": name,
        "expiry": expiry,
        "clock": datetime.now(UTC),
        "started": time.monotonic(),
        "journal": tmp_path,
        "sequence": 1,
        "role": q.ROLES[name][0],
        "http": 0,
        "http_bytes": 0,
        "aws": 0,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"GITHUB_RUN_ATTEMPT": "2"},
        {"GITHUB_EVENT_NAME": "push"},
        {"GITHUB_ACTOR_ID": "1"},
        {"GITHUB_TRIGGERING_ACTOR": "other"},
        {"GITHUB_REPOSITORY_ID": "1"},
        {"GITHUB_REPOSITORY_OWNER_ID": "1"},
        {"GITHUB_WORKFLOW_SHA": "d" * 40},
        {"P4_EXPECTED_SOURCE_SHA": "d" * 40},
        {"GITHUB_REF": "refs/tags/main"},
        {"P4_QUALIFY_ENVIRONMENT": "dev"},
        {"P4_STANDARD_READY": "true"},
        {"P4_AWS_EXECUTION_READY": "true"},
        {"AWS_PROFILE": "existing"},
        {"AWS_ACCESS_KEY_ID": "sentinel-secret"},
        {"AWS_ENDPOINT_URL": "https://example.invalid"},
        {"AWS_REGION": "us-east-1"},
    ],
)
def test_context_rejects_before_http(change):
    import oidc_qualification as q

    with pytest.raises(ValueError):
        q.context(environment() | change)


def test_context_accepts_two_exact_environments_with_short_session_window():
    import oidc_qualification as q

    env = environment()
    now = datetime.now(UTC)
    for name in q.ROLES:
        result, expiry = q.context(env | {"P4_QUALIFY_ENVIRONMENT": name}, now=now)
        assert result == name and expiry == now + timedelta(seconds=900)


def public_state(tmp_path):
    import oidc_qualification as q

    st = state(tmp_path)
    now = datetime.now(UTC)
    expected = {
        "assume-expected-environment": "allowed",
        "caller-identity": "allowed",
        "allowed-bucket-location": "allowed",
        "denied-bootstrap-role-read": "denied",
        "denied-opposite-environment": "denied",
    }
    st["checks"] = [
        {"role": role, "operation": operation, "outcome": outcome}
        for role in q.ROLES[st["name"]]
        for operation, outcome in expected.items()
    ]
    st["sessions"] = [
        {
            "role": role,
            "acquired_at_utc": now.isoformat(),
            "expires_at_utc": (now + timedelta(seconds=900)).isoformat(),
            "identity_matches_expected": True,
        }
        for role in q.ROLES[st["name"]]
    ]
    return st


def test_public_result_excludes_private_journal_and_credentials(tmp_path):
    import oidc_qualification as q

    st = public_state(tmp_path)
    (tmp_path / "0001.private.json").write_text('{"token":"sentinel-secret"}')
    q.publish_result(st, tmp_path, True)
    raw = (tmp_path / "p4-qualification-public/result.json").read_text()
    result = json.loads(raw)
    assert result["status"] == "verified" and len(result["checks"]) == 10
    assert len(result["sessions"]) == 2 and len(raw.encode()) <= 32768
    assert all(
        value not in raw
        for value in ("sentinel-secret", "123456789012", "arn:aws:", "AccessKeyId", "RequestId")
    )


@pytest.mark.parametrize(
    "change", ["extra-field", "duplicate-check", "short-session", "wrong-role"]
)
def test_public_result_rejects_untrusted_fields_or_incomplete_success(tmp_path, change):
    import oidc_qualification as q

    st = public_state(tmp_path)
    if change == "extra-field":
        st["checks"][0]["request_id"] = "sentinel-secret"
    elif change == "duplicate-check":
        st["checks"][-1] = st["checks"][0]
    elif change == "wrong-role":
        st["checks"][0]["role"] = "unapproved"
    else:
        st["sessions"][0]["expires_at_utc"] = st["sessions"][0]["acquired_at_utc"]
    with pytest.raises(ValueError):
        q.publish_result(st, tmp_path, True)
    assert not (tmp_path / "p4-qualification-public").exists()


def token(st, **change):
    import oidc_qualification as q

    env = st["env"]
    now = int(datetime.now(UTC).timestamp())
    value = {
        "iss": "https://token.actions.githubusercontent.com",
        "aud": "sts.amazonaws.com",
        "sub": q.STANDARD_SUBJECT + st["name"],
        "repository": q.REPOSITORY,
        "environment": st["name"],
        "ref": "refs/heads/main",
        "sha": env["GITHUB_SHA"],
        "repository_id": "1361325921",
        "repository_owner_id": "76547980",
        "actor_id": "76547980",
        "run_id": "123",
        "run_attempt": "1",
        "workflow_ref": env["GITHUB_WORKFLOW_REF"],
        "workflow_sha": env["GITHUB_SHA"],
        "event_name": "workflow_dispatch",
        "iat": now,
        "nbf": now,
        "exp": now + 300,
        **change,
    }
    return "synthetic." + base64.urlsafe_b64encode(json.dumps(value).encode()).decode() + ".sig"


@pytest.mark.parametrize(
    "change",
    [
        {"aud": "wrong"},
        {"environment": "dev-apply"},
        {"repository_id": "1"},
        {"workflow_sha": "d" * 40},
        {"run_attempt": "2"},
        {"exp": 0},
    ],
)
def test_token_claim_mismatch(tmp_path, change):
    import oidc_qualification as q

    st = state(tmp_path)
    q.claims(token(st), st)
    with pytest.raises(ValueError):
        q.claims(token(st, **change), st)


def denial(code="AccessDenied", status=403):
    return ClientError(
        {
            "Error": {"Code": code, "Message": "sentinel-secret"},
            "ResponseMetadata": {"HTTPStatusCode": status, "RequestId": "synthetic"},
        },
        "GetRole",
    )


def test_negative_probe_requires_exact_error_and_never_accepts_success(tmp_path):
    import oidc_qualification as q

    st = state(tmp_path)
    for error in (denial("ExpiredToken"), denial("NoSuchEntity", 404), denial()):
        with pytest.raises(ValueError, match="UnexpectedAwsFailure"):
            q.aws_call(st, "probe", lambda e=error: (_ for _ in ()).throw(e))
    with pytest.raises(ValueError, match="NegativeProbeAllowed"):
        q.aws_call(st, "probe", lambda: {}, denied=True)
    assert q.aws_call(st, "probe", lambda: (_ for _ in ()).throw(denial()), denied=True) is None
    assert "sentinel-secret" not in "".join(path.read_text() for path in tmp_path.iterdir())


def test_caps_expiry_and_retry_send_stop_before_next_request(tmp_path):
    import oidc_qualification as q

    st = state(tmp_path)
    st["aws"] = q.AWS_MAX
    with pytest.raises(ValueError, match="AwsLimit"):
        q.aws_call(st, "probe", lambda: pytest.fail("must not call"))
    st["started"] -= q.SECONDS_MAX
    with pytest.raises(ValueError, match="TimeExceeded"):
        q.checkpoint(st)


def test_context_and_journal_failure_never_expose_original_exception(tmp_path, monkeypatch, capsys):
    import oidc_qualification as q

    env = environment() | {
        "RUNNER_TEMP": str(tmp_path),
        "P4_QUALIFY_STARTED_MONOTONIC": str(time.monotonic()),
    }
    monkeypatch.setattr(q.os, "environ", env)
    monkeypatch.setattr(q, "verify_checkout", lambda *a: None)
    monkeypatch.setattr(q.Path, "mkdir", lambda *a, **kw: None)
    calls = []

    def broken_record(*args, **kwargs):
        calls.append(kwargs["stage"])
        if kwargs["stage"] == "started":
            raise RuntimeError("sentinel-secret-original-error")
        raise OSError("sentinel-secret-journal-error")

    monkeypatch.setattr(q, "record", broken_record)
    monkeypatch.setattr(q, "publish_result", lambda *a: None)
    assert q.main() == 1
    captured = capsys.readouterr()
    assert captured.out == "QualificationStopped\n" and captured.err == ""
    assert calls == ["started"]


def test_checkout_drift_stops_and_does_not_print_git_output(monkeypatch):
    import oidc_qualification as q

    monkeypatch.setattr(
        q.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=b"sentinel-secret-output"),
    )
    with pytest.raises(ValueError, match="QualificationCheckoutChanged"):
        q.verify_checkout(Path.cwd(), environment())


def test_http_and_history_caps_fail_closed(tmp_path, monkeypatch):
    import oidc_qualification as q

    st = state(tmp_path)
    st["http"] = q.HTTP_MAX
    with pytest.raises(ValueError, match="HttpLimit"):
        q.http_json(st, None)


def test_environment_control_and_main_sha_rejection(tmp_path, monkeypatch):
    import oidc_qualification as q

    st = state(tmp_path)
    values = {
        "": {"id": 1361325921, "owner": {"id": 76547980}},
        "branches/main": {"protected": True, "commit": {"sha": "a" * 40}},
        "environments/dev-plan": {
            "can_admins_bypass": False,
            "deployment_branch_policy": {
                "protected_branches": False,
                "custom_branch_policies": True,
            },
        },
        "environments/dev-plan/deployment-branch-policies?per_page=100": {
            "total_count": 1,
            "branch_policies": [{"name": "main", "type": "branch"}],
        },
    }
    monkeypatch.setattr(q, "github_get", lambda _, suffix: values[suffix])
    q.verify_control_plane(st)
    values["branches/main"]["commit"]["sha"] = "d" * 40
    with pytest.raises(ValueError, match="MainChanged"):
        q.verify_control_plane(st)


@pytest.mark.parametrize("name", ["dev-plan", "dev-apply"])
@pytest.mark.parametrize("identity_fails", [False, True])
def test_exact_read_only_call_graph_and_restriction(tmp_path, monkeypatch, name, identity_fails):
    import boto3
    import oidc_qualification as q

    st = state(tmp_path)
    st["name"] = name
    calls, tokens, hooks, expirations = [], [], [], {}

    def issue(state):
        tokens.append(name)
        return "sentinel-token"

    monkeypatch.setattr(q, "oidc_token", issue)

    class FakeSession:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def client(self, service, **kwargs):
            assert kwargs["config"].retries == {"total_max_attempts": 1}
            session = self

            def assume_role_with_web_identity(**request):
                calls.append(("assume", request["RoleArn"]))
                role = request["RoleArn"].split(q.ROLE_PREFIX)[1]
                if role not in q.ROLES[name]:
                    raise denial()
                policy = json.loads(request["Policy"])
                actions = {row["Action"] for row in policy["Statement"] if row["Effect"] == "Allow"}
                assert actions == {"sts:GetCallerIdentity", "s3:GetBucketLocation", "iam:GetRole"}
                assert request["DurationSeconds"] == 900
                expirations[role] = datetime.now(UTC) + timedelta(seconds=900)
                return {
                    "AssumedRoleUser": {
                        "Arn": f"arn:aws:sts::123456789012:assumed-role/"
                        f"{q.ROLE_PREFIX}{role}/{request['RoleSessionName']}"
                    },
                    "Credentials": {
                        "AccessKeyId": role,
                        "SecretAccessKey": "sentinel-secret",
                        "SessionToken": "sentinel-token",
                        "Expiration": expirations[role],
                    },
                    "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "synthetic"},
                }

            def get_caller_identity():
                role = session.kwargs["aws_access_key_id"]
                calls.append(("identity", role))
                if identity_fails:
                    raise denial()
                return {
                    "Account": "123456789012",
                    "Arn": "arn:aws:sts::123456789012:"
                    f"assumed-role/{q.ROLE_PREFIX}{role}/p4q-123-{role}",
                    "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "synthetic"},
                }

            def get_bucket_location(**request):
                calls.append(("location", request["Bucket"]))
                return {
                    "LocationConstraint": q.REGION,
                    "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "synthetic"},
                }

            def get_role(**request):
                calls.append(("denied-role", request["RoleName"]))
                raise denial()

            return SimpleNamespace(
                meta=SimpleNamespace(
                    events=SimpleNamespace(register=lambda event, hook: hooks.append(hook))
                ),
                assume_role_with_web_identity=assume_role_with_web_identity,
                get_caller_identity=get_caller_identity,
                get_bucket_location=get_bucket_location,
                get_role=get_role,
            )

    monkeypatch.setattr(boto3, "Session", FakeSession)
    before = datetime.now(UTC)
    if identity_fails:
        with pytest.raises(ValueError, match="UnexpectedAwsFailure"):
            q.qualify(st)
        assert len(calls) == 2 and st["aws"] == 2 and len(tokens) == 1
    else:
        q.qualify(st)
        assert len(calls) == 10 and st["aws"] == 10 and len(tokens) == 2
        assert len([call for call in calls if call[0] == "assume"]) == 4
    after = datetime.now(UTC)
    rows = [json.loads(path.read_text()) for path in sorted(tmp_path.iterdir())]
    acquired = [row for row in rows if row["stage"] == "session-acquired"]
    confirmed = [row for row in rows if row["stage"] == "session-identity-confirmed"]
    assert len(acquired) == (1 if identity_fails else 2)
    assert len(confirmed) == (0 if identity_fails else 2)
    for row in acquired:
        role = row["role"]
        assert row["assumed_role_arn"] == (
            f"arn:aws:sts::123456789012:assumed-role/{q.ROLE_PREFIX}{role}/p4q-123-{role}"
        )
        assert datetime.fromisoformat(row["expires_at_utc"]) == expirations[role]
        assert before <= datetime.fromisoformat(row["acquired_at_utc"]) <= after
        assert row["request_id"] == "synthetic"
    for acquisition, confirmation in zip(acquired, confirmed, strict=not identity_fails):
        assert all(
            confirmation[key] == value for key, value in acquisition.items() if key != "stage"
        )
        assert (
            datetime.fromisoformat(acquisition["acquired_at_utc"])
            <= datetime.fromisoformat(confirmation["confirmed_at_utc"])
            <= after
        )
    st["sends"] = 0
    hooks[0]()
    with pytest.raises(ValueError, match="SdkRetryForbidden"):
        hooks[0]()
    evidence = "".join(path.read_text() for path in tmp_path.iterdir())
    assert "sentinel-token" not in evidence and "sentinel-secret" not in evidence
