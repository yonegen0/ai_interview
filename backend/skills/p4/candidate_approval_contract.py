"""Untrusted candidate approval *claim* validation. OFFLINE_ONLY / NON_AUTHORIZING.

A structurally correct signed-looking object is not a verified signature,
an authenticated issuer, an approved policy, or an execution authorization.
"""

import base64
import binascii
import re
from datetime import UTC, datetime, timedelta

import candidate_bootstrap_preflight as preflight

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
MAX_LIFETIME = timedelta(hours=1)
BINDING_FIELDS = frozenset(
    {
        "operation",
        "namespace",
        "source_sha",
        "git_tree_sha",
        "terraform_sources_sha256",
        "terraform_version",
        "terraform_sha256",
        "provider_version",
        "platform",
        "configuration_sha256",
        "lock_sha256",
        "state_identity",
        "plan_sha256",
        "approval_id",
        "attempt_id",
    }
)
FIELDS = BINDING_FIELDS | {
    "schema_version",
    "kind",
    "issued_at",
    "expires_at",
    "signature_claim",
}
CLAIM_FIELDS = {"issuer", "key_id", "algorithm", "signature"}
PLAN_OPERATIONS = {"maintenance-plan", "recovery-plan"}
OPERATIONS = PLAN_OPERATIONS | {"maintenance-apply", "recovery-apply"}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def hex_digest(value: object, size: int = 64) -> bool:
    pattern = SHA40 if size == 40 else SHA64
    return type(value) is str and pattern.fullmatch(value) is not None


def instant(value: object) -> datetime:
    require(type(value) is str and not value.endswith("-00:00"), "CandidateApprovalTimeInvalid")
    try:
        parsed = datetime.fromisoformat(value)
        require(
            parsed.tzinfo is not None and parsed.utcoffset() is not None,
            "CandidateApprovalTimeInvalid",
        )
    except (TypeError, ValueError) as error:
        raise ValueError("CandidateApprovalTimeInvalid") from error
    return parsed.astimezone(UTC)


def _binding(value: object) -> None:
    require(type(value) is dict and set(value) == BINDING_FIELDS, "CandidateApprovalFields")
    require(
        type(value["operation"]) is str
        and value["operation"] in OPERATIONS
        and value["namespace"] == preflight.NAMESPACE
        and value["terraform_version"] == preflight.CLI
        and value["provider_version"] == preflight.PROVIDER
        and value["platform"] == preflight.PLATFORM
        and all(
            hex_digest(value[key], 40)
            for key in ("source_sha", "git_tree_sha", "approval_id", "attempt_id")
        )
        and all(
            hex_digest(value[key])
            for key in (
                "terraform_sources_sha256",
                "terraform_sha256",
                "configuration_sha256",
                "lock_sha256",
            )
        )
        and (
            value["plan_sha256"] is None
            if value["operation"] in PLAN_OPERATIONS
            else hex_digest(value["plan_sha256"])
        ),
        "CandidateApprovalBindingInvalid",
    )
    preflight.state_identity(value["state_identity"])


def validate_approval(
    approval: object, expected_binding: object, *, now: datetime
) -> dict[str, object]:
    """Compare strict v3 fields to an external expectation, without authenticating it.

    The expectation, claimed signer, clock and evidence are caller-supplied.
    No return value permits AWS, Terraform, retries, or ledger consumption.
    """
    require(type(approval) is dict and set(approval) == FIELDS, "CandidateApprovalFields")
    _binding({key: approval[key] for key in BINDING_FIELDS})
    _binding(expected_binding)
    require(
        all(
            type(approval[key]) is type(expected_binding[key])
            and approval[key] == expected_binding[key]
            for key in BINDING_FIELDS
        ),
        "CandidateApprovalTargetMismatch",
    )
    require(
        type(approval["schema_version"]) is int
        and approval["schema_version"] == 3
        and approval["kind"] == "p4-bootstrap-candidate-approval-claim-v3",
        "CandidateApprovalSchemaInvalid",
    )
    evidence = approval["signature_claim"]
    require(
        type(evidence) is dict and set(evidence) == CLAIM_FIELDS, "CandidateApprovalEvidenceMissing"
    )
    require(
        all(type(evidence[key]) is str and bool(evidence[key]) for key in CLAIM_FIELDS)
        and evidence["algorithm"] == "ed25519",
        "CandidateApprovalEvidenceInvalid",
    )
    try:
        decoded = base64.b64decode(evidence["signature"], validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("CandidateApprovalEvidenceInvalid") from error
    require(len(decoded) == 64, "CandidateApprovalEvidenceInvalid")
    require(
        isinstance(now, datetime) and now.tzinfo is not None and now.utcoffset() is not None,
        "CandidateApprovalClockInvalid",
    )
    issued = instant(approval["issued_at"])
    expires = instant(approval["expires_at"])
    current = now.astimezone(UTC)
    require(
        issued <= current < expires and issued < expires and expires - issued <= MAX_LIFETIME,
        "CandidateApprovalExpiredOrFuture",
    )
    return {
        "status": "OFFLINE_CONTRACT_CONSISTENT_AUTHENTICITY_UNVERIFIED",
        "contract_consistent": True,
        "approval_authenticity": "UNVERIFIED",
        "signature_verified": False,
        "authorized": False,
        "aws_operations": 0,
    }
