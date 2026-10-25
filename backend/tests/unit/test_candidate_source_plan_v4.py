"""Source-to-Plan v4 rejects cross-operation and stale or forged claims."""

import hashlib
from copy import deepcopy

import pytest
from test_p4_tools import tool


@pytest.fixture
def sample():
    m = tool("candidate_source_plan_v4")
    s = m.signed
    raw = b"synthetic bytes not produced by Terraform"
    claim = {
        "schema_version": 4,
        "kind": m.KIND,
        "namespace": s.preflight.NAMESPACE,
        "operation": "maintenance-apply",
        "source_sha": "a" * 40,
        "git_tree_sha": "b" * 40,
        "terraform_sources_sha256": "c" * 64,
        "configuration_sha256": "d" * 64,
        "lock_sha256": "e" * 64,
        "terraform_version": s.preflight.CLI,
        "terraform_sha256": "f" * 64,
        "provider_version": s.preflight.PROVIDER,
        "provider_inventory_sha256": "0" * 64,
        "platform": s.preflight.PLATFORM,
        "state_identity": {
            "lineage": "synthetic",
            "serial": 7,
            "version_id": "synthetic-v1",
            "sha256": "1" * 64,
        },
        "plan_sha256": hashlib.sha256(raw).hexdigest(),
        "account_id": "123456789012",
        "region": "ap-northeast-1",
        "resource_scope": "bootstrap",
        "max_execution_seconds": 120,
        "max_cost_usd_cents": 0,
        "plan_approval_id": "2" * 40,
        "plan_attempt_id": "3" * 40,
        "apply_approval_id": "4" * 40,
        "apply_attempt_id": "5" * 40,
    }
    receipt = {k: deepcopy(claim[k]) for k in m.RECEIPT_SHARED} | {
        "kind": "p4-bootstrap-candidate-origin-claim-v4",
        "producer_id": "untrusted-producer",
        "producer_key_id": "untrusted-key",
        "receipt_sha256": "6" * 64,
        "plan_approval_id": claim["plan_approval_id"],
        "plan_attempt_id": claim["plan_attempt_id"],
    }
    claim["generation_receipt"] = receipt
    expected = {k: deepcopy(claim[k]) for k in m.SHARED}

    def approval(operation, aid, tid, plan_hash):
        return {
            "schema_version": 4,
            "kind": s.KIND,
            "namespace": claim["namespace"],
            "issuer": "synthetic-issuer",
            "key_id": "synthetic-key",
            "algorithm": "ed25519",
            "trust_revision": "7" * 64,
            "operation": operation,
            **{key: deepcopy(claim[key]) for key in m.SHARED - {"namespace", "plan_sha256"}},
            "plan_sha256": plan_hash,
            "approval_id": aid,
            "attempt_id": tid,
            "issued_at": "2026-10-25T09:50:00Z",
            "expires_at": "2026-10-25T10:10:00Z",
            "account_id": "123456789012",
            "region": "ap-northeast-1",
            "resource_scope": "bootstrap",
            "max_execution_seconds": 120,
            "max_cost_usd_cents": 0,
        }

    return (
        m,
        claim,
        expected,
        raw,
        approval("maintenance-plan", claim["plan_approval_id"], claim["plan_attempt_id"], None),
        approval(
            "maintenance-apply",
            claim["apply_approval_id"],
            claim["apply_attempt_id"],
            claim["plan_sha256"],
        ),
    )


def run(sample, **overrides):
    m, claim, expected, raw, plan, apply = sample
    return m.validate_source_plan(
        claim,
        expected,
        plan_bytes=overrides.pop("plan_bytes", raw),
        plan_approval=plan,
        apply_approval=apply,
        terminal_state=overrides.pop("terminal_state", "COMPLETED"),
        **overrides,
    )


def test_structural_claim_remains_non_authorizing(sample):
    result = run(sample)
    assert result["binding_consistent"] is True
    assert result["origin_authenticated"] is False
    assert result["state_readback_verified"] is False
    assert result["plan_approval_signature_verified"] is False
    assert result["apply_approval_signature_verified"] is False
    assert result["authorized"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("namespace", "legacy"),
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
    ],
)
def test_mismatched_source_plan_toolchain_and_state_rejected(sample, field, value):
    sample[1][field] = value
    with pytest.raises(ValueError):
        run(sample)


@pytest.mark.parametrize(
    "field,value",
    [
        ("lineage", "wrong"),
        ("serial", 8),
        ("serial", True),
        ("version_id", "different"),
        ("sha256", "9" * 64),
    ],
)
def test_changed_state_identity_fails_closed(sample, field, value):
    sample[1]["state_identity"][field] = value
    with pytest.raises(ValueError):
        run(sample)


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong-operation",
        "unknown",
        "extra",
        "missing",
        "bool-schema",
        "old-schema",
        "empty",
        "tamper",
        "id-reuse-plan-apply",
        "id-cross-role",
        "id-cross-attempt",
        "wrong-plan-approval",
        "wrong-apply-approval",
        "receipt-missing",
        "receipt-id",
        "receipt-extra",
        "receipt-source",
        "receipt-invalid",
        "receipt-namespace",
        "receipt-state-type",
        "approval-schema-float",
        "account-redirect",
    ],
)
def test_replay_bad_receipt_or_partial_evidence_fails_closed(sample, mutation):
    m, claim, expected, raw, plan, apply = sample
    if mutation == "wrong-operation":
        claim["operation"] = "recovery-apply"
    elif mutation == "unknown":
        return run_unknown(sample)
    elif mutation == "extra":
        claim["authorized"] = True
    elif mutation == "missing":
        del claim["git_tree_sha"]
    elif mutation == "bool-schema":
        claim["schema_version"] = True
    elif mutation == "old-schema":
        claim["schema_version"] = 3
    elif mutation == "empty":
        raw = b""
    elif mutation == "tamper":
        raw = b"forged plan"
    elif mutation == "id-reuse-plan-apply":
        claim["apply_approval_id"] = claim["plan_approval_id"]
    elif mutation == "id-cross-role":
        claim["apply_approval_id"] = claim["plan_attempt_id"]
    elif mutation == "id-cross-attempt":
        claim["apply_attempt_id"] = claim["plan_approval_id"]
    elif mutation == "wrong-plan-approval":
        plan["operation"] = "recovery-plan"
    elif mutation == "wrong-apply-approval":
        apply["approval_id"] = "9" * 40
    elif mutation == "receipt-missing":
        del claim["generation_receipt"]
    elif mutation == "receipt-id":
        claim["generation_receipt"]["plan_approval_id"] = "9" * 40
    elif mutation == "receipt-extra":
        claim["generation_receipt"]["authenticated"] = True
    elif mutation == "receipt-source":
        claim["generation_receipt"]["source_sha"] = "9" * 40
    elif mutation == "receipt-invalid":
        claim["generation_receipt"]["receipt_sha256"] = "invalid"
    elif mutation == "receipt-namespace":
        claim["generation_receipt"]["namespace"] = "legacy"
    elif mutation == "receipt-state-type":
        claim["generation_receipt"]["state_identity"]["serial"] = 7.0
    elif mutation == "approval-schema-float":
        plan["schema_version"] = 4.0
    elif mutation == "account-redirect":
        claim["account_id"] = "999999999999"
    with pytest.raises(ValueError):
        run((m, claim, expected, raw, plan, apply))


def run_unknown(sample):
    with pytest.raises(ValueError, match="SchemaOrStateHOLD"):
        run(sample, terminal_state="UNKNOWN")


def test_plan_recovery_pair_distinct_from_maintenance(sample):
    m, claim, _, _, plan, apply = sample
    claim["operation"] = "recovery-apply"
    plan["operation"] = "recovery-plan"
    apply["operation"] = "recovery-apply"
    assert run(sample)["authorized"] is False
    plan["operation"] = "maintenance-plan"
    with pytest.raises(ValueError):
        run(sample)


def test_approval_binding_cannot_retarget_source_without_change_to_claim(sample):
    m, claim, expected, raw, plan, apply = sample
    plan["source_sha"] = "9" * 40
    with pytest.raises(ValueError, match="ApprovalBindingMismatch"):
        run(sample)
    plan["source_sha"] = claim["source_sha"]
    apply["provider_inventory_sha256"] = "9" * 64
    with pytest.raises(ValueError, match="ApprovalBindingMismatch"):
        run(sample)


def test_plan_and_apply_approval_id_and_attempt_cannot_swap(sample):
    m, claim, expected, raw, plan, apply = sample
    plan["approval_id"], apply["approval_id"] = apply["approval_id"], plan["approval_id"]
    with pytest.raises(ValueError):
        run(sample)


def test_no_external_io_or_terraform_process(sample, monkeypatch):
    import socket
    import subprocess

    def forbidden(*args, **kwargs):
        raise AssertionError("External I/O forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    assert run(sample)["authorized"] is False


@pytest.mark.parametrize(
    "approval_role,field,value",
    [
        ("plan", "issuer", ""),
        ("apply", "key_id", {}),
        ("plan", "algorithm", "none"),
        ("apply", "trust_revision", "not-a-hash"),
        ("plan", "issued_at", "not-a-time"),
        ("apply", "expires_at", "2026-10-25T12:01:00Z"),
        ("plan", "operation", {"invalid": "object"}),
    ],
)
def test_structurally_invalid_approvals_cannot_pass_consistency(
    sample, approval_role, field, value
):
    approval = sample[4] if approval_role == "plan" else sample[5]
    approval[field] = value
    with pytest.raises(ValueError):
        run(sample)


def test_plan_claim_rejects_nonstandard_integer_and_booleans(sample):
    m, claim, expected, raw, plan, apply = sample
    for invalid in (True, 1.0, None, [], {}):
        changed = deepcopy(claim)
        changed["max_execution_seconds"] = invalid
        with pytest.raises(ValueError):
            run((m, changed, expected, raw, plan, apply))



def test_recursive_comparison_state_identity_fails_closed(sample):
    m, claim, expected, raw, plan, apply = sample
    claim["state_identity"]["lineage"] = claim["state_identity"]
    expected["state_identity"]["lineage"] = expected["state_identity"]
    with pytest.raises(ValueError, match="CandidateStateIdentityInvalid"):
        run((m, claim, expected, raw, plan, apply))
