"""Offline approval claims are never an authenticated execution approval."""

import base64
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from test_p4_tools import tool


@pytest.fixture
def sample():
    m = tool("candidate_approval_contract")
    now = datetime(2026, 10, 25, 10, 0, tzinfo=UTC)
    expected = {
        "operation": "maintenance-apply",
        "namespace": m.preflight.NAMESPACE,
        "source_sha": "a" * 40,
        "git_tree_sha": "b" * 40,
        "terraform_sources_sha256": "c" * 64,
        "terraform_version": "1.16.7",
        "terraform_sha256": "d" * 64,
        "provider_version": "6.70.0",
        "platform": "linux_amd64",
        "configuration_sha256": "e" * 64,
        "lock_sha256": "f" * 64,
        "plan_sha256": "0" * 64,
        "state_identity": {
            "lineage": "synthetic",
            "serial": 7,
            "version_id": "synthetic-version",
            "sha256": "1" * 64,
        },
        "approval_id": "2" * 40,
        "attempt_id": "3" * 40,
    }
    claim = {
        **deepcopy(expected),
        "schema_version": 3,
        "kind": "p4-bootstrap-candidate-approval-claim-v3",
        "issued_at": (now - timedelta(minutes=10)).isoformat(),
        "expires_at": (now + timedelta(minutes=20)).isoformat(),
        "signature_claim": {
            "issuer": "claimed-issuer",
            "key_id": "claimed-key",
            "algorithm": "ed25519",
            "signature": base64.b64encode(b"x" * 64).decode(),
        },
    }
    return m, now, expected, claim


def test_valid_syntax_is_unverified_and_not_authorized(sample):
    m, now, expected, claim = sample
    result = m.validate_approval(claim, expected, now=now)
    assert result["contract_consistent"] is True
    assert result["signature_verified"] is False
    assert result["approval_authenticity"] == "UNVERIFIED"
    assert result["authorized"] is False
    assert result["aws_operations"] == 0


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema_version", 2),
        ("schema_version", True),
        ("kind", "legacy"),
        ("operation", "recovery-apply"),
        ("namespace", "legacy"),
        ("source_sha", "9" * 40),
        ("git_tree_sha", "9" * 40),
        ("terraform_sources_sha256", "9" * 64),
        ("terraform_version", "1.14.9"),
        ("terraform_version", "1.17.0"),
        ("terraform_sha256", "9" * 64),
        ("provider_version", "6.64.0"),
        ("platform", "windows_amd64"),
        ("configuration_sha256", "9" * 64),
        ("lock_sha256", "9" * 64),
        ("plan_sha256", "9" * 64),
        ("approval_id", "9" * 40),
        ("attempt_id", "9" * 40),
        ("attempt_id", None),
    ],
)
def test_cross_contract_mismatch_fail_closed(sample, key, value):
    m, now, expected, claim = sample
    claim[key] = value
    with pytest.raises(ValueError):
        m.validate_approval(claim, expected, now=now)


@pytest.mark.parametrize(
    "key,value",
    [
        ("serial", 8),
        ("serial", True),
        ("lineage", "wrong"),
        ("sha256", "9" * 64),
        ("version_id", "different"),
    ],
)
def test_state_identity_target_is_exact(sample, key, value):
    m, now, expected, claim = sample
    claim["state_identity"][key] = value
    with pytest.raises(ValueError):
        m.validate_approval(claim, expected, now=now)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-field",
        "unknown-field",
        "old-schema",
        "unknown-evidence",
        "missing-evidence",
        "bad-algorithm",
        "bad-signature",
        "invalid-json-type",
    ],
)
def test_missing_unknown_or_unauthenticated_claim_evidence_rejected(sample, mutation):
    m, now, expected, claim = sample
    if mutation == "missing-field":
        del claim["approval_id"]
    elif mutation == "unknown-field":
        claim["authorized"] = True
    elif mutation == "old-schema":
        claim["schema_version"] = 1
    elif mutation == "unknown-evidence":
        claim["signature_claim"]["verified"] = True
    elif mutation == "missing-evidence":
        del claim["signature_claim"]["signature"]
    elif mutation == "bad-algorithm":
        claim["signature_claim"]["algorithm"] = "none"
    elif mutation == "bad-signature":
        claim["signature_claim"]["signature"] = "invalid"
    elif mutation == "invalid-json-type":
        claim["signature_claim"] = []
    with pytest.raises(ValueError):
        m.validate_approval(claim, expected, now=now)


@pytest.mark.parametrize(
    "mutation",
    [
        "expired",
        "future",
        "long-ttl",
        "naive",
        "unknown-offset",
        "bad-type",
        "zero-ttl",
        "naive-clock",
    ],
)
def test_expiry_future_and_malformed_timestamps_rejected(sample, mutation):
    m, now, expected, claim = sample
    if mutation == "expired":
        claim["expires_at"] = now.isoformat()
    elif mutation == "future":
        claim["issued_at"] = (now + timedelta(seconds=1)).isoformat()
    elif mutation == "long-ttl":
        claim["expires_at"] = (now + timedelta(hours=2)).isoformat()
    elif mutation == "naive":
        claim["issued_at"] = "2026-10-25T09:50:00"
    elif mutation == "unknown-offset":
        claim["issued_at"] = "2026-10-25T09:50:00-00:00"
    elif mutation == "bad-type":
        claim["expires_at"] = True
    elif mutation == "zero-ttl":
        claim["expires_at"] = claim["issued_at"]
    elif mutation == "naive-clock":
        now = now.replace(tzinfo=None)
    with pytest.raises(ValueError):
        m.validate_approval(claim, expected, now=now)


def test_apply_and_plan_approval_targets_are_distinct(sample):
    m, now, expected, claim = sample
    expected["plan_sha256"] = None
    with pytest.raises(ValueError):
        m.validate_approval(claim, expected, now=now)
    expected["operation"] = "maintenance-plan"
    claim["operation"] = "maintenance-plan"
    claim["plan_sha256"] = None
    assert m.validate_approval(claim, expected, now=now)["authorized"] is False


def test_caller_forges_both_sides_but_still_never_authenticates(sample):
    m, now, expected, claim = sample
    expected["source_sha"] = "9" * 40
    claim["source_sha"] = "9" * 40
    assert m.validate_approval(claim, expected, now=now)["signature_verified"] is False
