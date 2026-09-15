"""Copy-on-write Memory adapter for the same domain operations as DynamoDB."""

from copy import deepcopy
from threading import RLock
from time import monotonic

from interview_backend.models.internal import (
    Candidate,
    CandidatePage,
    CorruptCandidate,
    IntegrityError,
    RetryExhausted,
    State,
    StorageError,
)
from interview_backend.repositories.budget import remaining_budget
from interview_backend.repositories.codec import (
    PARTITIONS,
    encode,
    validate,
    validate_cursor_key,
    work,
)
from interview_backend.repositories.domain import DomainRepository, utc_ms

COLLECTIONS = {
    "Session": "sessions",
    "Attempt": "attempts",
    "Evaluation": "evaluations",
    "Dispatch": "dispatches",
    "IdempotencyRecord": "requests",
    "RecoveryCursor": "cursors",
}


class MemoryUnit:
    def __init__(self, state, revisions):
        self.state, self.revisions = state, revisions
        self.writes = {}
        self.window = None

    def location(self, reference):
        kind, owner, identifier = reference
        records = getattr(self.state, COLLECTIONS[kind])
        if kind == "IdempotencyRecord":
            return records, (owner, identifier)
        if kind == "RecoveryCursor":
            return records, identifier
        existing = records.get(identifier)
        return records, (
            (owner, identifier) if existing is not None and existing.owner != owner else identifier
        )

    def get(self, reference):
        records, identifier = self.location(reference)
        record = deepcopy(records.get(identifier))
        if record is not None:
            validate(record)
        return record

    def many(self, references):
        return [self.get(r) for r in references]

    def refresh(self, reference):
        return self.get(reference)

    def ignore_dependency(self, reference):
        pass  # One lock already protects the entire Memory snapshot.

    def revision(self, reference):
        return self.revisions.get(reference)

    def put(self, reference, record):
        encode(reference[0], record, (self.revision(reference) or 0) + 1)
        records, identifier = self.location(reference)
        records[identifier] = deepcopy(record)
        self.writes[reference] = record

    def new(self, reference, record):
        if self.get(reference) is not None:
            raise IntegrityError("id_collision")
        self.put(reference, record)


class MemoryRepository(DomainRepository):
    def __init__(self, clock=utc_ms, monotonic_clock=monotonic):
        super().__init__(clock)
        self._state = State()
        self._revisions = {}
        self._lock = RLock()
        self.monotonic = monotonic_clock

    def snapshot(self):
        with self._lock:
            return deepcopy(self._state)

    def _commit(self, candidate):
        self._state = candidate

    def _atomic(self, operation, *, temporal=False, conflict_once=False):
        deadline = self.monotonic() + 5
        with self._lock:
            for _ in range(4):
                unit = MemoryUnit(deepcopy(self._state), self._revisions)
                result = deepcopy(operation(unit))
                if not unit.writes:
                    return result
                remaining = remaining_budget.get()
                if self.monotonic() >= deadline or (remaining is not None and remaining() < 400):
                    raise RetryExhausted("storage_budget")
                if unit.window is not None and not unit.window.valid(self.clock()):
                    continue
                self._commit(unit.state)
                for reference in unit.writes:
                    self._revisions[reference] = self._revisions.get(reference, -1) + 1
                return result
            raise RetryExhausted("storage_retry")

    def due_candidates(self, partition, cutoff, cursor=None, limit=100):
        if partition not in PARTITIONS or limit != 100:
            raise ValueError("query_parameters")
        if cursor is not None:
            validate_cursor_key(cursor, partition)
        with self._lock:
            candidates = []
            for kind, records in (
                ("Dispatch", self._state.dispatches),
                ("Evaluation", self._state.evaluations),
            ):
                for record in records.values():
                    expected_partition = (
                        PARTITIONS[2]
                        if kind == "Evaluation" and record.worker_state == "running"
                        else PARTITIONS[0]
                        if kind == "Dispatch" and record.status == "PENDING"
                        else PARTITIONS[1]
                        if kind == "Dispatch" and record.status == "QUEUED"
                        else None
                    )
                    if expected_partition != partition:
                        continue
                    try:
                        index = work(record)
                    except TypeError, ValueError:
                        return CandidatePage((CorruptCandidate(None),), None)
                    if index is None or index[0] != partition:
                        continue
                    candidate_key = {
                        "PK": f"USER#{record.owner}",
                        "SK": f"{kind.upper()}#{record.id}",
                        "work_pk": index[0],
                        "work_sk": f"{index[1]:013d}#{record.id}",
                    }
                    if candidate_key["work_sk"] > f"{cutoff:013d}#~":
                        continue
                    try:
                        encode(kind, record, 0)
                    except StorageError, ValueError, TypeError:
                        candidates.append(CorruptCandidate(candidate_key))
                    else:
                        candidates.append(Candidate(record.owner, record.id, candidate_key))

            def ordering(key):
                return key["work_sk"], key["PK"], key["SK"]

            candidates.sort(key=lambda c: ordering(c.key))
            if cursor:
                candidates = [c for c in candidates if ordering(c.key) > ordering(cursor)]
            page = candidates[:limit]
            return CandidatePage(tuple(page), page[-1].key if len(candidates) > limit else None)
