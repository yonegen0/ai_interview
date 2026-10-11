"""No real AWS: strict actor identity, cache-only credentials and durable one-call gating."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_p4_tools import tool


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "skills/p4"))
    return tool("operator_identity")


@pytest.fixture
def expected():
    return {
        "account_id": "123456789012",
        "region": "ap-northeast-1",
        "profile": "dev",
        "operator_role_arn": "arn:aws:iam::123456789012:role/aws-reserved/sso.amazonaws.com/"
        "ap-northeast-1/AWSReservedSSO_AdministratorAccess_1234567890abcdef",
        "sso_start_url": "https://example.awsapps.com/start",
    }


def configuration():
    return {
        "profiles": {
            "dev": {
                "sso_account_id": "123456789012",
                "sso_role_name": "AdministratorAccess",
                "region": "ap-northeast-1",
                "sso_session": "dev",
            }
        },
        "sso_sessions": {
            "dev": {
                "sso_region": "ap-northeast-1",
                "sso_start_url": "https://example.awsapps.com/start",
            }
        },
    }


def actor(expected, session="person@example.com"):
    role = expected["operator_role_arn"].rsplit("/", 1)[-1]
    return {
        "Account": expected["account_id"],
        "Arn": f"arn:aws:sts::{expected['account_id']}:assumed-role/{role}/{session}",
        "UserId": "AROA12345678901234567:" + session,
        "ResponseMetadata": {"RequestId": "request-id", "HTTPHeaders": {"secret": "NEVER_SAVE"}},
        "extra_secret": "NEVER_SAVE",
    }


def cache(module, tmp_path, expected, now, changes=None):
    key = module.profile_gate(configuration(), {}, expected)
    value = {
        "ProviderType": "sso",
        "Credentials": {
            "AccountId": expected["account_id"],
            "AccessKeyId": "NEVER_SAVE_ACCESS",
            "SecretAccessKey": "NEVER_SAVE_SECRET",
            "SessionToken": "NEVER_SAVE_TOKEN",
            "Expiration": (now + timedelta(hours=1)).isoformat(),
        },
    }
    if changes:
        value["Credentials"].update(changes)
    (tmp_path / (key + ".json")).write_text(json.dumps(value))
    return key


@pytest.mark.parametrize("session", ["yonegen-dev", "different-session", "person@example.com"])
def test_iam_role_path_and_sts_session_forms_are_validated_exactly(module, expected, session):
    module.validate_actor(actor(expected, session), expected)


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"Account": "999999999999"}, "ActorAccountMismatch"),
        ({"Account": None}, "ActorAccountMismatch"),
        ({"Arn": "arn:aws:iam::123456789012:role/wrong"}, "ActorRoleMismatch"),
        ({"Arn": "arn:aws:sts::999999999999:assumed-role/wrong/person"}, "ActorRoleMismatch"),
        ({"Arn": None}, "ActorRoleMismatch"),
        ({"UserId": None}, "ActorUserIdMismatch"),
        ({"UserId": "AROA123:other-session"}, "ActorUserIdMismatch"),
        ({"ResponseMetadata": {}}, "ActorRequestIdMissing"),
    ],
)
def test_actor_mismatch_and_missing_fields(module, expected, changes, code):
    with pytest.raises(module.IdentityDiagnosticError, match=code):
        module.validate_actor(actor(expected) | changes, expected)


@pytest.mark.parametrize("suffix", ["", "a/b", "one/extra", "x", "person\n"])
def test_invalid_session_never_passes_prefix_check(module, expected, suffix):
    value = actor(expected)
    value["Arn"] = value["Arn"].rsplit("/", 1)[0] + "/" + suffix
    with pytest.raises(module.IdentityDiagnosticError, match="ActorSessionMalformed"):
        module.validate_actor(value, expected)


def test_wrong_role_suffix_is_not_accepted(module, expected):
    value = actor(expected)
    value["Arn"] = value["Arn"].replace("1234567890abcdef", "ffffffffffffffff")
    with pytest.raises(module.IdentityDiagnosticError, match="ActorRoleMismatch"):
        module.validate_actor(value, expected)


@pytest.mark.parametrize(
    "environment,code",
    [
        ({"AWS_PROFILE": "other"}, "ProfileConflict"),
        ({"AWS_DEFAULT_PROFILE": "other"}, "ProfileConflict"),
        ({"AWS_REGION": "us-east-1"}, "RegionConflict"),
        ({"AWS_ACCESS_KEY_ID": "NEVER_SAVE"}, "CredentialEnvironmentConflict"),
        ({"AWS_SESSION_TOKEN": ""}, "CredentialEnvironmentConflict"),
        ({"AWS_ENDPOINT_URL_STS": "https://other"}, "CredentialEnvironmentConflict"),
        ({"AWS_WEB_IDENTITY_TOKEN_FILE": "path"}, "CredentialEnvironmentConflict"),
        ({"AWS_CONFIG_FILE": "path"}, "CredentialEnvironmentConflict"),
    ],
)
def test_credential_environment_conflicts(module, expected, environment, code):
    with pytest.raises(module.IdentityDiagnosticError, match=code):
        module.profile_gate(configuration(), environment, expected)


@pytest.mark.parametrize(
    "key", ["credential_process", "role_arn", "source_profile", "aws_access_key_id"]
)
def test_profile_provider_conflicts(module, expected, key):
    cfg = configuration()
    cfg["profiles"]["dev"][key] = "NEVER_SAVE"
    with pytest.raises(module.IdentityDiagnosticError, match="CredentialProviderConflict"):
        module.profile_gate(cfg, {}, expected)


class FakeSession:
    def __init__(self, response, error=None, operation="GetCallerIdentity", sends=1):
        self.response, self.error, self.operation, self.sends = response, error, operation, sends
        self.events = self
        self.hooks = {}
        self.calls = 0

    def register(self, event, callback):
        self.hooks[event] = callback

    def client(self, service, **kwargs):
        assert service == "sts"
        assert kwargs["config"].retries == {"total_max_attempts": 1}
        assert kwargs["endpoint_url"] == "https://sts.ap-northeast-1.amazonaws.com"
        return self

    def get_caller_identity(self):
        self.calls += 1
        self.hooks["before-call.*.*"](model=SimpleNamespace(name=self.operation))
        for _ in range(self.sends):
            self.hooks["before-send.*.*"]()
        if self.error:
            raise self.error
        return self.response


def run(module, tmp_path, expected, fake, changes=None):
    now = datetime(2026, 10, 11, tzinfo=UTC)
    cache(module, tmp_path, expected, now, changes)
    records = {}

    def record(name, value):
        assert name not in records
        records[name] = json.loads(json.dumps(value))

    def factory(**kwargs):
        assert set(kwargs) == {
            "region_name",
            "aws_access_key_id",
            "aws_secret_access_key",
            "aws_session_token",
        }
        return fake

    result = module.diagnose(expected, configuration(), {}, tmp_path, record, now, factory)
    assert "NEVER_SAVE" not in json.dumps(records)
    return result, records


def test_complete_safe_response_precedes_validation(module, tmp_path, expected):
    result, records = run(module, tmp_path, expected, FakeSession(actor(expected)))
    assert result["PASS"] and result["sts_invocations"] == result["http_sends"] == 1
    assert records["actor-response.private.json"]["RequestId"] == "request-id"
    assert records["actor-response.private.json"]["UserId"] == actor(expected)["UserId"]
    assert result["started_utc"] == "2026-10-11T00:00:00+00:00"
    assert result["started_jst"] == "2026-10-11T09:00:00+09:00"


def test_mismatch_still_preserves_actual_actor_and_exact_condition(module, tmp_path, expected):
    result, records = run(
        module, tmp_path, expected, FakeSession(actor(expected) | {"Account": "999999999999"})
    )
    assert not result["PASS"] and result["failed_condition"] == "ActorAccountMismatch"
    assert records["actor-response.private.json"]["Account"] == "999999999999"
    assert result["failure_frames"][-1]["function"] == "require"


@pytest.mark.parametrize("operation", ["CreateToken", "GetRoleCredentials", "PutObject", "GetRole"])
def test_additional_operations_are_blocked_before_http(module, tmp_path, expected, operation):
    result, _ = run(module, tmp_path, expected, FakeSession(actor(expected), operation=operation))
    assert result["failed_condition"] == "AdditionalAWSOperationForbidden"
    assert result["blocked_operations"] == [operation] and result["http_sends"] == 0


def test_no_automatic_second_send(module, tmp_path, expected):
    result, _ = run(module, tmp_path, expected, FakeSession(actor(expected), sends=2))
    assert result["failed_condition"] == "SecondHTTPSendForbidden" and result["http_sends"] == 1


def test_request_failure_is_distinct_and_message_is_not_logged(module, tmp_path, expected):
    from botocore.exceptions import ClientError

    error = ClientError(
        {
            "Error": {"Code": "ExpiredToken", "Message": "NEVER_SAVE"},
            "ResponseMetadata": {"RequestId": "error-request"},
        },
        "GetCallerIdentity",
    )
    result, _ = run(module, tmp_path, expected, FakeSession(None, error=error))
    assert (
        result["exception_type"] == "ClientError"
        and result["failed_condition"] == "AWSRequestFailed"
    )
    assert result["actor"]["RequestId"] == "error-request"


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"Expiration": "2026-10-10T00:00:00Z"}, "CachedCredentialsExpiredOrExpiring"),
        ({"Expiration": "2026-10-11T00:05:00Z"}, "CachedCredentialsExpiredOrExpiring"),
        ({"AccountId": "999999999999"}, "CacheAccountMismatch"),
        ({"SessionToken": None}, "CachedCredentialsIncomplete"),
        ({"Expiration": "bad"}, "CachedCredentialsMalformed"),
    ],
)
def test_bad_cache_blocks_session_creation(module, tmp_path, expected, changes, code):
    fake = FakeSession(actor(expected))
    result, records = run(module, tmp_path, expected, fake, changes)
    assert result["failed_condition"] == code and result["sts_invocations"] == fake.calls == 0
    assert "sts-started.private.json" not in records


def test_missing_cache_never_enters_provider_chain(module, tmp_path, expected):
    now = datetime(2026, 10, 11, tzinfo=UTC)
    records = {}

    def forbidden(**kwargs):
        pytest.fail("Missing cache entered credential provider chain")

    result = module.diagnose(
        expected, configuration(), {}, tmp_path, records.__setitem__, now, forbidden
    )
    assert (
        result["failed_condition"] == "CachedCredentialsUnavailable"
        and result["sts_invocations"] == 0
    )


def test_existing_journal_prevents_sts(module, tmp_path, expected):
    now = datetime(2026, 10, 11, tzinfo=UTC)
    cache(module, tmp_path, expected, now)
    records = {}

    def record(name, value):
        if name == "diagnostic-started.private.json":
            raise FileExistsError("NEVER_SAVE")
        records[name] = value

    def forbidden(**kwargs):
        pytest.fail("Existing journal allowed a second diagnostic")

    result = module.diagnose(expected, configuration(), {}, tmp_path, record, now, forbidden)
    assert result["sts_invocations"] == 0 and result["failed_condition"] == "LocalDiagnosticFailed"
    assert "NEVER_SAVE" not in json.dumps(records)


@pytest.mark.parametrize("metadata", [None, "NEVER_SAVE", {"RequestId": {"secret": "NEVER_SAVE"}}])
def test_malformed_exception_metadata_never_leaks_or_loses_result(
    module, tmp_path, expected, metadata
):
    error = RuntimeError("NEVER_SAVE")
    error.response = {"ResponseMetadata": metadata, "SecretAccessKey": "NEVER_SAVE"}
    result, records = run(module, tmp_path, expected, FakeSession(None, error=error))
    assert result["actor"]["RequestId"] is None
    assert records["diagnostic-result.private.json"]["exception_type"] == "RuntimeError"


@pytest.mark.parametrize("value", [[], {"Credentials": []}, {"Credentials": {"Expiration": None}}])
def test_malformed_cache_schema_is_diagnosed_locally(module, tmp_path, expected, value):
    now = datetime(2026, 10, 11, tzinfo=UTC)
    key = module.profile_gate(configuration(), {}, expected)
    (tmp_path / (key + ".json")).write_text(json.dumps(value))
    with pytest.raises(module.IdentityDiagnosticError, match="CachedCredentialsMalformed"):
        module.cached_credentials(tmp_path, key, expected["account_id"], now)
