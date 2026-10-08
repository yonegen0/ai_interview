"""Full saved-plan auditing and one-attempt lifecycle against synthetic State."""

import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from test_provider_validation_tools import tool


def fixture(module):
    account = "123456789012"
    artifact = {
        "bucket": "candidate",
        "key": "unique/app.zip",
        "version": "v1",
        "sha256_base64": "A" * 43 + "=",
    }
    active = {
        "account_id": account,
        "region": "ap-northeast-1",
        "environment": "dev",
        "configuration": dict.fromkeys(module.FLAGS, True),
        "artifact": artifact,
        "versions": {"worker": "4"},
        "aliases": {"worker": "latest"},
    }
    inputs = dict.fromkeys(module.FLAGS, True) | {
        "artifact_" + k: v for k, v in artifact.items() if k != "version"
    }
    inputs["artifact_version"] = artifact["version"]
    inputs_raw, manifest_raw = json.dumps(inputs).encode(), json.dumps(active).encode()
    enabled_plan = str(uuid4()).encode()
    state_before = {"lineage": "synthetic", "serial": 12}
    identity = {"lineage": "synthetic", "serial": 13, "version_id": "v13", "sha256": "state-hash"}
    approval = {
        "conditional_closure_authorized": True,
        "closure_source_sha256": module.digest(Path(module.__file__).read_bytes()),
        "driver_source_sha256": module.digest(
            Path(module.__file__).with_name("closure_aws.py").read_bytes()
        ),
        "enablement_plan_sha256": module.digest(enabled_plan),
        "account_id": account,
        "region": "ap-northeast-1",
        "code_sha": "0" * 40,
        "lock_sha256": "0" * 64,
        "state_before": state_before,
        "validation_alarms": {
            "module.service.aws_cloudwatch_metric_alarm.synthetic": "ai-interview-dev-validation"
        },
    }
    receipt = {
        "status": "ENABLEMENT_READBACK_VERIFIED",
        "partial_failure": False,
        "plan_sha256": module.digest(enabled_plan),
        "inputs_sha256": module.digest(inputs_raw),
        "manifest_sha256": module.digest(manifest_raw),
        "artifact": artifact,
        "versions": active["versions"],
        "aliases": active["aliases"],
        "state_before": state_before,
        "state_after": identity,
        **{k: approval[k] for k in ("account_id", "region", "code_sha", "lock_sha256")},
    }
    resources, changes = [], []
    for address, (key, before, after) in module.UPDATES.items():
        type_name, name = address.split(".")[2:]
        attrs = {key: before, "baseline": "preserved"}
        resources.append(
            {
                "module": "module.service",
                "mode": "managed",
                "type": type_name,
                "name": name,
                "instances": [{"attributes": attrs}],
            }
        )
        changes.append(
            {
                "address": address,
                "type": type_name,
                "change": {"actions": ["update"], "before": attrs, "after": attrs | {key: after}},
            }
        )
    instances = []
    for index in range(57):
        attrs = {"version": "latest"}
        instances.append({"index_key": index, "attributes": attrs})
        changes.append(
            {
                "address": f"module.service.aws_lambda_alias.baseline[{index}]",
                "type": "aws_lambda_alias",
                "change": {"actions": ["no-op"], "before": attrs, "after": attrs},
            }
        )
    resources.append(
        {
            "module": "module.service",
            "mode": "managed",
            "type": "aws_lambda_alias",
            "name": "baseline",
            "instances": instances,
        }
    )
    alarm = {"alarm_name": "ai-interview-dev-validation"}
    resources.append(
        {
            "module": "module.service",
            "mode": "managed",
            "type": "aws_cloudwatch_metric_alarm",
            "name": "synthetic",
            "instances": [{"attributes": alarm}],
        }
    )
    changes.append(
        {
            "address": next(iter(approval["validation_alarms"])),
            "type": "aws_cloudwatch_metric_alarm",
            "change": {"actions": ["delete"], "before": alarm, "after": None},
        }
    )
    state = {"resources": resources, "outputs": {"manifest": {"value": active}}}
    closed = deepcopy(active)
    closed["configuration"].update(dict.fromkeys(module.FLAGS, False))
    review = {
        "resource_changes": changes,
        "output_changes": {"manifest": {"before": active, "after": closed}},
    }
    return approval, receipt, inputs_raw, manifest_raw, enabled_plan, state, review


@pytest.mark.parametrize(
    "bad",
    ["extra-update", "create", "replace", "alarm", "unknown", "drift", "omitted", "output", "code"],
)
def test_whitelist_deviation_stops(bad):
    module = tool("closure_adapter")
    approval, _, _, _, _, state, review = fixture(module)
    if bad == "extra-update":
        review["resource_changes"][0]["change"]["after"]["baseline"] = "changed"
    elif bad in {"create", "replace"}:
        review["resource_changes"][4]["change"]["actions"] = (
            ["create"] if bad == "create" else ["delete", "create"]
        )
    elif bad == "alarm":
        review["resource_changes"][-1]["change"]["before"]["alarm_name"] = "unapproved"
    elif bad == "unknown":
        review["resource_changes"][0]["change"]["after_unknown"] = {"id": True}
    elif bad == "drift":
        review["resource_drift"] = [{"address": "unexpected"}]
    elif bad == "omitted":
        review["resource_changes"].pop()
    elif bad == "output":
        review["output_changes"]["manifest"]["after"]["artifact"]["version"] = "old"
    else:
        review["resource_changes"][4]["change"]["after"] = {"version": "old"}
    with pytest.raises(ValueError):
        module.audit_plan(review, state, approval["validation_alarms"])


@pytest.mark.parametrize("failure", [None, "partial", "receipt", "lock", "readback", "plan-hash"])
def test_lifecycle_applies_once_and_records_readback_or_stop(failure):
    module = tool("closure_adapter")
    approval, receipt, inputs, manifest, plan, state, review = fixture(module)
    active = json.loads(manifest)
    directory = Path(__file__).parents[2] / ".p4-artifacts" / ("closure-offline-" + str(uuid4()))
    directory.parent.mkdir(exist_ok=True)
    if failure == "receipt":
        receipt["partial_failure"] = True
    if failure == "plan-hash":
        approval["closure_plan_sha256"] = "0" * 64

    class Driver:
        calls = 0

        def snapshot(self, expected):
            closed = expected["configuration"]["api_enabled"] is False
            identity = dict(receipt["state_after"])
            current_state = deepcopy(state)
            if closed:
                identity["serial"] += 1
                current_state["resources"] = current_state["resources"][:-1]
            return {
                "state": current_state,
                "identity": identity,
                "manifest": active if failure == "readback" and closed else expected,
                "active_lock": failure == "lock",
                "state_outside_dev_resources": 0,
            }

        def plan(self, values, target):
            assert values == module.closed_inputs(json.loads(inputs))
            path = target / "closure.tfplan"
            path.write_bytes(b"synthetic-closure-plan")
            return path, review

        def apply(self, path, digest):
            self.calls += 1
            assert module.digest(path.read_bytes()) == digest
            if failure == "partial":
                raise ValueError("SyntheticPartialApply")

    driver = Driver()
    raw = json.dumps(approval).encode()
    args = (
        raw,
        module.digest(raw),
        json.dumps(receipt).encode(),
        inputs,
        manifest,
        plan,
        directory,
        driver,
    )
    if failure:
        with pytest.raises(ValueError):
            module.execute_closure(*args)
        assert driver.calls == (1 if failure in {"partial", "readback"} else 0)
        assert not (directory / "closed-readback.json").exists()
    else:
        evidence = module.execute_closure(*args)
        assert evidence["status"] == "CLOSED_READBACK_VERIFIED" and driver.calls == 1
        assert (directory / "audit.json").exists() and (directory / "closed-readback.json").exists()
    with pytest.raises((ValueError, FileExistsError)):
        module.execute_closure(*args)
    assert driver.calls <= 1


def test_readiness_hash_and_source_changes_gate_enablement(tmp_path):
    module = tool("closure_readiness")
    value = {
        "status": "OFFLINE_CLOSURE_EXECUTION_VERIFIED",
        "source_sha256": module.fingerprints(),
        "tests_passed": True,
    }
    raw = json.dumps(value).encode()
    path = tmp_path / "certificate"
    path.write_bytes(raw)
    assert (
        module.require_closure_ready(path, __import__("hashlib").sha256(raw).hexdigest()) == value
    )
    with pytest.raises(ValueError):
        module.require_closure_ready(path, "wrong")
    with pytest.raises(ValueError, match="EnablementForbidden"):
        module.require_closure_ready(None, None)


@pytest.mark.parametrize(
    "key",
    [
        "account_id",
        "region",
        "plan_sha256",
        "inputs_sha256",
        "manifest_sha256",
        "versions",
        "worker_ai_environment",
    ],
)
def test_receipt_binding_mismatch_never_executes(key):
    module = tool("closure_adapter")
    approval, receipt, inputs, manifest, plan, _, _ = fixture(module)
    receipt[key] = "unapproved"
    with pytest.raises(ValueError):
        module.bind_enablement(approval, receipt, inputs, manifest, plan)
