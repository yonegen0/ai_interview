"""Closure cannot act early, reopen an entry, or claim an unverified close."""

from copy import deepcopy

import pytest

from interview_backend.release_closure import close

TARGET = {
    "expires_at": 100,
    "api_id": "api",
    "mappings": ["worker", "stream"],
    "schedule_group": "invite",
    "distribution_id": "dist",
    "alarms": ["one", "two"],
}


class Cloud:
    def __init__(self):
        self.api = False
        self.mappings = dict.fromkeys(TARGET["mappings"], "Enabled")
        self.schedule = {
            "State": "ENABLED",
            "ScheduleExpression": "rate(1 minute)",
            "FlexibleTimeWindow": {"Mode": "OFF"},
            "Target": {"Arn": "recovery", "RoleArn": "role"},
            "ScheduleExpressionTimezone": "UTC",
            "Description": "preserve",
            "ActionAfterCompletion": "NONE",
        }
        self.distribution = {
            "Enabled": True,
            "CallerReference": "preserve",
            "Origins": {"Items": []},
        }
        self.deleted = False
        self.writes = []

    def get_api(self, **args):
        return {"DisableExecuteApiEndpoint": self.api}

    def update_api(self, **args):
        assert args == {"ApiId": "api", "DisableExecuteApiEndpoint": True}
        self.writes.append("api")
        self.api = True

    def get_event_source_mapping(self, **args):
        return {"State": self.mappings[args["UUID"]]}

    def update_event_source_mapping(self, **args):
        assert args["Enabled"] is False
        self.writes.append(args["UUID"])
        self.mappings[args["UUID"]] = "Disabled"

    def get_schedule(self, **args):
        return deepcopy(self.schedule)

    def update_schedule(self, **args):
        assert args["State"] == "DISABLED"
        for key, value in self.schedule.items():
            if key != "State":
                assert args[key] == value
        self.writes.append("schedule")
        self.schedule["State"] = "DISABLED"

    def get_distribution_config(self, **args):
        return {"ETag": "etag", "DistributionConfig": deepcopy(self.distribution)}

    def update_distribution(self, **args):
        assert args["IfMatch"] == "etag"
        assert args["DistributionConfig"] == self.distribution | {"Enabled": False}
        self.writes.append("distribution")
        self.distribution["Enabled"] = False

    def get_distribution(self, **args):
        return {"Distribution": {"DistributionConfig": self.distribution, "Status": "Deployed"}}

    def delete_alarms(self, **args):
        assert self.api and all(s == "Disabled" for s in self.mappings.values())
        assert self.schedule["State"] == "DISABLED" and not self.distribution["Enabled"]
        assert args["AlarmNames"] == TARGET["alarms"]
        self.deleted = True

    def describe_alarms(self, **args):
        return {"MetricAlarms": [] if self.deleted else [{}]}

    def clients(self):
        return dict.fromkeys(
            ("apigatewayv2", "lambda", "scheduler", "cloudfront", "cloudwatch"), self
        )


def test_closure_cannot_act_before_expiry():
    cloud = Cloud()
    with pytest.raises(ValueError, match="BeforeDeadline"):
        close(TARGET, cloud.clients(), clock=lambda: 99)
    assert not cloud.writes and not cloud.deleted


def test_closure_disables_exact_entries_preserves_configuration_and_is_idempotent():
    cloud = Cloud()
    result = close(TARGET, cloud.clients(), clock=lambda: 100)
    assert result["status"] == "PASS_CLOSED" and result["alarm_count"] == 0
    assert set(cloud.writes) == {"api", "worker", "stream", "schedule", "distribution"}
    cloud.writes.clear()
    assert close(TARGET, cloud.clients(), clock=lambda: 101) == result
    assert not cloud.writes


def test_failed_readback_keeps_alarms_and_never_claims_closed():
    cloud = Cloud()
    cloud.get_api = lambda **args: {"DisableExecuteApiEndpoint": False}
    with pytest.raises(RuntimeError, match="ClosureReadbackFailed"):
        close(TARGET, cloud.clients(), clock=lambda: 100)
    assert not cloud.deleted
