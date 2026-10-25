"""Integrated synthetic evidence with real Ed25519 and a disposable local DB."""

import base64
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_candidate_source_plan_v4 import sample  # noqa: F401
from test_p4_tools import tool


@pytest.fixture
def evidence(sample, tmp_path):  # noqa: F811
    gate = tool("candidate_evidence_gate")
    _, claim, expected, raw, plan, apply = sample
    private = Ed25519PrivateKey.generate()
    other = Ed25519PrivateKey.generate()
    now = datetime(2026, 10, 25, 10, tzinfo=UTC)
    for approval in (plan, apply):
        approval["issued_at"] = "2026-10-25T09:50:00Z"
        approval["expires_at"] = "2026-10-25T10:10:00Z"

    def pin(issuer, key, operations, revision):
        return gate.signed.TrustedKey(
            issuer,
            key.public_key().public_bytes_raw(),
            frozenset(operations),
            claim["namespace"],
            revision,
            now - timedelta(hours=1),
            now + timedelta(hours=1),
        )

    approval_keys = {
        plan["key_id"]: pin(
            plan["issuer"], private, [plan["operation"], apply["operation"]], plan["trust_revision"]
        )
    }
    receipt = claim["generation_receipt"]
    payload = {
        "schema_version": 4,
        "operation": plan["operation"],
        "receipt": receipt,
        "algorithm": "ed25519",
        "trust_revision": "7" * 64,
        "issued_at": plan["issued_at"],
        "expires_at": plan["expires_at"],
    }
    receipt["receipt_sha256"] = gate.producer.receipt_digest(payload)
    producer_keys = {
        receipt["producer_key_id"]: pin(
            receipt["producer_id"], other, [plan["operation"]], payload["trust_revision"]
        )
    }

    def signed_envelope(value, key, signing):
        return json.dumps(
            value | {"signature": base64.b64encode(key.sign(signing(value))).decode()}
        ).encode()

    journal = gate.storage.SQLiteJournalRepository.create(tmp_path / "journal.db")

    def event(approval, state, revision):
        return {
            **{k: approval[k] for k in gate.storage.contract.IDENTITY_FIELDS},
            "schema_version": 3,
            "kind": "p4-bootstrap-candidate-journal-v3",
            "state": state,
            "revision": revision,
            "updated_at": (now + timedelta(seconds=revision)).isoformat(),
        }

    for approval in (plan, apply):
        journal.reserve(
            event(approval, "NEW", 0),
            event(approval, "RESERVED", 1),
            operation=approval["operation"],
        )
    journal.compare_and_swap(event(plan, "RESERVED", 1), event(plan, "STARTED", 2))
    journal.compare_and_swap(event(plan, "STARTED", 2), event(plan, "COMPLETED", 3))
    args = dict(
        plan_bytes=raw,
        plan_envelope=signed_envelope(plan, private, gate.signed.signed_bytes),
        apply_envelope=signed_envelope(apply, private, gate.signed.signed_bytes),
        producer_envelope=signed_envelope(payload, other, gate.producer.signed_bytes),
        approval_keys=approval_keys,
        producer_keys=producer_keys,
        journal=journal,
        now=now,
    )
    return gate, claim, expected, args, payload, other, event, plan, apply


def test_full_local_evidence_remains_hold(evidence, monkeypatch):
    import socket
    import subprocess

    import boto3

    def forbidden(*args, **kwargs):
        raise AssertionError("External side effects forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(boto3, "client", forbidden)
    gate, claim, expected, args, *_ = evidence
    result = gate.inspect_evidence(claim, expected, **args)
    for key in (
        "plan_approval_signature_verified",
        "apply_approval_signature_verified",
        "producer_signature_verified",
        "binding_consistent",
        "local_journal_history_matched",
    ):
        assert result[key] is True
    for key in (
        "authorized",
        "origin_authenticated",
        "git_origin_authenticated",
        "retry_permitted",
        "journal_global_uniqueness_proven",
        "state_readback_verified",
        "executed_plan_identity_verified",
    ):
        assert result[key] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "plan-bytes",
        "signature",
        "producer-unknown",
        "approvals-unknown",
        "journal-source",
        "journal-unknown",
        "journal-operation",
        "journal-missing",
        "receipt-plan",
        "receipt-state",
        "receipt-operation",
        "receipt-domain",
        "receipt-digest",
        "receipt-key",
    ],
)
def test_integrated_negative_evidence_never_authorizes(evidence, mutation, tmp_path):
    gate, claim, expected, args, payload, private, event, plan, apply = evidence
    if mutation == "plan-bytes":
        args["plan_bytes"] += b"tampered"
    elif mutation == "signature":
        forged = json.loads(args["apply_envelope"])
        forged["signature"] = base64.b64encode(b"x" * 64).decode()
        args["apply_envelope"] = json.dumps(forged).encode()
    elif mutation in {"producer-unknown", "approvals-unknown"}:
        args["producer_keys" if mutation == "producer-unknown" else "approval_keys"] = {}
        result = gate.inspect_evidence(claim, expected, **args)
        assert result["authorized"] is False
        assert (
            result[
                "producer_signature_verified"
                if mutation == "producer-unknown"
                else "apply_approval_signature_verified"
            ]
            is False
        )
        return
    elif mutation.startswith("journal-"):
        repo = gate.storage.SQLiteJournalRepository.create(tmp_path / "another.db")
        changed = deepcopy(plan)
        if mutation == "journal-source":
            changed["source_sha"] = "f" * 40
        if mutation != "journal-missing":
            operation = "recovery-plan" if mutation == "journal-operation" else plan["operation"]
            repo.reserve(
                event(changed, "NEW", 0), event(changed, "RESERVED", 1), operation=operation
            )
            if mutation == "journal-unknown":
                repo.compare_and_swap(event(changed, "RESERVED", 1), event(changed, "UNKNOWN", 2))
            else:
                repo.compare_and_swap(event(changed, "RESERVED", 1), event(changed, "STARTED", 2))
                repo.compare_and_swap(event(changed, "STARTED", 2), event(changed, "COMPLETED", 3))
        args["journal"] = repo
    else:
        altered = deepcopy(payload)
        if mutation == "receipt-plan":
            altered["receipt"]["plan_sha256"] = "f" * 64
        elif mutation == "receipt-state":
            altered["receipt"]["state_identity"]["serial"] = True
        elif mutation == "receipt-operation":
            altered["operation"] = "recovery-plan"
        elif mutation == "receipt-digest":
            altered["receipt"]["receipt_sha256"] = "f" * 64
        # A hostile signer can bypass our signer grammar; verifier must still reject.
        signing = (
            gate.producer.DOMAIN + json.dumps(altered).encode()
            if mutation == "receipt-state"
            else gate.producer.signed_bytes(altered)
        )
        if mutation == "receipt-domain":
            signing = signing.replace(gate.producer.DOMAIN, gate.signed.DOMAIN)
        if mutation == "receipt-key":
            private = Ed25519PrivateKey.generate()
        altered["signature"] = base64.b64encode(private.sign(signing)).decode()
        args["producer_envelope"] = json.dumps(altered).encode()
    with pytest.raises(ValueError):
        gate.inspect_evidence(claim, expected, **args)
