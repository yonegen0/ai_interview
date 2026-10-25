"""Real disposable SQLite/process tests; no AWS, Terraform or production journals."""

import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_p4_tools import tool


@pytest.fixture
def storage(tmp_path):
    m = tool("candidate_journal_sqlite")
    repo = m.SQLiteJournalRepository.create(tmp_path / "journal.db")

    def event(state, revision, **changes):
        return {
            "schema_version": 3,
            "kind": "p4-bootstrap-candidate-journal-v3",
            "namespace": m.contract.approval_contract.preflight.NAMESPACE,
            "approval_id": "a" * 40,
            "attempt_id": "b" * 40,
            "source_sha": "c" * 40,
            "plan_sha256": "d" * 64,
            "state": state,
            "revision": revision,
            "updated_at": (
                datetime(2026, 10, 25, tzinfo=UTC) + timedelta(seconds=revision)
            ).isoformat(),
            **changes,
        }

    return m, repo, event


def reopen(m, repo, checkpoint=None):
    return m.SQLiteJournalRepository(repo.path, journal_id=repo.journal_id, checkpoint=checkpoint)


def test_persistent_lifecycle_and_reopen_preserve_consumption(storage):
    m, repo, event = storage
    result = repo.reserve(event("NEW", 0), event("RESERVED", 1))
    restored = reopen(m, repo, result["checkpoint"])
    assert restored.read("b" * 40)["restart"]["effective_state"] == "UNKNOWN"
    restored.compare_and_swap(event("RESERVED", 1), event("STARTED", 2))
    result = restored.compare_and_swap(event("STARTED", 2), event("COMPLETED", 3))
    assert reopen(m, repo).read("b" * 40)["entry"]["state"] == "COMPLETED"
    assert result["authorized"] is False
    assert result["global_uniqueness_proven"] is False
    assert result["rollback_verification"] == "UNVERIFIED_HOLD"
    assert result["retry_permitted"] is False
    with pytest.raises(m.ModelConflict):
        reopen(m, repo).reserve(event("NEW", 0), event("RESERVED", 1))


@pytest.mark.parametrize(
    "collision", ["approval", "attempt", "approval-as-attempt", "attempt-as-approval", "swap"]
)
def test_global_roles_and_plan_apply_collisions_leave_no_partial_ids(storage, collision):
    m, repo, event = storage
    repo.reserve(event("NEW", 0, plan_sha256=None), event("RESERVED", 1, plan_sha256=None))
    changes = {"approval_id": "e" * 40, "attempt_id": "f" * 40}
    if collision == "approval":
        changes["approval_id"] = "a" * 40
    elif collision == "attempt":
        changes["attempt_id"] = "b" * 40
    elif collision == "approval-as-attempt":
        changes["attempt_id"] = "a" * 40
    elif collision == "attempt-as-approval":
        changes["approval_id"] = "b" * 40
    else:
        changes = {"approval_id": "b" * 40, "attempt_id": "a" * 40}
    with pytest.raises(m.ModelConflict):
        repo.reserve(event("NEW", 0, **changes), event("RESERVED", 1, **changes))
    fresh = {"approval_id": "e" * 40, "attempt_id": "f" * 40}
    repo.reserve(event("NEW", 0, **fresh), event("RESERVED", 1, **fresh))


def test_threads_and_stale_complete_snapshot_cas(storage):
    m, repo, event = storage

    def reserve(_):
        try:
            reopen(m, repo).reserve(event("NEW", 0), event("RESERVED", 1))
            return "committed"
        except m.ModelConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sorted(pool.map(reserve, range(4))) == [
            "committed",
            "conflict",
            "conflict",
            "conflict",
        ]
    repo.compare_and_swap(event("RESERVED", 1), event("STARTED", 2))
    with pytest.raises(m.ModelConflict):
        repo.compare_and_swap(event("RESERVED", 1), event("STARTED", 2))
    forged = event("STARTED", 2, updated_at="2026-10-25T00:00:02.500000+00:00")
    with pytest.raises(m.ModelConflict):
        repo.compare_and_swap(forged, event("COMPLETED", 3))


def child_script(repo, event, action):
    return "\n".join(
        [
            "import sys, os, json",
            f"sys.path.insert(0, {str(Path(tool('candidate_journal_sqlite').__file__).parent)!r})",
            "import candidate_journal_sqlite as m",
            f"repo = m.SQLiteJournalRepository({str(repo.path)!r}, journal_id={repo.journal_id!r})",
            f"initial = json.loads({json.dumps(event('NEW', 0))!r})",
            f"reserved = json.loads({json.dumps(event('RESERVED', 1))!r})",
            action,
        ]
    )


def test_separate_processes_compete_on_same_database(storage):
    m, repo, event = storage
    action = "try:\n repo.reserve(initial, reserved)\nexcept m.ModelConflict:\n sys.exit(23)"
    script = child_script(repo, event, action)
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        for _ in range(4)
    ]
    exits = []
    for process in processes:
        _, error = process.communicate(timeout=30)
        assert process.returncode in (0, 23), error.decode()
        exits.append(process.returncode)
    assert sorted(exits) == [0, 23, 23, 23]
    assert reopen(m, repo).read("b" * 40)["entry"] == event("RESERVED", 1)


@pytest.mark.parametrize("stage,committed", [("before_commit", False), ("after_commit", True)])
def test_process_exit_at_commit_boundaries_is_atomic_and_never_grants_retry(
    storage, stage, committed
):
    m, repo, event = storage
    action = (
        f"def crash(phase, fault):\n if phase == {stage!r}: os._exit(71)\n"
        "m._commit_fault = crash\nrepo.reserve(initial, reserved)"
    )
    process = subprocess.run(
        [sys.executable, "-c", child_script(repo, event, action)], capture_output=True, timeout=30
    )
    assert process.returncode == 71, process.stderr.decode()
    restored = reopen(m, repo)
    if committed:
        assert restored.read("b" * 40)["restart"]["retry_permitted"] is False
        with pytest.raises(m.ModelConflict):
            restored.reserve(event("NEW", 0), event("RESERVED", 1))
    else:
        with pytest.raises(ValueError, match="HistoryMissingHOLD"):
            restored.read("b" * 40)
        with closing(sqlite3.connect(repo.path)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM ids").fetchone() == (0,)
            assert connection.execute("SELECT COUNT(*) FROM events").fetchone() == (0,)


@pytest.mark.parametrize("stage", ["before_commit", "after_commit"])
def test_response_loss_poisoned_client_and_recovery_no_retry(storage, stage):
    m, repo, event = storage
    with pytest.raises(m.ModelIndeterminateError):
        repo.reserve(event("NEW", 0), event("RESERVED", 1), fault=stage)
    with pytest.raises(ValueError, match="UncertaintyHOLD"):
        repo.reserve(event("NEW", 0), event("RESERVED", 1))
    if stage == "after_commit":
        observed = reopen(m, repo).read("b" * 40)
        assert observed["restart"]["effective_state"] == "UNKNOWN"
        assert observed["retry_permitted"] is False


def test_unknown_terminal_and_operation_cannot_change(storage):
    m, repo, event = storage
    with pytest.raises(ValueError, match="OperationHOLD"):
        repo.reserve(event("NEW", 0), event("RESERVED", 1), operation="recovery-plan")
    repo.reserve(event("NEW", 0), event("RESERVED", 1), operation="recovery-apply")
    repo.compare_and_swap(event("RESERVED", 1), event("UNKNOWN", 2))
    with pytest.raises(ValueError):
        repo.compare_and_swap(event("UNKNOWN", 2), event("STARTED", 3))
    assert repo.read("b" * 40)["operation"] == "recovery-apply"


def test_append_only_sql_tombstones_and_events(storage):
    _, repo, event = storage
    repo.reserve(event("NEW", 0), event("RESERVED", 1))
    for table in ("ids", "events", "metadata"):
        for action in (f"DELETE FROM {table}", f"UPDATE {table} SET rowid=rowid"):
            with closing(sqlite3.connect(repo.path)) as connection:
                with pytest.raises(sqlite3.IntegrityError, match="AppendOnly"):
                    connection.execute(action)


@pytest.mark.parametrize("damage", ["torn", "empty", "deleted", "payload", "ids", "schema"])
def test_corruption_incomplete_replacement_and_tamper_hold(storage, damage):
    m, repo, event = storage
    repo.reserve(event("NEW", 0), event("RESERVED", 1))
    if damage == "torn":
        repo.path.write_bytes(repo.path.read_bytes()[:177])
    elif damage == "empty":
        repo.path.write_bytes(b"")
    elif damage == "deleted":
        repo.path.unlink()
    else:
        with closing(sqlite3.connect(repo.path)) as connection:
            table = {"payload": "events", "ids": "ids", "schema": "metadata"}[damage]
            connection.execute(f"DROP TRIGGER {table}_delete")
            connection.execute(f"DELETE FROM {table}")
            connection.commit()
    with pytest.raises((ValueError, m.ModelIndeterminateError)):
        reopen(m, repo)
    if damage == "deleted":
        assert not repo.path.exists()


def test_checkpoint_detects_valid_old_database_and_same_sequence_rewrite(storage, tmp_path):
    m, repo, event = storage
    repo.reserve(event("NEW", 0), event("RESERVED", 1))
    previous = repo.path.read_bytes()
    result = repo.compare_and_swap(event("RESERVED", 1), event("STARTED", 2))
    repo.path.write_bytes(previous)
    with pytest.raises(ValueError, match="RollbackHOLD"):
        reopen(m, repo, result["checkpoint"])
    # Without an independently retained floor, this valid old DB is undetectable.
    assert reopen(m, repo).read("b" * 40)["rollback_verification"] == "UNVERIFIED_HOLD"
    bad = m.Checkpoint(repo.journal_id, 2, "0" * 64)
    with pytest.raises(ValueError, match="RollbackHOLD"):
        reopen(m, repo, bad)


def test_create_never_overwrites_and_new_identity_rejected(storage, tmp_path):
    m, repo, _ = storage
    original = repo.path.read_bytes()
    with pytest.raises(FileExistsError):
        m.SQLiteJournalRepository.create(repo.path)
    assert repo.path.read_bytes() == original
    other = m.SQLiteJournalRepository.create(tmp_path / "other.db")
    repo.path.write_bytes(other.path.read_bytes())
    with pytest.raises(ValueError, match="IdentityMismatchHOLD"):
        reopen(m, repo)


def test_database_and_checkpoint_rollback_together_cannot_prove_one_use(storage):
    m, repo, event = storage
    checkpoint = repo.reserve(event("NEW", 0), event("RESERVED", 1))["checkpoint"]
    previous = repo.path.read_bytes()
    changes = {"approval_id": "e" * 40, "attempt_id": "f" * 40}
    repo.reserve(event("NEW", 0, **changes), event("RESERVED", 1, **changes))
    repo.path.write_bytes(previous)
    restored = reopen(m, repo, checkpoint)
    result = restored.reserve(event("NEW", 0, **changes), event("RESERVED", 1, **changes))
    # The caller's floor was also rolled back: local consistency is not authority.
    assert result["authorized"] is False
    assert result["retry_permitted"] is False
    assert result["rollback_verification"] == "UNVERIFIED_HOLD"


def test_separate_databases_do_not_share_id_consumption(storage, tmp_path):
    m, repo, event = storage
    other = m.SQLiteJournalRepository.create(tmp_path / "independent.db")
    for database in (repo, other):
        result = database.reserve(event("NEW", 0), event("RESERVED", 1))
        assert result["global_uniqueness_proven"] is False
        assert result["authorized"] is False
        assert result["retry_permitted"] is False


def test_no_network_or_aws_and_copy_isolation(storage, monkeypatch):
    import socket

    import boto3

    def forbidden(*args, **kwargs):
        raise AssertionError("External side effect forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(boto3, "client", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    _, repo, event = storage
    initial, reserved = event("NEW", 0), event("RESERVED", 1)
    result = repo.reserve(initial, reserved)
    result["entry"]["state"] = "COMPLETED"
    reserved["approval_id"] = "f" * 40
    assert repo.read("b" * 40)["entry"] == event("RESERVED", 1)


@pytest.mark.parametrize("damage", ["chain", "incomplete", "tombstone"])
def test_schema_restored_after_tamper_still_rejected(storage, damage):
    m, repo, event = storage
    repo.reserve(event("NEW", 0), event("RESERVED", 1))
    with closing(sqlite3.connect(repo.path)) as connection:
        trigger = "ids_delete" if damage == "tombstone" else "events_delete"
        if damage == "chain":
            trigger = "events_update"
        original = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name=?", (trigger,)
        ).fetchone()[0]
        connection.execute(f"DROP TRIGGER {trigger}")
        if damage == "chain":
            connection.execute("UPDATE events SET digest=? WHERE seq=2", ("f" * 64,))
        elif damage == "incomplete":
            connection.execute("DELETE FROM events WHERE seq=2")
        else:
            connection.execute("DELETE FROM ids WHERE role='approval'")
        connection.execute(original)
        connection.commit()
    reason = {
        "chain": "ChainHOLD",
        "incomplete": "IncompleteReservationHOLD",
        "tombstone": "TombstonesHOLD",
    }[damage]
    with pytest.raises(ValueError, match=reason):
        reopen(m, repo)


@pytest.mark.parametrize("stage", ["before_commit", "after_commit"])
def test_injected_filesystem_error_poisoned_writer_preserves_atomic_state(
    storage, monkeypatch, stage
):
    m, repo, event = storage

    def fail(phase, fault):
        if phase == stage:
            raise OSError("synthetic disk sync failure")

    monkeypatch.setattr(m, "_commit_fault", fail)
    with pytest.raises(m.ModelIndeterminateError, match="UnavailableOrCorruptHOLD"):
        repo.reserve(event("NEW", 0), event("RESERVED", 1))
    with pytest.raises(ValueError, match="UncertaintyHOLD"):
        repo.reserve(event("NEW", 0), event("RESERVED", 1))
    restored = reopen(m, repo)
    if stage == "after_commit":
        assert restored.read("b" * 40)["restart"]["effective_state"] == "UNKNOWN"
    else:
        with pytest.raises(ValueError, match="HistoryMissingHOLD"):
            restored.read("b" * 40)


@pytest.mark.parametrize("invalid", [[], None, 1, True, "", "a"])
def test_invalid_read_id_is_a_contract_error(storage, invalid):
    _, repo, _ = storage
    with pytest.raises(ValueError, match="AttemptInvalidHOLD"):
        repo.read(invalid)


def test_related_reads_share_one_checkpoint_and_reject_duplicates(storage):
    _, repo, event = storage
    repo.reserve(event("NEW", 0), event("RESERVED", 1))
    changes = {"approval_id": "e" * 40, "attempt_id": "f" * 40}
    repo.reserve(event("NEW", 0, **changes), event("RESERVED", 1, **changes))
    observations = repo.read_many(("b" * 40, "f" * 40))
    assert observations[0]["checkpoint"] == observations[1]["checkpoint"]
    with pytest.raises(ValueError, match="AttemptInvalidHOLD"):
        repo.read_many(("b" * 40, "b" * 40))
