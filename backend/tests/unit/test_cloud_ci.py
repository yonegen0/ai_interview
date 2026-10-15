"""Cloud parent binding and private runner qualification, without AWS."""

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_p4_tools import tool


def parent():
    return {
        "schema": 1,
        "profile": "hosted-linux-plan-only-v1",
        "execution_ready": True,
        "apply": False,
        "issued_at_utc": "2026-10-14T12:00:00Z",
        "expires_at_utc": "2026-10-17T12:00:00Z",
        "repository": "yonegen0/ai_interview",
        "account_id": "835384817629",
        "region": "ap-northeast-1",
        "source_tree": "b" * 40,
        "base_commit": "4a31727a7c2eb361c0e9609bf4e51be00524547a",
        "plan_max": 1,
        "dispatch_max": 1,
        "run_attempt": 1,
        "artifact_sha256": "cc067d535699792204e4ec038b45a19b0d018536355a49b4e0f8ce4377a8ef6d",
        "s3_put_max": 6,
        "sdk_request_max": 1500,
        "oidc_sts_each": {"plan": 1, "artifact": 1},
        "role_duration_seconds": 3600,
        "limited_existing_role_profile_accepted": True,
        "bootstrap_namespace_history_unconfirmed_accepted": True,
        "linux_private_profile_accepted": True,
        "v6_historical_risk_accepted": True,
        "mode": "B",
        "hard_billing_cap_guaranteed": False,
    }


def environment():
    return {
        "GITHUB_REPOSITORY": "yonegen0/ai_interview",
        "GITHUB_REPOSITORY_ID": "1361325921",
        "GITHUB_REPOSITORY_OWNER_ID": "76547980",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_ACTOR_ID": "76547980",
        "GITHUB_ACTOR": "yonegen0",
        "GITHUB_RUN_ID": "123",
        "GITHUB_SHA": "a" * 40,
        "AWS_DEV_ACCOUNT_ID": "835384817629",
        "AWS_REGION": "ap-northeast-1",
        "P4_AWS_EXECUTION_READY": "true",
        "P4_OIDC_SUBJECT": "repo:yonegen0@76547980/ai_interview@1361325921:environment:dev",
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("apply", True),
        ("execution_ready", False),
        ("plan_max", 2),
        ("dispatch_max", 2),
        ("run_attempt", 2),
        ("sdk_request_max", 1501),
        ("role_duration_seconds", 7200),
        ("linux_private_profile_accepted", False),
        ("v6_historical_risk_accepted", False),
        ("source_tree", "c" * 40),
        ("account_id", "123456789012"),
        ("expires_at_utc", "2026-10-18T12:00:00Z"),
    ],
)
def test_parent_rejects_expanded_or_changed_binding(field, value):
    m = tool("cloud_ci")
    p = parent()
    p[field] = value
    raw = json.dumps(p)
    with pytest.raises(ValueError):
        m.validate_parent(
            raw,
            hashlib.sha256(raw.encode()).hexdigest(),
            environment(),
            "b" * 40,
            datetime(2026, 10, 14, 13, tzinfo=UTC),
        )


def test_parent_accepts_exact_scope():
    m = tool("cloud_ci")
    p = parent()
    raw = json.dumps(p)
    assert (
        m.validate_parent(
            raw,
            hashlib.sha256(raw.encode()).hexdigest(),
            environment(),
            "b" * 40,
            datetime(2026, 10, 14, 13, tzinfo=UTC),
        )
        == p
    )


@pytest.mark.skipif(
    sys.platform != "linux", reason="actual POSIX controls require Linux; mandatory before OIDC"
)
def test_private_modes_and_nofollow(tmp_path):
    m = tool("cloud_private")
    result = m.qualify(tmp_path)
    assert (
        result["posix_modes"] and result["no_follow"] and result["rename_same_uid"] == "permitted"
    )


@pytest.mark.skipif(
    sys.platform != "linux",
    reason="actual seccomp qualification requires Linux; mandatory before OIDC",
)
def test_credential_free_independent_audit_network_filter():
    path = Path(__file__).resolve().parents[2] / "skills/p4/cloud_independent_audit.py"
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("AWS_", "ACTIONS_", "GH_", "P4_", "GITHUB_", "TF_"))
    }
    result = subprocess.run(
        [sys.executable, str(path), "--qualification"], env=env, capture_output=True, timeout=15
    )
    assert result.returncode == 0


def test_static_role_cache_and_credential_budget(monkeypatch):
    monkeypatch.setattr(os, "environ", os.environ.copy())
    from datetime import timedelta
    from types import SimpleNamespace

    module = tool("cloud_ci")
    module.PARENT = parent()
    events = []
    calls = []
    credential = SimpleNamespace(access_key="synthetic", secret_key="synthetic", token="synthetic")
    session = SimpleNamespace(
        p4_expiration=datetime.now(UTC) + timedelta(minutes=45),
        events=SimpleNamespace(register=lambda name, fn: events.append((name, fn))),
        get_credentials=lambda: SimpleNamespace(get_frozen_credentials=lambda: credential),
    )
    monkeypatch.setitem(
        sys.modules,
        "ci_identity",
        SimpleNamespace(assume=lambda *a, **k: calls.append(a) or session),
    )
    monkeypatch.setenv("P4_OIDC_SUBJECT", environment()["P4_OIDC_SUBJECT"])
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    assert module.session("plan", "835384817629", "ap-northeast-1", 1920) is session
    assert module.session("plan", "835384817629", "ap-northeast-1", 1500) is session
    assert len(calls) == 1 and module.WIRE_COUNT == 1 and len(events) == 1
    with pytest.raises(ValueError, match="CredentialsExpiring"):
        module.session("plan", "835384817629", "ap-northeast-1", 3600)
    assert len(calls) == 1


def test_static_role_cache_restores_credential_environment(monkeypatch):
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    before = dict(os.environ)
    with monkeypatch.context() as isolated:
        test_static_role_cache_and_credential_budget(isolated)
    assert dict(os.environ) == before
