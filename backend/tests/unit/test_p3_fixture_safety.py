"""Exercise P4 fixture lifecycle without creating an AWS client."""

from types import SimpleNamespace

import conftest
import pytest
from conftest import dynamodb_table

from interview_backend import deployment
from interview_backend.repositories import dynamodb


@pytest.fixture(autouse=True)
def offline_account_guard(monkeypatch):
    monkeypatch.setattr(conftest, "record_table", lambda *args: None)
    monkeypatch.setattr(deployment, "account_settings", lambda root: ("123456789012", "synthetic"))
    monkeypatch.setattr(deployment, "checked_session", lambda *args: None)


@pytest.mark.parametrize("missing", ["mode", "region", "prefix"])
def test_fixture_configuration_fails_without_client(monkeypatch, missing):
    monkeypatch.setenv("P4_AWS_EXECUTION_READY", "true")
    monkeypatch.setenv("INTERVIEW_TEST_MODE", "aws")
    monkeypatch.setenv("INTERVIEW_TEST_AWS_REGION", "synthetic")
    monkeypatch.setenv("INTERVIEW_TEST_TABLE_PREFIX", "interview-p3-test-synthetic")
    variable = {
        "mode": "INTERVIEW_TEST_MODE",
        "region": "INTERVIEW_TEST_AWS_REGION",
        "prefix": "INTERVIEW_TEST_TABLE_PREFIX",
    }[missing]
    monkeypatch.delenv(variable)
    monkeypatch.setattr(dynamodb, "client_for", lambda _: pytest.fail("unexpected client"))
    with pytest.raises(pytest.fail.Exception):
        next(dynamodb_table.__wrapped__())


@pytest.mark.parametrize("failure", [None, "connect", "create", "wait", "body", "delete"])
def test_fixture_deletes_only_confirmed_created_table(monkeypatch, failure):
    monkeypatch.setenv("P4_AWS_EXECUTION_READY", "true")
    monkeypatch.setenv("INTERVIEW_TEST_MODE", "aws")
    monkeypatch.setenv("INTERVIEW_TEST_AWS_REGION", "synthetic")
    monkeypatch.setenv("INTERVIEW_TEST_TABLE_PREFIX", "interview-p3-test-synthetic")
    calls = []

    def operation(stage, request):
        calls.append((stage, request))
        if stage == failure:
            raise RuntimeError(stage)

    client = SimpleNamespace(
        create_table=lambda **r: operation("create", r),
        delete_table=lambda **r: operation("delete", r),
        get_waiter=lambda _: SimpleNamespace(wait=lambda **r: operation("wait", r)),
    )

    def connect(_):
        operation("connect", {})
        return client

    monkeypatch.setattr(dynamodb, "client_for", connect)
    fixture = dynamodb_table.__wrapped__()
    if failure in {"connect", "create", "wait"}:
        with pytest.raises(RuntimeError, match=failure):
            next(fixture)
    else:
        _, name = next(fixture)
        assert name.startswith("interview-p3-test-synthetic-")
        assert len(name.rsplit("-", 1)[1]) == 32
        if failure == "body":
            with pytest.raises(RuntimeError, match="body"):
                fixture.throw(RuntimeError("body"))
        elif failure == "delete":
            with pytest.raises(RuntimeError, match="delete"):
                fixture.close()
        else:
            fixture.close()
    deletes = [r for stage, r in calls if stage == "delete"]
    creates = [r for stage, r in calls if stage == "create"]
    assert len(deletes) == (0 if failure in {"connect", "create"} else 1)
    if deletes:
        assert deletes[0]["TableName"] == creates[0]["TableName"]
