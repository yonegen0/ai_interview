"""Focused safety contracts for the invite monitoring and deadline changes."""

import json
from types import SimpleNamespace

import pytest

from interview_backend.evaluation.anthropic_provider import AnthropicSettings
from interview_backend.evaluation.openai_provider import ProviderFailure
from interview_backend.observability import Metrics
from interview_backend.release_window import expired


def test_minimal_profile_emits_only_two_series_across_all_roles():
    rows = []
    for role in ("api", "worker", "dispatcher", "admin"):
        m = Metrics(role, environment="invite-g1", profile="minimal", sink=rows.append)
        for name in ("ApiRequest", "Unauthorized", "ApiDuration", "EvaluationCompleted"):
            m.emit(name)
        m.emit("IntegrityError")
        m.emit("EvaluationFailed")
        m.emit("OutcomeUnknown")
    Metrics("dispatcher", environment="invite-g1", profile="minimal", sink=rows.append).emit(
        "RecoveryHeartbeat"
    )
    series = set()
    for line in rows:
        item = json.loads(line)
        metric = item["_aws"]["CloudWatchMetrics"][0]
        assert metric["Dimensions"] == [["Project", "Environment"]]
        series.add(metric["Metrics"][0]["Name"])
    assert len(rows) == 13
    assert series == {"CriticalFailure", "RecoveryHeartbeat"}


def test_minimal_profile_detects_stalled_processing_without_extra_series():
    rows = []
    m = Metrics("dispatcher", environment="invite-g1", profile="minimal", sink=rows.append)
    m.emit("PendingAge", 120)
    m.emit("QueuedAge", 120)
    m.emit("RecoverySweepLag", 180)
    assert not rows
    for name, value in (("PendingAge", 121), ("QueuedAge", 121), ("RecoverySweepLag", 181)):
        m.emit(name, value)
    assert len(rows) == 3
    assert all(json.loads(row)["CriticalFailure"] == 1 for row in rows)


@pytest.mark.parametrize("value", ["bad", "-1", "1.5", None])
def test_invalid_deadline_fails_closed(value):
    assert expired({"INTERVIEW_RELEASE_EXPIRES_AT": value}, clock=lambda: 100)


def test_access_closes_at_exact_boundary_without_scheduler():
    env = {"INTERVIEW_RELEASE_EXPIRES_AT": "100"}
    assert not expired(env, clock=lambda: 99.999)
    assert expired(env, clock=lambda: 100)
    assert expired(env, clock=lambda: 101)
    assert not expired({}, clock=lambda: 100)


def test_expanded_emergency_limits_remain_finite_and_keep_legacy_defaults():
    settings = AnthropicSettings(monthly_user_limit=100, monthly_global_limit=2000)
    assert (settings.monthly_user_limit, settings.monthly_global_limit) == (100, 2000)
    assert AnthropicSettings().monthly_user_limit == 20
    for user, total in ((101, 2000), (100, 2001), (0, 2000), (True, 2000)):
        with pytest.raises(ProviderFailure, match="CONFIGURATION"):
            AnthropicSettings(monthly_user_limit=user, monthly_global_limit=total)


def test_expired_api_never_invokes_business_handler(monkeypatch):
    from interview_backend.aws_runtime import ApiEntry

    monkeypatch.setenv("INTERVIEW_RELEASE_EXPIRES_AT", "1")
    settings = SimpleNamespace(require_invocation=lambda *args: "live")
    called = []
    entry = ApiEntry(settings, lambda event: called.append(event))
    result = entry({}, SimpleNamespace())
    assert result["statusCode"] == 403
    assert not called


def test_star_options_and_quota_use_server_owned_limits(runtime):
    from interview_backend.star_assist.api import handle

    repo = runtime.repository
    repo.star_monthly_limits = (100, 2000)
    result = handle(repo, "owner", "GET", "/star-assist/options", {}, {})
    assert result.body["userMonthlyLimit"] == 100
    assert result.body["globalMonthlyLimit"] == 2000
    quota = repo.star_quota("owner").body
    assert quota["user"]["remaining"] == 100
    assert quota["global"]["remaining"] == 2000
