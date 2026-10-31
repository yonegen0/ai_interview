"""Paid providers share the existing owner/global UTC reservation records."""

from copy import deepcopy
from datetime import UTC, datetime
from itertools import count
from types import SimpleNamespace

import pytest
from conftest import uid
from test_openai_provider import Authentication, Transport, start

from interview_backend.bootstrap import build_runtime
from interview_backend.evaluation.openai_provider import OpenAIProvider, OpenAISettings
from interview_backend.evaluation.worker import Worker
from interview_backend.repositories.memory import MemoryUnit
from interview_backend.star_assist.provider import FakeStarProvider


class NeverCalledBedrock:
    provider_id = "bedrock:jp:haiku-5-5:low:2048:1:3000"
    model_id = "anthropic.claude-haiku-5-5"
    settings = SimpleNamespace(monthly_user_limit=1, monthly_global_limit=3000)

    def __init__(self):
        self.calls = 0

    def evaluate_with_deadline(self, prompt, deadline):
        self.calls += 1
        raise AssertionError("quota should stop this request")


def test_provider_switch_does_not_reset_owner_usage(runtime):
    openai = OpenAIProvider(
        Authentication(),
        transport=Transport(),
        settings=OpenAISettings(monthly_user_limit=1),
    )
    first = start(runtime, owner="same-owner", number=1)
    assert Worker(runtime.repository, openai, runtime.worker.clock).run("same-owner", first)
    bedrock = NeverCalledBedrock()
    second = start(runtime, owner="same-owner", number=2)
    # Quota test stub is not a real BedrockProvider; opt into the fake STAR
    # adapter explicitly rather than relying on an implicit paid-to-fake switch.
    worker = Worker(
        runtime.repository, bedrock, runtime.worker.clock, star_provider=FakeStarProvider()
    )
    assert worker.run("same-owner", second)
    assert bedrock.calls == 0
    snapshot = runtime.repository.snapshot()
    assert snapshot.evaluations[second].failure_reason == "PREPARATION_FAILED"
    assert (
        len([item for item in snapshot.provider_usage.values() if item.owner == "same-owner"]) == 1
    )
    assert (
        next(item for item in snapshot.provider_usage.values() if item.owner == "same-owner").calls
        == 1
    )


def test_repository_rejects_limits_above_shared_contract(runtime):
    evaluation_id = start(runtime, number=3)
    lease = runtime.repository.claim(
        "owner", evaluation_id, 1, uid(900), runtime.worker.coaching_config
    ).lease
    for user_limit, global_limit in ((101, 3000), (100, 3001), (True, 3000)):
        with pytest.raises(ValueError, match="provider_usage_limit"):
            runtime.repository.reserve_provider_call(lease, user_limit, global_limit)


def test_reservation_window_excludes_next_utc_month(monkeypatch):
    now = datetime(2026, 9, 30, 23, 59, 59, 500000, tzinfo=UTC)
    ids = count(1)
    runtime = build_runtime(clock=lambda: now, new_id=lambda: uid(next(ids)))
    evaluation_id = start(runtime, number=9)
    lease = runtime.repository.claim(
        "owner", evaluation_id, 1, uid(901), runtime.worker.coaching_config
    ).lease
    captured = []

    def inspect(operation, **kwargs):
        unit = MemoryUnit(deepcopy(runtime.repository._state), runtime.repository._revisions)
        result = operation(unit)
        captured.append(unit.window)
        return result

    monkeypatch.setattr(runtime.repository, "_atomic", inspect)
    assert runtime.repository.reserve_provider_call(lease, 100, 3000).status == "reserved"
    boundary = int(datetime(2026, 10, 1, tzinfo=UTC).timestamp() * 1000)
    assert captured[0].upper == boundary
    assert captured[0].valid(boundary - 1)
    assert not captured[0].valid(boundary)
