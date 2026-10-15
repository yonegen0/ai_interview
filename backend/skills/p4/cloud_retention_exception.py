"""Exact five in-place 7->14 updates; never an Apply or generic log update grant."""

import json
import math

from cloud_controller_core import canonical, require
from cloud_retention_policy import POLICY


def comparable(value):
    if value is None or type(value) in (bool, int, str):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is list:
        return all(comparable(v) for v in value)
    if type(value) is dict:
        return all(type(k) is str and comparable(v) for k, v in value.items())
    return False


def all_known(value):
    if value is False:
        return True
    if type(value) is dict:
        return all(all_known(v) for v in value.values())
    if type(value) is list:
        return all(all_known(v) for v in value)
    return False


def validate_policy(policy):
    require(
        comparable(policy) and canonical(policy) == canonical(POLICY),
        "RetentionExceptionPolicyMismatch",
    )


def state_rows(state):
    rows = {}
    for r in state["resources"]:
        if r.get("mode") != "managed":
            continue
        for i in r["instances"]:
            address = (
                (r.get("module", "") + "." if r.get("module") else "") + r["type"] + "." + r["name"]
            )
            if "index_key" in i:
                address += "[" + json.dumps(i["index_key"]) + "]"
            require(address not in rows, "RetentionBaselineDuplicateAddress")
            rows[address] = i["attributes"]
    return rows


def changes(plan, policy, state):
    """Bind before/prior/after/planned full values and insist on all five updates."""
    validate_policy(policy)
    require(
        not plan.get("resource_drift")
        and not plan.get("errored")
        and not plan.get("deferred_changes"),
        "RetentionPlanDriftOrUnknown",
    )
    from cloud_plan_semantics import walk_values

    baseline = state_rows(state)
    prior_rows = list(walk_values(plan["prior_state"]["values"]["root_module"]))
    planned_rows = list(walk_values(plan["planned_values"]["root_module"]))
    result = []
    for target in policy["targets"]:
        addr = target["address"]
        require(
            addr in baseline
            and comparable(baseline[addr])
            and canonical(baseline[addr]) == target["before_attributes_sha256"],
            "RetentionBaselineMismatch",
        )
        selected = [r for r in plan["resource_changes"] if r["address"] == addr]
        prior = [r for r in prior_rows if r["address"] == addr]
        planned = [r for r in planned_rows if r["address"] == addr]
        require(len(selected) == len(prior) == len(planned) == 1, "RetentionFiveTargetsRequired")
        entry = selected[0]
        change = entry["change"]
        require(
            entry.get("mode") == "managed"
            and entry["type"] == "aws_cloudwatch_log_group"
            and change["actions"] == ["update"]
            and not entry.get("previous_address")
            and not entry.get("deposed")
            and not change.get("importing")
            and not change.get("replace_paths"),
            "RetentionUpdateOnly",
        )
        before = change.get("before")
        after = change.get("after")
        require(
            type(before) is dict
            and type(after) is dict
            and comparable(before)
            and comparable(after)
            and all_known(change.get("after_unknown", {})),
            "RetentionUnknownOrIncomparable",
        )
        require(
            type(before.get("retention_in_days")) is int
            and before["retention_in_days"] == 7
            and type(after.get("retention_in_days")) is int
            and after["retention_in_days"] == 14,
            "RetentionExactSevenToFourteenRequired",
        )
        require(
            canonical(before) == target["before_attributes_sha256"]
            and before["name"] == target["name"]
            and before["arn"] == target["arn"]
            and canonical(after) == canonical(before | {"retention_in_days": 14}),
            "RetentionOtherAttributeChanged",
        )
        require(
            comparable(prior[0]["values"])
            and comparable(planned[0]["values"])
            and canonical(prior[0]["values"]) == canonical(before)
            and canonical(planned[0]["values"]) == canonical(after),
            "RetentionPriorPlannedValueMismatch",
        )
        require(
            canonical(change.get("before_sensitive", {}))
            == canonical(change.get("after_sensitive", {})),
            "RetentionSensitivityContractChanged",
        )
        result.append(
            {
                "address": addr,
                "type": "aws_cloudwatch_log_group",
                "category": "update",
                "before_retention_days": 7,
                "after_retention_days": 14,
                "review": "RETENTION_EXTENSION_REQUIRES_SEPARATE_SAVED_PLAN_APPLY_APPROVAL",
                "apply_authorized": False,
            }
        )
    require(len(result) == policy["required_updates"] == 5, "RetentionFiveTargetsRequired")
    return result
