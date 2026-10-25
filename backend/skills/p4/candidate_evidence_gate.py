"""Inspect v4 signatures, exact in-memory Plan bytes and durable local histories.

No execution API, no authority and no caller-provided 'verified=True' overrides.
Even all locally consistent evidence returns HOLD. Immutable execution source,
producer/key/time/State trust and an independent checkpoint remain separate.
"""

from datetime import datetime

import candidate_journal_sqlite as storage
import candidate_producer_receipt as producer
import candidate_signed_approval as signed
import candidate_source_plan_v4 as source


def inspect_evidence(
    claim: dict[str, object],
    expected: dict[str, object],
    *,
    plan_bytes: bytes,
    plan_envelope: bytes,
    apply_envelope: bytes,
    producer_envelope: bytes,
    approval_keys: dict[str, signed.TrustedKey],
    producer_keys: dict[str, signed.TrustedKey],
    journal: storage.SQLiteJournalRepository,
    now: datetime,
) -> dict[str, object]:
    """Read actual local storage; syntax/binding/signature results never grant rights."""
    signed.require(type(journal) is storage.SQLiteJournalRepository, "CandidateGateStorageHOLD")
    signed.require(type(claim) is dict and set(claim) == source.FIELDS, "CandidateSourcePlanFields")
    plan = signed.parse_json(plan_envelope)
    apply = signed.parse_json(apply_envelope)
    approvals = []
    for envelope in (plan, apply):
        signed.require(set(envelope) == signed.ENVELOPE_FIELDS, "CandidateSignedApprovalFields")
        approvals.append({k: envelope[k] for k in signed.FIELDS})
    # Full consistency validation occurs before any receipt/Journal comparison.
    binding = source.validate_source_plan(
        claim,
        expected,
        plan_bytes=plan_bytes,
        plan_approval=approvals[0],
        apply_approval=approvals[1],
        terminal_state="COMPLETED",
    )
    signatures = [
        signed.verify_signed_approval(
            envelope,
            {k: approval[k] for k in signed.TARGET_FIELDS},
            trust_registry=approval_keys,
            now=now,
        )
        for envelope, approval in zip((plan_envelope, apply_envelope), approvals, strict=True)
    ]
    receipt = producer.verify_receipt(
        producer_envelope,
        claim["generation_receipt"],
        trust_registry=producer_keys,
        operation=source.PAIRS[claim["operation"]],
        now=now,
    )
    histories = []
    observations = journal.read_many(tuple(approval["attempt_id"] for approval in approvals))
    for approval, state, observed in zip(
        approvals, ("COMPLETED", "RESERVED"), observations, strict=True
    ):
        entry = observed["entry"]
        signed.require(
            observed["operation"] == approval["operation"]
            and entry["state"] == state
            and all(
                type(entry[k]) is type(approval[k]) and entry[k] == approval[k]
                for k in storage.contract.IDENTITY_FIELDS
            ),
            "CandidateGateJournalBindingOrStateHOLD",
        )
        histories.append(observed["history"])
    storage.contract.check_unique_histories(histories)
    return {
        "status": "LOCAL_EVIDENCE_CONSISTENT_NON_AUTHORIZING_HOLD",
        "binding_consistent": binding["binding_consistent"],
        "plan_approval_signature_verified": signatures[0]["signature_verified"],
        "apply_approval_signature_verified": signatures[1]["signature_verified"],
        "producer_signature_verified": receipt["signature_verified"],
        "plan_bytes_digest_matched": True,
        "local_journal_history_matched": True,
        "journal_global_uniqueness_proven": False,
        "rollback_verification": "UNVERIFIED_HOLD",
        "origin_authenticated": False,
        "git_origin_authenticated": False,
        "immutable_execution_snapshot_verified": False,
        "toolchain_authenticated": False,
        "trust_enrollment_authenticated": False,
        "clock_authenticated": False,
        "state_readback_verified": False,
        "executed_plan_identity_verified": False,
        "authorized": False,
        "retry_permitted": False,
        "aws_operations": 0,
    }
