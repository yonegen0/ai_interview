"""Standard OIDC read-only verification v2; no Terraform, IAM repair or public raw journal.

AWS validates the tokens. Only a fixed, identifier-free result is uploaded; private
requests, credentials and session ARNs stay on the ephemeral runner. This result
is distinct from the historical CMS-qualified Phase D contract.
"""

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, build_opener

from ci_identity import REPOSITORY, STANDARD_SUBJECT, NoRedirect

from interview_backend.deployment import DeploymentError, validate_target

WORKFLOW = ".github/workflows/p4-standard-qualify.yml"
ROLE_PREFIX = "ai-interview-standard-ci-"
REGION = "ap-northeast-1"
ROLES = {"dev-plan": ("plan", "artifact-plan"), "dev-apply": ("deploy", "artifact-apply")}
HTTP_MAX = 16
AWS_MAX = 10
READ_MAX = 1024 * 1024
SECONDS_MAX = 600


def require(condition, reason):
    if not condition:
        raise DeploymentError(reason)


def context(env, *, now=None):
    """Check local source/dispatch binding before any HTTP or credential discovery."""
    sha = env.get("GITHUB_SHA", "")
    name = env.get("P4_QUALIFY_ENVIRONMENT")
    fixed = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_REPOSITORY_ID": "1361325921",
        "GITHUB_REPOSITORY_OWNER_ID": "76547980",
        "GITHUB_ACTOR": "yonegen0",
        "GITHUB_ACTOR_ID": "76547980",
        "GITHUB_TRIGGERING_ACTOR": "yonegen0",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": f"{REPOSITORY}/{WORKFLOW}@refs/heads/main",
        "GITHUB_WORKFLOW_SHA": sha,
        "P4_EXPECTED_SOURCE_SHA": sha,
        "P4_STANDARD_READY": "false",
        "P4_AWS_EXECUTION_READY": "false",
        "AWS_REGION": REGION,
    }
    require(
        name in ROLES
        and re.fullmatch(r"[0-9a-f]{40}", sha)
        and re.fullmatch(r"[1-9][0-9]*", env.get("GITHUB_RUN_ID", ""))
        and all(env.get(key) == value for key, value in fixed.items())
        and env.get("P4_STANDARD_REVIEW_MODE") in {"manual", "reviewers"},
        "QualificationContextMismatch",
    )
    forbidden = (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_SECURITY_TOKEN",
        "AWS_PROFILE",
        "AWS_DEFAULT_PROFILE",
        "AWS_ROLE_ARN",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        "AWS_CONFIG_FILE",
        "AWS_SHARED_CREDENTIALS_FILE",
        "BOTO_CONFIG",
        "AWS_CA_BUNDLE",
    )
    require(
        not any(env.get(key) for key in forbidden)
        and not any(key.startswith("AWS_ENDPOINT_URL") for key in env)
        and env.get("AWS_EC2_METADATA_DISABLED") == "true"
        and env.get("AWS_DEFAULT_REGION", REGION) == REGION,
        "QualificationCredentialSourceConflict",
    )
    validate_target(env.get("AWS_DEV_ACCOUNT_ID"), REGION)
    return name, (now or datetime.now(UTC)) + timedelta(seconds=900)


def checkpoint(state):
    elapsed = time.monotonic() - state["started"]
    clock = max(datetime.now(UTC), state["clock"] + timedelta(seconds=elapsed))
    require(0 <= elapsed < SECONDS_MAX, "QualificationTimeExceeded")
    require(clock < state["expiry"] - timedelta(seconds=30), "QualificationApprovalExpired")


def verify_checkout(project, env):
    """Read committed source locally; never inherit credential-bearing environment."""
    clean = {key: env[key] for key in ("PATH", "SYSTEMROOT") if key in env}
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project,
        env=clean,
        capture_output=True,
        timeout=10,
        check=False,
    )
    changes = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=project,
        env=clean,
        capture_output=True,
        timeout=10,
        check=False,
    )
    require(
        head.returncode == 0
        and head.stdout.decode().strip() == env["GITHUB_SHA"]
        and changes.returncode == 0
        and not changes.stdout.strip(),
        "QualificationCheckoutChanged",
    )


def record(state, **value):
    path = state["journal"] / f"{state['sequence']:04d}.private.json"
    state["sequence"] += 1
    with path.open("x", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def http_json(state, request):
    checkpoint(state)
    require(state["http"] < HTTP_MAX, "QualificationHttpLimit")
    state["http"] += 1
    record(state, stage="http-started", ordinal=state["http"])
    with build_opener(NoRedirect()).open(request, timeout=15) as response:
        raw = response.read(READ_MAX + 1)
    require(len(raw) <= READ_MAX, "QualificationHttpResponseLimit")
    state["http_bytes"] += len(raw)
    result = json.loads(raw)
    checkpoint(state)
    return result


def github_get(state, suffix):
    env = state["env"]
    url = f"https://api.github.com/repos/{REPOSITORY}"
    if suffix:
        url += "/" + suffix
    return http_json(
        state,
        Request(
            url,
            headers={
                "Authorization": "Bearer " + env["GH_TOKEN"],
                "Accept": "application/vnd.github+json",
            },
        ),
    )


def verify_control_plane(state):
    """Bind this checkout to the protected current main; GitHub enforces Environment policy."""
    env = state["env"]
    repo = github_get(state, "")
    require(
        repo.get("id") == 1361325921 and repo.get("owner", {}).get("id") == 76547980,
        "QualificationRepositoryChanged",
    )
    branch = github_get(state, "branches/main")
    require(
        branch.get("protected") is True
        and branch.get("commit", {}).get("sha") == env["GITHUB_SHA"],
        "QualificationMainChanged",
    )


def claims(token, state):
    """Local payload preflight; only AWS STS verifies the JWT signature."""
    env, name = state["env"], state["name"]
    payload = token.split(".")[1]
    value = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    expected = {
        "iss": "https://token.actions.githubusercontent.com",
        "aud": "sts.amazonaws.com",
        "sub": STANDARD_SUBJECT + name,
        "repository": REPOSITORY,
        "environment": name,
        "ref": "refs/heads/main",
        "sha": env["GITHUB_SHA"],
        "repository_id": "1361325921",
        "repository_owner_id": "76547980",
        "actor_id": "76547980",
        "run_id": env["GITHUB_RUN_ID"],
        "run_attempt": "1",
        "workflow_ref": env["GITHUB_WORKFLOW_REF"],
        "workflow_sha": env["GITHUB_SHA"],
        "event_name": "workflow_dispatch",
    }
    require(
        all(value.get(key) == item for key, item in expected.items()),
        "QualificationOidcClaimsMismatch",
    )
    now = datetime.now(UTC).timestamp()
    require(
        type(value.get("exp")) is int
        and value["exp"] > now + 60
        and type(value.get("nbf")) is int
        and value["nbf"] <= now
        and type(value.get("iat")) is int
        and value["iat"] <= now,
        "QualificationOidcTimeMismatch",
    )


def oidc_token(state):
    env = state["env"]
    url = urlsplit(env["ACTIONS_ID_TOKEN_REQUEST_URL"])
    require(
        url.scheme == "https"
        and url.hostname
        and url.hostname.endswith(".actions.githubusercontent.com")
        and not url.username
        and not url.password
        and url.port in {None, 443},
        "QualificationOidcEndpointMismatch",
    )
    query = dict(parse_qsl(url.query)) | {"audience": "sts.amazonaws.com"}
    value = http_json(
        state,
        Request(
            urlunsplit(url._replace(query=urlencode(query))),
            headers={"Authorization": "Bearer " + env["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]},
        ),
    )
    token = value["value"]
    claims(token, state)
    return token


def restriction(account, role, bucket, expiry):
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": "sts:GetCallerIdentity", "Resource": "*"},
                {
                    "Effect": "Allow",
                    "Action": "s3:GetBucketLocation",
                    "Resource": f"arn:aws:s3:::{bucket}",
                },
                {
                    "Effect": "Allow",
                    "Action": "iam:GetRole",
                    "Resource": f"arn:aws:iam::{account}:role/{ROLE_PREFIX}{role}",
                },
                {
                    "Effect": "Deny",
                    "Action": "*",
                    "Resource": "*",
                    "Condition": {"DateGreaterThanEquals": {"aws:CurrentTime": expiry}},
                },
            ],
        },
        separators=(",", ":"),
    )


def aws_call(state, label, call, *, denied=False, target=None):
    from botocore.exceptions import ClientError

    checkpoint(state)
    require(state["aws"] < AWS_MAX, "QualificationAwsLimit")
    state["aws"] += 1
    state["sends"] = 0
    record(
        state,
        stage="aws-started",
        operation=label,
        ordinal=state["aws"],
        role=state.get("role"),
        target=target,
    )
    try:
        result = call()
    except ClientError as error:
        metadata = error.response.get("ResponseMetadata", {})
        require(
            denied
            and error.response.get("Error", {}).get("Code") == "AccessDenied"
            and metadata.get("HTTPStatusCode") == 403
            and isinstance(metadata.get("RequestId"), str)
            and metadata["RequestId"],
            "QualificationUnexpectedAwsFailure",
        )
        record(
            state,
            stage="expected-denial",
            operation=label,
            request_id=metadata["RequestId"],
            role=state.get("role"),
            target=target,
        )
        state.setdefault("checks", []).append(
            {"operation": label, "role": state["role"], "outcome": "denied"}
        )
        checkpoint(state)
        return None
    require(not denied, "QualificationNegativeProbeAllowed")
    metadata = result.get("ResponseMetadata", {})
    require(
        metadata.get("HTTPStatusCode") == 200 and metadata.get("RequestId"),
        "QualificationAwsResponseUnknown",
    )
    record(
        state,
        stage="aws-read-success",
        operation=label,
        request_id=metadata["RequestId"],
        role=state.get("role"),
        target=target,
    )
    state.setdefault("checks", []).append(
        {"operation": label, "role": state["role"], "outcome": "allowed"}
    )
    checkpoint(state)
    return result


def client(session, service, state, config, endpoint):
    """Reject SDK redirects/retries before a second HTTP send, even for S3."""
    result = session.client(service, config=config, endpoint_url=endpoint)

    def sending(**_):
        checkpoint(state)
        require(state["sends"] == 0, "QualificationSdkRetryForbidden")
        state["sends"] += 1

    result.meta.events.register("before-send.*.*", sending)
    return result


def qualify(state):
    from boto3 import Session
    from botocore import UNSIGNED
    from botocore.config import Config

    env, account = state["env"], state["env"]["AWS_DEV_ACCOUNT_ID"]
    config = Config(retries={"total_max_attempts": 1}, connect_timeout=5, read_timeout=15)
    anonymous = Session(
        aws_access_key_id="unsigned", aws_secret_access_key="unsigned", region_name=REGION
    )
    sts = client(
        anonymous,
        "sts",
        state,
        config.merge(Config(signature_version=UNSIGNED)),
        f"https://sts.{REGION}.amazonaws.com",
    )
    opposite = ROLES["dev-apply" if state["name"] == "dev-plan" else "dev-plan"]
    for role, wrong_role in zip(ROLES[state["name"]], opposite, strict=True):
        state["role"] = role
        token = oidc_token(state)
        bucket_kind = "artifacts" if role.startswith("artifact-") else "state"
        bucket = f"ai-interview-{bucket_kind}-{account}-{REGION}"
        session_name = f"p4q-{env['GITHUB_RUN_ID']}-{role}"
        request = {
            "RoleArn": f"arn:aws:iam::{account}:role/{ROLE_PREFIX}{role}",
            "RoleSessionName": session_name,
            "WebIdentityToken": token,
            "DurationSeconds": 900,
            "Policy": restriction(account, role, bucket, state["expiry"].isoformat()),
        }
        response = aws_call(
            state,
            "assume-expected-environment",
            lambda request=request: sts.assume_role_with_web_identity(**request),
            target=role,
        )
        acquired_at = datetime.now(UTC)
        expected = f"arn:aws:sts::{account}:assumed-role/{ROLE_PREFIX}{role}/{session_name}"
        credentials = response["Credentials"]
        require(
            response.get("AssumedRoleUser", {}).get("Arn") == expected
            and all(
                isinstance(credentials.get(key), str) and credentials[key]
                for key in ("AccessKeyId", "SecretAccessKey", "SessionToken")
            )
            and isinstance(credentials.get("Expiration"), datetime)
            and credentials["Expiration"].tzinfo is not None
            and credentials["Expiration"] > datetime.now(UTC) + timedelta(seconds=600),
            "QualificationCredentialsMismatch",
        )
        session_evidence = {
            "role": role,
            "assumed_role_arn": response["AssumedRoleUser"]["Arn"],
            "expires_at_utc": credentials["Expiration"].astimezone(UTC).isoformat(),
            "acquired_at_utc": acquired_at.isoformat(),
        }
        record(
            state,
            stage="session-acquired",
            request_id=response["ResponseMetadata"]["RequestId"],
            **session_evidence,
        )
        session = Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
            region_name=REGION,
        )
        identity = aws_call(
            state,
            "caller-identity",
            lambda session=session: client(
                session, "sts", state, config, f"https://sts.{REGION}.amazonaws.com"
            ).get_caller_identity(),
            target=role,
        )
        require(
            identity.get("Account") == account and identity.get("Arn") == expected,
            "QualificationCallerMismatch",
        )
        record(
            state,
            stage="session-identity-confirmed",
            confirmed_at_utc=datetime.now(UTC).isoformat(),
            request_id=identity["ResponseMetadata"]["RequestId"],
            **session_evidence,
        )
        state.setdefault("sessions", []).append(
            {
                "role": role,
                "acquired_at_utc": acquired_at.isoformat(),
                "expires_at_utc": credentials["Expiration"].astimezone(UTC).isoformat(),
                "identity_matches_expected": True,
            }
        )
        location = aws_call(
            state,
            "allowed-bucket-location",
            lambda session=session, bucket=bucket: client(
                session, "s3", state, config, f"https://s3.{REGION}.amazonaws.com"
            ).get_bucket_location(Bucket=bucket, ExpectedBucketOwner=account),
            target=bucket_kind,
        )
        require(location.get("LocationConstraint") == REGION, "QualificationBucketRegionMismatch")
        aws_call(
            state,
            "denied-bootstrap-role-read",
            lambda session=session, role=role: client(
                session, "iam", state, config, "https://iam.amazonaws.com"
            ).get_role(RoleName=ROLE_PREFIX + role),
            denied=True,
            target=role,
        )
        # One cross-Environment request per target role: two per job, four total.
        request["RoleArn"] = f"arn:aws:iam::{account}:role/{ROLE_PREFIX}{wrong_role}"
        aws_call(
            state,
            "denied-opposite-environment",
            lambda request=request: sts.assume_role_with_web_identity(**request),
            denied=True,
            target=wrong_role,
        )
        del token, request, credentials, response, session
    require(state["aws"] == AWS_MAX, "QualificationCallGraphIncomplete")


def publish_result(state, runner_temp, success):
    """Explicit allowlist projection; never serialize a journal or exception into an artifact."""
    checks, sessions = [], []
    expected_operations = {
        "assume-expected-environment": "allowed",
        "caller-identity": "allowed",
        "allowed-bucket-location": "allowed",
        "denied-bootstrap-role-read": "denied",
        "denied-opposite-environment": "denied",
    }
    for row in state.get("checks", []):
        require(
            set(row) == {"operation", "role", "outcome"}
            and row["role"] in ROLES[state["name"]]
            and expected_operations.get(row["operation"]) == row["outcome"],
            "QualificationPublicProjectionMismatch",
        )
        checks.append({key: row[key] for key in ("operation", "role", "outcome")})
    for row in state.get("sessions", []):
        require(
            set(row) == {"role", "acquired_at_utc", "expires_at_utc", "identity_matches_expected"}
            and row["role"] in ROLES[state["name"]]
            and row["identity_matches_expected"] is True,
            "QualificationPublicProjectionMismatch",
        )
        acquired, expiry = (
            datetime.fromisoformat(row[key]) for key in ("acquired_at_utc", "expires_at_utc")
        )
        require(
            acquired.tzinfo is not None
            and expiry.tzinfo is not None
            and 600 < (expiry - acquired).total_seconds() <= 901,
            "QualificationPublicSessionMismatch",
        )
        sessions.append(
            {
                "role": row["role"],
                "acquired_at_utc": acquired.astimezone(UTC).isoformat(),
                "expires_at_utc": expiry.astimezone(UTC).isoformat(),
                "identity_matches_expected": True,
            }
        )
    if success:
        expected = {
            (role, op, outcome)
            for role in ROLES[state["name"]]
            for op, outcome in expected_operations.items()
        }
        require(
            len(checks) == AWS_MAX
            and len(sessions) == 2
            and {row["role"] for row in sessions} == set(ROLES[state["name"]])
            and {(row["role"], row["operation"], row["outcome"]) for row in checks} == expected,
            "QualificationCallGraphIncomplete",
        )
    env = state["env"]
    # Validate metadata again before publishing even a partial result.
    context(env)
    result = {
        "schema_version": 2,
        "kind": "standard-oidc-readonly-v2",
        "status": "verified" if success else "stopped",
        "source_sha": env["GITHUB_SHA"],
        "reader_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "run_id": env["GITHUB_RUN_ID"],
        "attempt": 1,
        "environment": state["name"],
        "checks": checks,
        "sessions": sessions,
    }
    raw = json.dumps(result, sort_keys=True).encode()
    require(len(raw) <= 32768, "QualificationPublicResultTooLarge")
    output = Path(runner_temp) / "p4-qualification-public"
    output.mkdir(mode=0o700, exist_ok=False)
    with (output / "result.json").open("xb") as stream:
        stream.write(raw)


def main():
    env, project = os.environ, Path(__file__).resolve().parents[3]
    state = None
    success = False
    try:
        name, expiry = context(env)
        verify_checkout(project, env)
        started = float(env["P4_QUALIFY_STARTED_MONOTONIC"])
        journal = Path(env["RUNNER_TEMP"]) / "p4-qualification-private"
        journal.mkdir(mode=0o700, exist_ok=False)
        state = {
            "env": env,
            "name": name,
            "expiry": expiry,
            "clock": datetime.now(UTC),
            "started": started,
            "journal": journal,
            "sequence": 1,
            "http": 0,
            "aws": 0,
            "http_bytes": 0,
        }
        checkpoint(state)
        record(
            state,
            stage="started",
            source_sha=env["GITHUB_SHA"],
            environment=name,
            run_id=env["GITHUB_RUN_ID"],
            attempt=1,
        )
        verify_control_plane(state)
        qualify(state)
        success = True
    except Exception:
        # Raw SDK/HTTP failures can contain tokens or identifiers. Never print them.
        pass
    try:
        if state is not None:
            publish_result(state, env["RUNNER_TEMP"], success)
        else:
            success = False
    except Exception:
        success = False
    print("StandardOidcReadOnlyV2Verified" if success else "QualificationStopped")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
