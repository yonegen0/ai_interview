"""Synthetic evidence only: no AWS, Terraform State, Plan binary or execution authority."""

import copy
import json
from pathlib import Path

import pytest
from test_p4_tools import tool


def schema():
    return {
        "format_version": "1.0",
        "provider_schemas": {
            tool("toolchain_compatibility").AWS: {
                "resource_schemas": {
                    kind: {"version": 0, "block": {"attributes": {"id": {"computed": True}}}}
                    for kind in ("aws_sns_topic", "aws_cloudwatch_metric_alarm", "aws_iam_role")
                }
            }
        },
    }


def test_schema_comparison_reports_reviewed_additions_without_claiming_defaults():
    m = tool("toolchain_compatibility")
    before, after = schema(), schema()
    resources = after["provider_schemas"][m.AWS]["resource_schemas"]
    resources["aws_sns_topic"]["block"]["attributes"]["maximum_message_size"] = {
        "type": "number",
        "optional": True,
        "computed": True,
    }
    resources["aws_cloudwatch_metric_alarm"]["block"]["block_types"] = {
        "evaluation_window": {"nesting_mode": "list", "max_items": 1, "block": {"attributes": {}}}
    }
    result = m.compare_schemas(before, after, set(resources))
    assert result["additions"] == {
        "aws_sns_topic": "attributes.maximum_message_size",
        "aws_cloudwatch_metric_alarm": "block_types.evaluation_window",
    }
    assert result["defaults_and_state_upgraders_proven"] is False
    assert result["baseline_schema_sha256"] != result["candidate_schema_sha256"]


@pytest.mark.parametrize(
    "failure", ["version", "removed", "changed", "added", "provider", "format", "empty"]
)
def test_schema_comparison_requires_review_for_every_other_change(failure):
    m = tool("toolchain_compatibility")
    before, after = schema(), schema()
    resources = after["provider_schemas"][m.AWS]["resource_schemas"]
    kinds = set(resources)
    if failure == "version":
        resources["aws_iam_role"]["version"] = 1
    elif failure == "removed":
        del resources["aws_iam_role"]
    elif failure == "changed":
        resources["aws_iam_role"]["block"]["attributes"]["id"]["computed"] = False
    elif failure == "added":
        resources["aws_iam_role"]["block"]["attributes"]["permissions"] = {"optional": True}
    elif failure == "provider":
        after["provider_schemas"]["unexpected"] = {}
    elif failure == "format":
        after["format_version"] = "2.0"
    else:
        kinds = set()
    with pytest.raises(ValueError):
        m.compare_schemas(before, after, kinds)


def noop(version="1.14.9"):
    row = {
        "address": "module.synthetic.aws_sns_topic.alarms",
        "mode": "managed",
        "type": "aws_sns_topic",
        "name": "alarms",
        "provider_name": "registry.terraform.io/hashicorp/aws",
        "schema_version": 0,
        "values": {"id": "synthetic", "maximum_message_size": None, "tags": {}},
    }
    values = {
        "root_module": {"child_modules": [{"resources": [row]}]},
        "outputs": {"flag": {"value": False, "type": "bool", "sensitive": False}},
    }
    return {
        "format_version": "1.2",
        "terraform_version": version,
        "complete": True,
        "errored": False,
        "applyable": False,
        "prior_state": {"values": copy.deepcopy(values)},
        "planned_values": values,
        "variables": {"flag": {"value": False}},
        "resource_changes": [
            {
                "address": row["address"],
                "mode": "managed",
                "change": {
                    "actions": ["no-op"],
                    "before": copy.deepcopy(row["values"]),
                    "after": copy.deepcopy(row["values"]),
                    "after_unknown": {},
                },
            }
        ],
        "output_changes": {
            "flag": {"actions": ["no-op"], "before": False, "after": False, "after_unknown": False}
        },
    }


@pytest.mark.parametrize("version", ["1.16.7", "1.17.0"])
def test_nested_noop_synthetic_plan_pair(version):
    m = tool("toolchain_compatibility")
    assert m.assert_noop_plan_pair(noop(), noop(version), version) == {
        "status": "SYNTHETIC_NOOP_COMPATIBLE_NOT_APPLY_APPROVAL",
        "resources": 1,
    }


@pytest.mark.parametrize(
    "failure",
    [
        "replacement",
        "iam",
        "default",
        "hidden-default",
        "schema-version",
        "state-address",
        "unknown",
        "malformed-unknown",
        "missing-unknown",
        "partial",
        "error",
        "drift",
        "deferred",
        "action",
        "duplicate",
        "missing-resource",
        "import",
        "move",
        "replace-path",
        "output",
        "output-unknown",
        "missing-output",
        "spoofed-output",
        "failed-check",
        "format",
        "old-cli",
        "input",
        "empty",
        "missing-errored",
        "proposed-unknown",
        "malformed-proposed-unknown",
    ],
)
def test_plan_pair_fails_closed_on_defaults_state_changes_and_incomplete_evidence(failure):
    m = tool("toolchain_compatibility")
    before, after = noop(), noop("1.16.7")
    row = after["planned_values"]["root_module"]["child_modules"][0]["resources"][0]
    change = after["resource_changes"][0]["change"]
    if failure == "replacement":
        change["actions"] = ["delete", "create"]
    elif failure in {"iam", "default"}:
        row["values"]["policy" if failure == "iam" else "maximum_message_size"] = "changed"
    elif failure in {"hidden-default", "schema-version", "state-address"}:
        for document in (after["prior_state"]["values"], after["planned_values"]):
            resource = document["root_module"]["child_modules"][0]["resources"][0]
            if failure == "hidden-default":
                resource["values"]["maximum_message_size"] = 262144
            elif failure == "schema-version":
                resource["schema_version"] = 1
            else:
                resource["address"] += "_moved"
        if failure == "hidden-default":
            change["before"]["maximum_message_size"] = change["after"]["maximum_message_size"] = (
                262144
            )
    elif failure in {"unknown", "malformed-unknown"}:
        change["after_unknown"] = {"maximum_message_size": True if failure == "unknown" else None}
    elif failure == "missing-unknown":
        del change["after_unknown"]
    elif failure == "partial":
        after["complete"] = False
    elif failure == "error":
        after["errored"] = True
    elif failure in {"drift", "deferred", "action"}:
        after[
            {
                "drift": "resource_drift",
                "deferred": "deferred_changes",
                "action": "action_invocations",
            }[failure]
        ] = [{}]
    elif failure == "duplicate":
        after["planned_values"]["root_module"]["child_modules"][0]["resources"].append(row)
    elif failure == "missing-resource":
        after["resource_changes"] = []
    elif failure == "import":
        change["importing"] = {"id": "synthetic"}
    elif failure == "move":
        after["resource_changes"][0]["previous_address"] = "aws_sns_topic.old"
    elif failure == "replace-path":
        change["replace_paths"] = [["name"]]
    elif failure == "output":
        after["planned_values"]["outputs"]["flag"]["value"] = True
    elif failure == "output-unknown":
        after["output_changes"]["flag"]["after_unknown"] = True
    elif failure == "missing-output":
        after["output_changes"] = {}
    elif failure == "spoofed-output":
        after["output_changes"]["flag"].update(before=True, after=True)
    elif failure == "failed-check":
        after["checks"] = [{"status": "unknown"}]
    elif failure == "format":
        after["format_version"] = "2.0"
    elif failure == "old-cli":
        after["terraform_version"] = "1.14.9"
    elif failure == "input":
        after["variables"]["flag"]["value"] = 0
    elif failure == "missing-errored":
        del after["errored"]
    elif failure in {"proposed-unknown", "malformed-proposed-unknown"}:
        after["proposed_unknown"] = {
            "root_module": {"resources": [{"values": {"id": True if failure == "proposed-unknown" else None}}]}
        }
    else:
        before = noop("1.14.9")
        after = noop("1.16.7")
        for document in (before, after):
            document["prior_state"]["values"]["root_module"] = {}
            document["planned_values"]["root_module"] = {}
            document["resource_changes"] = []
    with pytest.raises(ValueError):
        m.assert_noop_plan_pair(before, after, "1.16.7")


def test_tracked_inventory_covers_all_used_types_and_rejects_data_sources():
    m = tool("toolchain_compatibility")
    root = Path(__file__).resolve().parents[3]
    files = {str(path): path.read_bytes() for path in (root / "terraform").rglob("*.tf")}
    assert len(m.resource_types(files)) == 41
    with pytest.raises(ValueError, match="DataSourceReview"):
        m.resource_types({"synthetic.tf": b'data "aws_caller_identity" "synthetic" {}'})


@pytest.mark.parametrize("version", ["1.14.9", "1.16.7", "1.17.0"])
def test_actual_cli_boolean_null_values_reach_legacy_maintenance_consumer(version):
    m = tool("maintenance_contract")
    root = Path(__file__).resolve().parents[1] / "fixtures/p4"
    show = json.loads((root / f"terraform-{version}-offline-json.json").read_text())["show"]
    values = dict.fromkeys(m.INPUT_KEYS, "synthetic") | {"worker_wif_enabled": False}
    variables = {key: {"value": value} for key, value in values.items()}
    variables["worker_wif_enabled"] = show["variables"]["worker_wif_enabled"]
    m.audit_variables(variables, values)
    assert show["planned_values"]["outputs"]["null_value"]["value"] is None
    # The old reader accepts shape compatibility; runtime and historical evidence stay pinned.
    from interview_backend.deployment import DeploymentError

    raw = json.dumps(
        {"version": 4, "terraform_version": version, "serial": 1, "lineage": "synthetic"}
    ).encode()
    if version == "1.14.9":
        assert m.identity(raw, "synthetic-version")["serial"] == 1
    else:
        with pytest.raises(DeploymentError, match="MaintenanceStateIdentity"):
            m.identity(raw, "synthetic-version")
