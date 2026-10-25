"""v4 signature and independent trust-policy regression tests. Synthetic keys only."""

import base64
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from test_p4_tools import tool


@pytest.fixture
def sample():
    m = tool("candidate_signed_approval")
    now = datetime(2026, 10, 25, 10, tzinfo=UTC)
    claim = {
        "schema_version": 4,
        "kind": m.KIND,
        "namespace": m.preflight.NAMESPACE,
        "issuer": "test-issuer",
        "key_id": "test-key",
        "algorithm": "ed25519",
        "trust_revision": "1" * 64,
        "operation": "maintenance-apply",
        "source_sha": "a" * 40,
        "git_tree_sha": "b" * 40,
        "terraform_sources_sha256": "c" * 64,
        "configuration_sha256": "d" * 64,
        "lock_sha256": "e" * 64,
        "terraform_version": m.preflight.CLI,
        "terraform_sha256": "f" * 64,
        "provider_version": m.preflight.PROVIDER,
        "provider_inventory_sha256": "0" * 64,
        "platform": m.preflight.PLATFORM,
        "state_identity": {
            "lineage": "synthetic",
            "serial": 7,
            "version_id": "synthetic-v1",
            "sha256": "2" * 64,
        },
        "plan_sha256": "3" * 64,
        "approval_id": "4" * 40,
        "attempt_id": "5" * 40,
        "issued_at": "2026-10-25T09:50:00Z",
        "expires_at": "2026-10-25T10:10:00Z",
        "account_id": "123456789012",
        "region": "ap-northeast-1",
        "resource_scope": "bootstrap",
        "max_execution_seconds": 120,
        "max_cost_usd_cents": 0,
    }
    expected = {k: deepcopy(claim[k]) for k in m.TARGET_FIELDS}
    envelope = claim | {"signature": base64.b64encode(b"x" * 64).decode("ascii")}
    return m, now, claim, expected, envelope


def as_json(value):
    return json.dumps(value, sort_keys=True).encode()


def registry(m, claim, now, public_key=b"\x01" * 32, **changes):
    return {
        claim["key_id"]: m.TrustedKey(
            issuer=claim["issuer"],
            public_key=public_key,
            operations=frozenset({claim["operation"]}),
            namespace=claim["namespace"],
            trust_revision=claim["trust_revision"],
            not_before=now - timedelta(hours=1),
            not_after=now + timedelta(hours=1),
            **changes,
        )
    }


def test_no_enrolled_key_is_unverified_hold(sample):
    m, now, _, expected, envelope = sample
    result = m.verify_signed_approval(as_json(envelope), expected, trust_registry={}, now=now)
    assert result["status"] == "UNVERIFIED_HOLD"
    assert result["signature_verified"] is False
    assert result["authorized"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 3),
        ("schema_version", True),
        ("kind", "legacy"),
        ("namespace", "legacy"),
        ("operation", "recovery-apply"),
        ("source_sha", "9" * 40),
        ("git_tree_sha", "9" * 40),
        ("terraform_sources_sha256", "9" * 64),
        ("configuration_sha256", "9" * 64),
        ("lock_sha256", "9" * 64),
        ("terraform_version", "1.14.9"),
        ("terraform_sha256", "9" * 64),
        ("provider_version", "6.64.0"),
        ("provider_inventory_sha256", "9" * 64),
        ("platform", "windows_amd64"),
        ("plan_sha256", "9" * 64),
        ("approval_id", "9" * 40),
        ("attempt_id", "9" * 40),
        ("account_id", "000000000000"),
        ("region", "us-east-1"),
        ("resource_scope", "other"),
        ("max_execution_seconds", True),
        ("max_cost_usd_cents", 1.0),
    ],
)
def test_binding_mismatches_fail_closed(sample, field, value):
    m, now, _, expected, envelope = sample
    envelope[field] = value
    with pytest.raises(ValueError):
        m.verify_signed_approval(as_json(envelope), expected, trust_registry={}, now=now)


@pytest.mark.parametrize(
    "field,value",
    [
        ("serial", True),
        ("serial", 7.0),
        ("serial", 8),
        ("lineage", "other"),
        ("version_id", "changed"),
        ("sha256", "0" * 64),
    ],
)
def test_state_identity_rejects_cross_target(sample, field, value):
    m, now, _, expected, envelope = sample
    envelope["state_identity"][field] = value
    with pytest.raises(ValueError):
        m.verify_signed_approval(as_json(envelope), expected, trust_registry={}, now=now)


@pytest.mark.parametrize(
    "field,value",
    [
        ("issuer", ""),
        ("key_id", ""),
        ("algorithm", "none"),
        ("trust_revision", "other"),
        ("issued_at", "2026-10-25T10:01:00Z"),
        ("expires_at", "2026-10-25T10:00:00Z"),
        ("expires_at", "2026-10-25T12:00:00Z"),
        ("issued_at", "2026-10-25T09:50:00+00:00"),
    ],
)
def test_signature_policy_and_timing_fails_closed(sample, field, value):
    m, now, _, expected, envelope = sample
    envelope[field] = value
    if field == "issuer":
        with pytest.raises(ValueError):
            m.verify_signed_approval(as_json(envelope), expected, trust_registry={}, now=now)
    elif field == "key_id":
        with pytest.raises(ValueError):
            m.verify_signed_approval(as_json(envelope), expected, trust_registry={}, now=now)
    elif field == "trust_revision":
        with pytest.raises(ValueError):
            m.verify_signed_approval(as_json(envelope), expected, trust_registry={}, now=now)
    else:
        with pytest.raises(ValueError):
            m.verify_signed_approval(as_json(envelope), expected, trust_registry={}, now=now)


@pytest.mark.parametrize(
    "mutation",
    ["extra", "missing", "signature-b64", "signature-padding", "duplicate", "float", "nan"],
)
def test_strict_json_and_signature_envelope(sample, mutation):
    m, now, _, expected, envelope = sample
    if mutation == "extra":
        envelope["new_field"] = True
    elif mutation == "missing":
        del envelope["approval_id"]
    elif mutation == "signature-b64":
        envelope["signature"] = "!!!"
    elif mutation == "signature-padding":
        envelope["signature"] = envelope["signature"][:-1] + "A"
    raw = as_json(envelope)
    if mutation == "duplicate":
        raw = raw[:-1] + b',"issuer":"duplicate"}'
    elif mutation == "float":
        raw = raw.replace(b'"max_execution_seconds": 120', b'"max_execution_seconds": 120.0')
    elif mutation == "nan":
        raw = raw.replace(b'"max_execution_seconds": 120', b'"max_execution_seconds": NaN')
    with pytest.raises(ValueError):
        m.verify_signed_approval(raw, expected, trust_registry={}, now=now)


def test_canonical_signed_bytes_differ_across_source_and_namespace(sample):
    m, _, claim, _, _ = sample
    original = m.signed_bytes(claim)
    changed = deepcopy(claim)
    changed["source_sha"] = "9" * 40
    assert m.signed_bytes(changed) != original
    assert original.startswith(m.DOMAIN)
    assert b"signature" not in m.canonical_payload(claim)


def test_plan_operation_requires_null_plan_hash(sample):
    m, now, claim, _, envelope = sample
    claim["operation"] = envelope["operation"] = "maintenance-plan"
    expected = {k: deepcopy(claim[k]) for k in m.TARGET_FIELDS}
    with pytest.raises(ValueError):
        m.verify_signed_approval(as_json(envelope), expected, trust_registry={}, now=now)
    envelope["plan_sha256"] = expected["plan_sha256"] = None
    assert (
        m.verify_signed_approval(as_json(envelope), expected, trust_registry={}, now=now)[
            "authorized"
        ]
        is False
    )


def test_wrong_key_issuer_policy_revocation_and_missing_key(sample):
    m, now, claim, expected, envelope = sample
    for mapping in (
        {"unknown": registry(m, claim, now)[claim["key_id"]]},
        registry(m, claim, now, public_key=b"\x01" * 31),
        {
            claim["key_id"]: m.TrustedKey(
                "another-issuer",
                b"\x01" * 32,
                frozenset({"maintenance-apply"}),
                claim["namespace"],
                claim["trust_revision"],
                now - timedelta(hours=1),
                now + timedelta(hours=1),
            )
        },
        {
            claim["key_id"]: m.TrustedKey(
                claim["issuer"],
                b"\x01" * 32,
                frozenset({"recovery-plan"}),
                claim["namespace"],
                claim["trust_revision"],
                now - timedelta(hours=1),
                now + timedelta(hours=1),
            )
        },
        {
            claim["key_id"]: m.TrustedKey(
                claim["issuer"],
                b"\x01" * 32,
                frozenset({"maintenance-apply"}),
                claim["namespace"],
                claim["trust_revision"],
                now - timedelta(hours=1),
                now + timedelta(hours=1),
                revoked=True,
            )
        },
    ):
        with pytest.raises(ValueError):
            m.verify_signed_approval(as_json(envelope), expected, trust_registry=mapping, now=now)


def test_real_ed25519_signature_or_crypto_dependency_fail_closed(sample):
    """CI lacking the optional crypto dependency must explicitly HOLD, never bypass."""
    m, now, claim, expected, envelope = sample
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:
        with pytest.raises(ValueError, match="CryptoDependencyMissingHOLD"):
            m.verify_signed_approval(
                as_json(envelope), expected, trust_registry=registry(m, claim, now), now=now
            )
        return

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    envelope["signature"] = base64.b64encode(private.sign(m.signed_bytes(claim))).decode()
    enrolled = registry(m, claim, now, public_key=public)
    assert m.verify_signed_approval(
        as_json(envelope), expected, trust_registry=enrolled, now=now
    ) == {
        "status": "LOCAL_SIGNATURE_VERIFIED_ENROLLMENT_UNVERIFIED_HOLD",
        "signature_verified": True,
        "trusted_key_policy_matched": True,
        "trust_enrollment_authenticated": False,
        "clock_authenticated": False,
        "origin_authenticated": False,
        "state_readback_verified": False,
        "authorized": False,
        "aws_operations": 0,
    }
    for mutation in ("message", "signature", "different-public-key"):
        forged = deepcopy(envelope)
        trust = enrolled
        if mutation == "message":
            forged["source_sha"] = "9" * 40
            target = {k: deepcopy(forged[k]) for k in m.TARGET_FIELDS}
        else:
            target = expected
        if mutation == "signature":
            forged["signature"] = base64.b64encode(b"\x00" * 64).decode()
        elif mutation == "different-public-key":
            second = Ed25519PrivateKey.generate()
            trust = registry(
                m,
                claim,
                now,
                public_key=second.public_key().public_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PublicFormat.Raw,
                ),
            )
        with pytest.raises(ValueError, match="BadSignatureHOLD"):
            m.verify_signed_approval(as_json(forged), target, trust_registry=trust, now=now)


def test_no_network_or_process_in_pure_contract(sample, monkeypatch):
    import socket
    import subprocess

    def forbidden(*args, **kwargs):
        raise AssertionError("External side effect forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    m, now, _, expected, envelope = sample
    assert (
        m.verify_signed_approval(as_json(envelope), expected, trust_registry={}, now=now)[
            "authorized"
        ]
        is False
    )


def test_unhashable_operation_rejected_with_value_error(sample):
    m, now, _, expected, envelope = sample
    envelope["operation"] = {"unexpected": "dict"}
    with pytest.raises(ValueError, match="BindingInvalid"):
        m.verify_signed_approval(as_json(envelope), expected, trust_registry={}, now=now)


def test_recursive_direct_payload_fails_closed(sample):
    m, _, claim, _, _ = sample
    claim["state_identity"]["lineage"] = claim["state_identity"]
    with pytest.raises(ValueError, match="CanonicalInvalid"):
        m.canonical_payload(claim)


def test_canonical_json_stable_for_field_order_and_escape(sample):
    m, _, claim, _, _ = sample
    original = m.canonical_payload(claim)
    assert original == m.canonical_payload(dict(reversed(list(claim.items()))))
    escaped = deepcopy(claim)
    escaped["state_identity"]["lineage"] = 'quote" and backslash\\'
    encoded = m.canonical_payload(escaped)
    assert json.loads(encoded)["state_identity"]["lineage"] == escaped["state_identity"]["lineage"]
    assert encoded != original
    escaped["state_identity"]["lineage"] = "\u00e9"
    with pytest.raises(ValueError, match="AsciiOnly"):
        m.canonical_payload(escaped)


def test_recursive_expected_state_fails_closed(sample):
    m, now, _, expected, envelope = sample
    expected["state_identity"]["lineage"] = expected["state_identity"]
    with pytest.raises(ValueError, match="CandidateStateIdentityInvalid"):
        m.verify_signed_approval(as_json(envelope), expected, trust_registry={}, now=now)


def test_key_valid_now_but_not_at_issuance_is_rejected(sample):
    """A key enrolled after issuance cannot retroactively validate the approval."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    m, now, claim, expected, envelope = sample
    private = Ed25519PrivateKey.generate()
    envelope["signature"] = base64.b64encode(private.sign(m.signed_bytes(claim))).decode()
    # The key is active now but was not active at claim["issued_at"] (09:50).
    key = m.TrustedKey(
        issuer=claim["issuer"],
        public_key=private.public_key().public_bytes_raw(),
        operations=frozenset({claim["operation"]}),
        namespace=claim["namespace"],
        trust_revision=claim["trust_revision"],
        not_before=now - timedelta(minutes=5),
        not_after=now + timedelta(minutes=5),
    )
    with pytest.raises(ValueError, match="CandidateSignedApprovalKeyPolicyHOLD"):
        m.verify_signed_approval(
            as_json(envelope), expected, trust_registry={claim["key_id"]: key}, now=now
        )
