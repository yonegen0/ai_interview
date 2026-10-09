"""Real closure lifecycle over variable-sized authoritative State; no AWS execution."""

import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from test_closure_adapter import fixture
from test_provider_validation_tools import tool


def scenario(baseline=61, alarms=1, failure=None):
    module = tool("closure_adapter")
    approval, receipt, inputs, manifest, enabled_plan, state, review = fixture(module)
    instances = state["resources"][-2]["instances"]
    for index in range(57, baseline - 4):
        attrs = {"version": "latest", "baseline": "preserved"}
        instances.append({"index_key": index, "attributes": attrs})
        review["resource_changes"].insert(
            -1,
            {
                "address": f"module.service.aws_lambda_alias.baseline[{index}]",
                "type": "aws_lambda_alias",
                "change": {"actions": ["no-op"], "before": attrs, "after": attrs},
            },
        )
    for index in range(1, alarms):
        name = f"extra{index}"
        address = f"module.service.aws_cloudwatch_metric_alarm.{name}"
        attrs = {"alarm_name": "ai-interview-dev-" + name}
        approval["validation_alarms"][address] = attrs["alarm_name"]
        state["resources"].append(
            {
                "module": "module.service",
                "mode": "managed",
                "type": "aws_cloudwatch_metric_alarm",
                "name": name,
                "instances": [{"attributes": attrs}],
            }
        )
        review["resource_changes"].append(
            {
                "address": address,
                "type": "aws_cloudwatch_metric_alarm",
                "change": {"actions": ["delete"], "before": attrs, "after": None},
            }
        )
    receipt["state_addresses"] = sorted(module.state_addresses(state))
    active = json.loads(manifest)

    class Driver:
        calls = 0

        def snapshot(self, expected):
            result = deepcopy(state)
            identity = dict(receipt["state_after"])
            if expected["configuration"]["api_enabled"] is False:
                identity["serial"] += 1
                result["resources"] = [
                    r for r in result["resources"] if r["type"] != "aws_cloudwatch_metric_alarm"
                ]
                for resource in result["resources"]:
                    address = f"module.service.{resource['type']}.{resource['name']}"
                    if address in module.UPDATES:
                        key, _, value = module.UPDATES[address]
                        resource["instances"][0]["attributes"][key] = value
                        if (
                            resource["type"] == "aws_lambda_event_source_mapping"
                            and "state" in resource["instances"][0]["attributes"]
                        ):
                            resource["instances"][0]["attributes"].update(
                                state="Disabled",
                                last_modified=2000,
                                last_processing_result="No records processed",
                            )
                result["outputs"]["manifest"]["value"] = expected
                if failure == "missing":
                    result["resources"][-1]["instances"].pop()
                if failure == "extra":
                    result["resources"][-1]["instances"].append(
                        {"index_key": 999, "attributes": {"version": "latest"}}
                    )
                if failure == "attribute":
                    result["resources"][-1]["instances"][0]["attributes"]["version"] = "old"
                if failure == "manifest":
                    expected = active
            return {
                "state": result,
                "identity": identity,
                "manifest": expected,
                "active_lock": failure == "lock",
                "state_outside_dev_resources": 0,
            }

        def plan(self, values, target):
            path = target / "closure.tfplan"
            path.write_bytes(b"closure-saved-plan")
            return path, review

        def apply(self, *args):
            self.calls += 1
            if failure == "partial":
                raise ValueError("SyntheticPartialApply")

    driver = Driver()
    directory = Path(__file__).parents[2] / ".p4-artifacts" / ("inventory-" + uuid4().hex)
    directory.parent.mkdir(exist_ok=True)

    def execute():
        raw = json.dumps(approval).encode()
        return module.execute_closure(
            raw,
            module.digest(raw),
            json.dumps(receipt).encode(),
            inputs,
            manifest,
            enabled_plan,
            directory,
            driver,
        )

    return module, state, review, approval, receipt, driver, directory, execute


@pytest.mark.parametrize("baseline,alarms", [(61, 1), (61, 17), (72, 17), (76, 21)])
def test_variable_baseline_closes_once(baseline, alarms):
    _, _, _, _, _, driver, directory, execute = scenario(baseline, alarms)
    assert execute()["status"] == "CLOSED_READBACK_VERIFIED"
    assert driver.calls == 1 and (directory / "closed-readback.json").is_file()
    with pytest.raises((ValueError, FileExistsError)):
        execute()
    assert driver.calls == 1


@pytest.mark.parametrize(
    "failure", ["missing", "extra", "attribute", "manifest", "partial", "lock"]
)
def test_partial_and_readback_failures_never_retry(failure):
    _, _, _, _, _, driver, directory, execute = scenario(72, 17, failure)
    with pytest.raises(ValueError):
        execute()
    assert driver.calls == (0 if failure == "lock" else 1)
    assert not (directory / "closed-readback.json").exists()
    with pytest.raises((ValueError, FileExistsError)):
        execute()
    assert driver.calls <= 1


@pytest.mark.parametrize("bad", ["create", "replace", "unapproved-delete", "state", "before"])
def test_unapproved_plan_and_state_changes_refused(bad):
    _, _, review, approval, receipt, driver, _, execute = scenario(72, 17)
    if bad in {"create", "replace"}:
        review["resource_changes"][4]["change"]["actions"] = (
            ["create"] if bad == "create" else ["delete", "create"]
        )
    elif bad == "unapproved-delete":
        approval["validation_alarms"].pop(next(iter(approval["validation_alarms"])))
    elif bad == "state":
        receipt["state_addresses"].pop()
    else:
        # An internally consistent no-op must still match authoritative State.
        review["resource_changes"][4]["change"]["before"] = {"version": "tampered"}
        review["resource_changes"][4]["change"]["after"] = {"version": "tampered"}
    with pytest.raises(ValueError):
        execute()
    assert driver.calls == 0


def test_mapping_computed_metadata_does_not_stop_approved_closure():
    module, state, review, _, _, driver, _, execute = scenario(72, 17)
    for resource in state["resources"]:
        if resource["type"] == "aws_lambda_event_source_mapping":
            attrs = resource["instances"][0]["attributes"]
            attrs.update(
                state="Enabled",
                last_modified=1000,
                last_processing_result="OK",
                state_transition_reason="USER_INITIATED",
            )
            address = f"module.service.{resource['type']}.{resource['name']}"
            entry = next(e for e in review["resource_changes"] if e["address"] == address)
            entry["change"]["after"] = attrs | {module.UPDATES[address][0]: False}
    assert execute()["status"] == "CLOSED_READBACK_VERIFIED"
    assert driver.calls == 1


@pytest.mark.parametrize("field", ["uuid", "function_arn", "scaling_config", "state"])
def test_mapping_configuration_and_disabled_state_remain_exact(field):
    module, state, review, _, _, driver, _, execute = scenario(72, 17)
    resource = next(r for r in state["resources"] if r["type"] == "aws_lambda_event_source_mapping")
    value = (
        [{"maximum_concurrency": 2}]
        if field == "scaling_config"
        else "Enabled"
        if field == "state"
        else "fixed-identity"
    )
    resource["instances"][0]["attributes"][field] = value
    address = f"module.service.{resource['type']}.{resource['name']}"
    entry = next(e for e in review["resource_changes"] if e["address"] == address)
    entry["change"]["after"][field] = value
    original = driver.snapshot

    def snapshot(expected):
        result = original(expected)
        if expected["configuration"]["api_enabled"] is False:
            target = next(
                r
                for r in result["state"]["resources"]
                if r["name"] == resource["name"] and r["type"] == resource["type"]
            )
            target["instances"][0]["attributes"][field] = (
                "Enabled" if field == "state" else "tampered"
            )
        return result

    driver.snapshot = snapshot
    with pytest.raises(ValueError, match="ClosedStateInventoryMismatch"):
        execute()
    assert driver.calls == 1
