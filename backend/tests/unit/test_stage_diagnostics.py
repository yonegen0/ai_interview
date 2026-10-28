"""Exhaustive offline diagnostics reuse the existing recovery fixtures and auditor."""

import copy
import json

import pytest
from test_stage_recovery import (
    cors_recovery as cors_recovery,
)
from test_stage_recovery import (
    deployment_recovery as deployment_recovery,
)
from test_stage_recovery import (
    policy_cache_recovery as policy_cache_recovery,
)
from test_stage_recovery import (
    recovery as recovery,
)
from test_stage_recovery import (
    route_recovery as route_recovery,
)


def diagnostic_plan(h):
    h.descriptor["state_snapshot_sha256"] = h.m.canonical_hash(h.snapshot)
    plan = copy.deepcopy(h.plan)
    for prefix in ("api", "route"):
        if hasattr(h, prefix + "_original"):
            plan["resource_drift"].append(
                dict(
                    address=getattr(h, prefix + "_address"),
                    change=dict(
                        actions=["update"],
                        before=getattr(h, prefix + "_original"),
                        after=getattr(h, prefix + "_refreshed"),
                    ),
                )
            )
    plan["prior_state"] = {
        "values": {
            "root_module": {
                "resources": [
                    dict(address=r["address"], values=copy.deepcopy(r["change"]["before"]))
                    for r in plan["resource_changes"]
                ]
            }
        }
    }
    return plan


@pytest.mark.parametrize(
    "fixture",
    ["recovery", "cors_recovery", "route_recovery", "policy_cache_recovery", "deployment_recovery"],
)
def test_full_diagnosis_reuses_only_proven_equivalences_and_preserves_inputs(request, fixture):
    import stage_diagnostics as diagnostics

    h = request.getfixturevalue(fixture)
    plan = diagnostic_plan(h)
    original = copy.deepcopy((plan, h.descriptor, h.snapshot))
    report = diagnostics.diagnose(plan, h.descriptor, h.snapshot)
    assert report["diagnostic_only"] is True
    assert report["status"] == "DIAGNOSED"
    assert report["formal_plan_audit"] == "ACCEPTED"
    assert report["state_resource_count"] == len(h.m.state_resources(h.snapshot))
    assert report["inspected_address_count"] == sum(report["counts"].values())
    assert report["counts"]["C"] == 1  # intended Stage update, explicitly allowed
    assert not any(row["requires_action"] for row in report["resources"])
    assert (plan, h.descriptor, h.snapshot) == original
    assert h.m.audit_plan(plan, h.descriptor, h.snapshot)["change"] == 1


def test_full_diagnosis_continues_across_all_77_resources_and_all_outputs(recovery):
    import stage_diagnostics as diagnostics

    h = recovery
    for index in range(75):
        name = f"synthetic_{index}"
        attributes = {"id": "private-value-never-in-report"}
        h.snapshot["state"]["resources"].append(
            dict(type="synthetic_resource", name=name, instances=[dict(attributes=attributes)])
        )
        h.plan["resource_changes"].append(
            dict(
                address="synthetic_resource." + name,
                change=dict(actions=["no-op"], before=attributes, after=attributes),
            )
        )
        h.plan["planned_values"]["root_module"]["resources"].append(
            dict(address="synthetic_resource." + name, values=attributes)
        )
    h.descriptor["state_snapshot_sha256"] = h.m.canonical_hash(h.snapshot)
    plan = diagnostic_plan(h)
    for index, fault in [(0, "after_unknown"), (38, "replace_paths"), (76, "importing")]:
        plan["resource_changes"][index]["change"][fault] = {"id": True}
    plan["output_changes"] = {
        name: dict(actions=["update"], before="secret-before", after="secret-after")
        for name in ("first", "last")
    }
    report = diagnostics.diagnose(plan, h.descriptor, h.snapshot)
    assert report["state_resource_count"] == report["inspected_address_count"] == 77
    assert sum(row["requires_action"] for row in report["resources"]) == 3
    assert len(report["outputs"]) == 2
    assert all(row["status"] == "REJECTED" for row in report["outputs"])
    assert report["formal_plan_audit"] == "REJECTED"
    assert "private-value" not in json.dumps(report)
    assert "secret-" not in json.dumps(report)


@pytest.mark.parametrize(
    "fault",
    ["state", "refresh", "missing", "duplicate", "unknown", "extra", "delete", "move", "drift"],
)
def test_diagnostic_never_calls_incomplete_or_unapproved_evidence_pass(recovery, fault):
    import stage_diagnostics as diagnostics

    h = recovery
    plan = diagnostic_plan(h)
    row = plan["resource_changes"][-1]
    if fault == "state":
        h.snapshot["identity"]["serial"] += 1
    elif fault == "refresh":
        plan.pop("prior_state")
    elif fault == "missing":
        plan["resource_changes"].pop()
    elif fault == "duplicate":
        plan["resource_changes"].append(copy.deepcopy(row))
    elif fault == "unknown":
        row["change"]["after_unknown"] = {"s3_key": True}
    elif fault == "extra":
        plan["resource_changes"].append(
            dict(
                address="unapproved.resource",
                change=dict(actions=["create"], before=None, after={}),
            )
        )
    elif fault == "delete":
        row["change"]["actions"] = ["delete"]
    elif fault == "move":
        row["previous_address"] = "unapproved.old"
    else:
        plan["resource_drift"].append(
            dict(
                address=row["address"],
                change=dict(
                    actions=["update"], before=row["change"]["before"], after={"s3_key": "other"}
                ),
            )
        )
    report = diagnostics.diagnose(plan, h.descriptor, h.snapshot)
    assert report["status"] == "FINDINGS"
    assert report["inspected_address_count"] >= 2
    assert any(row["requires_action"] for row in report["resources"])
    if fault not in {"state", "refresh"}:  # separate state binding / evidence requirements
        with pytest.raises(ValueError):
            h.m.audit_plan(plan, h.descriptor, h.snapshot)


def test_diagnostic_rejects_real_iam_change_alongside_allowed_cache(policy_cache_recovery):
    import stage_diagnostics as diagnostics

    h = policy_cache_recovery
    plan = diagnostic_plan(h)
    plan["resource_changes"][-2]["change"]["after"]["permissions_boundary"] = "secret-boundary"
    report = diagnostics.diagnose(plan, h.descriptor, h.snapshot)
    role = next(r for r in report["resources"] if r["address"] == h.m.API_ROLE)
    assert role["category"] == "C" and role["requires_action"]
    assert "secret-boundary" not in json.dumps(report)
    assert report["formal_plan_audit"] == "REJECTED"


def test_diagnostic_cli_never_overwrites_evidence_or_prints_input_values(
    recovery, tmp_path, monkeypatch, capsys
):
    import stage_diagnostics as diagnostics

    h = recovery
    paths = []
    for name, value in [
        ("plan", diagnostic_plan(h)),
        ("descriptor", h.descriptor),
        ("snapshot", h.snapshot),
    ]:
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(value))
        paths.extend(["--" + name, str(path)])
    output = tmp_path / "report.private.json"
    monkeypatch.setattr("sys.argv", ["stage_diagnostics", *paths, "--output", str(output)])
    assert diagnostics.main() == 0
    saved = output.read_bytes()
    with pytest.raises(SystemExit) as error:
        diagnostics.main()
    assert error.value.code == 2
    assert output.read_bytes() == saved
    stdout = capsys.readouterr().out
    assert h.descriptor["artifact"]["artifact_key"] not in stdout
    assert "module.service" not in stdout
