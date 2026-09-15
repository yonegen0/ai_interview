"""GitHub OIDC -> short-lived credentials, kept only in this process environment."""

import base64
import json
import os
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from interview_backend.deployment import (
    DeploymentError,
    checked_session,
    require_aws_execution,
    validate_target,
)

REPOSITORY = "yonegen0/ai_interview"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validated_claims(token, expected_subject, environment):
    """Preflight only: AWS STS, not this decoder, verifies the JWT signature."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if (
            claims["iss"] != "https://token.actions.githubusercontent.com"
            or claims["aud"] != "sts.amazonaws.com"
            or claims["sub"] != expected_subject
            or claims["repository"] != REPOSITORY
            or claims["environment"] != "dev"
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
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise DeploymentError("GitHubOidcRequired")
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
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            token = json.loads(response.read(65537))["value"]
        validated_claims(token, expected_subject, os.environ)
        sts = Session(region_name=region).client(
            "sts",
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
        response = sts.assume_role_with_web_identity(
            RoleArn=f"arn:aws:iam::{account}:role/ai-interview-ci-{role}",
            RoleSessionName=f"p4-{run_id}-{role}",
            WebIdentityToken=token,
            DurationSeconds=3600,
        )["Credentials"]
        os.environ.update(
            {
                "AWS_ACCESS_KEY_ID": response["AccessKeyId"],
                "AWS_SECRET_ACCESS_KEY": response["SecretAccessKey"],
                "AWS_SESSION_TOKEN": response["SessionToken"],
                "AWS_REGION": region,
                "AWS_DEFAULT_REGION": region,
            }
        )
    except Exception:
        raise DeploymentError("OidcAuthenticationFailed") from None
    return checked_session(account, region)
