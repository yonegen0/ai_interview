"""v4 strict source-to-Plan consistency checks. OFFLINE_ONLY / NON_AUTHORIZING.

No caller-supplied receipt or hash authenticates its origin, Git source, a
Terraform process, a signed approval, remote State or journal one-use.
"""

import hashlib
import re

import candidate_signed_approval as signed

KIND = "p4-bootstrap-candidate-source-plan-claim-v4"
FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "namespace",
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
        "account_id",
        "region",
        "resource_scope",
        "max_execution_seconds",
        "max_cost_usd_cents",
        "plan_sha256",
        "plan_approval_id",
        "plan_attempt_id",
        "apply_approval_id",
        "apply_attempt_id",
        "generation_receipt",
    }
)
RECEIPT_FIELDS = frozenset(
    {
        "kind",
        "namespace",
        "producer_id",
        "producer_key_id",
        "receipt_sha256",
        "plan_approval_id",
        "plan_attempt_id",
        "plan_sha256",
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
        "account_id",
        "region",
        "resource_scope",
        "max_execution_seconds",
        "max_cost_usd_cents",
    }
)
PAIRS = {
    "maintenance-apply": "maintenance-plan",
    "recovery-apply": "recovery-plan",
}
SHARED = FIELDS - {
    "schema_version",
    "kind",
    "operation",
    "plan_approval_id",
    "plan_attempt_id",
    "apply_approval_id",
    "apply_attempt_id",
    "generation_receipt",
}
RECEIPT_SHARED = SHARED


def _compare(actual: object, expected: object, keys: frozenset[str]) -> None:
    signed.require(
        type(actual) is dict
        and type(expected) is dict
        and all(
            key in actual
            and key in expected
            and type(actual[key]) is type(expected[key])
            and actual[key] == expected[key]
            for key in keys
        ),
        "CandidateSourcePlanTargetMismatch",
    )


def validate_source_plan(
    claim: object,
    expected: object,
    *,
    plan_bytes: bytes,
    plan_approval: dict[str, object],
    apply_approval: dict[str, object],
    terminal_state: str,
) -> dict[str, object]:
    """Match strict claims and operation-specific approval bindings, not origins."""
    signed.require(type(claim) is dict and set(claim) == FIELDS, "CandidateSourcePlanFields")
    signed.require(
        type(expected) is dict and set(expected) == SHARED, "CandidateSourcePlanExpectedFields"
    )
    signed.require(
        type(claim["schema_version"]) is int
        and claim["schema_version"] == 4
        and claim["kind"] == KIND
        and type(claim["operation"]) is str
        and claim["operation"] in PAIRS
        and type(terminal_state) is str
        and terminal_state == "COMPLETED",
        "CandidateSourcePlanSchemaOrStateHOLD",
    )
    # Fail closed on malformed nested State before recursive equality is possible.
    signed.preflight.state_identity(claim["state_identity"])
    signed.preflight.state_identity(expected["state_identity"])
    _compare(claim, expected, SHARED)
    signed.require(
        claim["namespace"] == signed.preflight.NAMESPACE
        and claim["terraform_version"] == signed.preflight.CLI
        and claim["provider_version"] == signed.preflight.PROVIDER
        and claim["platform"] == signed.preflight.PLATFORM,
        "CandidateSourcePlanToolchainInvalid",
    )
    signed.require(
        all(
            type(claim[k]) is str and signed.ID.fullmatch(claim[k]) is not None
            for k in ("source_sha", "git_tree_sha")
        )
        and all(
            type(claim[k]) is str and signed.SHA.fullmatch(claim[k]) is not None
            for k in (
                "terraform_sources_sha256",
                "configuration_sha256",
                "lock_sha256",
                "terraform_sha256",
                "provider_inventory_sha256",
                "plan_sha256",
            )
        )
        and all(
            type(claim[k]) is str and signed.ID.fullmatch(claim[k]) is not None
            for k in (
                "plan_approval_id",
                "plan_attempt_id",
                "apply_approval_id",
                "apply_attempt_id",
            )
        )
        and len(
            {
                claim["plan_approval_id"],
                claim["plan_attempt_id"],
                claim["apply_approval_id"],
                claim["apply_attempt_id"],
            }
        )
        == 4,
        "CandidateSourcePlanIdsOrDigestsInvalid",
    )
    signed.preflight.state_identity(claim["state_identity"])
    signed.preflight.state_identity(expected["state_identity"])
    signed.require(
        type(claim["account_id"]) is str
        and re.fullmatch(r"\d{12}", claim["account_id"]) is not None
        and type(claim["region"]) is str
        and signed.REGION.fullmatch(claim["region"]) is not None
        and type(claim["resource_scope"]) is str
        and signed.NAME.fullmatch(claim["resource_scope"]) is not None
        and type(claim["max_execution_seconds"]) is int
        and 1 <= claim["max_execution_seconds"] <= 3600
        and type(claim["max_cost_usd_cents"]) is int
        and 0 <= claim["max_cost_usd_cents"] <= 10000,
        "CandidateSourcePlanScopeInvalid",
    )
    signed.require(
        type(plan_bytes) is bytes
        and bool(plan_bytes)
        and hashlib.sha256(plan_bytes).hexdigest() == claim["plan_sha256"],
        "CandidateSourcePlanBytesMismatch",
    )
    # These must be distinct plan/apply approval claims, not ID-only strings.
    signed.require(
        type(plan_approval) is dict
        and set(plan_approval) == signed.FIELDS
        and type(apply_approval) is dict
        and set(apply_approval) == signed.FIELDS
        and plan_approval["operation"] == PAIRS[claim["operation"]]
        and apply_approval["operation"] == claim["operation"],
        "CandidateSourcePlanApprovalOperationMismatch",
    )
    # Full signed-claim syntax must be valid even though signatures are not verified here.
    signed.validate_payload_fields(plan_approval)
    signed.validate_payload_fields(apply_approval)
    for approval, role in (
        (plan_approval, "plan"),
        (apply_approval, "apply"),
    ):
        signed.require(
            approval["schema_version"] == 4
            and approval["kind"] == signed.KIND
            and approval["approval_id"] == claim[f"{role}_approval_id"]
            and approval["attempt_id"] == claim[f"{role}_attempt_id"]
            and all(
                type(approval[key]) is type(claim[key]) and approval[key] == claim[key]
                for key in SHARED - {"plan_sha256"}
            )
            and (
                approval["plan_sha256"] is None
                if role == "plan"
                else approval["plan_sha256"] == claim["plan_sha256"]
            ),
            "CandidateSourcePlanApprovalBindingMismatch",
        )
    receipt = claim["generation_receipt"]
    signed.require(
        type(receipt) is dict
        and set(receipt) == RECEIPT_FIELDS
        and receipt["kind"] == "p4-bootstrap-candidate-origin-claim-v4"
        and all(
            type(receipt[k]) is str and signed.NAME.fullmatch(receipt[k]) is not None
            for k in ("producer_id", "producer_key_id")
        )
        and type(receipt["receipt_sha256"]) is str
        and signed.SHA.fullmatch(receipt["receipt_sha256"]) is not None
        and receipt["plan_approval_id"] == claim["plan_approval_id"]
        and receipt["plan_attempt_id"] == claim["plan_attempt_id"],
        "CandidateSourcePlanReceiptMissingOrInvalid",
    )
    signed.preflight.state_identity(receipt["state_identity"])
    _compare(receipt, claim, RECEIPT_SHARED)
    return {
        "status": "OFFLINE_SOURCE_PLAN_MATCH_ORIGIN_UNVERIFIED_HOLD",
        "binding_consistent": True,
        "plan_approval_signature_verified": False,
        "apply_approval_signature_verified": False,
        "origin_authenticated": False,
        "git_origin_authenticated": False,
        "state_readback_verified": False,
        "journal_persistence_verified": False,
        "authorized": False,
        "aws_operations": 0,
    }
