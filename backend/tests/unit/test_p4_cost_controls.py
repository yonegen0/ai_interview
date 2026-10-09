"""Customer monitoring contracts and fail-closed test lifecycle, without AWS."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_p4_artifact_inputs import valid_inputs
from test_p4_manifest_v3 import admin_deployment as admin_deployment
from test_p4_tools import tool

FLAGS = ("api_enabled", "worker_enabled", "streams_enabled", "scheduler_enabled")


@pytest.fixture(autouse=True)
def tools_path(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "skills/p4"))


@pytest.fixture
def cost_deployment(admin_deployment):
    m, data, session = admin_deployment
    m["schema_version"] = 4
    m["monitoring_contract_version"] = 2
    m["configuration"].update(
        log_usage="customer",
        log_retention_days=14,
        test_monitoring_enabled=True,
        test_closure_confirmed=False,
    )
    for (service, method, _), value in data.items():
        if service == "logs" and method == "describe_log_groups":
            for group in value["logGroups"]:
                group["retentionInDays"] = 14
    stage = data["apigatewayv2", "get_stage", ""]
    format_ = json.loads(stage["AccessLogSettings"]["Format"])
    format_.update(
        requestTimeEpoch="$context.requestTimeEpoch", responseLatency="$context.responseLatency"
    )
    stage["AccessLogSettings"]["Format"] = json.dumps(format_)
    return m, data, session


def test_schema4_full_closed_readback_and_old_receipts(cost_deployment, tmp_path):
    m, _, session = cost_deployment
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(m))
    assert tool("manifest").read_manifest(path, m["account_id"], m["region"]) == m
    tool("manifest").verify_live_manifest(session, m, require_api_enabled=False)


@pytest.mark.parametrize(
    "key,value",
    [
        ("log_usage", "prod"),
        ("log_retention_days", 3),
        ("log_retention_days", True),
        ("test_monitoring_enabled", False),
        ("test_closure_confirmed", True),
        ("unexpected", "anything"),
    ],
)
def test_schema4_rejects_wrong_use_missing_proof_and_unknown_keys(
    cost_deployment, tmp_path, key, value
):
    m, _, _ = cost_deployment
    m["configuration"][key] = value
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(m))
    with pytest.raises(ValueError):
        tool("manifest").read_manifest(path, m["account_id"], m["region"])


def test_customer_keeps_existing17_adds_four_with_five_references(cost_deployment):
    m, _, _ = cost_deployment
    m["configuration"].update(dict.fromkeys(FLAGS, True))
    alarms = tool("manifest_alarms").expected_alarms(m, "dev")
    developer = copy.deepcopy(m)
    developer["configuration"].update(log_usage="developer", log_retention_days=3)
    original = tool("manifest_alarms").expected_alarms(developer, "dev")
    assert len(original) == 17 and len(alarms) == 21
    assert set(alarms) - set(original) == {
        "dev-PendingAge",
        "dev-QueuedAge",
        "dev-api-5xx",
        "dev-evaluation-failed",
    }
    for key in original:
        assert alarms[key] == original[key]
    references = sum(
        sum("MetricStat" in q for q in a["Metrics"]) if "Metrics" in a else 1
        for a in alarms.values()
    )
    assert references == 23
    assert alarms["dev-api-5xx"]["MetricName"] == "5xx"
    assert alarms["dev-api-5xx"]["Dimensions"] == [{"Name": "ApiId", "Value": m["api_id"]}]
    failed = alarms["dev-evaluation-failed"]
    assert failed["Threshold"] == 1
    assert failed["Metrics"][0]["Expression"] == "SUM([wf,df])"
    for key in set(alarms) - set(original):
        assert alarms[key]["TreatMissingData"] == "notBreaching"
        assert alarms[key]["AlarmActions"] == [m["alarm_topic_arn"]]
    assert alarms["dev-RecoveryHeartbeat"]["TreatMissingData"] == "breaching"


def test_schema4_cannot_hide_live_test_alarms(cost_deployment):
    m, _, _ = cost_deployment
    m["environment"] = "test"
    m["configuration"].update(log_usage="developer", log_retention_days=3)
    assert len(tool("manifest_alarms").expected_alarms(m, "test")) == 39
    m["configuration"]["test_monitoring_enabled"] = False
    with pytest.raises(ValueError, match="VerifiedTestClosure"):
        tool("manifest_alarms").expected_alarms(m, "test")
    m["configuration"]["test_closure_confirmed"] = True
    with pytest.raises(ValueError, match="StateBoundTestClosureEvidence"):
        tool("manifest_alarms").expected_alarms(m, "test")
    m["test_closure_evidence_sha256"] = "a" * 64
    assert tool("manifest_alarms").expected_alarms(m, "test") == {}
    m["configuration"]["worker_enabled"] = True
    with pytest.raises(ValueError, match="ClosedTest"):
        tool("manifest_alarms").expected_alarms(m, "test")


def test_new_deployment_requires_declared_use():
    values = valid_inputs()
    values.pop("log_usage")
    with pytest.raises(ValueError):
        tool("terraform_dev").validate_inputs(values, "123456789012", "ap-northeast-1")


@pytest.mark.parametrize(
    "bad", [None, "queue", "dlq", "work", "unknown_queue", "unknown_query", "live"]
)
def test_readonly_test_drain_refuses_residual_and_unknown(cost_deployment, monkeypatch, bad):
    m, _, _ = cost_deployment
    m.update(environment="test", run_id="synthetic")
    module = tool("test_monitoring_closure")
    monkeypatch.setattr(module, "verify_live_manifest", lambda *a, **kw: None)
    calls = []

    def queue(**kw):
        calls.append(kw)
        attrs = dict.fromkeys(kw["AttributeNames"], "0")
        if bad == "queue" or (bad == "dlq" and kw["QueueUrl"] == m["worker_dlq_url"]):
            attrs[kw["AttributeNames"][0]] = "1"
        if bad == "unknown_queue":
            attrs.pop(kw["AttributeNames"][0])
        return {"Attributes": attrs}

    def query(**kw):
        assert "work_sk" not in kw["KeyConditionExpression"]  # Include future-due work.
        return {} if bad == "unknown_query" else {"Count": 1 if bad == "work" else 0}

    session = SimpleNamespace(
        client=lambda name, **kw: SimpleNamespace(get_queue_attributes=queue, query=query)
    )
    if bad == "live":
        m["configuration"]["api_enabled"] = True
    if bad:
        with pytest.raises(ValueError):
            module.verify_idle(session, m, sleep=lambda _: None)
    else:
        waits = []
        result = module.verify_idle(session, m, sleep=waits.append)
        assert result["status"] == "TEST_DRAIN_OBSERVED"
        assert len(calls) == 6 and waits == [60]
        assert len(result["manifest_sha256"]) == 64


def test_schema4_closure_changes_only_four_flags_and_approved_alarm_set():
    from test_closure_adapter import fixture

    module = tool("closure_adapter")
    approval, _, _, _, _, state, review = fixture(module)
    before = state["outputs"]["manifest"]["value"]
    before["schema_version"] = 4
    before["configuration"].update(
        log_usage="customer",
        log_retention_days=14,
        test_monitoring_enabled=True,
        test_closure_confirmed=False,
    )
    review["output_changes"]["manifest"]["after"] = copy.deepcopy(before)
    review["output_changes"]["manifest"]["after"]["configuration"].update(
        dict.fromkeys(FLAGS, False)
    )
    audit = module.audit_plan(review, state, approval["validation_alarms"])
    assert audit["update"] == 4 and audit["destroy"] == 1
    review["output_changes"]["manifest"]["after"]["configuration"]["log_retention_days"] = 3
    with pytest.raises(ValueError, match="ClosureOutputMismatch"):
        module.audit_plan(review, state, approval["validation_alarms"])
