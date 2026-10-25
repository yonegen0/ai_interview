"""Additional immutable-looking source/Plan *claims* for offline comparison only.

Preflight already checks Plan bytes, operation and configuration/lock hashes.
This module adds full Git tree/source inventory and claimed Plan origin, with
no inference of producer authenticity, immutable checkout, or authorization.
"""

import hashlib

import candidate_approval_contract as approval_contract

FIELDS = {
    "schema_version",
    "kind",
    "operation",
    "namespace",
    "source_sha",
    "git_tree_sha",
    "terraform_sources_sha256",
    "configuration_sha256",
    "lock_sha256",
    "terraform_version",
    "terraform_sha256",
    "provider_version",
    "platform",
    "state_identity",
    "plan_sha256",
    "generation_evidence",
}
ORIGIN_FIELDS = {"producer_id", "run_id", "evidence_sha256"}
BINDING_FIELDS = FIELDS - {"schema_version", "kind", "operation", "generation_evidence"}
APPLY_TO_PLAN = {
    "maintenance-apply": "maintenance-plan",
    "recovery-apply": "recovery-plan",
}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def validate_plan_binding(
    plan: object,
    expected: object,
    *,
    apply_operation: str,
    plan_binary: bytes,
    plan_approval_id: str,
    apply_approval_id: str,
) -> dict[str, object]:
    """Compare caller-provided claims. No attested Plan generator or trust root."""
    require(type(plan) is dict and set(plan) == FIELDS, "CandidatePlanClaimFields")
    require(
        type(expected) is dict and set(expected) == BINDING_FIELDS, "CandidatePlanExpectedFields"
    )
    require(
        type(plan["schema_version"]) is int
        and plan["schema_version"] == 3
        and plan["kind"] == "p4-bootstrap-candidate-plan-origin-claim-v3"
        and type(apply_operation) is str
        and apply_operation in APPLY_TO_PLAN
        and plan["operation"] == APPLY_TO_PLAN[apply_operation],
        "CandidatePlanSchemaOrOperationInvalid",
    )
    require(
        plan["namespace"] == approval_contract.preflight.NAMESPACE
        and plan["terraform_version"] == approval_contract.preflight.CLI
        and plan["provider_version"] == approval_contract.preflight.PROVIDER
        and plan["platform"] == approval_contract.preflight.PLATFORM
        and all(
            approval_contract.hex_digest(plan[key], 40) for key in ("source_sha", "git_tree_sha")
        )
        and all(
            approval_contract.hex_digest(plan[key])
            for key in (
                "terraform_sources_sha256",
                "configuration_sha256",
                "lock_sha256",
                "terraform_sha256",
                "plan_sha256",
            )
        ),
        "CandidatePlanClaimVersionOrDigestInvalid",
    )
    approval_contract.preflight.state_identity(plan["state_identity"])
    approval_contract.preflight.state_identity(expected["state_identity"])
    require(
        all(
            type(plan[key]) is type(expected[key]) and plan[key] == expected[key]
            for key in BINDING_FIELDS
        ),
        "CandidatePlanSourceOrStateMismatch",
    )
    require(
        type(plan_binary) is bytes
        and len(plan_binary) > 0
        and hashlib.sha256(plan_binary).hexdigest() == plan["plan_sha256"],
        "CandidatePlanBinaryHashMismatch",
    )
    require(
        approval_contract.hex_digest(plan_approval_id, 40)
        and approval_contract.hex_digest(apply_approval_id, 40)
        and plan_approval_id != apply_approval_id,
        "CandidatePlanApprovalsNotSeparated",
    )
    origin = plan["generation_evidence"]
    require(
        type(origin) is dict
        and set(origin) == ORIGIN_FIELDS
        and type(origin["producer_id"]) is str
        and bool(origin["producer_id"])
        and type(origin["run_id"]) is str
        and bool(origin["run_id"])
        and approval_contract.hex_digest(origin["evidence_sha256"]),
        "CandidatePlanProvenanceEvidenceMissing",
    )
    return {
        "status": "OFFLINE_PLAN_CLAIMS_CONSISTENT_ORIGIN_UNVERIFIED",
        "binding_consistent": True,
        "origin_authenticated": False,
        "git_origin_authenticated": False,
        "state_readback_verified": False,
        "authorized": False,
        "aws_operations": 0,
    }
