"""Strict v4 candidate approval signature contract. OFFLINE_ONLY / NON_AUTHORIZING.

New v4 signatures never reinterpret v2/v3 claim bytes. A caller-supplied registry
is NOT evidence of independently authenticated key enrollment or execution rights.
No I/O, AWS, Terraform, Journal mutation or execution code lives here.
"""

import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import candidate_approval_contract as legacy
import candidate_bootstrap_preflight as preflight

DOMAIN = b"ai_interview:p4:candidate:approval:v4\x00"
KIND = "p4-bootstrap-candidate-signed-approval-v4"
SHA = re.compile(r"[0-9a-f]{64}\Z")
ID = re.compile(r"[0-9a-f]{40}\Z")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
REGION = re.compile(r"[a-z]{2}-[a-z]+-\d\Z")
TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
MAX_BYTES = 16384
MAX_TTL = timedelta(hours=1)
FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "namespace",
        "issuer",
        "key_id",
        "algorithm",
        "trust_revision",
        "operation",
        "source_sha",
        "git_tree_sha",
        "terraform_sources_sha256",
        "configuration_sha256",
        "lock_sha256",
        "terraform_version",
        "terraform_sha256",
        "provider_version",
        "provider_inventory_sha256",
        "platform",
        "state_identity",
        "plan_sha256",
        "approval_id",
        "attempt_id",
        "issued_at",
        "expires_at",
        "account_id",
        "region",
        "resource_scope",
        "max_execution_seconds",
        "max_cost_usd_cents",
    }
)
ENVELOPE_FIELDS = FIELDS | {"signature"}
TARGET_FIELDS = FIELDS - {
    "schema_version",
    "kind",
    "issuer",
    "key_id",
    "algorithm",
    "trust_revision",
    "issued_at",
    "expires_at",
}


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        require(key not in result, "CandidateSignedApprovalDuplicateJsonKey")
        result[key] = value
    return result


def _reject_numeric(_: str) -> None:
    raise ValueError("CandidateSignedApprovalUnsupportedNumber")


def parse_json(raw: bytes) -> dict[str, object]:
    """UTF-8 JSON with no duplicate keys, float, NaN or boolean/integer aliases."""
    require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, "CandidateSignedApprovalJsonInvalid")
    try:
        result = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_float=_reject_numeric,
            parse_constant=_reject_numeric,
            parse_int=lambda n: int(n) if len(n) <= 20 else _reject_numeric(n),
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("CandidateSignedApprovalJsonInvalid") from exc
    require(type(result) is dict, "CandidateSignedApprovalJsonInvalid")
    return result


def _ascii_tree(value: object) -> None:
    if type(value) is str:
        require(all(32 <= ord(char) <= 126 for char in value), "CandidateSignedApprovalAsciiOnly")
    elif type(value) is dict:
        for key, child in value.items():
            require(type(key) is str, "CandidateSignedApprovalKeyType")
            _ascii_tree(key)
            _ascii_tree(child)
    elif type(value) is int:
        require(0 <= value <= 2**53 - 1, "CandidateSignedApprovalIntegerRange")
    elif value is None:
        return
    else:
        require(False, "CandidateSignedApprovalTypeInvalid")


def canonical_payload(payload: dict[str, object]) -> bytes:
    """Fixed-profile canonical JSON (ASCII-only, integers/null/strings), NOT RFC 8785."""
    require(type(payload) is dict and set(payload) == FIELDS, "CandidateSignedApprovalFields")
    try:
        _ascii_tree(payload)
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (RecursionError, TypeError, OverflowError) as exc:
        raise ValueError("CandidateSignedApprovalCanonicalInvalid") from exc


def signed_bytes(payload: dict[str, object]) -> bytes:
    return DOMAIN + canonical_payload(payload)


def _instant(value: object) -> datetime:
    require(
        type(value) is str and TIME.fullmatch(value) is not None,
        "CandidateSignedApprovalTimeInvalid",
    )
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError("CandidateSignedApprovalTimeInvalid") from exc


def validate_payload_fields(payload: object) -> None:
    """Validate complete v4 signed-claim structure without claiming trusted time."""
    require(type(payload) is dict and set(payload) == FIELDS, "CandidateSignedApprovalFields")
    canonical_payload(payload)
    require(
        type(payload["schema_version"]) is int
        and payload["schema_version"] == 4
        and payload["kind"] == KIND
        and payload["namespace"] == preflight.NAMESPACE
        and payload["algorithm"] == "ed25519"
        and all(
            type(payload[k]) is str and NAME.fullmatch(payload[k])
            for k in ("issuer", "key_id", "resource_scope")
        )
        and type(payload["trust_revision"]) is str
        and SHA.fullmatch(payload["trust_revision"]) is not None
        and type(payload["operation"]) is str
        and payload["operation"] in legacy.OPERATIONS
        and all(
            type(payload[k]) is str and ID.fullmatch(payload[k])
            for k in ("source_sha", "git_tree_sha", "approval_id", "attempt_id")
        )
        and payload["approval_id"] != payload["attempt_id"]
        and all(
            type(payload[k]) is str and SHA.fullmatch(payload[k])
            for k in (
                "terraform_sources_sha256",
                "configuration_sha256",
                "lock_sha256",
                "terraform_sha256",
                "provider_inventory_sha256",
            )
        )
        and payload["terraform_version"] == preflight.CLI
        and payload["provider_version"] == preflight.PROVIDER
        and payload["platform"] == preflight.PLATFORM
        and (
            payload["plan_sha256"] is None
            if payload["operation"] in legacy.PLAN_OPERATIONS
            else type(payload["plan_sha256"]) is str
            and SHA.fullmatch(payload["plan_sha256"]) is not None
        )
        and type(payload["account_id"]) is str
        and re.fullmatch(r"\d{12}", payload["account_id"]) is not None
        and type(payload["region"]) is str
        and REGION.fullmatch(payload["region"]) is not None
        and type(payload["max_execution_seconds"]) is int
        and 1 <= payload["max_execution_seconds"] <= 3600
        and type(payload["max_cost_usd_cents"]) is int
        and 0 <= payload["max_cost_usd_cents"] <= 10000,
        "CandidateSignedApprovalBindingInvalid",
    )
    preflight.state_identity(payload["state_identity"])
    issued, expires = _instant(payload["issued_at"]), _instant(payload["expires_at"])
    require(
        issued < expires and expires - issued <= MAX_TTL,
        "CandidateSignedApprovalTimeWindowInvalid",
    )


def validate_payload(payload: object, expected: object, *, now: datetime) -> None:
    validate_payload_fields(payload)
    require(
        type(expected) is dict and set(expected) == TARGET_FIELDS,
        "CandidateSignedApprovalExpectedFields",
    )
    # Validate the caller's expectation too, to prevent bool == 1 or other aliases.
    reference = {**payload, **expected}
    require(
        all(
            type(payload[key]) is type(expected[key]) and payload[key] == expected[key]
            for key in TARGET_FIELDS
        ),
        "CandidateSignedApprovalTargetMismatch",
    )
    canonical_payload(reference)
    preflight.state_identity(expected["state_identity"])
    require(
        isinstance(now, datetime) and now.tzinfo is not None and now.utcoffset() is not None,
        "CandidateSignedApprovalClockInvalid",
    )
    issued, expires = _instant(payload["issued_at"]), _instant(payload["expires_at"])
    require(
        issued <= now.astimezone(UTC) < expires
        and issued < expires
        and expires - issued <= MAX_TTL,
        "CandidateSignedApprovalExpiredOrFuture",
    )


@dataclass(frozen=True, slots=True)
class TrustedKey:
    """Externally configured public-key pin. Constructor is NOT enrollment."""

    issuer: str
    public_key: bytes
    operations: frozenset[str]
    namespace: str
    trust_revision: str
    not_before: datetime
    not_after: datetime
    revoked: bool = False


def _trusted(key: object, payload: dict[str, object], current: datetime) -> None:
    require(type(key) is TrustedKey, "CandidateSignedApprovalUnknownKeyHOLD")
    require(
        type(key.public_key) is bytes
        and len(key.public_key) == 32
        and type(key.operations) is frozenset
        and all(type(op) is str and op in legacy.OPERATIONS for op in key.operations)
        and type(key.issuer) is str
        and key.issuer == payload["issuer"]
        and type(key.namespace) is str
        and key.namespace == payload["namespace"]
        and type(key.trust_revision) is str
        and key.trust_revision == payload["trust_revision"]
        and payload["operation"] in key.operations
        and type(key.revoked) is bool
        and not key.revoked
        and isinstance(key.not_before, datetime)
        and key.not_before.tzinfo is not None
        and key.not_before.utcoffset() is not None
        and isinstance(key.not_after, datetime)
        and key.not_after.tzinfo is not None
        and key.not_after.utcoffset() is not None
        and key.not_before.astimezone(UTC) <= current < key.not_after.astimezone(UTC),
        "CandidateSignedApprovalKeyPolicyHOLD",
    )


def verify_signed_approval(
    envelope_json: bytes,
    expected: dict[str, object],
    *,
    trust_registry: dict[str, TrustedKey],
    now: datetime,
) -> dict[str, object]:
    """Check local cryptographic signature; NEVER authenticate enrollment or authorize."""
    envelope = parse_json(envelope_json)
    require(set(envelope) == ENVELOPE_FIELDS, "CandidateSignedApprovalFields")
    payload = {field: envelope[field] for field in FIELDS}
    validate_payload(payload, expected, now=now)
    encoded = envelope["signature"]
    require(
        type(encoded) is str and len(encoded) == 88,
        "CandidateSignedApprovalSignatureEncodingInvalid",
    )
    try:
        signature = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("CandidateSignedApprovalSignatureEncodingInvalid") from exc
    require(
        len(signature) == 64 and base64.b64encode(signature).decode("ascii") == encoded,
        "CandidateSignedApprovalSignatureEncodingInvalid",
    )
    require(type(trust_registry) is dict, "CandidateSignedApprovalRegistryInvalidHOLD")
    # No automatically trusted keys exist. An empty registry remains UNVERIFIED/HOLD.
    if not trust_registry:
        return {
            "status": "UNVERIFIED_HOLD",
            "signature_verified": False,
            "trust_enrollment_authenticated": False,
            "authorized": False,
            "aws_operations": 0,
        }
    key = trust_registry.get(payload["key_id"])
    _trusted(key, payload, now.astimezone(UTC))
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise ValueError("CandidateSignedApprovalCryptoDependencyMissingHOLD") from exc
    try:
        Ed25519PublicKey.from_public_bytes(key.public_key).verify(signature, signed_bytes(payload))
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("CandidateSignedApprovalBadSignatureHOLD") from exc
    return {
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
