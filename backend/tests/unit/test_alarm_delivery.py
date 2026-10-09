"""Bounded sparse/delayed metric model; this is not a CloudWatch acceptance test."""

from copy import deepcopy

import pytest
from test_p4_cost_controls import cost_deployment as cost_deployment
from test_p4_manifest_v3 import admin_deployment as admin_deployment
from test_provider_validation_tools import tool


@pytest.mark.parametrize(
    "metric,name", [("OutcomeUnknown", "OutcomeUnknown"), ("EvaluationFailed", "evaluation-failed")]
)
@pytest.mark.parametrize("source", ["worker", "dispatcher", "both", "none", "delayed"])
def test_sparse_single_and_delayed_failures_in_one_of_five_window(
    cost_deployment, monkeypatch, metric, name, source
):
    monkeypatch.syspath_prepend("skills/p4")
    manifest, _, _ = cost_deployment
    manifest["monitoring_contract_version"] = 2
    manifest["configuration"].update(
        api_enabled=True, worker_enabled=True, streams_enabled=True, scheduler_enabled=True
    )
    alarm = tool("manifest_alarms").expected_alarms(manifest, "dev")["dev-" + name]
    assert alarm["EvaluationPeriods"] == 5 and alarm["DatapointsToAlarm"] == 1
    assert alarm["TreatMissingData"] == "notBreaching"
    queries = [q for q in alarm["Metrics"] if "MetricStat" in q]
    assert len(queries) == 2
    assert {
        next(
            d["Value"] for d in q["MetricStat"]["Metric"]["Dimensions"] if d["Name"] == "Component"
        )
        for q in queries
    } == {"worker", "dispatcher"}
    assert all(q["MetricStat"]["Metric"]["MetricName"] == metric for q in queries)
    assert (
        alarm["Metrics"][0]["Expression"] == "SUM([wo,do])"
        if metric == "OutcomeUnknown"
        else alarm["Metrics"][0]["Expression"] == "SUM([wf,df])"
    )
    # A count timestamped at minute 0 becomes visible at minute 2 for delayed delivery.
    delivered_at = 2 if source == "delayed" else 0
    series = {
        "worker": {0: 1} if source in {"worker", "both", "delayed"} else {},
        "dispatcher": {0: 1} if source in {"dispatcher", "both"} else {},
    }

    def evaluate(now):
        if now < delivered_at:
            return False
        return any(
            sum(s.get(t, 0) for s in series.values()) >= alarm["Threshold"]
            for t in range(now - alarm["EvaluationPeriods"] + 1, now + 1)
        )

    assert evaluate(2) is (source != "none")
    assert evaluate(6) is False  # Recovery after the finite evidence window expires.


def test_reproduces_old_fill_latest_period_late_point_miss():
    # Illustrative evaluation model: FILL synthesizes the newest non-breaching 0.
    delivered = {0: 1}
    assert delivered.get(2, 0) < 1  # Old 1/1 selects the latest filled zero.
    assert any(delivered.get(t, 0) >= 1 for t in range(-2, 3))  # New 1/5 retains the point.


def test_worker_outcome_unknown_emits_the_exact_aggregated_dimension(runtime):
    import json

    from test_openai_provider import Authentication, Transport, start

    from interview_backend.evaluation.openai_provider import OpenAIProvider, ProviderFailure
    from interview_backend.evaluation.worker import Worker
    from interview_backend.observability import Metrics, ObservedRepository

    rows = []
    repository = ObservedRepository(runtime.repository, Metrics("worker", sink=rows.append))
    provider = OpenAIProvider(
        Authentication(), transport=Transport(error=ProviderFailure("NETWORK", uncertain=True))
    )
    worker = Worker(repository, provider, runtime.worker.clock)
    eid = start(runtime)
    assert worker.run("owner", eid)
    outcomes = [json.loads(row) for row in rows if "OutcomeUnknown" in json.loads(row)]
    assert len(outcomes) == 1
    assert outcomes[0]["Component"] == "worker" and outcomes[0]["Environment"] == "dev"
    assert outcomes[0]["OutcomeUnknown"] == 1


@pytest.mark.parametrize("schema", [2, 3, 4])
def test_legacy_alarm_receipts_are_not_rewritten(cost_deployment, monkeypatch, schema):
    monkeypatch.syspath_prepend("skills/p4")
    manifest, _, _ = cost_deployment
    manifest = deepcopy(manifest)
    manifest["schema_version"] = schema
    manifest.pop("monitoring_contract_version", None)
    manifest["configuration"].update(
        api_enabled=True, worker_enabled=True, streams_enabled=True, scheduler_enabled=True
    )
    alarm = tool("manifest_alarms").expected_alarms(manifest, "dev")["dev-OutcomeUnknown"]
    assert alarm["MetricName"] == "OutcomeUnknown" and "Metrics" not in alarm
    assert alarm["EvaluationPeriods"] == 1
