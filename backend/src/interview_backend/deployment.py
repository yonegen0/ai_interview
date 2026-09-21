"""Explicit dev configuration and offline-testable AWS operation guards.

Importing this module never reads credentials, files, or contacts AWS.
It is deployment tooling, not an application invocation dependency.
"""

import os
import re
from datetime import date
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from pathlib import Path

REGION = "ap-northeast-1"
LOCAL_KEYS = frozenset(
    {
        "AWS_DEV_ACCOUNT_ID",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "AWS_PROFILE",
        "SES_IDENTITY_TYPE",
        "SES_DOMAIN",
        "SES_FROM_EMAIL",
        "ALARM_EMAIL",
        "BUDGET_JPY_PER_USD",
        "BUDGET_RATE_DATE",
        "STATE_BUCKET",
        "ARTIFACT_BUCKET",
        "SES_IDENTITY_ARN",
        "RUNTIME_BOUNDARY_ARN",
    }
)


class DeploymentError(ValueError):
    """Only fixed safe classifications may be used as messages."""

    def __init__(self, message, *, reason_code=None):
        super().__init__(message)
        self.reason_code = reason_code or message


def authentication_reason(error):
    """Classify SDK failures without retaining messages, responses or credentials."""
    from botocore.exceptions import (
        ClientError,
        ConnectionError,
        CredentialRetrievalError,
        TokenRetrievalError,
        UnauthorizedSSOTokenError,
    )

    if isinstance(error, (TokenRetrievalError, UnauthorizedSSOTokenError)):
        return "SsoTokenUnavailable"
    if isinstance(error, ConnectionError):
        return "AwsConnectionFailed"
    if isinstance(error, ClientError):
        code = error.response.get("Error", {}).get("Code")
        if code in {
            "ExpiredToken",
            "ExpiredTokenException",
            "InvalidClientTokenId",
            "AccessDenied",
            "AccessDeniedException",
            "UnrecognizedClientException",
        }:
            return "AwsAuthenticationRejected"
    if isinstance(error, CredentialRetrievalError):
        return "CredentialRetrievalFailed"
    return "AwsIdentityUnavailable"


def require_aws_execution(environment=None):
    """Run before credential discovery, HTTP requests, or AWS client creation."""
    env = os.environ if environment is None else environment
    if env.get("P4_AWS_EXECUTION_READY") != "true":
        raise DeploymentError("AwsExecutionPrerequisitesUnconfirmed")
    if any(key.startswith("AWS_ENDPOINT_URL") for key in env):
        raise DeploymentError("AwsEndpointOverrideForbidden")


def read_local_settings(root: Path) -> dict[str, str]:
    try:
        content = (root / ".env.local").read_text(encoding="utf-8-sig")
    except OSError, UnicodeError:
        raise DeploymentError("LocalSettingsUnavailable") from None
    result = {}
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line)
        if not match:
            raise DeploymentError("InvalidLocalSettingsSyntax")
        key, value = match.groups()
        if key not in LOCAL_KEYS:
            continue
        if key in result:
            raise DeploymentError("DuplicateLocalSetting")
        value = value.strip()
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise DeploymentError("InvalidLocalSettingsSyntax")
            value = value[1:-1]
        elif any(c.isspace() for c in value) or "'" in value or '"' in value:
            raise DeploymentError("InvalidLocalSettingsSyntax")
        result[key] = value
    return result


def validate_target(account: str, region: str) -> None:
    if not isinstance(account, str) or not re.fullmatch(r"[0-9]{12}", account):
        raise DeploymentError("InvalidDevAccount")
    if region != REGION:
        raise DeploymentError("InvalidDevRegion")


def account_settings(root: Path, environment=None) -> tuple[str, str]:
    env = os.environ if environment is None else environment
    ci = env.get("CI", "").lower() == "true" or env.get("GITHUB_ACTIONS") == "true"
    values = env if ci else read_local_settings(root)
    account = values.get("AWS_DEV_ACCOUNT_ID", "")
    validate_target(account, REGION)
    if not ci and env.get("AWS_DEV_ACCOUNT_ID", account) != account:
        raise DeploymentError("ConflictingDevAccount")
    for source in (values, env):
        if any(source.get(key, REGION) != REGION for key in ("AWS_REGION", "AWS_DEFAULT_REGION")):
            raise DeploymentError("ConflictingDevRegion")
    return account, REGION


def checked_session(account, region, *, session_factory=None, environment=None):
    """Validate the real identity before returning any usable AWS session."""
    validate_target(account, region)
    env = os.environ if environment is None else environment
    if any(key.startswith("AWS_ENDPOINT_URL") for key in env):
        raise DeploymentError("AwsEndpointOverrideForbidden")
    from boto3 import Session
    from botocore.config import Config

    try:
        kwargs = {"region_name": region}
        if environment is not None:
            keys = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")
            present = [bool(env.get(key)) for key in keys]
            if any(present):
                if not all(present):
                    raise DeploymentError(
                        "AwsIdentityUnavailable", reason_code="PartialCredentials"
                    )
                if env.get("AWS_PROFILE") or env.get("AWS_DEFAULT_PROFILE"):
                    raise DeploymentError(
                        "AwsIdentityUnavailable", reason_code="MixedCredentialSources"
                    )
                kwargs.update(
                    zip(
                        ("aws_access_key_id", "aws_secret_access_key", "aws_session_token"),
                        (env[key] for key in keys),
                        strict=True,
                    )
                )
            else:
                profile = env.get("AWS_PROFILE")
                if not profile or env.get("AWS_DEFAULT_PROFILE", profile) != profile:
                    raise DeploymentError(
                        "AwsIdentityUnavailable", reason_code="CredentialProfileConflict"
                    )
                kwargs["profile_name"] = profile
        session = (session_factory or Session)(**kwargs)
        if hasattr(session, "_session"):
            pending = [session._session.full_config]
            while pending:
                section = pending.pop()
                if isinstance(section, dict):
                    if "endpoint_url" in section:
                        raise DeploymentError("AwsEndpointOverrideForbidden")
                    pending.extend(section.values())
        sts = session.client(
            "sts",
            endpoint_url=f"https://sts.{region}.amazonaws.com",
            config=Config(retries={"total_max_attempts": 1}, connect_timeout=5, read_timeout=5),
        )
        observed = sts.get_caller_identity()["Account"]
    except DeploymentError:
        raise
    except Exception as error:
        raise DeploymentError(
            "AwsIdentityUnavailable", reason_code=authentication_reason(error)
        ) from None
    if observed != account:
        raise DeploymentError("AwsAccountMismatch")
    return session


def credential_environment(session, environment):
    """Freeze the SDK credentials for the child; never serialize this mapping."""
    try:
        credentials = session.get_credentials().get_frozen_credentials()
        if not all((credentials.access_key, credentials.secret_key, credentials.token)):
            raise ValueError
        child = dict(environment)
        for key in (
            "AWS_PROFILE",
            "AWS_DEFAULT_PROFILE",
            "AWS_ROLE_ARN",
            "AWS_WEB_IDENTITY_TOKEN_FILE",
        ):
            child.pop(key, None)
        child.update(
            AWS_ACCESS_KEY_ID=credentials.access_key,
            AWS_SECRET_ACCESS_KEY=credentials.secret_key,
            AWS_SESSION_TOKEN=credentials.token,
            AWS_EC2_METADATA_DISABLED="true",
        )
        return child
    except Exception as error:
        reason = (
            "ShortTermCredentialsRequired"
            if isinstance(error, ValueError)
            else authentication_reason(error)
        )
        raise DeploymentError("ShortTermCredentialsRequired", reason_code=reason) from None


def terraform_environment(root, environment, account, region):
    """Build a child-only environment; reject hidden Terraform input channels."""
    validate_target(account, region)
    env = dict(environment)
    if any(key.startswith("AWS_ENDPOINT_URL") for key in env):
        raise DeploymentError("AwsEndpointOverrideForbidden")
    if env.get("TF_WORKSPACE", "default") != "default":
        raise DeploymentError("TerraformWorkspaceForbidden")
    if any(key.startswith("TF_CLI_ARGS") for key in env):
        raise DeploymentError("TerraformArgumentsForbidden")
    if any(env.get(key) for key in ("TF_LOG", "TF_LOG_PATH", "TF_DATA_DIR")):
        raise DeploymentError("TerraformRuntimeOverrideForbidden")
    for key, expected in {
        "TF_VAR_account_id": account,
        "TF_VAR_region": region,
        "AWS_REGION": region,
        "AWS_DEFAULT_REGION": region,
    }.items():
        if key in env and env[key] != expected:
            raise DeploymentError("TerraformSettingConflict")
        env[key] = expected
    if any(Path(root).glob("*.auto.tfvars*")) or any(
        (Path(root) / name).exists() for name in ("terraform.tfvars", "terraform.tfvars.json")
    ):
        raise DeploymentError("TerraformAutoloadForbidden")
    env["TF_INPUT"] = "0"
    return env


def monthly_budget(jpy_per_usd, basis_date):
    try:
        date.fromisoformat(basis_date)
        rate = Decimal(jpy_per_usd)
        if not rate.is_finite() or rate <= 0:
            raise ValueError
        amount = (Decimal(3000) / rate).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        if amount <= 0:
            raise ValueError
    except ValueError, TypeError, InvalidOperation, OverflowError:
        raise DeploymentError("InvalidBudgetBasis") from None
    return format(amount, ".2f")
