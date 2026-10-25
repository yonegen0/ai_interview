"""Mock storage law/fault tests; no real hosts, persistence, AWS, or execution."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from test_p4_tools import tool


@pytest.fixture
def model():
    m = tool("candidate_journal_model")
    binding = {
        "namespace": m.contract.approval_contract.preflight.NAMESPACE,
        "approval_id": "a" * 40,
        "attempt_id": "b" * 40,
        "source_sha": "c" * 40,
        "plan_sha256": "d" * 64,
    }
    now = datetime(2026, 10, 25, tzinfo=UTC)

    def event(state, revision, **changes):
        return {
            **binding,
            "schema_version": 3,
            "kind": "p4-bootstrap-candidate-journal-v3",
            "state": state,
            "revision": revision,
            "updated_at": (now + timedelta(seconds=revision)).isoformat(),
            **changes,
        }

    return m, m.MockJournalRepository(), event


def test_mock_lifecycle_and_all_results_stay_non_authorizing(model):
    _, repo, event = model
    results = [repo.reserve(event("NEW", 0), event("RESERVED", 1))]
    results.append(repo.compare_and_swap(event("RESERVED", 1), event("STARTED", 2)))
    results.append(repo.compare_and_swap(event("STARTED", 2), event("COMPLETED", 3)))
    results.append(repo.read("b" * 40))
    for result in results:
        assert result["authorized"] is False
        assert result["persistence_verified"] is False
        assert result["global_uniqueness_proven"] is False
        assert result["retry_permitted"] is False


@pytest.mark.parametrize(
    "collision", ["approval", "attempt", "both", "approval-as-attempt", "attempt-as-approval"]
)
def test_two_host_clients_cannot_reserve_same_ids_in_shared_mock(model, collision):
    m, repo, event = model
    barrier = Barrier(2)

    def host(number):
        changes = {}
        if number == 1 and collision == "approval":
            changes["attempt_id"] = "e" * 40
        elif number == 1 and collision == "attempt":
            changes["approval_id"] = "f" * 40
        elif number == 1 and collision == "approval-as-attempt":
            changes = {"approval_id": "f" * 40, "attempt_id": "a" * 40}
        elif number == 1 and collision == "attempt-as-approval":
            changes = {"approval_id": "b" * 40, "attempt_id": "e" * 40}
        initial, reserved = event("NEW", 0, **changes), event("RESERVED", 1, **changes)
        barrier.wait(timeout=5)
        try:
            return repo.reserve(initial, reserved)
        except m.ModelConflict:
            return "conflict-hold"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(host, [0, 1]))
    assert outcomes.count("conflict-hold") == 1
    assert sum(type(outcome) is dict for outcome in outcomes) == 1


def test_distinct_mock_ids_can_reserve_independently(model):
    _, repo, event = model
    repo.reserve(event("NEW", 0), event("RESERVED", 1))
    changes = {"approval_id": "e" * 40, "attempt_id": "f" * 40}
    repo.reserve(event("NEW", 0, **changes), event("RESERVED", 1, **changes))
    assert repo.read("b" * 40)["entry"]["approval_id"] == "a" * 40
    assert repo.read("f" * 40)["entry"]["approval_id"] == "e" * 40


@pytest.mark.parametrize(
    "collision", ["approval", "attempt", "approval-as-attempt", "attempt-as-approval"]
)
def test_rejected_reservation_does_not_partially_consume_other_id(model, collision):
    m, repo, event = model
    repo.reserve(event("NEW", 0), event("RESERVED", 1))
    conflicting = {"approval_id": "a" * 40, "attempt_id": "e" * 40}
    if collision == "attempt":
        conflicting = {"approval_id": "f" * 40, "attempt_id": "b" * 40}
    elif collision == "approval-as-attempt":
        conflicting = {"approval_id": "f" * 40, "attempt_id": "a" * 40}
    elif collision == "attempt-as-approval":
        conflicting = {"approval_id": "b" * 40, "attempt_id": "e" * 40}
    with pytest.raises(m.ModelConflict):
        repo.reserve(event("NEW", 0, **conflicting), event("RESERVED", 1, **conflicting))
    fresh = {"approval_id": "f" * 40, "attempt_id": "e" * 40}
    assert (
        repo.reserve(event("NEW", 0, **fresh), event("RESERVED", 1, **fresh))["authorized"] is False
    )


def test_same_entry_cross_role_collision_is_rejected_without_consumption(model):
    _, repo, event = model
    same_id = {"attempt_id": "a" * 40}
    with pytest.raises(ValueError, match="CandidateJournalIdReused"):
        repo.reserve(event("NEW", 0, **same_id), event("RESERVED", 1, **same_id))
    assert repo.reserve(event("NEW", 0), event("RESERVED", 1))["authorized"] is False


@pytest.mark.parametrize("mutation", ["partial", "identity", "gap", "schema", "fault"])
def test_invalid_reservation_does_not_consume_either_id(model, mutation):
    _, repo, event = model
    initial, reserved = event("NEW", 0), event("RESERVED", 1)
    fault = None
    if mutation == "partial":
        del reserved["state"]
    elif mutation == "identity":
        reserved["approval_id"] = "e" * 40
    elif mutation == "gap":
        reserved["revision"] = 2
    elif mutation == "schema":
        reserved["schema_version"] = True
    elif mutation == "fault":
        fault = "unknown-fault-name"
    with pytest.raises(ValueError):
        repo.reserve(initial, reserved, fault=fault)
    assert repo.reserve(event("NEW", 0), event("RESERVED", 1))["authorized"] is False


def test_two_host_clients_share_one_cas_winner(model):
    m, repo, event = model
    repo.reserve(event("NEW", 0), event("RESERVED", 1))
    expected = repo.read("b" * 40)["entry"]
    barrier = Barrier(2)

    def host(_):
        barrier.wait(timeout=5)
        try:
            return repo.compare_and_swap(expected, event("STARTED", 2))
        except m.ModelConflict:
            return "conflict-hold"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(host, [0, 1]))
    assert outcomes.count("conflict-hold") == 1
    assert len(repo.read("b" * 40)["history"]) == 3


@pytest.mark.parametrize("fault", ["before_commit", "after_commit"])
def test_lost_reservation_response_cannot_authorize_retry(model, fault):
    m, repo, event = model
    with pytest.raises(m.ModelIndeterminateError, match="CandidateModelOutcomeUnknownHold"):
        repo.reserve(event("NEW", 0), event("RESERVED", 1), fault=fault)
    if fault == "before_commit":
        with pytest.raises(ValueError, match="CandidateModelHistoryMissingHold"):
            repo.read("b" * 40)
    else:
        result = repo.read("b" * 40)
        assert result["restart"]["effective_state"] == "UNKNOWN"
        assert result["restart"]["retry_permitted"] is False
        with pytest.raises(m.ModelConflict, match="CandidateModelIdReused"):
            repo.reserve(event("NEW", 0), event("RESERVED", 1))


@pytest.mark.parametrize("fault", ["before_commit", "after_commit"])
def test_lost_cas_response_is_unknown_even_if_readback_shows_commit(model, fault):
    m, repo, event = model
    repo.reserve(event("NEW", 0), event("RESERVED", 1))
    with pytest.raises(m.ModelIndeterminateError, match="CandidateModelOutcomeUnknownHold"):
        repo.compare_and_swap(event("RESERVED", 1), event("STARTED", 2), fault=fault)
    result = repo.read("b" * 40)
    assert result["entry"]["state"] == ("RESERVED" if fault == "before_commit" else "STARTED")
    assert result["restart"]["effective_state"] == "UNKNOWN"
    assert result["retry_permitted"] is False


@pytest.mark.parametrize("terminal", ["COMPLETED", "FAILED", "UNKNOWN"])
def test_terminal_states_cannot_restart_or_reuse_ids(model, terminal):
    m, repo, event = model
    repo.reserve(event("NEW", 0), event("RESERVED", 1))
    repo.compare_and_swap(event("RESERVED", 1), event("STARTED", 2))
    repo.compare_and_swap(event("STARTED", 2), event(terminal, 3))
    with pytest.raises(ValueError):
        repo.compare_and_swap(event(terminal, 3), event("STARTED", 4))
    with pytest.raises(m.ModelConflict):
        repo.reserve(event("NEW", 0), event("RESERVED", 1))


def test_reserved_crash_can_only_be_recorded_as_unknown(model):
    _, repo, event = model
    repo.reserve(event("NEW", 0), event("RESERVED", 1))
    repo.compare_and_swap(event("RESERVED", 1), event("UNKNOWN", 2))
    assert repo.read("b" * 40)["entry"]["state"] == "UNKNOWN"
    with pytest.raises(ValueError):
        repo.compare_and_swap(event("UNKNOWN", 2), event("STARTED", 3))


def test_input_output_mutation_cannot_rewrite_mock_history(model):
    m, repo, event = model
    initial, reserved = event("NEW", 0), event("RESERVED", 1)
    result = repo.reserve(initial, reserved)
    initial["approval_id"] = "e" * 40
    reserved["state"] = "COMPLETED"
    result["entry"]["state"] = "FAILED"
    view = repo.read("b" * 40)
    view["history"][0]["approval_id"] = "e" * 40
    view["entry"]["revision"] = 100
    assert repo.read("b" * 40)["history"] == [event("NEW", 0), event("RESERVED", 1)]
    with pytest.raises(m.ModelConflict):
        repo.reserve(event("NEW", 0), event("RESERVED", 1))


@pytest.mark.parametrize("mutation", ["missing", "rewrite", "gap", "identity", "backward"])
def test_partial_or_rewritten_cas_is_rejected_without_append(model, mutation):
    _, repo, event = model
    repo.reserve(event("NEW", 0), event("RESERVED", 1))
    expected, proposed = event("RESERVED", 1), event("STARTED", 2)
    if mutation == "missing":
        del proposed["updated_at"]
    elif mutation == "rewrite":
        expected["updated_at"] = "2026-10-25T00:00:00.500000+00:00"
    elif mutation == "gap":
        proposed["revision"] = 3
    elif mutation == "identity":
        proposed["approval_id"] = "f" * 40
    elif mutation == "backward":
        proposed = event("NEW", 2)
    before = deepcopy(repo.read("b" * 40)["history"])
    with pytest.raises(ValueError):
        repo.compare_and_swap(expected, proposed)
    assert repo.read("b" * 40)["history"] == before


def test_separate_instances_demonstrate_no_distributed_one_use_proof(model):
    m, one, event = model
    two = m.MockJournalRepository()
    assert one.reserve(event("NEW", 0), event("RESERVED", 1))["authorized"] is False
    assert two.reserve(event("NEW", 0), event("RESERVED", 1))["global_uniqueness_proven"] is False


def test_model_never_opens_network_or_starts_process(model, monkeypatch):
    import socket
    import subprocess

    def forbidden(*args, **kwargs):
        raise AssertionError("Mock repository cannot execute network or Terraform")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    _, repo, event = model
    repo.reserve(event("NEW", 0), event("RESERVED", 1))
    assert repo.read("b" * 40)["authorized"] is False
