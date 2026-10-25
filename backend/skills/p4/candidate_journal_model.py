"""In-memory fault/concurrency model. OFFLINE_ONLY / NON_AUTHORIZING.

One Python Lock models a single linearizable repository shared by test clients.
It is not durable, distributed, rollback resistant, or connected to a controller.
Losing a write response must always stop the caller, regardless of commit outcome.
"""

from copy import deepcopy
from threading import Lock

import candidate_journal_contract as contract


class ModelConflict(ValueError):
    """A claimed ID is used or the expected snapshot is stale. Never retry execution."""


class ModelIndeterminateError(RuntimeError):
    """Synthetic missing response. Caller must HOLD; it cannot infer commit outcome."""


def _binding(entry: object) -> dict[str, object]:
    contract.require(type(entry) is dict, "CandidateJournalFields")
    return {key: entry.get(key) for key in contract.IDENTITY_FIELDS}


def _fault(value: object) -> None:
    contract.require(
        value is None or type(value) is str and value in {"before_commit", "after_commit"},
        "CandidateModelFaultInvalid",
    )


def _result(entry: dict[str, object]) -> dict[str, object]:
    return {
        "status": "MOCK_JOURNAL_ONLY_HOLD",
        "entry": deepcopy(entry),
        "authorized": False,
        "retry_permitted": False,
        "persistence_verified": False,
        "global_uniqueness_proven": False,
    }


class MockJournalRepository:
    """Model atomic reservation and CAS only within this process and instance.

    The ID indexes never expire in this model. Two instances are independent and
    unsafe as a shared authority. Private state is not an authenticated trust root.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._used_ids: set[str] = set()
        self._histories: dict[str, list[dict[str, object]]] = {}

    def reserve(
        self, initial: object, reserved: object, *, fault: str | None = None
    ) -> dict[str, object]:
        """Atomically model NEW and RESERVED history plus both one-use indexes."""
        _fault(fault)
        initial, reserved = deepcopy(initial), deepcopy(reserved)
        binding = _binding(initial)
        contract.check_history([initial, reserved], binding)
        contract.require(reserved["state"] == "RESERVED", "CandidateModelReservationInvalid")
        approval_id, attempt_id = initial["approval_id"], initial["attempt_id"]
        with self._lock:
            if approval_id in self._used_ids or attempt_id in self._used_ids:
                raise ModelConflict("CandidateModelIdReused")
            if fault == "before_commit":
                raise ModelIndeterminateError("CandidateModelOutcomeUnknownHold")
            # No fault boundary exists between indexes and history: this is the
            # atomicity a real transactional storage adapter must independently prove.
            self._used_ids.update((approval_id, attempt_id))
            self._histories[attempt_id] = [initial, reserved]
            if fault == "after_commit":
                raise ModelIndeterminateError("CandidateModelOutcomeUnknownHold")
            return _result(reserved)

    def compare_and_swap(
        self, expected: object, proposed: object, *, fault: str | None = None
    ) -> dict[str, object]:
        """Require a complete matching snapshot; condition and append share the lock."""
        _fault(fault)
        expected, proposed = deepcopy(expected), deepcopy(proposed)
        binding = _binding(expected)
        contract.check_entry(expected, binding)
        contract.transition(expected, proposed, binding)
        with self._lock:
            history = self._histories.get(expected["attempt_id"])
            if history is None or history[-1] != expected:
                raise ModelConflict("CandidateModelCASConflict")
            contract.check_history([*history, proposed], binding)
            if fault == "before_commit":
                raise ModelIndeterminateError("CandidateModelOutcomeUnknownHold")
            history.append(proposed)
            if fault == "after_commit":
                raise ModelIndeterminateError("CandidateModelOutcomeUnknownHold")
            return _result(proposed)

    def read(self, attempt_id: object) -> dict[str, object]:
        """Return an isolated mock view, never a durable or authenticated receipt."""
        contract.require(
            contract.approval_contract.hex_digest(attempt_id, 40), "CandidateModelAttemptInvalid"
        )
        with self._lock:
            history = self._histories.get(attempt_id)
            contract.require(history is not None, "CandidateModelHistoryMissingHold")
            binding = _binding(history[0])
            contract.check_history(history, binding)
            return {
                **_result(history[-1]),
                "history": deepcopy(history),
                "restart": contract.crash_disposition(history[-1], binding),
            }
