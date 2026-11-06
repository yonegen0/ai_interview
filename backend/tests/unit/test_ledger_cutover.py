"""Fail-closed offline reviews; synthetic claims never prove live isolation."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from test_p4_tools import tool

cutover = tool("ledger_cutover")
EvidenceClaim = cutover.EvidenceClaim
GenerationReview = cutover.GenerationReview
IsolationReview = cutover.IsolationReview
assess_cutover = cutover.assess_cutover

PROOF = EvidenceClaim(status="PASS", sha256=("a" * 64,))
UNKNOWN = EvidenceClaim(status="UNPROVEN")


def review(**changes):
    values = dict(
        source_sha="b" * 40,
        inventory_sha256="c" * 64,
        legacy_table_arn="arn:aws:dynamodb:ap-northeast-1:123456789012:table/legacy",
        new_table_arn="arn:aws:dynamodb:ap-northeast-1:123456789012:table/isolated",
        legacy_writer_roles=("arn:aws:iam::123456789012:role/old-worker",),
        new_writer_roles=("arn:aws:iam::123456789012:role/new-worker",),
        isolation=IsolationReview(**dict.fromkeys(IsolationReview.model_fields, PROOF)),
        isolation_effective_at=datetime(2026, 11, 30, 23, 59, 59, tzinfo=UTC),
        period_start=datetime(2026, 12, 1, tzinfo=UTC),
        monthly_user_limit=20,
        monthly_global_limit=600,
        initial_state_verified=PROOF,
        generation_fencing_implemented=PROOF,
        atomic_shared_quota_verified=PROOF,
        rollback_and_stop_reviewed=PROOF,
        historical_accounting=UNKNOWN,
        historical_uncertainty_accepted=PROOF,
    )
    return GenerationReview(**(values | changes))


def test_unrestored_history_remains_unproven_with_safe_future_generation():
    result = assess_cutover(review())
    assert result.isolation == result.new_generation == "PASS"
    assert result.historical_accounting == "UNPROVEN"
    assert result.publication == "NOT_EVALUATED" and result.authorization == "NONE"


@pytest.mark.parametrize("name", list(IsolationReview.model_fields))
@pytest.mark.parametrize("status", ["UNPROVEN", "FAIL"])
def test_each_unknown_or_failed_isolation_claim_blocks_cutover(name, status):
    claims = dict.fromkeys(IsolationReview.model_fields, PROOF)
    claims[name] = EvidenceClaim(status=status)
    result = assess_cutover(review(isolation=IsolationReview(**claims)))
    assert result.isolation == result.new_generation == "BLOCKED"
    assert "isolation." + name in result.blockers


@pytest.mark.parametrize(
    "name",
    [
        "initial_state_verified",
        "generation_fencing_implemented",
        "atomic_shared_quota_verified",
        "rollback_and_stop_reviewed",
        "historical_uncertainty_accepted",
    ],
)
def test_new_generation_requires_every_implementation_and_acceptance_gate(name):
    assert assess_cutover(review(**{name: UNKNOWN})).new_generation == "BLOCKED"


@pytest.mark.parametrize("offset", [0, 1, 3600000])
def test_month_change_cannot_hide_legacy_activity(offset):
    start = datetime(2026, 12, 1, tzinfo=UTC)
    result = assess_cutover(review(isolation_effective_at=start + timedelta(milliseconds=offset)))
    assert "legacy_activity_overlaps_new_period" in result.blockers
    assert result.isolation == result.new_generation == "BLOCKED"


@pytest.mark.parametrize(
    "field,original,blocker",
    [
        ("new_table_arn", "legacy_table_arn", "storage_not_isolated"),
        ("new_writer_roles", "legacy_writer_roles", "writer_roles_reused"),
    ],
)
def test_isolation_status_rejects_shared_storage_or_writer_roles(field, original, blocker):
    base = review()
    result = assess_cutover(review(**{field: getattr(base, original)}))
    assert result.isolation == result.new_generation == "BLOCKED"
    assert blocker in result.blockers


def test_unknown_isolation_time_and_same_storage_or_role_are_blocked():
    base = review()
    result = assess_cutover(
        review(
            isolation_effective_at=None,
            new_table_arn=base.legacy_table_arn,
            new_writer_roles=base.legacy_writer_roles,
        )
    )
    assert set(result.blockers) == {
        "isolation_effective_at_unproven",
        "storage_not_isolated",
        "writer_roles_reused",
    }
    assert result.isolation == "BLOCKED"


@pytest.mark.parametrize(
    "user,global_", [(21, 600), (20, 601), (100, 3000), (True, 600), (20, False), (0, 600)]
)
def test_limits_cannot_exceed_shared_contract_or_use_boolean(user, global_):
    with pytest.raises(ValidationError):
        review(monthly_user_limit=user, monthly_global_limit=global_)


@pytest.mark.parametrize(
    "at",
    [
        datetime(2026, 12, 1),
        datetime(2026, 12, 1, 0, 0, 1, tzinfo=UTC),
        datetime(2026, 12, 2, tzinfo=UTC),
    ],
)
def test_period_requires_full_timezone_aware_utc_month(at):
    with pytest.raises(ValidationError):
        review(period_start=at)


def test_jst_representation_of_utc_boundary_and_stricter_limits_are_valid():
    start = datetime(2026, 12, 1, 9, tzinfo=timezone(timedelta(hours=9)))
    assert (
        assess_cutover(
            review(period_start=start, monthly_user_limit=1, monthly_global_limit=30)
        ).new_generation
        == "PASS"
    )


def test_naive_stop_timestamp_is_rejected():
    with pytest.raises(ValidationError):
        review(isolation_effective_at=datetime(2026, 11, 1))


@pytest.mark.parametrize(
    "changes",
    [
        {"new_table_arn": "arn:aws:dynamodb:ap-northeast-1:999999999999:table/new"},
        {"new_table_arn": "prefix-only"},
        {"new_writer_roles": ("arn:aws:iam::999999999999:role/new",)},
        {"new_writer_roles": ()},
    ],
)
def test_unknown_or_cross_account_target_is_rejected(changes):
    with pytest.raises(ValidationError):
        review(**changes)


def test_failed_historical_reconciliation_cannot_be_accepted_as_missing_history():
    result = assess_cutover(review(historical_accounting=EvidenceClaim(status="FAIL")))
    assert "historical_accounting_failed" in result.blockers


def test_reconciled_history_does_not_require_uncertainty_acceptance():
    assert (
        assess_cutover(
            review(historical_accounting=PROOF, historical_uncertainty_accepted=UNKNOWN)
        ).new_generation
        == "PASS"
    )


@pytest.mark.parametrize(
    "values",
    [
        {"status": "PASS"},
        {"status": "PASS", "sha256": ("wrong",)},
        {"status": "PASS", "sha256": ("a" * 64,), "aws_verified": True},
        {"status": True},
    ],
)
def test_missing_or_malformed_evidence_is_never_a_pass(values):
    with pytest.raises(ValidationError):
        EvidenceClaim(**values)
