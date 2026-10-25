"""Local SQLite storage experiment. OFFLINE_ONLY / NON_AUTHORIZING.

One database serializes processes on one tested local filesystem. It is NOT a
distributed authority or an independently authenticated rollback checkpoint.
Hash chains detect corruption, not an owner rewriting the entire database.
No execution or retry API exists. An absent pre-commit write is never permission
to retry execution; resolving uncertainty requires an independent authority.
"""

import hashlib
import json
import os
import sqlite3
import stat
import uuid
from contextlib import closing, contextmanager
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

import candidate_journal_contract as contract
from candidate_journal_model import ModelConflict, ModelIndeterminateError, _binding, _fault

TABLES = (
    "CREATE TABLE metadata (id TEXT PRIMARY KEY CHECK(id='identity'), value TEXT NOT NULL)",
    "CREATE TABLE ids (id TEXT PRIMARY KEY, attempt TEXT NOT NULL, role TEXT NOT NULL)",
    "CREATE TABLE events (seq INTEGER PRIMARY KEY, attempt TEXT NOT NULL, "
    "operation TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL, "
    "digest TEXT NOT NULL, UNIQUE(attempt, revision))",
)
TRIGGERS = tuple(
    f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} "
    "BEGIN SELECT RAISE(ABORT, 'CandidateJournalAppendOnly'); END"
    for table in ("metadata", "ids", "events")
    for action in ("UPDATE", "DELETE")
)
SCHEMA = TABLES + TRIGGERS
OPERATIONS = {"maintenance-plan", "maintenance-apply", "recovery-plan", "recovery-apply"}


@dataclass(frozen=True)
class Checkpoint:
    """Caller-held observation only; storing this beside the DB adds no trust."""

    journal_id: str
    sequence: int
    digest: str


def encoded(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(previous: str, operation: str, payload: str) -> str:
    return hashlib.sha256(encoded([previous, operation, payload]).encode()).hexdigest()


def _path(path: Path) -> None:
    contract.require(path.is_absolute(), "CandidateStorageAbsolutePathRequiredHOLD")
    for part in (path, *path.parents):
        contract.require(
            not part.is_symlink() and not part.is_junction(), "CandidateStorageLinkedPathHOLD"
        )
    contract.require(stat.S_ISREG(path.stat().st_mode), "CandidateStorageRegularFileRequiredHOLD")


def _result(entry: dict[str, object], checkpoint: Checkpoint) -> dict[str, object]:
    return {
        "status": "LOCAL_SQLITE_COMMITTED_HOLD",
        "entry": deepcopy(entry),
        "checkpoint": checkpoint,
        "local_persistence_observed": True,
        "persistence_verified": False,
        "global_uniqueness_proven": False,
        "rollback_verification": "UNVERIFIED_HOLD",
        "authorized": False,
        "retry_permitted": False,
    }


def _commit_fault(stage: str, fault: str | None) -> None:
    if stage == fault:
        raise ModelIndeterminateError("CandidateStorageOutcomeUnknownHOLD")


class SQLiteJournalRepository:
    """Append-only API with atomic IDs/events, full-snapshot CAS and pinned identity.

    Explicit creation is separate from reopening: missing/corrupt files are never
    silently initialized. Only the same DB has a shared ID namespace. SQLite and
    filesystem ownership/locking/fsync are trust assumptions, not proven here.
    """

    @classmethod
    def create(cls, path: Path) -> SQLiteJournalRepository:
        path = Path(path)
        contract.require(path.is_absolute(), "CandidateStorageAbsolutePathRequiredHOLD")
        contract.require(
            all(not p.is_symlink() and not p.is_junction() for p in path.parents),
            "CandidateStorageLinkedPathHOLD",
        )
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        journal_id = uuid.uuid4().hex
        # Failures deliberately leave an incomplete file for diagnosis, never reuse.
        with closing(sqlite3.connect(path, isolation_level=None)) as connection:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            for statement in SCHEMA:
                connection.execute(statement)
            connection.execute("INSERT INTO metadata VALUES ('identity', ?)", (journal_id,))
            connection.commit()
        return cls(path, journal_id=journal_id)

    def __init__(
        self, path: Path, *, journal_id: str, checkpoint: Checkpoint | None = None
    ) -> None:
        contract.require(
            type(journal_id) is str
            and len(journal_id) == 32
            and all(c in "0123456789abcdef" for c in journal_id),
            "CandidateStorageIdentityInvalidHOLD",
        )
        self.path = Path(path)
        self.journal_id = journal_id
        self._checkpoint = checkpoint
        self._uncertain = False
        self._lock = RLock()
        with self._transaction() as connection:
            self._scan(connection)

    @contextmanager
    def _transaction(self):
        self._lock.acquire()
        connection = None
        try:
            _path(self.path)
            before = self.path.stat()
            connection = sqlite3.connect(
                self.path.as_uri() + "?mode=rw", uri=True, isolation_level=None, timeout=10
            )
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA synchronous=FULL")
            contract.require(
                connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete",
                "CandidateStorageJournalModeHOLD",
            )
            connection.execute("BEGIN IMMEDIATE")
            _path(self.path)
            after = self.path.stat()
            contract.require(
                (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino),
                "CandidateStorageReplacementHOLD",
            )
            yield connection
        except (sqlite3.Error, OSError) as exc:
            self._uncertain = True
            raise ModelIndeterminateError("CandidateStorageUnavailableOrCorruptHOLD") from exc
        finally:
            if connection is not None:
                connection.close()  # Rolls back any uncommitted transaction.
            self._lock.release()

    def _scan(self, connection):
        contract.require(
            connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)],
            "CandidateStorageIntegrityHOLD",
        )
        schema = {
            row[0]
            for row in connection.execute(
                "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
            )
        }
        contract.require(schema == set(SCHEMA), "CandidateStorageSchemaHOLD")
        contract.require(
            connection.execute("SELECT * FROM metadata").fetchall()
            == [("identity", self.journal_id)],
            "CandidateStorageIdentityMismatchHOLD",
        )
        previous = hashlib.sha256(self.journal_id.encode()).hexdigest()
        chain = [previous]
        histories = {}
        operations = {}
        for seq, attempt, operation, revision, raw, digest in connection.execute(
            "SELECT * FROM events ORDER BY seq"
        ):
            contract.require(
                seq == len(chain)
                and operation in OPERATIONS
                and digest == _digest(previous, operation, raw),
                "CandidateStorageChainHOLD",
            )
            try:
                entry = json.loads(raw)
            except (ValueError, RecursionError) as exc:
                raise ValueError("CandidateStoragePayloadHOLD") from exc
            contract.require(
                type(entry) is dict
                and encoded(entry) == raw
                and entry.get("attempt_id") == attempt
                and entry.get("revision") == revision,
                "CandidateStoragePayloadHOLD",
            )
            history = histories.setdefault(attempt, [])
            history.append(entry)
            contract.check_history(history, _binding(history[0]))
            contract.require(
                operations.setdefault(attempt, operation) == operation
                and (entry["plan_sha256"] is None) == operation.endswith("-plan"),
                "CandidateStorageOperationHOLD",
            )
            previous = digest
            chain.append(previous)
        expected_ids = set()
        for attempt, history in histories.items():
            contract.require(len(history) >= 2, "CandidateStorageIncompleteReservationHOLD")
            for role in ("approval", "attempt"):
                expected_ids.add((history[0][f"{role}_id"], attempt, role))
        if histories:
            contract.check_unique_histories(list(histories.values()))
        contract.require(
            set(connection.execute("SELECT * FROM ids")) == expected_ids,
            "CandidateStorageTombstonesHOLD",
        )
        floor = self._checkpoint
        if floor is not None:
            contract.require(
                type(floor) is Checkpoint
                and floor.journal_id == self.journal_id
                and type(floor.sequence) is int
                and 0 <= floor.sequence < len(chain)
                and floor.digest == chain[floor.sequence],
                "CandidateStorageRollbackHOLD",
            )
        head = Checkpoint(self.journal_id, len(chain) - 1, chain[-1])
        return histories, operations, head

    def _finish(self, connection, fault):
        _commit_fault("before_commit", fault)
        connection.commit()
        _commit_fault("after_commit", fault)

    def _write(self, expected, proposed, *, operation=None, fault=None):
        _fault(fault)
        contract.require(not self._uncertain, "CandidateStorageUncertaintyHOLD")
        expected, proposed = deepcopy(expected), deepcopy(proposed)
        binding = _binding(expected)
        contract.transition(expected, proposed, binding)
        reserving = expected["state"] == "NEW"
        if reserving:
            contract.require(proposed["state"] == "RESERVED", "CandidateStorageReservationHOLD")
            if operation is None:
                operation = (
                    "maintenance-plan" if expected["plan_sha256"] is None else "maintenance-apply"
                )
            contract.require(
                type(operation) is str
                and operation in OPERATIONS
                and (expected["plan_sha256"] is None) == operation.endswith("-plan"),
                "CandidateStorageOperationHOLD",
            )
        try:
            with self._transaction() as connection:
                contract.require(not self._uncertain, "CandidateStorageUncertaintyHOLD")
                histories, operations, head = self._scan(connection)
                attempt = expected["attempt_id"]
                if reserving:
                    ids = {row[0] for row in connection.execute("SELECT id FROM ids")}
                    if expected["approval_id"] in ids or attempt in ids:
                        raise ModelConflict("CandidateStorageIdReusedHOLD")
                    for role in ("approval", "attempt"):
                        connection.execute(
                            "INSERT INTO ids VALUES (?, ?, ?)",
                            (expected[f"{role}_id"], attempt, role),
                        )
                    append = [expected, proposed]
                else:
                    if attempt not in histories or histories[attempt][-1] != expected:
                        raise ModelConflict("CandidateStorageCASConflictHOLD")
                    operation = operations[attempt]
                    contract.check_history([*histories[attempt], proposed], binding)
                    append = [proposed]
                for entry in append:
                    raw = encoded(entry)
                    head = Checkpoint(
                        self.journal_id, head.sequence + 1, _digest(head.digest, operation, raw)
                    )
                    connection.execute(
                        "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
                        (head.sequence, attempt, operation, entry["revision"], raw, head.digest),
                    )
                self._finish(connection, fault)
                self._checkpoint = head
                return _result(proposed, head)
        except ModelIndeterminateError:
            self._uncertain = True
            raise

    def reserve(
        self,
        initial: object,
        reserved: object,
        *,
        fault: str | None = None,
        operation: str | None = None,
    ) -> dict[str, object]:
        return self._write(initial, reserved, operation=operation, fault=fault)

    def compare_and_swap(
        self, expected: object, proposed: object, *, fault: str | None = None
    ) -> dict[str, object]:
        return self._write(expected, proposed, fault=fault)

    def read(self, attempt_id: object) -> dict[str, object]:
        return self.read_many((attempt_id,))[0]

    def read_many(self, attempt_ids: tuple[str, ...]) -> list[dict[str, object]]:
        """Observe related attempts at one serialized database checkpoint."""
        contract.require(
            type(attempt_ids) is tuple
            and bool(attempt_ids)
            and all(contract.approval_contract.hex_digest(value, 40) for value in attempt_ids)
            and len(set(attempt_ids)) == len(attempt_ids),
            "CandidateStorageAttemptInvalidHOLD",
        )
        with self._transaction() as connection:
            histories, operations, head = self._scan(connection)
            result = []
            for attempt_id in attempt_ids:
                contract.require(attempt_id in histories, "CandidateStorageHistoryMissingHOLD")
                history = histories[attempt_id]
                result.append(
                    {
                        **_result(history[-1], head),
                        "history": deepcopy(history),
                        "operation": operations[attempt_id],
                        "restart": contract.crash_disposition(history[-1], _binding(history[0])),
                    }
                )
            self._checkpoint = head
            return result
