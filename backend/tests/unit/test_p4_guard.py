"""Offline safety tests: no AWS credentials or real clients are used."""

from types import SimpleNamespace

import pytest

from interview_backend.deployment import (
    DeploymentError,
    account_settings,
    checked_session,
    credential_environment,
    monthly_budget,
    read_local_settings,
    require_aws_execution,
    terraform_environment,
)


@pytest.mark.parametrize("value", [None, "false", "TRUE", "1", ""])
def test_aws_execution_requires_literal_true(value):
    env = {} if value is None else {"P4_AWS_EXECUTION_READY": value}
    with pytest.raises(DeploymentError, match="AwsExecutionPrerequisitesUnconfirmed"):
        require_aws_execution(env)


def test_aws_gate_accepts_explicit_ready_and_rejects_endpoint():
    require_aws_execution({"P4_AWS_EXECUTION_READY": "true"})
    with pytest.raises(DeploymentError, match="AwsEndpointOverrideForbidden"):
        require_aws_execution({"P4_AWS_EXECUTION_READY": "true", "AWS_ENDPOINT_URL_STS": "invalid"})


@pytest.mark.parametrize("key", ["TF_LOG", "TF_LOG_PATH", "TF_DATA_DIR"])
def test_terraform_rejects_logging_and_data_overrides(tmp_path, key):
    with pytest.raises(DeploymentError, match="TerraformRuntimeOverrideForbidden"):
        terraform_environment(tmp_path, {key: "private"}, "123456789012", "ap-northeast-1")


def test_local_bom_quotes_and_no_execution(tmp_path):
    (tmp_path / ".env.local").write_text(
        "\ufeff# local\nAWS_DEV_ACCOUNT_ID='123456789012'\n"
        'SES_FROM_EMAIL="$(never-execute)@example.invalid"\n'
        "AWS_SECRET_ACCESS_KEY=do-not-import\n",
        encoding="utf-8",
    )
    values = read_local_settings(tmp_path)
    assert values["AWS_DEV_ACCOUNT_ID"] == "123456789012"
    assert values["SES_FROM_EMAIL"] == "$(never-execute)@example.invalid"
    assert "AWS_SECRET_ACCESS_KEY" not in values


@pytest.mark.parametrize(
    "line",
    [
        "AWS_DEV_ACCOUNT_ID=123456789012\nAWS_DEV_ACCOUNT_ID=123456789012",
        "export AWS_DEV_ACCOUNT_ID=123456789012",
        "AWS_DEV_ACCOUNT_ID 'secret-value'",
        "AWS_DEV_ACCOUNT_ID='secret-value",
    ],
)
def test_bad_local_syntax_is_redacted(tmp_path, line):
    (tmp_path / ".env.local").write_text(line, encoding="utf-8")
    with pytest.raises(DeploymentError) as error:
        read_local_settings(tmp_path)
    assert "secret-value" not in str(error.value)


def test_ci_does_not_read_local_file(tmp_path):
    (tmp_path / ".env.local").write_text("invalid", encoding="utf-8")
    assert account_settings(tmp_path, {"CI": "true", "AWS_DEV_ACCOUNT_ID": "123456789012"}) == (
        "123456789012",
        "ap-northeast-1",
    )


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"AWS_DEV_ACCOUNT_ID": "123"},
        {"AWS_DEV_ACCOUNT_ID": "123456789012", "AWS_REGION": "us-east-1"},
    ],
)
def test_invalid_account_settings(tmp_path, values):
    with pytest.raises(DeploymentError):
        account_settings(tmp_path, {"CI": "true", **values})


def test_guard_rejects_before_downstream_clients():
    calls = []
    session = SimpleNamespace(
        client=lambda name, **kw: (
            calls.append(name)
            or SimpleNamespace(get_caller_identity=lambda: {"Account": "999999999999"})
        )
    )
    with pytest.raises(DeploymentError, match="AwsAccountMismatch"):
        checked_session("123456789012", "ap-northeast-1", session_factory=lambda **kw: session)
    assert calls == ["sts"]


def test_guard_redacts_connection_error():
    def fail(**kwargs):
        raise RuntimeError("credential-and-sdk-detail")

    with pytest.raises(DeploymentError, match="AwsIdentityUnavailable") as error:
        checked_session("123456789012", "ap-northeast-1", session_factory=fail)
    assert "credential" not in str(error.value)


@pytest.mark.parametrize(
    "environment,reason",
    [
        ({"AWS_ACCESS_KEY_ID": "synthetic"}, "PartialCredentials"),
        (
            {
                "AWS_ACCESS_KEY_ID": "synthetic",
                "AWS_SECRET_ACCESS_KEY": "synthetic",
                "AWS_SESSION_TOKEN": "synthetic",
                "AWS_PROFILE": "synthetic",
            },
            "MixedCredentialSources",
        ),
        ({"AWS_PROFILE": "one", "AWS_DEFAULT_PROFILE": "two"}, "CredentialProfileConflict"),
    ],
)
def test_authentication_source_reasons_preserve_legacy_message(environment, reason):
    with pytest.raises(DeploymentError, match="^AwsIdentityUnavailable$") as caught:
        checked_session(
            "123456789012",
            "ap-northeast-1",
            environment=environment,
            session_factory=lambda **kw: pytest.fail("session must not be created"),
        )
    assert caught.value.reason_code == reason


@pytest.mark.parametrize(
    "kind,reason",
    [
        ("sso", "SsoTokenUnavailable"),
        ("denied", "AwsAuthenticationRejected"),
        ("network", "AwsConnectionFailed"),
        ("unknown", "AwsIdentityUnavailable"),
    ],
)
def test_sdk_failure_classification_never_retains_message(kind, reason):
    from botocore.exceptions import ClientError, EndpointConnectionError, TokenRetrievalError

    errors = {
        "sso": TokenRetrievalError(provider="sso", error_msg="synthetic-token"),
        "denied": ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "synthetic-token"}}, "GetCallerIdentity"
        ),
        "network": EndpointConnectionError(endpoint_url="https://secret.invalid"),
        "unknown": RuntimeError("synthetic-token"),
    }

    def fail(**kwargs):
        raise errors[kind]

    with pytest.raises(DeploymentError, match="^AwsIdentityUnavailable$") as caught:
        checked_session("123456789012", "ap-northeast-1", session_factory=fail)
    assert caught.value.reason_code == reason
    assert "synthetic-token" not in str(caught.value)


def test_explicit_credentials_are_shared_with_terraform():
    captured = []
    credentials = SimpleNamespace(
        access_key="synthetic-key", secret_key="synthetic-secret", token="synthetic-token"
    )
    session = SimpleNamespace(
        client=lambda *a, **kw: SimpleNamespace(
            get_caller_identity=lambda: {"Account": "123456789012"}
        ),
        get_credentials=lambda: SimpleNamespace(get_frozen_credentials=lambda: credentials),
    )
    parent = {
        "AWS_ACCESS_KEY_ID": credentials.access_key,
        "AWS_SECRET_ACCESS_KEY": credentials.secret_key,
        "AWS_SESSION_TOKEN": credentials.token,
    }
    checked_session(
        "123456789012",
        "ap-northeast-1",
        environment=parent,
        session_factory=lambda **kw: captured.append(kw) or session,
    )
    child = credential_environment(session, parent)
    assert captured[0]["aws_access_key_id"] == child["AWS_ACCESS_KEY_ID"]
    assert captured[0]["aws_session_token"] == child["AWS_SESSION_TOKEN"]
    assert "AWS_EC2_METADATA_DISABLED" not in parent


def test_long_term_credentials_cannot_be_exported_to_terraform():
    credentials = SimpleNamespace(access_key="key", secret_key="secret", token=None)
    session = SimpleNamespace(
        get_credentials=lambda: SimpleNamespace(get_frozen_credentials=lambda: credentials)
    )
    with pytest.raises(DeploymentError, match="ShortTermCredentialsRequired"):
        credential_environment(session, {})


def test_shared_config_endpoint_rejected_before_sts():
    session = SimpleNamespace(
        _session=SimpleNamespace(
            full_config={
                "services": {"custom": {"s3": {"endpoint_url": "https://private.invalid"}}}
            }
        ),
        client=lambda *a, **kw: pytest.fail("STS called"),
    )
    with pytest.raises(DeploymentError, match="AwsEndpointOverrideForbidden"):
        checked_session("123456789012", "ap-northeast-1", session_factory=lambda **kw: session)


@pytest.mark.parametrize(
    "values",
    [
        {"TF_VAR_account_id": "999999999999"},
        {"TF_CLI_ARGS_plan": "-var=account_id=999"},
        {"AWS_DEFAULT_REGION": "us-east-1"},
    ],
)
def test_terraform_environment_rejects_overrides(tmp_path, values):
    with pytest.raises(DeploymentError):
        terraform_environment(tmp_path, values, "123456789012", "ap-northeast-1")


def test_terraform_autoload_rejected_and_parent_unchanged(tmp_path):
    parent = {"AWS_SESSION_TOKEN": "memory-only"}
    child = terraform_environment(tmp_path, parent, "123456789012", "ap-northeast-1")
    assert child["TF_VAR_account_id"] == "123456789012"
    assert "TF_VAR_account_id" not in parent
    (tmp_path / "override.auto.tfvars.json").write_text("{}", encoding="utf-8")
    with pytest.raises(DeploymentError, match="TerraformAutoloadForbidden"):
        terraform_environment(tmp_path, parent, "123456789012", "ap-northeast-1")


def test_budget_decimal_round_down():
    assert monthly_budget("149", "2026-09-13") == "20.13"


@pytest.mark.parametrize("rate", ["0", "-1", "NaN", "Infinity", "invalid", "1e100"])
def test_budget_rejects_invalid_rate(rate):
    with pytest.raises(DeploymentError):
        monthly_budget(rate, "2026-09-13")
