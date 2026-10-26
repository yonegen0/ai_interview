"""GitHub OIDC -> short-lived credentials, kept only in this process environment."""

import base64
import json
import os
import re
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from plan_authorization import active_guard, session_policy

from interview_backend.deployment import (
    DeploymentError,
    checked_session,
    require_aws_execution,
    validate_target,
)

REPOSITORY = "yonegen0/ai_interview"
STANDARD_SUBJECT = "repo:yonegen0@76547980/ai_interview@1361325921:environment:"


def standard_context(environment, *, now=None, reserve=0):
    """Bind the standard dispatch to protected main; no custom identity issuer."""
    operation = environment.get("P4_OPERATION")
    workflow = f"{REPOSITORY}/.github/workflows/p4-standard-{operation}.yml@refs/heads/main"
    sha = environment.get("GITHUB_SHA", "")
    if (
        operation not in {"plan", "apply"}
        or environment.get("GITHUB_ACTIONS") != "true"
        or environment.get("GITHUB_REPOSITORY") != REPOSITORY
        or environment.get("GITHUB_REPOSITORY_ID") != "1361325921"
        or environment.get("GITHUB_REPOSITORY_OWNER_ID") != "76547980"
        or environment.get("GITHUB_ACTOR_ID") != "76547980"
        or environment.get("GITHUB_ACTOR") != "yonegen0"
        or environment.get("GITHUB_TRIGGERING_ACTOR") != "yonegen0"
        or environment.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or environment.get("GITHUB_RUN_ATTEMPT") != "1"
        or not re.fullmatch(r"[0-9]+", environment.get("GITHUB_RUN_ID", ""))
        or environment.get("GITHUB_REF") != "refs/heads/main"
        or not re.fullmatch(r"[0-9a-f]{40}", sha)
        or environment.get("P4_APPROVED_SOURCE_SHA") != sha
        or environment.get("GITHUB_WORKFLOW_SHA") != sha
        or environment.get("GITHUB_WORKFLOW_REF") != workflow
        or environment.get("P4_STANDARD_READY") != "true"
        or environment.get("P4_STANDARD_REVIEW_MODE") not in {"reviewers", "manual"}
        or environment.get("P4_OIDC_SUBJECT") != STANDARD_SUBJECT + "dev-" + operation
        or any(environment.get(key) == "true" for key in ("P4_CLOUD_ACTIVE", "P4_COMPOUND_ACTIVE"))
    ):
        raise DeploymentError("StandardWorkflowIdentityMismatch")
    from approval_validity import utc_stamp

    issued = utc_stamp(environment.get("P4_APPROVED_AT_UTC"))
    expiry = utc_stamp(environment.get("P4_APPROVAL_EXPIRES_AT"))
    clock = now or datetime.now(UTC)
    if expiry - issued != timedelta(hours=72) or not issued <= clock < expiry - timedelta(
        seconds=reserve
    ):
        raise DeploymentError("StandardApprovalExpiredOrNotIssued")
    return "dev-" + operation


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def oidc_http_diagnostic(error: HTTPError) -> dict[str, object]:
    """Keep only status and strictly shaped correlation IDs, never URL/body/token."""
    status = error.code
    if type(status) is not int or not 100 <= status <= 599:
        status = None
    identifiers = {}
    for header, pattern in (
        ("x-github-request-id", r"[0-9A-F]{4}(?::[0-9A-F]{1,16}){4}"),
        ("x-vss-e2eid", r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"),
        ("x-tfs-session", r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"),
    ):
        value = error.headers.get(header) if error.headers is not None else None
        if isinstance(value, str) and len(value) <= 72 and re.fullmatch(pattern, value):
            identifiers[header] = value
    return {
        "http_status": status,
        "request_ids": identifiers,
        "raw_response_preserved": False,
    }


def validated_claims(token, expected_subject, environment):
    """Preflight only: AWS STS, not this decoder, verifies the JWT signature."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        standard = environment.get("P4_STANDARD_ACTIVE") == "true"
        expected_environment = standard_context(environment) if standard else "dev"
        if standard and any(
            claims.get(claim) != environment.get(variable)
            for claim, variable in {
                "repository_id": "GITHUB_REPOSITORY_ID",
                "repository_owner_id": "GITHUB_REPOSITORY_OWNER_ID",
                "actor_id": "GITHUB_ACTOR_ID",
                "run_id": "GITHUB_RUN_ID",
                "run_attempt": "GITHUB_RUN_ATTEMPT",
                "workflow_ref": "GITHUB_WORKFLOW_REF",
                "workflow_sha": "GITHUB_WORKFLOW_SHA",
                "event_name": "GITHUB_EVENT_NAME",
            }.items()
        ):
            raise ValueError
        if (
            claims["iss"] != "https://token.actions.githubusercontent.com"
            or claims["aud"] != "sts.amazonaws.com"
            or claims["sub"] != expected_subject
            or claims["repository"] != REPOSITORY
            or claims["environment"] != expected_environment
            or claims["ref"] != "refs/heads/main"
            or claims["sha"] != environment["GITHUB_SHA"]
            or environment.get("GITHUB_REF") != "refs/heads/main"
            or environment.get("GITHUB_REPOSITORY") != REPOSITORY
            or not expected_subject
            or "*" in expected_subject
            or "?" in expected_subject
        ):
            raise ValueError
    except Exception:
        raise DeploymentError("OidcClaimsMismatch") from None
    return {
        key: claims[key] for key in ("iss", "aud", "sub", "repository", "environment", "ref", "sha")
    }


def assume(role, account, region, *, expected_subject):
    require_aws_execution()
    validate_target(account, region)
    if role not in {"artifact", "plan", "deploy", "test"}:
        raise DeploymentError("InvalidCiRole")
    standard = os.environ.get("P4_STANDARD_ACTIVE") == "true"
    role_name = "ai-interview-ci-" + role
    if standard:
        standard_context(os.environ, reserve=120)
        operation = os.environ["P4_OPERATION"]
        allowed = {"plan": {"plan", "artifact"}, "apply": {"deploy", "artifact"}}
        if role not in allowed[operation]:
            raise DeploymentError("StandardRolePurposeMismatch")
        suffix = f"artifact-{operation}" if role == "artifact" else role
        role_name = "ai-interview-standard-ci-" + suffix
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise DeploymentError("GitHubOidcRequired")
    guard = active_guard()
    if guard and (
        role not in {"plan", "artifact"}
        or account != guard.package["account_id"]
        or region != guard.package["region"]
        or expected_subject != guard.package["oidc_subject"]
    ):
        error = DeploymentError("PlanAuthenticationScopeMismatch")
        guard.fail(error)
        raise error
    from boto3 import Session
    from botocore import UNSIGNED
    from botocore.config import Config

    try:
        url = urlsplit(os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"])
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError
        if not url.hostname.endswith(".actions.githubusercontent.com"):
            raise ValueError
        query = dict(parse_qsl(url.query)) | {"audience": "sts.amazonaws.com"}
        request = Request(
            urlunsplit(url._replace(query=urlencode(query))),
            headers={"Authorization": "Bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]},
        )

        def request_token():
            try:
                with build_opener(NoRedirect()).open(request, timeout=15) as response:
                    raw = response.read(65537)
                    if len(raw) > 65536:
                        raise ValueError
                    return json.loads(raw)["value"]
            except HTTPError as error:
                if guard:
                    guard.record("oidc-http-error", role=role, **oidc_http_diagnostic(error))
                raise

        token = guard.authenticate("oidc", role, request_token) if guard else request_token()
        validated_claims(token, expected_subject, os.environ)
        sts = Session(region_name=region).client(
            "sts",
            endpoint_url=f"https://sts.{region}.amazonaws.com",
            config=Config(
                signature_version=UNSIGNED,
                retries={"total_max_attempts": 1},
                connect_timeout=5,
                read_timeout=15,
            ),
        )
        run_id = os.environ.get("GITHUB_RUN_ID", "")
        if not re.fullmatch(r"[0-9]+", run_id):
            raise ValueError

        def request_credentials():
            restriction = (
                {
                    "Policy": json.dumps(
                        session_policy(guard.package["expires_at_utc"]), separators=(",", ":")
                    )
                }
                if guard
                else (
                    {"Policy": json.dumps(session_policy(os.environ["P4_APPROVAL_EXPIRES_AT"]))}
                    if standard
                    else {}
                )
            )
            response = sts.assume_role_with_web_identity(
                RoleArn=f"arn:aws:iam::{account}:role/{role_name}",
                RoleSessionName=f"p4-{run_id}-{role}",
                WebIdentityToken=token,
                DurationSeconds=3600,
                **restriction,
            )
            if guard or standard:
                if guard:
                    guard.record(
                        "sts-response",
                        role=role,
                        request_id=response.get("ResponseMetadata", {}).get("RequestId"),
                    )
                expected_arn = f"arn:aws:sts::{account}:assumed-role/{role_name}/p4-{run_id}-{role}"
                credentials = response["Credentials"]
                if (
                    response.get("AssumedRoleUser", {}).get("Arn") != expected_arn
                    or not all(
                        credentials.get(key)
                        for key in ("AccessKeyId", "SecretAccessKey", "SessionToken")
                    )
                    or not isinstance(credentials.get("Expiration"), datetime)
                    or credentials["Expiration"].tzinfo is None
                    or credentials["Expiration"] <= (guard.clock() if guard else datetime.now(UTC))
                ):
                    raise DeploymentError("PlanAuthenticationScopeMismatch")
            return response["Credentials"]

        response = (
            guard.authenticate("sts", role, request_credentials) if guard else request_credentials()
        )
        os.environ.update(
            {
                "AWS_ACCESS_KEY_ID": response["AccessKeyId"],
                "AWS_SECRET_ACCESS_KEY": response["SecretAccessKey"],
                "AWS_SESSION_TOKEN": response["SessionToken"],
                "AWS_REGION": region,
                "AWS_DEFAULT_REGION": region,
            }
        )
        if guard:
            guard.check("caller-identity", 25)
            session = guard.call(
                "caller-identity", lambda: checked_session(account, region, environment=os.environ)
            )
            if os.environ.get("P4_CLOUD_ACTIVE") == "true":
                session.p4_expiration = response["Expiration"]
            return session
        return checked_session(account, region)
    except Exception as error:
        if guard:
            guard.fail(error)
        raise DeploymentError("OidcAuthenticationFailed") from None
