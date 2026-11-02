"""Offline review of an isolated ledger generation; never an execution authorization.

Evidence claims must be reviewed externally. Digests bind those claims to saved
evidence; this pure checker neither opens that evidence nor proves effective IAM.
The deployed application does not call this module.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from interview_backend.evaluation.provider_limits import validate_limits

Status = Literal["PASS", "FAIL", "UNPROVEN"]


class EvidenceClaim(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    status: Status
    sha256: tuple[str, ...] = ()

    @model_validator(mode="after")
    def evidence_required(self):
        if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in self.sha256):
            raise ValueError("evidence_digest")
        if self.status == "PASS" and not self.sha256:
            raise ValueError("pass_requires_evidence")
        return self


class IsolationReview(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    targets_and_shared_dependencies: EvidenceClaim
    ingress_blocked: EvidenceClaim
    mappings_disabled: EvidenceClaim
    execution_stopped: EvidenceClaim
    inflight_provider_requests_settled: EvidenceClaim
    old_writes_denied: EvidenceClaim
    credentials_revoked: EvidenceClaim
    credential_reacquisition_blocked: EvidenceClaim
    pending_payloads_preserved: EvidenceClaim
    redelivery_quarantined: EvidenceClaim
    independent_readback: EvidenceClaim


class GenerationReview(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    source_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    inventory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    legacy_table_arn: str = Field(min_length=1)
    new_table_arn: str = Field(min_length=1)
    legacy_writer_roles: tuple[str, ...] = Field(min_length=1)
    new_writer_roles: tuple[str, ...] = Field(min_length=1)
    isolation: IsolationReview
    isolation_effective_at: datetime | None
    period_start: datetime
    monthly_user_limit: int
    monthly_global_limit: int
    initial_state_verified: EvidenceClaim
    generation_fencing_implemented: EvidenceClaim
    atomic_shared_quota_verified: EvidenceClaim
    rollback_and_stop_reviewed: EvidenceClaim
    historical_accounting: EvidenceClaim
    historical_uncertainty_accepted: EvidenceClaim

    @model_validator(mode="after")
    def valid_period_and_limits(self):
        validate_limits(self.monthly_user_limit, self.monthly_global_limit)
        for at in (self.period_start, self.isolation_effective_at):
            if at is not None and (at.tzinfo is None or at.utcoffset() is None):
                raise ValueError("timezone_required")
        at = self.period_start.astimezone(UTC)
        if (at.day, at.hour, at.minute, at.second, at.microsecond) != (1, 0, 0, 0, 0):
            raise ValueError("full_utc_accounting_period_required")
        for arn in (self.legacy_table_arn, self.new_table_arn):
            if (
                re.fullmatch(
                    r"arn:aws:dynamodb:ap-northeast-1:[0-9]{12}:table/[A-Za-z0-9_.-]+", arn
                )
                is None
            ):
                raise ValueError("table_arn")
        scope = self.legacy_table_arn.split(":")[3:5]
        if self.new_table_arn.split(":")[3:5] != scope:
            raise ValueError("account_region_mismatch")
        for roles in (self.legacy_writer_roles, self.new_writer_roles):
            if len(set(roles)) != len(roles):
                raise ValueError("duplicate_role")
            for arn in roles:
                if (
                    re.fullmatch(r"arn:aws:iam::" + scope[1] + r":role/[A-Za-z0-9_+=,.@/-]+", arn)
                    is None
                ):
                    raise ValueError("writer_role_arn")
        return self


@dataclass(frozen=True)
class CutoverAssessment:
    historical_accounting: Status
    isolation: Literal["PASS", "BLOCKED"]
    new_generation: Literal["PASS", "BLOCKED"]
    blockers: tuple[str, ...]
    publication: Literal["NOT_EVALUATED"] = "NOT_EVALUATED"
    authorization: Literal["NONE"] = "NONE"


def assess_cutover(review: GenerationReview) -> CutoverAssessment:
    """Check supplied review claims without treating missing history as zero.

    A PASS is conditional on the truth and completeness of the supplied review.
    Source/inventory hashes must also be matched by the independent operator.
    This result cannot authorize AWS changes, paid calls, deployment or release.
    """
    isolation_blockers = tuple(
        "isolation." + name
        for name in IsolationReview.model_fields
        if getattr(review.isolation, name).status != "PASS"
    )
    blockers = list(isolation_blockers)
    if review.isolation_effective_at is None:
        blockers.append("isolation_effective_at_unproven")
    elif review.isolation_effective_at >= review.period_start:
        blockers.append("legacy_activity_overlaps_new_period")
    if review.legacy_table_arn == review.new_table_arn:
        blockers.append("storage_not_isolated")
    if set(review.legacy_writer_roles) & set(review.new_writer_roles):
        blockers.append("writer_roles_reused")
    for name in (
        "initial_state_verified",
        "generation_fencing_implemented",
        "atomic_shared_quota_verified",
        "rollback_and_stop_reviewed",
    ):
        if getattr(review, name).status != "PASS":
            blockers.append(name)
    if review.historical_accounting.status == "FAIL":
        blockers.append("historical_accounting_failed")
    elif (
        review.historical_accounting.status == "UNPROVEN"
        and review.historical_uncertainty_accepted.status != "PASS"
    ):
        blockers.append("historical_uncertainty_not_accepted")
    return CutoverAssessment(
        historical_accounting=review.historical_accounting.status,
        isolation="BLOCKED"
        if isolation_blockers
        or any(
            name in blockers
            for name in (
                "isolation_effective_at_unproven",
                "legacy_activity_overlaps_new_period",
                "storage_not_isolated",
                "writer_roles_reused",
            )
        )
        else "PASS",
        new_generation="BLOCKED" if blockers else "PASS",
        blockers=tuple(blockers),
    )
