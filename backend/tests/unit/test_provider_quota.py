"""Paid providers share the existing owner/global UTC reservation records."""

from copy import deepcopy
from datetime import UTC, datetime
from itertools import count
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from conftest import uid
from test_openai_provider import Authentication, Transport, start
from test_star_assist import star as star

from interview_backend.bootstrap import build_runtime
from interview_backend.evaluation.openai_provider import OpenAIProvider, OpenAISettings
from interview_backend.evaluation.worker import Worker
from interview_backend.repositories.memory import MemoryUnit


def seed_usage(repository, user_calls, global_calls):
    from interview_backend.models.internal import ProviderUsage

    month = "2026-10"
    identifier = str(uuid5(NAMESPACE_URL, "interview-provider-usage:" + month))

    def seed(tx):
        for owner, calls in (("owner", user_calls), ("@ai-global-budget", global_calls)):
            tx.new(
                ("ProviderUsage", owner, identifier), ProviderUsage(owner, identifier, month, calls)
            )

    repository._atomic(seed)


def paid_star(star, *, user_limit=20, global_limit=600, claim=True):
    from interview_backend.evaluation.bedrock_provider import BedrockProvider, BedrockSettings
    from interview_backend.star_assist.live_provider import LiveStarProvider

    runtime, _, request, _, _, _, _, _, draft, _ = star
    calls = []

    def forbidden(**kwargs):
        calls.append(True)
        raise AssertionError("No transport may be constructed after quota rejection")

    provider = LiveStarProvider(
        BedrockProvider(
            settings=BedrockSettings(
                monthly_user_limit=user_limit, monthly_global_limit=global_limit
            ),
            client_factory=forbidden,
        )
    )
    status, body = request(
        "POST",
        "/star-assist/generations",
        {
            "starDraftId": draft["id"],
            "expectedVersion": 1,
        },
    )
    assert status == 202
    if not claim:
        return body["generationId"], provider, calls
    lease = runtime.repository.star_claim(
        "owner", body["generationId"], 1, str(uuid4()), provider.provider_id
    )
    return lease, provider, calls


def evaluation_lease(runtime):
    identifier = start(runtime, number=500)
    return runtime.repository.claim(
        "owner", identifier, 1, uid(950), runtime.worker.coaching_config
    ).lease


@pytest.mark.parametrize("user_calls,global_calls", [(20, 20), (0, 600)])
def test_paid_star_cannot_bypass_evaluation_budget(star, user_calls, global_calls):
    from interview_backend.star_assist.repository import ref

    runtime = star[0]
    seed_usage(runtime.repository, user_calls, global_calls)
    lease, _, calls = paid_star(star)
    before = runtime.repository.snapshot().provider_usage
    assert not runtime.repository.star_start(lease)
    job = runtime.repository._read(ref("StarGeneration", "owner", lease.id))
    assert job.status == "FAILED_BEFORE_START" and not job.call_started
    assert runtime.repository.star_quota("owner").body["user"] == {
        "reserved": 0,
        "consumed": 0,
        "remaining": 20,
    }
    assert runtime.repository.snapshot().provider_usage == before and calls == []


def test_star_reserves_last_combined_slot_once_then_evaluation_is_rejected(star):
    runtime = star[0]
    seed_usage(runtime.repository, 19, 599)
    lease, _, _ = paid_star(star)
    assert runtime.repository.star_start(lease)
    assert runtime.repository.star_start(lease)  # Same execution, durable confirmation only.
    assert (
        runtime.repository.reserve_provider_call(evaluation_lease(runtime), 20, 600).status
        == "limited"
    )
    usage = {row.owner: row.calls for row in runtime.repository.snapshot().provider_usage.values()}
    assert usage == {"owner": 20, "@ai-global-budget": 600}


def test_evaluation_and_star_compete_atomically_for_the_last_slot(star):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    runtime = star[0]
    seed_usage(runtime.repository, 19, 599)
    star_lease, _, _ = paid_star(star)
    normal_lease = evaluation_lease(runtime)
    barrier = Barrier(2)

    def reserve_star():
        barrier.wait()
        return runtime.repository.star_start(star_lease)

    def reserve_normal():
        barrier.wait()
        return runtime.repository.reserve_provider_call(normal_lease, 20, 600).status == "reserved"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(reserve_star), pool.submit(reserve_normal)
        assert sum((first.result(), second.result())) == 1
    usage = {row.owner: row.calls for row in runtime.repository.snapshot().provider_usage.values()}
    assert usage == {"owner": 20, "@ai-global-budget": 600}


def test_star_respects_lower_explicit_paid_limit(star):
    from interview_backend.star_assist.worker import StarWorker

    runtime = star[0]
    seed_usage(runtime.repository, 1, 1)
    identifier, provider, calls = paid_star(star, user_limit=1, claim=False)
    assert not StarWorker(runtime.repository, provider).run("owner", identifier)
    assert calls == []


def test_all_paid_provider_defaults_use_combined_ceiling():
    from interview_backend.evaluation.anthropic_provider import AnthropicSettings
    from interview_backend.evaluation.bedrock_provider import BedrockSettings

    for settings in (AnthropicSettings(), BedrockSettings(), OpenAISettings()):
        assert (settings.monthly_user_limit, settings.monthly_global_limit) == (20, 600)


class NeverCalledBedrock:
    provider_id = "bedrock:jp:haiku-5-5:low:2048:1:600"
    model_id = "anthropic.claude-haiku-5-5"
    settings = SimpleNamespace(monthly_user_limit=1, monthly_global_limit=600)

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
    assert Worker(runtime.repository, bedrock, runtime.worker.clock).run("same-owner", second)
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
    for user_limit, global_limit in ((21, 600), (20, 601), (True, 600), (100, 3000)):
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
    assert runtime.repository.reserve_provider_call(lease, 20, 600).status == "reserved"
    boundary = int(datetime(2026, 10, 1, tzinfo=UTC).timestamp() * 1000)
    assert captured[0].upper == boundary
    assert captured[0].valid(boundary - 1)
    assert not captured[0].valid(boundary)
