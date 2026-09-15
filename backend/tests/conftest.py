"""Fresh deterministic runtime per test, with no external services."""

import json
import os
import socket
from datetime import UTC, datetime
from itertools import count
from pathlib import Path
from uuid import uuid4

import pytest

from interview_backend.bootstrap import build_runtime


@pytest.fixture(autouse=True)
def offline_boundary(request, monkeypatch):
    if request.node.get_closest_marker("dynamodb") or request.node.get_closest_marker("aws_e2e"):
        return
    import boto3.session
    import botocore.httpsession

    original_client = boto3.session.Session.client

    def forbidden(*args, **kwargs):
        pytest.fail("OfflineBoundaryViolation")

    def stub_client(session, *args, **kwargs):
        # Existing botocore Stubber tests validate SDK request shapes offline.
        if (
            kwargs.get("aws_access_key_id") != "synthetic"
            or kwargs.get("aws_secret_access_key") != "synthetic"
        ):
            forbidden()
        return original_client(session, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(botocore.httpsession.URLLib3Session, "send", forbidden)
    monkeypatch.setattr(boto3.session.Session, "client", stub_client)


def record_table(name, stage):
    """Durable local run journal; never infer creation from a lost SDK response."""
    path = Path(os.environ.get("INTERVIEW_TEST_MANIFEST", "")).resolve()
    private = (Path(__file__).resolve().parents[2] / ".p4-artifacts").resolve()
    if not path.is_relative_to(private) or not path.parent.is_dir():
        raise ValueError("ExplicitPrivateTestManifestRequired")
    if stage not in {"attempted", "created", "deleted", "cleanup_failed"}:
        raise ValueError("InvalidTestLifecycle")
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"table_name": name, "stage": stage}) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def uid(number: int) -> str:
    return f"10000000-0000-4000-8000-{number:012d}"


@pytest.fixture
def runtime():
    ids = count(1)
    return build_runtime(
        new_id=lambda: uid(next(ids)), clock=lambda: datetime(2026, 9, 11, tzinfo=UTC)
    )


@pytest.fixture
def dynamodb_table():
    """Explicit P4-only fixture. Delete only the unique table this fixture created."""
    from interview_backend.deployment import require_aws_execution
    from interview_backend.repositories.dynamodb import client_for, table_definition

    require_aws_execution()

    if os.environ.get("INTERVIEW_TEST_MODE") != "aws":
        pytest.fail("Set INTERVIEW_TEST_MODE=aws explicitly for DynamoDB tests")
    region = os.environ.get("INTERVIEW_TEST_AWS_REGION")
    prefix = os.environ.get("INTERVIEW_TEST_TABLE_PREFIX")
    if not region or not prefix or not prefix.startswith("interview-p3-test-"):
        pytest.fail("Set AWS region and INTERVIEW_TEST_TABLE_PREFIX=interview-p3-test-<label>")
    name = f"{prefix}-{uuid4().hex}"
    from interview_backend.deployment import account_settings, checked_session

    account, guarded_region = account_settings(Path(__file__).resolve().parents[2])
    if region != guarded_region:
        pytest.fail("DynamoDB test region must match the guarded dev region")
    checked_session(account, guarded_region)
    record_table(name, "attempted")
    client = client_for(region)
    created = False
    try:
        client.create_table(**table_definition(name))
        created = True
        record_table(name, "created")
        client.get_waiter("table_exists").wait(
            TableName=name, WaiterConfig={"Delay": 1, "MaxAttempts": 60}
        )
        yield region, name
    finally:
        if created:
            try:
                checked_session(account, guarded_region)
                client.delete_table(TableName=name)
                client.get_waiter("table_not_exists").wait(
                    TableName=name, WaiterConfig={"Delay": 1, "MaxAttempts": 60}
                )
                record_table(name, "deleted")
            except Exception:
                record_table(name, "cleanup_failed")
                raise


@pytest.fixture(params=["memory", pytest.param("dynamodb", marks=pytest.mark.dynamodb)])
def contract_runtime(request):
    ids = count(1)
    repository = None
    if request.param == "dynamodb":
        from interview_backend.repositories.dynamodb import DynamoDBRepository, client_for

        region, name = request.getfixturevalue("dynamodb_table")
        repository = DynamoDBRepository(client_for(region), name, lambda: 1789084800000)
    return build_runtime(
        new_id=lambda: uid(next(ids)),
        clock=lambda: datetime(2026, 9, 11, tzinfo=UTC),
        repository=repository,
    )
