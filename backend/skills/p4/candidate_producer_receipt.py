"""Signed producer claims, never authenticated producer enrollment or execution.

Uses a distinct domain and the v4 constrained ASCII/integer JSON profile, NOT
JCS. A signature covers receipt, algorithm, trust revision and validity window.
receipt_sha256 hashes those unsigned bytes with its own field omitted.
"""

import base64
import binascii
import hashlib
import json
from datetime import datetime

import candidate_signed_approval as signed
import candidate_source_plan_v4 as source
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

DOMAIN = b"ai_interview:p4:candidate:producer-receipt:v4\x00"
FIELDS = frozenset(
    {
        "schema_version",
        "operation",
        "receipt",
        "algorithm",
        "trust_revision",
        "issued_at",
        "expires_at",
    }
)


def signed_bytes(payload: dict[str, object]) -> bytes:
    signed.require(type(payload) is dict and set(payload) == FIELDS, "CandidateProducerFieldsHOLD")
    receipt = payload["receipt"]
    signed.require(
        type(receipt) is dict and set(receipt) == source.RECEIPT_FIELDS,
        "CandidateProducerReceiptFieldsHOLD",
    )
    try:
        signed._ascii_tree(payload)
        return DOMAIN + json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("ascii")
    except (RecursionError, TypeError, OverflowError) as exc:
        raise ValueError("CandidateProducerCanonicalHOLD") from exc


def receipt_digest(payload: dict[str, object]) -> str:
    # Validate full shape before deliberately removing the self-referential field.
    signed_bytes(payload)
    value = {
        **payload,
        "receipt": {k: v for k, v in payload["receipt"].items() if k != "receipt_sha256"},
    }
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )
    return hashlib.sha256(DOMAIN + raw).hexdigest()


def verify_receipt(
    envelope_json: bytes,
    expected_receipt: dict[str, object],
    *,
    trust_registry: dict[str, signed.TrustedKey],
    operation: str,
    now: datetime,
) -> dict[str, object]:
    """Real Ed25519 verification with caller pins; origin remains UNVERIFIED/HOLD."""
    envelope = signed.parse_json(envelope_json)
    signed.require(set(envelope) == FIELDS | {"signature"}, "CandidateProducerFieldsHOLD")
    payload = {key: envelope[key] for key in FIELDS}
    raw = signed_bytes(payload)
    signed_bytes({**payload, "receipt": expected_receipt})
    receipt = payload["receipt"]
    signed.require(
        type(payload["schema_version"]) is int
        and payload["schema_version"] == 4
        and type(operation) is str
        and operation in source.PAIRS.values()
        and payload["operation"] == operation,
        "CandidateProducerOperationHOLD",
    )
    # Reuse the complete approval grammar for shared fields, IDs and timestamps.
    reference = {key: receipt[key] for key in source.SHARED - {"plan_sha256"}}
    reference.update(
        schema_version=4,
        kind=signed.KIND,
        operation=operation,
        issuer=receipt["producer_id"],
        key_id=receipt["producer_key_id"],
        algorithm=payload["algorithm"],
        trust_revision=payload["trust_revision"],
        approval_id=receipt["plan_approval_id"],
        attempt_id=receipt["plan_attempt_id"],
        plan_sha256=None,
        issued_at=payload["issued_at"],
        expires_at=payload["expires_at"],
    )
    signed.validate_payload(reference, {k: reference[k] for k in signed.TARGET_FIELDS}, now=now)
    signed.preflight.state_identity(expected_receipt["state_identity"])
    signed.require(
        receipt["kind"] == "p4-bootstrap-candidate-origin-claim-v4"
        and type(receipt["plan_sha256"]) is str
        and signed.SHA.fullmatch(receipt["plan_sha256"])
        and type(receipt["receipt_sha256"]) is str
        and receipt["receipt_sha256"] == receipt_digest(payload)
        and receipt == expected_receipt,
        "CandidateProducerBindingOrDigestHOLD",
    )
    signature = envelope["signature"]
    signed.require(
        type(signature) is str and len(signature) == 88, "CandidateProducerSignatureHOLD"
    )
    try:
        signature_bytes = base64.b64decode(signature, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("CandidateProducerSignatureHOLD") from exc
    signed.require(
        len(signature_bytes) == 64 and base64.b64encode(signature_bytes).decode() == signature,
        "CandidateProducerSignatureHOLD",
    )
    signed.require(type(trust_registry) is dict, "CandidateProducerRegistryHOLD")
    verified = False
    if trust_registry:
        key = trust_registry.get(receipt["producer_key_id"])
        signed._trusted(key, reference, now)
        try:
            Ed25519PublicKey.from_public_bytes(key.public_key).verify(signature_bytes, raw)
        except (ValueError, InvalidSignature) as exc:
            raise ValueError("CandidateProducerBadSignatureHOLD") from exc
        verified = True
    return {
        "status": "PRODUCER_SIGNATURE_CHECKED_ENROLLMENT_UNVERIFIED_HOLD",
        "signature_verified": verified,
        "producer_enrollment_authenticated": False,
        "clock_authenticated": False,
        "origin_authenticated": False,
        "authorized": False,
        "aws_operations": 0,
    }
