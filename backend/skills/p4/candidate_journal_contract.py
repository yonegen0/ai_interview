"""Pure candidate journal checks; snapshots cannot establish persistent one-use rights.

No storage, locking, external I/O, retry granting, or authorization.
"""

from datetime import datetime

import candidate_approval_contract as approval_contract

STATES = {"NEW", "RESERVED", "STARTED", "COMPLETED", "FAILED", "UNKNOWN"}
TRANSITIONS = {
    "NEW": {"RESERVED"},
    "RESERVED": {"STARTED", "UNKNOWN"},
    "STARTED": {"COMPLETED", "FAILED", "UNKNOWN"},
    "COMPLETED": set(),
    "FAILED": set(),
    "UNKNOWN": set(),
}
# The non-retrying acyclic graph fixes every reachable state's event ordinal.
STATE_REVISIONS = {
    "NEW": {0},
    "RESERVED": {1},
    "STARTED": {2},
    "COMPLETED": {3},
    "FAILED": {3},
    "UNKNOWN": {2, 3},
}
FIELDS = {
    "schema_version",
    "kind",
    "namespace",
    "approval_id",
    "attempt_id",
    "source_sha",
    "plan_sha256",
    "state",
    "revision",
    "updated_at",
}
IDENTITY_FIELDS = {"namespace", "approval_id", "attempt_id", "source_sha", "plan_sha256"}


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def check_entry(entry: object, binding: object) -> datetime:
    """Verify structure and target, not whether this entry was ever committed."""
    require(type(entry) is dict and set(entry) == FIELDS, "CandidateJournalFields")
    require(
        type(binding) is dict and set(binding) == IDENTITY_FIELDS,
        "CandidateJournalBindingMissing",
    )
    require(
        type(entry["schema_version"]) is int
        and entry["schema_version"] == 3
        and entry["kind"] == "p4-bootstrap-candidate-journal-v3"
        and type(entry["state"]) is str
        and entry["state"] in STATES
        and type(entry["revision"]) is int
        and entry["revision"] >= 0
        and all(
            type(entry[key]) is type(binding[key]) and entry[key] == binding[key]
            for key in IDENTITY_FIELDS
        ),
        "CandidateJournalInvalid",
    )
    require(
        entry["namespace"] == approval_contract.preflight.NAMESPACE
        and all(
            approval_contract.hex_digest(entry[key], 40)
            for key in ("approval_id", "attempt_id", "source_sha")
        )
        and (entry["plan_sha256"] is None or approval_contract.hex_digest(entry["plan_sha256"])),
        "CandidateJournalIdentityInvalid",
    )
    require(
        entry["revision"] in STATE_REVISIONS[entry["state"]],
        "CandidateJournalStateRevisionInvalid",
    )
    return approval_contract.instant(entry["updated_at"])


def transition(previous: object, proposed: object, binding: object) -> dict[str, object]:
    """Check only an ordered claimed transition. Does not commit either record."""
    older = check_entry(previous, binding)
    newer = check_entry(proposed, binding)
    require(
        proposed["revision"] == previous["revision"] + 1
        and newer > older
        and proposed["state"] in TRANSITIONS[previous["state"]],
        "CandidateJournalTransitionForbidden",
    )
    return {
        "status": "OFFLINE_TRANSITION_CONSISTENT_NOT_PERSISTED",
        "transition_valid": True,
        "persistence_verified": False,
        "authorized": False,
    }


def check_history(entries: object, binding: object) -> dict[str, object]:
    """Detect missing/reordered events in *supplied* history, never authenticate it."""
    require(type(entries) is list and len(entries) > 0, "CandidateJournalMissing")
    check_entry(entries[0], binding)
    require(
        entries[0]["revision"] == 0 and entries[0]["state"] == "NEW",
        "CandidateJournalInitialStateInvalid",
    )
    for old, new in zip(entries, entries[1:], strict=False):
        transition(old, new, binding)
    return {
        "status": "OFFLINE_HISTORY_CONSISTENT_NOT_AUTHENTICATED",
        "state": entries[-1]["state"],
        "persistence_verified": False,
        "single_use_proven": False,
        "authorized": False,
    }


def check_unique_histories(histories: object) -> dict[str, object]:
    """Catch collisions visible in histories; omission/rollback remains unprovable."""
    require(type(histories) is list and len(histories) > 0, "CandidateJournalMissing")
    approvals: set[str] = set()
    attempts: set[str] = set()
    for history in histories:
        require(type(history) is list and bool(history), "CandidateJournalMissing")
        head = history[0]
        require(type(head) is dict, "CandidateJournalFields")
        binding = {key: head.get(key) for key in IDENTITY_FIELDS}
        check_history(history, binding)
        approval_id, attempt_id = head["approval_id"], head["attempt_id"]
        require(
            approval_id not in approvals and attempt_id not in attempts, "CandidateJournalIdReused"
        )
        approvals.add(approval_id)
        attempts.add(attempt_id)
    return {
        "status": "OFFLINE_VISIBLE_IDS_DISTINCT_ONLY",
        "global_uniqueness_proven": False,
        "authorized": False,
    }


def check_snapshot_rollback(
    previous_seen: object, observed: object, binding: object, *, history: object = None
) -> None:
    """Compare supplied views; gaps require complete, anchored claimed history.

    Validation errors require UNKNOWN/HOLD, never a retry. Even a complete
    caller-supplied history cannot authenticate storage or detect unseen rollback.
    """
    check_entry(previous_seen, binding)
    check_entry(observed, binding)
    require(
        observed["revision"] >= previous_seen["revision"]
        and (observed["revision"] != previous_seen["revision"] or observed == previous_seen),
        "CandidateJournalRollbackOrRewrite",
    )
    if history is not None:
        check_history(history, binding)
        require(
            history[-1] == observed
            and previous_seen["revision"] < len(history)
            and history[previous_seen["revision"]] == previous_seen,
            "CandidateJournalHistoryAnchorMismatch",
        )
    if observed["revision"] == previous_seen["revision"]:
        return
    if observed["revision"] == previous_seen["revision"] + 1:
        transition(previous_seen, observed, binding)
        return
    require(history is not None, "CandidateJournalHistoryRequired")


def crash_disposition(last_observed: object, binding: object) -> dict[str, object]:
    """On restart, RESERVED/STARTED is frozen as UNKNOWN; never retry automatically."""
    check_entry(last_observed, binding)
    state = last_observed["state"]
    return {
        "status": "OFFLINE_RESTART_HOLD",
        "effective_state": "UNKNOWN" if state in {"RESERVED", "STARTED"} else state,
        "retry_permitted": False,
        "authorized": False,
    }
