"""Bounded Session creation: offline domain, codec and concurrency regression tests."""

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
