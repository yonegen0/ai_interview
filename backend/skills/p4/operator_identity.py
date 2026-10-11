"""One explicitly approved STS diagnostic; never refresh credentials or change AWS."""

import hashlib
import json
import re
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from botocore.config import Config


class IdentityDiagnosticError(ValueError):
    def __init__(self, condition):
        super().__init__(condition)
        self.condition = condition


def require(condition, code):
    if not condition:
        raise IdentityDiagnosticError(code)


def profile_gate(configuration, environment, expected):
    """Inspect only local settings, without entering a credential provider chain."""
    account, region = expected["account_id"], expected["region"]
    role = expected["operator_role_arn"]
    require(bool(re.fullmatch(r"[0-9]{12}", account)), "InvalidExpectedAccount")
    require(region == "ap-northeast-1", "InvalidExpectedRegion")
    prefix = f"arn:aws:iam::{account}:role/aws-reserved/sso.amazonaws.com/{region}/"
    require(
        role.startswith(prefix)
        and bool(
            re.fullmatch(r"AWSReservedSSO_AdministratorAccess_[0-9a-f]{16}", role[len(prefix) :])
        ),
        "InvalidExpectedRole",
    )
    for key in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
        require(environment.get(key, expected["profile"]) == expected["profile"], "ProfileConflict")
    for key in ("AWS_REGION", "AWS_DEFAULT_REGION"):
        require(environment.get(key, region) == region, "RegionConflict")
    forbidden = {
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_SECURITY_TOKEN",
        "AWS_ROLE_ARN",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_CONFIG_FILE",
        "AWS_SHARED_CREDENTIALS_FILE",
        "BOTO_CONFIG",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        "AWS_ENDPOINT_URL",
        "AWS_DEV_ACCOUNT_ID",
    }
    require(
        not any(key in environment for key in forbidden)
        and not any(key.startswith("AWS_ENDPOINT_URL_") for key in environment),
        "CredentialEnvironmentConflict",
    )
    profiles = configuration.get("profiles", {})
    profile = profiles.get(expected["profile"], {})
    require(isinstance(profile, dict), "ProfileMissing")
    require(
        not any(
            profile.get(key)
            for key in (
                "credential_process",
                "role_arn",
                "source_profile",
                "credential_source",
                "aws_access_key_id",
                "aws_secret_access_key",
                "aws_session_token",
                "endpoint_url",
            )
        ),
        "CredentialProviderConflict",
    )
    require(
        profile.get("sso_account_id") == account
        and profile.get("sso_role_name") == "AdministratorAccess"
        and profile.get("region") == region,
        "ProfileTargetMismatch",
    )
    name = profile.get("sso_session")
    session = configuration.get("sso_sessions", {}).get(name, {})
    require(
        isinstance(name, str)
        and bool(name)
        and session.get("sso_region") == region
        and session.get("sso_start_url") == expected["sso_start_url"],
        "SSOSessionTargetMismatch",
    )
    require(not session.get("endpoint_url"), "SSOEndpointOverride")
    # Same local cache identity as botocore SSOCredentialFetcher; no token loader.
    key = json.dumps(
        {"accountId": account, "roleName": "AdministratorAccess", "sessionName": name},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha1(key.encode()).hexdigest()


def cached_credentials(cache_directory, cache_key, account, now):
    path = Path(cache_directory) / (cache_key + ".json")
    require(path.is_file() and not path.is_symlink(), "CachedCredentialsUnavailable")
    try:
        value = json.loads(path.read_bytes())
        require(isinstance(value, dict), "CachedCredentialsMalformed")
        credentials = value["Credentials"]
        require(isinstance(credentials, dict), "CachedCredentialsMalformed")
        require(isinstance(credentials.get("Expiration"), str), "CachedCredentialsMalformed")
        expiry = datetime.fromisoformat(credentials["Expiration"].replace("Z", "+00:00"))
        require(value.get("ProviderType") == "sso", "CacheProviderMismatch")
        require(credentials.get("AccountId") == account, "CacheAccountMismatch")
        require(
            expiry.tzinfo is not None and expiry > now + timedelta(minutes=15),
            "CachedCredentialsExpiredOrExpiring",
        )
        require(
            all(
                isinstance(credentials.get(k), str) and credentials[k]
                for k in ("AccessKeyId", "SecretAccessKey", "SessionToken")
            ),
            "CachedCredentialsIncomplete",
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, IdentityDiagnosticError):
            raise
        raise IdentityDiagnosticError("CachedCredentialsMalformed") from None
    return credentials


def validate_actor(actor, expected):
    require(isinstance(actor, dict), "ActorResponseMalformed")
    require(actor.get("Account") == expected["account_id"], "ActorAccountMismatch")
    name = expected["operator_role_arn"].rsplit("/", 1)[-1]
    prefix = f"arn:aws:sts::{expected['account_id']}:assumed-role/{name}/"
    arn = actor.get("Arn")
    require(isinstance(arn, str) and arn.startswith(prefix), "ActorRoleMismatch")
    session = arn[len(prefix) :]
    require(bool(re.fullmatch(r"[A-Za-z0-9_+=,.@-]{2,64}", session)), "ActorSessionMalformed")
    user_id = actor.get("UserId")
    require(
        isinstance(user_id, str)
        and bool(re.fullmatch(r"ARO[A-Z0-9]+:" + re.escape(session), user_id)),
        "ActorUserIdMismatch",
    )
    require(
        isinstance(actor.get("ResponseMetadata"), dict)
        and isinstance(actor["ResponseMetadata"].get("RequestId"), str)
        and bool(actor["ResponseMetadata"]["RequestId"]),
        "ActorRequestIdMissing",
    )


def safe_actor(actor):
    if not isinstance(actor, dict):
        return {"Account": None, "Arn": None, "UserId": None, "RequestId": None}
    metadata = actor.get("ResponseMetadata", {})
    return {
        **{
            key: actor.get(key) if isinstance(actor.get(key), str) else None
            for key in ("Account", "Arn", "UserId")
        },
        "RequestId": metadata.get("RequestId")
        if isinstance(metadata, dict) and isinstance(metadata.get("RequestId"), str)
        else None,
    }


def diagnose(expected, configuration, environment, cache_directory, record, now, session_factory):
    """record must be a private, exclusive, durable writer in a new fixed run directory."""
    report = {
        "PASS": False,
        "expected": {
            k: expected[k] for k in ("account_id", "region", "operator_role_arn", "profile")
        },
        "actor": safe_actor(None),
        "started_utc": now.isoformat(),
        "started_jst": now.astimezone(timezone(timedelta(hours=9))).isoformat(),
        "stage": "local_preflight",
        "sts_invocations": 0,
        "http_sends": 0,
        "blocked_operations": [],
        "exception_type": None,
        "failed_condition": None,
        "aws_writes": 0,
        "credentials_persisted": False,
    }
    actor = None
    try:
        record(
            "diagnostic-started.private.json",
            {"started_utc": now.isoformat(), "maximum_sts_calls": 1},
        )
        key = profile_gate(configuration, environment, expected)
        credentials = cached_credentials(cache_directory, key, expected["account_id"], now)
        session = session_factory(
            region_name=expected["region"],
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
        )
        credentials = None

        def before_call(model, **kwargs):
            if model.name != "GetCallerIdentity":
                report["blocked_operations"].append(model.name)
                raise IdentityDiagnosticError("AdditionalAWSOperationForbidden")

        def before_send(**kwargs):
            require(report["http_sends"] == 0, "SecondHTTPSendForbidden")
            report["http_sends"] += 1

        session.events.register("before-call.*.*", before_call)
        session.events.register("before-send.*.*", before_send)
        client = session.client(
            "sts",
            endpoint_url=f"https://sts.{expected['region']}.amazonaws.com",
            config=Config(retries={"total_max_attempts": 1}, connect_timeout=5, read_timeout=5),
        )
        record("sts-started.private.json", {"maximum_sts_calls": 1, "automatic_retries": 0})
        report["stage"] = "sts_request"
        report["sts_invocations"] = 1
        actor = client.get_caller_identity()
        report["actor"] = safe_actor(actor)
        record("actor-response.private.json", report["actor"])
        report["stage"] = "actor_validation"
        validate_actor(actor, expected)
        report["PASS"] = True
    except Exception as error:
        report["exception_type"] = type(error).__name__
        report["failed_condition"] = (
            error.condition
            if isinstance(error, IdentityDiagnosticError)
            else "AWSRequestFailed"
            if report["stage"] == "sts_request"
            else "LocalDiagnosticFailed"
        )
        if isinstance(getattr(error, "response", None), dict):
            report["actor"]["RequestId"] = safe_actor(error.response)["RequestId"]
        report["failure_frames"] = [
            {"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
            for f in traceback.extract_tb(error.__traceback__)
        ]
        # Never persist exception messages, headers, response bodies, or credential objects.
    record("diagnostic-result.private.json", report)
    return report
