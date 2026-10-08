"""Offline lifecycle gates; callback fixtures never contact AWS."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from test_provider_validation_tools import tool


def inputs(tmp_path):
    manifest = {
        "account_id": "111111111111",
        "region": "ap-northeast-1",
        "environment": "dev",
        "configuration": dict.fromkeys(
            ("api_enabled", "worker_enabled", "streams_enabled", "scheduler_enabled"), True
        ),
    }
    raw_manifest = json.dumps(manifest).encode()
    source = Path(__file__)
    callbacks = dict.fromkeys(("audit", "authenticate", "close"), source)
    approval = {
        "live_authorized": True,
        "conditional_closure_authorized": True,
        "enablement_succeeded": True,
        "run_id": "offline-binding",
        "account_id": manifest["account_id"],
        "region": manifest["region"],
        "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "subjects": {"USER_A": "a", "USER_B": "b", "ADMIN": "c"},
        "provider": "fake",
        "expected_rounds": 0,
        "admin_writes": False,
        "callback_sha256": dict.fromkeys(
            callbacks, hashlib.sha256(source.read_bytes()).hexdigest()
        ),
    }
    return approval, raw_manifest, callbacks


@pytest.mark.parametrize(
    "bad", ["hash", "closure", "subject", "callback", "paid", "window", "manifest", "rounds"]
)
def test_invalid_binding_prevents_callbacks(tmp_path, bad):
    binding = tool("coaching_binding")
    approval, manifest, callbacks = inputs(tmp_path)
    if bad == "closure":
        approval["conditional_closure_authorized"] = False
    elif bad == "subject":
        approval["subjects"]["USER_B"] = "a"
    elif bad == "callback":
        approval["callback_sha256"]["close"] = "0" * 64
    elif bad == "paid":
        approval["provider"] = "openai"
    elif bad == "window":
        approval["admin_writes"] = True
    elif bad == "manifest":
        manifest += b" "
    elif bad == "rounds":
        approval["expected_rounds"] = True
    raw = json.dumps(approval).encode()
    digest = "0" * 64 if bad == "hash" else hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        binding.approval_binding(
            raw,
            digest,
            manifest,
            run_id=approval["run_id"],
            account=approval["account_id"],
            callbacks=callbacks,
        )


def test_auth_failure_closes_and_journal_blocks_replay(tmp_path):
    binding = tool("coaching_binding")
    approval, manifest, callbacks = inputs(tmp_path)
    raw = json.dumps(approval).encode()
    calls = []

    def audit(*args):
        return True

    def authenticate(*args):
        raise ValueError("SyntheticAuthenticationFailure")

    def close(*args):
        calls.append("close")
        return {
            "status": "CLOSED_READBACK_VERIFIED",
            "api_disabled": True,
            "worker_disabled": True,
            "streams_disabled": True,
            "scheduler_disabled": True,
            "validation_alarm_count": 0,
            "active_lock": False,
            "state_outside_dev_resources": 0,
        }

    path = Path(__file__).parents[2] / ".p4-artifacts" / ("binding-test-" + str(uuid4()) + ".jsonl")
    kwargs = dict(
        run_id=approval["run_id"],
        account=approval["account_id"],
        callbacks=callbacks,
        audit=audit,
        authenticate=authenticate,
        close=close,
    )
    with pytest.raises(ValueError, match="SyntheticAuthenticationFailure"):
        binding.execute_bound(raw, hashlib.sha256(raw).hexdigest(), manifest, path, **kwargs)
    assert calls == ["close"]
    assert "closed-readback" in path.read_text()
    with pytest.raises(FileExistsError):
        binding.execute_bound(raw, hashlib.sha256(raw).hexdigest(), manifest, path, **kwargs)
    assert calls == ["close"]


def test_unsafe_audit_stops_without_auth_or_closure(tmp_path):
    binding = tool("coaching_binding")
    approval, manifest, callbacks = inputs(tmp_path)
    raw = json.dumps(approval).encode()

    def audit(*args):
        return False

    def forbidden(*args):
        pytest.fail("Unsafe audit must stop")

    with pytest.raises(ValueError, match="SafeSuccessfulEnablementAuditRequired"):
        binding.execute_bound(
            raw,
            hashlib.sha256(raw).hexdigest(),
            manifest,
            tmp_path / "journal",
            run_id=approval["run_id"],
            account=approval["account_id"],
            callbacks=callbacks,
            audit=audit,
            authenticate=forbidden,
            close=forbidden,
        )


def test_cleanup_reads_only_journal_keys_and_retains_usage():
    binding = tool("coaching_binding")
    seen = []
    rows = [{"session_id": "s", "evaluation_id": "e"}, {"session_id": "s"}]

    def read(key):
        seen.append(key)
        return key

    assert binding.cleanup_candidates(rows, "a", read) == seen
    assert len(seen) == 2
    assert all(k["PK"] == "USER#a" and "PROVIDER_USAGE" not in k["SK"] for k in seen)
    with pytest.raises(ValueError, match="CleanupExactKeyMismatch"):
        binding.cleanup_candidates(rows, "a", lambda key: key | {"PK": "USER#other"})
