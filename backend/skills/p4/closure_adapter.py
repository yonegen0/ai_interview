"""Saved-plan-only conditional Closure with no retry after an apply attempt."""

import hashlib
import json
import os
import re
from copy import deepcopy
from pathlib import Path

FLAGS = ("api_enabled", "worker_enabled", "streams_enabled", "scheduler_enabled")
UPDATES = {
    "module.service.aws_apigatewayv2_api.main": ("disable_execute_api_endpoint", False, True),
    "module.service.aws_lambda_event_source_mapping.worker": ("enabled", True, False),
    "module.service.aws_lambda_event_source_mapping.streams": ("enabled", True, False),
    "module.service.aws_scheduler_schedule.recovery": ("state", "ENABLED", "DISABLED"),
}
MAPPING_METADATA = ("last_modified", "last_processing_result", "state_transition_reason")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def closed_inputs(inputs):
    if any(inputs.get(k) is not True for k in FLAGS):
        raise ValueError("FourActiveFlagsRequired")
    return deepcopy(inputs) | dict.fromkeys(FLAGS, False)


def state_instances(state):
    """Exact address -> attributes; duplicate instances cannot disappear in a set."""
    instances = {}
    for resource in state["resources"]:
        prefix = resource.get("module", "")
        prefix = prefix + "." if prefix else ""
        prefix += "data." if resource.get("mode") == "data" else ""
        base = prefix + resource["type"] + "." + resource["name"]
        for instance in resource["instances"]:
            index = instance.get("index_key")
            address = base if index is None else base + "[" + json.dumps(index) + "]"
            if address in instances:
                raise ValueError("DuplicateStateAddress")
            instances[address] = instance["attributes"]
    return instances


def state_addresses(state):
    return set(state_instances(state))


def readback_inventory(state):
    """Mapping service status metadata changes when the approved enabled flag closes.

    Only these read-only provider fields of the two approved mapping resources
    are excluded. All identities/configuration and every baseline resource stay
    exact; the mapping's final state is still required to become Disabled.
    """
    result = deepcopy(state_instances(state))
    for address in UPDATES:
        if ".aws_lambda_event_source_mapping." in address and address in result:
            for name in MAPPING_METADATA:
                result[address].pop(name, None)
    return result


def closed_inventory(state, alarm_addresses):
    """Derive the closure result from the bound authoritative State, never a count."""
    original = state_instances(state)
    actual_alarms = {
        address: attrs.get("alarm_name")
        for address, attrs in original.items()
        if address.startswith("module.service.aws_cloudwatch_metric_alarm.")
    }
    if (
        not isinstance(alarm_addresses, dict)
        or not alarm_addresses
        or actual_alarms != alarm_addresses
        or len(set(alarm_addresses.values())) != len(alarm_addresses)
        or not set(UPDATES) <= original.keys()
    ):
        raise ValueError("AuthoritativeStateAndApprovedAlarmsRequired")
    expected = {a: v for a, v in readback_inventory(state).items() if a not in alarm_addresses}
    for address, (key, before, after) in UPDATES.items():
        if type(expected[address].get(key)) is not type(before) or expected[address][key] != before:
            raise ValueError("ActiveClosureStateRequired")
        expected[address][key] = after
        if ".aws_lambda_event_source_mapping." in address and "state" in expected[address]:
            if expected[address]["state"] != "Enabled":
                raise ValueError("ActiveMappingStateRequired")
            expected[address]["state"] = "Disabled"
    return expected


def unknown(value):
    if isinstance(value, dict):
        return any(unknown(v) for v in value.values())
    if isinstance(value, list):
        return any(unknown(v) for v in value)
    return value is True


def audit_plan(review, state, alarm_addresses):
    """Every saved-plan entry is audited, including refresh drift and outputs."""
    if review.get("errored") or review.get("deferred_changes"):
        raise ValueError("PlanDriftOrDeferredChange")
    state_values = deepcopy(state_instances(state))
    refreshed = set()
    for entry in review.get("resource_drift", []):
        address, change = entry.get("address"), entry.get("change", {})
        before, after = change.get("before"), change.get("after")
        if (
            address not in UPDATES
            or ".aws_lambda_event_source_mapping." not in address
            or entry.get("type") != "aws_lambda_event_source_mapping"
            or entry.get("previous_address")
            or entry.get("deposed")
            or entry.get("mode", "managed") != "managed"
            or address in refreshed
            or change.get("actions") != ["update"]
            or change.get("replace_paths")
            or unknown(change.get("after_unknown", {}))
            or not isinstance(before, dict)
            or not isinstance(after, dict)
            or any(
                value.get(key) is not None and not isinstance(value[key], str)
                for value in (before, after)
                for key in MAPPING_METADATA
            )
            or before != state_values.get(address)
            or {k: v for k, v in before.items() if k not in MAPPING_METADATA}
            != {k: v for k, v in after.items() if k not in MAPPING_METADATA}
        ):
            raise ValueError("PlanDriftOrDeferredChange")
        state_values[address] = after
        refreshed.add(address)
    entries = review.get("resource_changes", [])
    addresses = [e["address"] for e in entries]
    if len(set(addresses)) != len(addresses) or set(addresses) != state_addresses(state):
        raise ValueError("FullStatePlanAuditRequired")
    updates, deletes = set(), set()
    for entry in entries:
        address, change = entry["address"], entry["change"]
        actions = change["actions"]
        if change.get("before") != state_values[address]:
            raise ValueError("SavedPlanBeforeStateMismatch")
        if unknown(change.get("after_unknown", {})) or change.get("replace_paths"):
            raise ValueError("UnknownOrReplacementForbidden")
        if actions == ["no-op"]:
            if change["before"] != change["after"]:
                raise ValueError("BaselineNoOpMismatch")
        elif address in UPDATES and actions == ["update"]:
            key, before, after = UPDATES[address]
            original, result = change["before"], change["after"]
            if (
                type(original.get(key)) is not type(before)
                or original[key] != before
                or result != original | {key: after}
            ):
                raise ValueError("UnexpectedClosureUpdate")
            updates.add(address)
        elif address in alarm_addresses and actions == ["delete"]:
            if (
                entry.get("type") != "aws_cloudwatch_metric_alarm"
                or change["after"] is not None
                or change["before"].get("alarm_name") != alarm_addresses[address]
            ):
                raise ValueError("AlarmDeletionScopeMismatch")
            deletes.add(address)
        else:
            raise ValueError("ClosureWhitelistDeviation:" + address)
    if updates != set(UPDATES) or deletes != set(alarm_addresses):
        raise ValueError("FourUpdatesAndApprovedAlarmDeletesRequired")
    outputs = review.get("output_changes", {})
    if (
        "manifest" not in outputs
        or outputs["manifest"]["before"] != state["outputs"]["manifest"]["value"]
    ):
        raise ValueError("FullManifestOutputAuditRequired")
    for name, change in outputs.items():
        if unknown(change.get("after_unknown", {})):
            raise ValueError("UnknownClosureOutput")
        expected = deepcopy(change["before"])
        if name == "manifest":
            expected["configuration"].update(dict.fromkeys(FLAGS, False))
        if change["after"] != expected:
            raise ValueError("ClosureOutputMismatch")
    return {
        "create": 0,
        "replace": 0,
        "update": 4,
        "destroy": len(deletes),
        "audited": len(entries),
    }


def bind_enablement(approval, receipt, inputs_raw, manifest_raw, enablement_plan):
    """No placeholders accepted; a real successful receipt must bind actual bytes."""
    inputs, manifest = json.loads(inputs_raw), json.loads(manifest_raw)
    if approval.get("conditional_closure_authorized") is not True or approval.get(
        "closure_source_sha256"
    ) != digest(Path(__file__).read_bytes()):
        raise ValueError("ApprovedClosureSourceRequired")
    if approval.get("driver_source_sha256") != digest(
        Path(__file__).with_name("closure_aws.py").read_bytes()
    ):
        raise ValueError("ApprovedClosureDriverRequired")
    if (
        receipt.get("status") != "ENABLEMENT_READBACK_VERIFIED"
        or receipt.get("partial_failure") is not False
    ):
        raise ValueError("SuccessfulEnablementReceiptRequired")
    if approval.get("enablement_plan_sha256") != digest(enablement_plan) or receipt.get(
        "plan_sha256"
    ) != digest(enablement_plan):
        raise ValueError("EnablementSavedPlanMismatch")
    for key in ("account_id", "region", "code_sha", "lock_sha256"):
        if not approval.get(key) or receipt.get(key) != approval[key]:
            raise ValueError("EnablementReceiptBindingMismatch")
    if (
        not re.fullmatch(r"\d{12}", approval["account_id"])
        or approval["region"] != "ap-northeast-1"
    ):
        raise ValueError("AccountRegionMismatch")
    if (
        manifest.get("account_id") != approval["account_id"]
        or manifest.get("region") != approval["region"]
        or manifest.get("environment") != "dev"
    ):
        raise ValueError("DevManifestRequired")
    if receipt.get("inputs_sha256") != digest(inputs_raw) or receipt.get(
        "manifest_sha256"
    ) != digest(manifest_raw):
        raise ValueError("LatestSuccessfulInputsRequired")
    if (
        receipt.get("artifact") != manifest.get("artifact")
        or receipt.get("versions") != manifest.get("versions")
        or receipt.get("aliases") != manifest.get("aliases")
    ):
        raise ValueError("LatestArtifactVersionsAliasesRequired")
    expected_artifact = {
        "bucket": inputs.get("artifact_bucket"),
        "key": inputs.get("artifact_key"),
        "version": inputs.get("artifact_version"),
        "sha256_base64": inputs.get("artifact_sha256_base64"),
    }
    if expected_artifact != manifest["artifact"]:
        raise ValueError("ArtifactInputMismatch")
    if receipt.get("worker_ai_environment", {}) != inputs.get(
        "worker_ai_environment", {}
    ) or manifest.get("worker_ai_environment", {}) != inputs.get("worker_ai_environment", {}):
        raise ValueError("ProviderConfigurationMismatch")
    if receipt.get("worker_wif_enabled", False) != inputs.get("worker_wif_enabled", False):
        raise ValueError("WorkerGrantConfigurationMismatch")
    if manifest.get("worker_wif_enabled", False) != inputs.get("worker_wif_enabled", False):
        raise ValueError("WorkerGrantManifestMismatch")
    for key in FLAGS:
        if inputs.get(key) is not True or manifest.get("configuration", {}).get(key) is not True:
            raise ValueError("SuccessfulActiveEnablementRequired")
    state_before, state_after = receipt.get("state_before", {}), receipt.get("state_after", {})
    if (
        state_before != approval.get("state_before")
        or state_after.get("lineage") != state_before.get("lineage")
        or type(state_after.get("serial")) is not int
        or state_after["serial"] <= state_before.get("serial", -1)
    ):
        raise ValueError("EnablementStateReceiptMismatch")
    return inputs, manifest


def require_snapshot(snapshot, receipt, manifest):
    identity = snapshot["identity"]
    if (
        identity != receipt["state_after"]
        or snapshot.get("active_lock") is not False
        or snapshot.get("state_outside_dev_resources") != 0
        or snapshot.get("manifest") != manifest
        or (
            "state_addresses" in receipt
            and sorted(state_addresses(snapshot["state"])) != receipt["state_addresses"]
        )
    ):
        raise ValueError("CurrentStateOrNamespaceMismatch")


def execute_closure(
    approval_raw,
    approval_sha256,
    receipt_raw,
    inputs_raw,
    manifest_raw,
    enablement_plan,
    directory,
    driver,
):
    """driver is the concrete TerraformAWS driver; tests use a network-free fixture."""
    if digest(approval_raw) != approval_sha256:
        raise ValueError("ClosureApprovalHashMismatch")
    approval, receipt = json.loads(approval_raw), json.loads(receipt_raw)
    inputs, active = bind_enablement(approval, receipt, inputs_raw, manifest_raw, enablement_plan)
    directory = Path(directory).resolve()
    private = Path(__file__).resolve().parents[2] / ".p4-artifacts"
    if not directory.is_relative_to(private.resolve()):
        raise ValueError("PrivateClosureDirectoryRequired")
    directory.mkdir(exist_ok=False)
    attempts = private / "closure-attempts"
    attempts.mkdir(exist_ok=True)
    write(
        attempts / (digest(enablement_plan) + ".json"),
        {"approval_sha256": approval_sha256, "directory": str(directory)},
    )
    write(
        directory / "started.json",
        {"approval_sha256": approval_sha256, "receipt_sha256": digest(receipt_raw)},
    )
    try:
        before = driver.snapshot(active)
        require_snapshot(before, receipt, active)
        expected_inventory = closed_inventory(before["state"], approval["validation_alarms"])
        closed = closed_inputs(inputs)
        plan, review = driver.plan(closed, directory)
        summary = audit_plan(review, before["state"], approval["validation_alarms"])
        plan_hash = digest(plan.read_bytes())
        if (
            approval.get("closure_plan_sha256") is not None
            and approval["closure_plan_sha256"] != plan_hash
        ):
            raise ValueError("ClosureSavedPlanHashMismatch")
        write(directory / "audit.json", summary | {"plan_sha256": plan_hash})
        immediately_before = driver.snapshot(active)
        require_snapshot(immediately_before, receipt, active)
        if immediately_before["state"] != before["state"]:
            raise ValueError("ClosureStateChangedBeforeApply")
        if digest(plan.read_bytes()) != plan_hash:
            raise ValueError("ClosurePlanChangedAfterAudit")
        write(directory / "apply-started.json", {"plan_sha256": plan_hash})
        # No retry, replan, destroy, state surgery or manual repair on any failure.
        driver.apply(plan, plan_hash)
        write(directory / "apply-completed.json", {"plan_sha256": plan_hash})
        expected = deepcopy(active)
        expected["configuration"].update(dict.fromkeys(FLAGS, False))
        after = driver.snapshot(expected)
        if readback_inventory(after["state"]) != expected_inventory:
            raise ValueError("ClosedStateInventoryMismatch")
        if (
            after.get("active_lock") is not False
            or after.get("state_outside_dev_resources") != 0
            or after["manifest"] != expected
            or after["identity"]["lineage"] != before["identity"]["lineage"]
            or after["identity"]["serial"] <= before["identity"]["serial"]
        ):
            raise ValueError("ClosureReadbackMismatch")
        evidence = {
            "status": "CLOSED_READBACK_VERIFIED",
            "api_disabled": True,
            "worker_disabled": True,
            "streams_disabled": True,
            "scheduler_disabled": True,
            "validation_alarm_count": 0,
            "active_lock": False,
            "state_outside_dev_resources": 0,
            "plan_sha256": plan_hash,
            "state": after["identity"],
        }
        write(directory / "closed-readback.json", evidence)
        return evidence
    except Exception:
        write(
            directory / "stopped.json",
            {
                "status": "READ_ONLY_DIAGNOSIS_REQUIRED",
                "apply_started": (directory / "apply-started.json").exists(),
                "active_may_remain": True,
            },
        )
        raise


def save_enablement_receipt(directory, approval, inputs_raw, manifest_raw, plan, before, driver):
    """Normalize real successful apply evidence only; never called in preparation."""
    directory = Path(directory)
    started = json.loads((directory / "apply-started.json").read_bytes())
    completed = json.loads((directory / "apply-completed.json").read_bytes())
    plan_hash = digest(Path(plan).read_bytes())
    if (
        started.get("plan_sha256") != plan_hash
        or completed.get("plan_sha256") != plan_hash
        or approval["enablement_plan_sha256"] != plan_hash
    ):
        raise ValueError("RealSuccessfulApplyEvidenceRequired")
    manifest = json.loads(manifest_raw)
    after = driver.snapshot(manifest)
    receipt = {
        "status": "ENABLEMENT_READBACK_VERIFIED",
        "partial_failure": False,
        "plan_sha256": plan_hash,
        "inputs_sha256": digest(inputs_raw),
        "manifest_sha256": digest(manifest_raw),
        "state_before": before,
        "state_after": after["identity"],
        "state_addresses": sorted(state_addresses(after["state"])),
        "artifact": manifest["artifact"],
        "versions": manifest["versions"],
        "aliases": manifest["aliases"],
        "worker_ai_environment": manifest.get("worker_ai_environment", {}),
        "worker_wif_enabled": json.loads(inputs_raw).get("worker_wif_enabled", False),
        **{k: approval[k] for k in ("account_id", "region", "code_sha", "lock_sha256")},
    }
    bind_enablement(approval, receipt, inputs_raw, manifest_raw, Path(plan).read_bytes())
    write(directory / "enablement-receipt.json", receipt)
    return receipt


class BoundClosure:
    """Runtime paths are mandatory bindings; absent future receipt fails closed."""

    def __init__(
        self,
        *,
        approval_path,
        approval_sha256,
        receipt_path,
        inputs_path,
        manifest_path,
        enablement_plan_path,
        directory,
        terraform_root,
        environment=None,
    ):
        self.approval_path, self.approval_sha256 = Path(approval_path), approval_sha256
        self.receipt_path, self.inputs_path = receipt_path, inputs_path
        self.manifest_path, self.enablement_plan_path = manifest_path, enablement_plan_path
        self.directory, self.terraform_root, self.environment = (
            directory,
            terraform_root,
            environment,
        )

    def __call__(self, manifest, live_approval):
        from closure_aws import TerraformAWS

        raw = self.approval_path.read_bytes()
        if digest(raw) != self.approval_sha256:
            raise ValueError("ClosureApprovalHashMismatch")
        active_raw = Path(self.manifest_path).read_bytes()
        if (
            json.loads(active_raw) != manifest
            or live_approval.get("closure_approval_sha256") != self.approval_sha256
        ):
            raise ValueError("LiveClosureManifestBindingMismatch")
        approval = json.loads(raw)
        driver = TerraformAWS(self.terraform_root, approval, self.environment)
        return execute_closure(
            raw,
            self.approval_sha256,
            Path(self.receipt_path).read_bytes(),
            Path(self.inputs_path).read_bytes(),
            active_raw,
            Path(self.enablement_plan_path).read_bytes(),
            self.directory,
            driver,
        )
