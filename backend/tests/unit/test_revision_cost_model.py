"""Tie cost reference counts to actual schema-4 Alarm contracts; no billed-price claim."""

import csv
import json
from pathlib import Path

import pytest
from test_p4_cost_controls import cost_deployment as cost_deployment
from test_p4_manifest_v3 import admin_deployment as admin_deployment
from test_p4_tools import tool


@pytest.mark.parametrize(
    "scenario,environment,usage,objects,refs",
    [
        ("P1_developer_dev", "dev", "developer", 17, 18),
        ("D_customer_optimized", "dev", "customer", 21, 23),
        ("E_test_increment", "test", "developer", 39, 43),
    ],
)
def test_cost_reference_inventory_matches_alarm_contract(
    cost_deployment, monkeypatch, scenario, environment, usage, objects, refs
):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "skills/p4"))
    m, _, _ = cost_deployment
    m["environment"] = environment
    m["configuration"].update(
        log_usage=usage, log_retention_days=14 if usage == "customer" else 3, api_enabled=True
    )
    alarms = tool("manifest_alarms").expected_alarms(m, "synthetic")
    actual_refs = sum(
        sum("MetricStat" in q for q in a["Metrics"]) if "Metrics" in a else 1
        for a in alarms.values()
    )
    assert len(alarms) == objects and actual_refs == refs
    docs = Path(__file__).parents[3] / "docs"
    model = json.loads((docs / "P4_COST_LOG_ESTIMATES_20261009.json").read_text())
    for row in model["rows"]:
        if row["scenario"] == scenario:
            assert row["alarm_objects"] == objects and row["alarm_metric_references"] == refs
            assert row["alarm_metric_hours"] == refs * row["hours"]
            assert row["total_usd"] == pytest.approx(sum(row["costs"].values()))
    csv_rows = list(csv.DictReader((docs / "P4_COST_LOG_ESTIMATES_20261009.csv").open()))
    assert len(csv_rows) == len(model["rows"]) == 64
    for actual, row in zip(csv_rows, model["rows"], strict=True):
        assert int(actual["alarm_metric_references"]) == row["alarm_metric_references"]
        if "total_usd" in row:
            assert float(actual["total_usd"]) == pytest.approx(row["total_usd"])
        assert actual["aws_verified"] == "false"
