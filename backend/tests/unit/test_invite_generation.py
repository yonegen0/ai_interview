"""Independent generation rejects legacy sources and preserves bounded observations."""

import json
from types import SimpleNamespace

import pytest
from test_p4_runtime import environment

from interview_backend.aws_settings import AwsSettings, ConfigurationError, function_environment
from interview_backend.observability import Metrics
from interview_backend.operational_logs import invocation_context, log_event


@pytest.mark.parametrize("role", ["api", "admin", "worker", "dispatcher"])
def test_invite_generation_accepts_only_its_own_resources(role):
    values = {
        k: v.replace("ai-interview-dev", "ai-interview-invite-g1")
        for k, v in environment(role).items()
    }
    settings = AwsSettings.load(values, role)
    assert settings.table == "ai-interview-invite-g1-main"
    assert function_environment(settings.function_name) == "invite-g1"
    for key in (
        ["INTERVIEW_TABLE_NAME", "INTERVIEW_FUNCTION_NAME"]
        + (["INTERVIEW_QUEUE_ARN"] if role == "worker" else [])
        + (
            [
                "INTERVIEW_QUEUE_ARN",
                "INTERVIEW_QUEUE_URL",
                "INTERVIEW_STREAM_ARN",
                "INTERVIEW_SCHEDULE_ARN",
            ]
            if role == "dispatcher"
            else []
        )
    ):
        for other in ["ai-interview-dev", "ai-interview-invite-g2"]:
            crossed = values | {key: values[key].replace("ai-interview-invite-g1", other)}
            with pytest.raises(ConfigurationError):
                AwsSettings.load(crossed, role)


def test_generation_metrics_and_logs_match_alarm_dimensions():
    output = []
    Metrics("worker", environment="invite-g1", sink=output.append).emit("OutcomeUnknown")
    assert json.loads(output.pop())["Environment"] == "invite-g1"
    with invocation_context("worker", "invite-g1", {}, SimpleNamespace()):
        log_event("provider_usage", sink=output.append)
    assert json.loads(output.pop())["environment"] == "invite-g1"


@pytest.mark.parametrize("value", ["invite-", "invite-G1", "invite-" + "x" * 17, "arbitrary"])
def test_unbounded_metric_generations_rejected(value):
    with pytest.raises(ValueError, match="InvalidMetricDimension"):
        Metrics("worker", environment=value)


@pytest.mark.parametrize(
    "name,expected",
    [
        ("ai-interview-dev-worker", "dev"),
        ("ai-interview-test-run1-dispatcher", "test"),
        ("ai-interview-invite-g1-worker", "invite-g1"),
        ("ai-interview-invite-g2-api", "invite-g2"),
    ],
)
def test_existing_and_invite_observability_names(name, expected):
    assert function_environment(name) == expected
