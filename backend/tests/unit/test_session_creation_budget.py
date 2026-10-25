"""Bounded Session creation: offline domain, codec and concurrency regression tests."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from itertools import count
from threading import Barrier
from uuid import NAMESPACE_URL, uuid5

import pytest
from conftest import uid

from interview_backend.application.service import Application
from interview_backend.assets import load_questions
from interview_backend.models.internal import (
    BusinessError,
    IntegrityError,
    SessionCreationBudget,
    StorageFormatError,
)
from interview_backend.repositories import domain
from interview_backend.repositories.codec import decode, encode
from interview_backend.repositories.memory import MemoryRepository

PAYLOAD = {"category": "job_change", "difficulty": "standard"}
OWNER = "session-budget-owner"


def app_for(clock):
    identifiers = count(1)
    repository = MemoryRepository(clock)
    app = Application(repository, load_questions(), lambda: uid(next(identifiers)))
    return app, repository


def test_distinct_keys_have_hard_limit_and_replays_do_not_charge(monkeypatch):
    monkeypatch.setattr(domain, "SESSION_CREATION_MONTHLY_LIMIT", 3)
    app, repository = app_for(lambda: 1789084800000)
    first = app.create(OWNER, uid(100), PAYLOAD)
    assert first.status == 201
    assert app.create(OWNER, uid(100), PAYLOAD) == first
    assert app.create(OWNER, uid(101), PAYLOAD).status == 201
    assert app.create(OWNER, uid(102), PAYLOAD).status == 201

    with pytest.raises(BusinessError) as limit:
        app.create(OWNER, uid(103), PAYLOAD)
    assert (limit.value.status, limit.value.code) == (429, "SESSION_CREATION_LIMIT")
    with pytest.raises(BusinessError) as mismatch:
        app.create(OWNER, uid(100), {"category": "motivation", "difficulty": "standard"})
    assert mismatch.value.code == "IDEMPOTENCY_CONFLICT"
    assert app.create(OWNER, uid(100), PAYLOAD) == first
    assert app.create("different-owner", uid(103), PAYLOAD).status == 201

    state = repository.snapshot()
    assert len(state.sessions) == len(state.requests) == 4
    assert sorted(b.count for b in state.session_creation_budgets.values()) == [1, 3]
    assert (OWNER, uid(103)) not in state.requests


def test_utc_month_rollover_preserves_prior_session_and_replay(monkeypatch):
    monkeypatch.setattr(domain, "SESSION_CREATION_MONTHLY_LIMIT", 1)
    instant = [int(datetime(2026, 9, 30, 23, 59, tzinfo=UTC).timestamp() * 1000)]
    app, repository = app_for(lambda: instant[0])
    old = app.create(OWNER, uid(100), PAYLOAD)
    instant[0] = int(datetime(2026, 10, 1, 0, 1, tzinfo=UTC).timestamp() * 1000)
    assert app.create(OWNER, uid(100), PAYLOAD) == old
    fresh = app.create(OWNER, uid(101), PAYLOAD)
    assert fresh.body["sessionId"] != old.body["sessionId"]
    with pytest.raises(BusinessError) as limited:
        app.create(OWNER, uid(102), PAYLOAD)
    assert limited.value.status == 429
    assert app.question(OWNER, old.body["sessionId"]).status == 200
    months = {(v.month, v.count) for v in repository.snapshot().session_creation_budgets.values()}
    assert months == {
        ("2026-09", 1),
        ("2026-10", 1),
    }


def test_simultaneous_distinct_requests_cannot_exceed_limit(monkeypatch):
    monkeypatch.setattr(domain, "SESSION_CREATION_MONTHLY_LIMIT", 3)
    app, repository = app_for(lambda: 1789084800000)
    app.create(OWNER, uid(100), PAYLOAD)
    barrier = Barrier(6)

    def create(index):
        barrier.wait(timeout=10)
        try:
            return app.create(OWNER, uid(200 + index), PAYLOAD).status
        except BusinessError as exc:
            assert exc.code == "SESSION_CREATION_LIMIT"
            return exc.status

    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(create, range(6)))
    assert sorted(statuses) == [201, 201, 429, 429, 429, 429]
    state = repository.snapshot()
    assert len(state.sessions) == len(state.requests) == 3
    assert next(iter(state.session_creation_budgets.values())).count == 3


def test_session_budget_codec_and_invalid_calendar_month():
    identifier = str(uuid5(NAMESPACE_URL, "interview-session-budget:2026-09"))
    budget = SessionCreationBudget(OWNER, identifier, "2026-09", 2)
    serialized = encode("SessionCreationBudget", budget, 0)
    assert serialized["SK"] == "SESSION_BUDGET#" + identifier
    assert decode(serialized) == (budget, 0)
    with pytest.raises(StorageFormatError):
        encode("SessionCreationBudget", SessionCreationBudget(OWNER, identifier, "2026-13"), 0)


def test_second_boundary_with_one_second_precision(monkeypatch):
    monkeypatch.setattr(domain, "SESSION_CREATION_MONTHLY_LIMIT", 1)
    instant = [int(datetime(2026, 9, 30, 23, 59, 59, tzinfo=UTC).timestamp() * 1000)]
    app, repository = app_for(lambda: instant[0])
    september = app.create(OWNER, uid(300), PAYLOAD)
    with pytest.raises(BusinessError) as at_limit:
        app.create(OWNER, uid(301), PAYLOAD)
    assert (at_limit.value.status, at_limit.value.code) == (
        429, "SESSION_CREATION_LIMIT"
    )
    instant[0] = int(datetime(2026, 10, 1, 0, 0, 1, tzinfo=UTC).timestamp() * 1000)
    assert app.create(OWNER, uid(300), PAYLOAD) == september
    october = app.create(OWNER, uid(302), PAYLOAD)
    assert october.status == 201 and october.body != september.body
    with pytest.raises(BusinessError):
        app.create(OWNER, uid(303), PAYLOAD)
    assert sorted(
        (budget.month, budget.count)
        for budget in repository.snapshot().session_creation_budgets.values()
    ) == [("2026-09", 1), ("2026-10", 1)]


@pytest.mark.parametrize(
    "field,value",
    [
        ("count", "1"),
        ("count", True),
        ("count", -1),
        ("month", "2026-13"),
        ("month", "invalid"),
        ("owner", "another-user"),
        ("id", str(uuid5(NAMESPACE_URL, "interview-session-budget:2026-10"))),
    ],
)
def test_session_budget_corrupt_serialization_rejected(field, value):
    identifier = str(uuid5(NAMESPACE_URL, "interview-session-budget:2026-09"))
    item = encode(
        "SessionCreationBudget", SessionCreationBudget(OWNER, identifier, "2026-09", 1), 2
    )
    raw = json.loads(item["data"])
    raw[field] = value
    item["data"] = json.dumps(raw)
    with pytest.raises((StorageFormatError, IntegrityError)):
        decode(item)


def test_session_budget_wrong_reference_identity_fails_closed():
    app, repository = app_for(lambda: 1789171200000)
    first = app.create(OWNER, uid(400), PAYLOAD)
    month = "2026-09"
    identifier = str(uuid5(NAMESPACE_URL, "interview-session-budget:" + month))
    repository._state.session_creation_budgets[identifier].id = uid(888)
    with pytest.raises(IntegrityError):
        app.create(OWNER, uid(401), PAYLOAD)
    assert app.create(OWNER, uid(400), PAYLOAD) == first
    assert len(repository.snapshot().sessions) == 1
