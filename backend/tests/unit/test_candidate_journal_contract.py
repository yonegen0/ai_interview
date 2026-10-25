"""Pure journal snapshots cannot establish remote atomicity or one-use proof."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from test_p4_tools import tool


@pytest.fixture
def sample():
    m = tool("candidate_journal_contract")
    binding = {
        "namespace": m.approval_contract.preflight.NAMESPACE,
        "approval_id": "a" * 40,
        "attempt_id": "b" * 40,
        "source_sha": "c" * 40,
        "plan_sha256": "d" * 64,
    }
    now = datetime(2026, 10, 25, 10, 0, tzinfo=UTC)

    def event(state, revision):
        return {
            **binding,
            "schema_version": 3,
            "kind": "p4-bootstrap-candidate-journal-v3",
            "state": state,
            "revision": revision,
            "updated_at": (now + timedelta(seconds=revision)).isoformat(),
        }

    return m, binding, event


def test_valid_history_never_proves_single_use(sample):
    m, binding, event = sample
    history = [event("NEW", 0), event("RESERVED", 1), event("STARTED", 2), event("COMPLETED", 3)]
    assert m.transition(history[1], history[2], binding)["authorized"] is False
    result = m.check_history(history, binding)
    assert result["state"] == "COMPLETED"
    assert result["single_use_proven"] is False
    assert result["persistence_verified"] is False
    assert result["authorized"] is False


@pytest.mark.parametrize("state", ["FAILED", "UNKNOWN", "COMPLETED"])
def test_terminal_state_cannot_be_retried(sample, state):
    m, binding, event = sample
    m.check_history(
        [event("NEW", 0), event("RESERVED", 1), event("STARTED", 2), event(state, 3)], binding
    )
    with pytest.raises(
        ValueError, match="CandidateJournal(TransitionForbidden|StateRevisionInvalid)"
    ):
        m.transition(event(state, 3), event("STARTED", 4), binding)


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong-state",
        "skipped-revision",
        "double-start",
        "out-of-order",
        "partial-write",
        "old-schema",
        "old-namespace",
        "different-approval",
        "different-attempt",
        "different-source",
        "different-plan",
        "bool-revision",
        "naive-time",
    ],
)
def test_ordering_and_partial_write_fail_closed(sample, mutation):
    m, binding, event = sample
    history = [event("NEW", 0), event("RESERVED", 1), event("STARTED", 2)]
    latest = history[2]
    if mutation == "wrong-state":
        history[1]["state"] = "COMPLETED"
    elif mutation == "skipped-revision":
        latest["revision"] = 3
    elif mutation == "double-start":
        latest["state"] = "RESERVED"
    elif mutation == "out-of-order":
        latest["updated_at"] = history[1]["updated_at"]
    elif mutation == "partial-write":
        del latest["state"]
    elif mutation == "old-schema":
        latest["schema_version"] = 2
    elif mutation == "old-namespace":
        latest["namespace"] = "legacy"
    elif mutation == "different-approval":
        latest["approval_id"] = "e" * 40
    elif mutation == "different-attempt":
        latest["attempt_id"] = "e" * 40
    elif mutation == "different-source":
        latest["source_sha"] = "e" * 40
    elif mutation == "different-plan":
        latest["plan_sha256"] = "e" * 64
    elif mutation == "bool-revision":
        latest["revision"] = True
    elif mutation == "naive-time":
        latest["updated_at"] = "2026-10-25T10:00:02"
    with pytest.raises(ValueError):
        m.check_history(history, binding)


@pytest.mark.parametrize("reuse", ["same", "approval", "attempt"])
def test_conflicting_approval_attempt_ids_rejected(sample, reuse):
    m, _, event = sample
    one = [event("NEW", 0), event("RESERVED", 1)]
    two = deepcopy(one)
    for row in two:
        if reuse == "approval":
            row["attempt_id"] = "e" * 40
        elif reuse == "attempt":
            row["approval_id"] = "e" * 40
    with pytest.raises(ValueError, match="CandidateJournalIdReused"):
        m.check_unique_histories([one, two])


def test_distinct_histories_do_not_prove_global_uniqueness(sample):
    m, _, event = sample
    one = [event("NEW", 0)]
    two = deepcopy(one)
    two[0]["approval_id"] = "e" * 40
    two[0]["attempt_id"] = "f" * 40
    result = m.check_unique_histories([one, two])
    assert result["global_uniqueness_proven"] is False
    assert result["authorized"] is False


@pytest.mark.parametrize("state", ["NEW", "RESERVED", "STARTED", "FAILED", "UNKNOWN"])
def test_restart_always_freezes_without_retry(sample, state):
    m, binding, event = sample
    revision = {"NEW": 0, "RESERVED": 1, "STARTED": 2, "FAILED": 3, "UNKNOWN": 2}[state]
    result = m.crash_disposition(event(state, revision), binding)
    assert result["authorized"] is False
    assert result["retry_permitted"] is False
    if state in {"RESERVED", "STARTED"}:
        assert result["effective_state"] == "UNKNOWN"


def test_snapshot_rollback_or_equivocation_rejected(sample):
    m, binding, event = sample
    old, latest = event("NEW", 0), event("RESERVED", 1)
    m.check_snapshot_rollback(old, latest, binding)
    with pytest.raises(ValueError, match="CandidateJournalRollbackOrRewrite"):
        m.check_snapshot_rollback(latest, old, binding)
    rewrite = deepcopy(latest)
    rewrite["state"] = "FAILED"
    with pytest.raises(
        ValueError, match="CandidateJournal(RollbackOrRewrite|StateRevisionInvalid)"
    ):
        m.check_snapshot_rollback(latest, rewrite, binding)


def test_absent_or_non_new_history_is_not_valid(sample):
    m, binding, event = sample
    with pytest.raises(ValueError, match="CandidateJournalMissing"):
        m.check_history([], binding)
    with pytest.raises(ValueError, match="CandidateJournalStateRevisionInvalid"):
        m.check_history([event("STARTED", 0)], binding)


@pytest.mark.parametrize("terminal", ["COMPLETED", "FAILED", "UNKNOWN"])
@pytest.mark.parametrize("target", ["NEW", "RESERVED", "STARTED", "COMPLETED", "FAILED", "UNKNOWN"])
def test_snapshot_forward_revision_cannot_leave_terminal_state(sample, terminal, target):
    m, binding, event = sample
    with pytest.raises(ValueError, match="CandidateJournalStateRevisionInvalid"):
        m.check_snapshot_rollback(event(terminal, 3), event(target, 4), binding)


def test_snapshot_forward_revision_cannot_reverse_started(sample):
    m, binding, event = sample
    with pytest.raises(ValueError, match="CandidateJournalStateRevisionInvalid"):
        m.check_snapshot_rollback(event("STARTED", 2), event("RESERVED", 3), binding)


def test_snapshot_gap_without_complete_history_stays_on_hold(sample):
    m, binding, event = sample
    with pytest.raises(ValueError, match="CandidateJournalHistoryRequired"):
        m.check_snapshot_rollback(event("NEW", 0), event("COMPLETED", 3), binding)


def test_snapshot_equal_revision_is_only_idempotent_for_identical_content(sample):
    m, binding, event = sample
    entry = event("RESERVED", 1)
    m.check_snapshot_rollback(entry, deepcopy(entry), binding)
    changed = deepcopy(entry)
    changed["updated_at"] = event("RESERVED", 2)["updated_at"]
    with pytest.raises(ValueError, match="CandidateJournalRollbackOrRewrite"):
        m.check_snapshot_rollback(entry, changed, binding)


def test_snapshot_forward_revision_requires_monotonic_time(sample):
    m, binding, event = sample
    previous, observed = event("NEW", 0), event("RESERVED", 1)
    observed["updated_at"] = previous["updated_at"]
    with pytest.raises(ValueError, match="CandidateJournalTransitionForbidden"):
        m.check_snapshot_rollback(previous, observed, binding)


def test_snapshot_gap_accepts_only_complete_anchored_claimed_history(sample):
    m, binding, event = sample
    history = [event("NEW", 0), event("RESERVED", 1), event("STARTED", 2), event("COMPLETED", 3)]
    m.check_snapshot_rollback(history[1], history[-1], binding, history=history)
    assert m.check_history(history, binding)["authorized"] is False


@pytest.mark.parametrize(
    "mutation",
    ["partial", "missing", "duplicate", "reordered", "unanchored", "rewritten", "truncated"],
)
def test_snapshot_gap_rejects_corrupt_or_incomplete_history(sample, mutation):
    m, binding, event = sample
    history = [event("NEW", 0), event("RESERVED", 1), event("STARTED", 2), event("COMPLETED", 3)]
    previous, observed = deepcopy(history[1]), deepcopy(history[-1])
    if mutation == "partial":
        del history[2]["updated_at"]
    elif mutation == "missing":
        del history[2]
    elif mutation == "duplicate":
        history.insert(2, deepcopy(history[1]))
    elif mutation == "reordered":
        history[1], history[2] = history[2], history[1]
    elif mutation == "unanchored":
        history = history[1:]
    elif mutation == "rewritten":
        history[1]["updated_at"] = "2026-10-25T10:00:00.500000+00:00"
    elif mutation == "truncated":
        history.pop()
    with pytest.raises(ValueError):
        m.check_snapshot_rollback(previous, observed, binding, history=history)


def test_snapshot_supplied_history_cannot_hide_terminal_reset(sample):
    m, binding, event = sample
    history = [event("NEW", 0), event("RESERVED", 1), event("UNKNOWN", 2), event("NEW", 3)]
    with pytest.raises(ValueError, match="CandidateJournalStateRevisionInvalid"):
        m.check_snapshot_rollback(history[0], history[-1], binding, history=history)


@pytest.mark.parametrize(
    "state,revision,next_state,next_revision",
    [
        ("NEW", 3, "RESERVED", 4),
        ("RESERVED", 100, "STARTED", 101),
        ("STARTED", 100, "COMPLETED", 101),
        ("NEW", 100, "NEW", 100),
        ("COMPLETED", 100, "COMPLETED", 100),
    ],
)
def test_snapshot_cannot_trust_unreachable_state_revision(
    sample, state, revision, next_state, next_revision
):
    m, binding, event = sample
    with pytest.raises(ValueError, match="CandidateJournalStateRevisionInvalid"):
        m.check_snapshot_rollback(event(state, revision), event(next_state, next_revision), binding)
