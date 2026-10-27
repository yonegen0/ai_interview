"""Explicit, immutable Gate B Stage-only recovery; no implicit operational consent."""

import base64
import copy
import hashlib
import json
import os
import re
import signal
import subprocess
import time

from interview_backend.deployment import DeploymentError

ADDRESS = "module.service.aws_apigatewayv2_stage.dev"
PACKAGE_KEYS = {"artifact_bucket", "artifact_key", "artifact_version", "artifact_sha256_base64"}
BEFORE = {
    "requestId": "$context.requestId",
    "routeKey": "$context.routeKey",
    "status": "$context.status",
    "responseLength": "$context.responseLength",
}
AFTER = BEFORE | {
    "requestTimeEpoch": "$context.requestTimeEpoch",
    "responseLatency": "$context.responseLatency",
}


def require(condition):
    if not condition:
        raise DeploymentError("StageRecoveryScopeMismatch")


def canonical_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def parse_format(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result)
            result[key] = value
        return result

    require(isinstance(raw, str))
    return json.loads(raw, object_pairs_hook=unique)


def validate(value, account, region):
    """Only this fixed defect and an existing versioned artifact can be approved."""
    try:
        require(
            set(value)
            == {
                "schema_version",
                "kind",
                "state_identity",
                "state_snapshot_sha256",
                "artifact",
                "stage",
            }
        )
        require(type(value["schema_version"]) is int and value["schema_version"] == 1)
        require(value["kind"] == "gate-b-stage-access-log" and region == "ap-northeast-1")
        identity = value["state_identity"]
        require(set(identity) == {"lineage", "serial", "version_id", "sha256"})
        require(type(identity["serial"]) is int and identity["serial"] == 13)
        require(
            all(isinstance(identity[k], str) and identity[k] for k in ("lineage", "version_id"))
        )
        require(identity["version_id"] != "null")
        for digest in (identity["sha256"], value["state_snapshot_sha256"]):
            require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest))
        artifact = value["artifact"]
        require(set(artifact) == PACKAGE_KEYS)
        require(artifact["artifact_bucket"] == f"ai-interview-artifacts-{account}-{region}")
        require(
            isinstance(artifact["artifact_key"], str)
            and re.fullmatch(r"lambda/[A-Za-z0-9/_-]+[.]zip", artifact["artifact_key"])
        )
        require(
            isinstance(artifact["artifact_version"], str)
            and artifact["artifact_version"] not in {"", "null"}
        )
        require(
            isinstance(artifact["artifact_sha256_base64"], str)
            and re.fullmatch(r"[A-Za-z0-9+/]{43}=", artifact["artifact_sha256_base64"])
        )
        stage = value["stage"]
        require(set(stage) == {"address", "api_id", "stage_name", "format_before", "format_after"})
        require(stage["address"] == ADDRESS and stage["stage_name"] == "dev")
        require(isinstance(stage["api_id"], str) and re.fullmatch(r"[a-z0-9]+", stage["api_id"]))
        require(parse_format(stage["format_before"]) == BEFORE)
        require(parse_format(stage["format_after"]) == AFTER)
    except KeyError, TypeError, ValueError, AttributeError:
        raise DeploymentError("StageRecoveryScopeMismatch") from None
    return copy.deepcopy(value)


def from_approval(package, environment):
    value = package.get("stage_recovery")
    if value is None:
        return None
    require(environment.get("P4_STANDARD_ACTIVE") == "true")
    return validate(value, package["account_id"], package["region"])


def artifact_digest(value):
    return base64.b64decode(value["artifact"]["artifact_sha256_base64"], validate=True).hex()


def state_resources(snapshot):
    resources = {}
    for resource in snapshot["state"]["resources"]:
        if resource.get("mode", "managed") != "managed":
            continue
        for instance in resource["instances"]:
            address = resource.get("module", "")
            address = (address + "." if address else "") + resource["type"] + "." + resource["name"]
            if "index_key" in instance:
                address += "[" + json.dumps(instance["index_key"], separators=(",", ":")) + "]"
            require(address not in resources)
            resources[address] = instance["attributes"]
    return resources


def check_state(snapshot, value):
    require(snapshot["identity"] == value["state_identity"])
    require(canonical_hash(snapshot) == value["state_snapshot_sha256"])
    m, a = snapshot["manifest"], value["artifact"]
    require(
        m["artifact"]
        == {
            "bucket": a["artifact_bucket"],
            "key": a["artifact_key"],
            "version": a["artifact_version"],
            "sha256_base64": a["artifact_sha256_base64"],
        }
    )
    stage = state_resources(snapshot)[ADDRESS]
    require(stage["api_id"] == value["stage"]["api_id"] and stage["name"] == "dev")
    require(stage["access_log_settings"][0]["format"] == value["stage"]["format_after"])
    require(
        all(
            m["configuration"].get(k) is False
            for k in ("api_enabled", "worker_enabled", "streams_enabled", "scheduler_enabled")
        )
    )


def has_unknown(value):
    if isinstance(value, dict):
        return any(has_unknown(v) for v in value.values())
    if isinstance(value, list):
        return any(has_unknown(v) for v in value)
    return value is not False and value is not None


def stage_change(before, after, value, *, drift=False):
    require(isinstance(before, dict) and isinstance(after, dict))
    expected_before = value["stage"]["format_after" if drift else "format_before"]
    expected_after = value["stage"]["format_before" if drift else "format_after"]
    require(before["api_id"] == after["api_id"] == value["stage"]["api_id"])
    require(before["name"] == after["name"] == "dev")
    require(len(before["access_log_settings"]) == len(after["access_log_settings"]) == 1)
    require(before["access_log_settings"][0]["format"] == expected_before)
    require(after["access_log_settings"][0]["format"] == expected_after)
    changed = copy.deepcopy(before)
    changed["access_log_settings"][0]["format"] = expected_after
    require(changed == after)


def planned_resources(root):
    found = {}
    for row in root.get("resources", []):
        if row.get("mode", "managed") == "managed":
            require(row["address"] not in found)
            found[row["address"]] = row["values"]
    for child in root.get("child_modules", []):
        for address, attributes in planned_resources(child).items():
            require(address not in found)
            found[address] = attributes
    return found


def audit_plan(plan, value, snapshot):
    """Reject any mutation, drift, import, uncertainty or output beyond this Format."""
    try:
        require(plan.get("terraform_version") == "1.14.9")
        require(not plan.get("errored") and plan.get("complete", True) is True)
        seen, managed, updates = set(), set(), 0
        original = state_resources(snapshot)
        planned = planned_resources(plan["planned_values"]["root_module"])
        for row in plan["resource_changes"]:
            address, change = row["address"], row["change"]
            require(address not in seen)
            seen.add(address)
            if row.get("mode", "managed") == "managed":
                managed.add(address)
                require(address in planned and planned[address] == change["after"])
            require(
                not row.get("previous_address")
                and not row.get("deposed")
                and not change.get("importing")
            )
            require(
                not change.get("replace_paths") and not has_unknown(change.get("after_unknown", {}))
            )
            if address == ADDRESS:
                require(
                    row["type"] == "aws_apigatewayv2_stage"
                    and row.get("mode", "managed") == "managed"
                )
                require(change["actions"] == ["update"])
                stage_change(change["before"], change["after"], value)
                require(change["after"] == original[ADDRESS])
                updates += 1
            else:
                require(change["actions"] == ["no-op"] and change["before"] == change["after"])
                if row.get("mode", "managed") == "managed":
                    require(change["after"] == original[address])
        require(updates == 1)
        require(managed == set(state_resources(snapshot)) == set(planned))
        drifts = set()
        for row in plan.get("resource_drift", []):
            change = row["change"]
            require(row["address"] not in drifts)
            drifts.add(row["address"])
            require(row["address"] == ADDRESS and change["actions"] == ["update"])
            require(
                not row.get("previous_address")
                and not row.get("deposed")
                and not change.get("importing")
            )
            require(
                not has_unknown(change.get("after_unknown", {})) and not change.get("replace_paths")
            )
            stage_change(change["before"], change["after"], value, drift=True)
        for change in plan.get("output_changes", {}).values():
            require(change["actions"] == ["no-op"] and change["before"] == change["after"])
            require(not has_unknown(change.get("after_unknown", {})))
    except KeyError, TypeError, ValueError, AttributeError:
        raise DeploymentError("StageRecoveryPlanRejected") from None
    return {
        "add": 0,
        "change": 1,
        "destroy": 0,
        "replace": 0,
        "stage_recovery_sha256": canonical_hash(value),
    }


def check_live(session, snapshot, value, environment, *, applied=False):
    """Fresh safety reads; active CI readiness is true only in its own Environment."""
    from botocore.config import Config
    from github_control import github_json
    from standard_diagnostics import checkpoint

    cfg = Config(retries={"total_max_attempts": 1}, connect_timeout=5, read_timeout=10)
    m = snapshot["manifest"]
    api = session.client("apigatewayv2", config=cfg)
    checkpoint("live-api")
    require(api.get_api(ApiId=m["api_id"]).get("DisableExecuteApiEndpoint") is True)
    for mapping in ("worker", "streams"):
        checkpoint("live-" + mapping)
        require(
            session.client("lambda", config=cfg)
            .get_event_source_mapping(UUID=m["mappings"][mapping])
            .get("State")
            == "Disabled"
        )
    checkpoint("live-scheduler")
    require(
        session.client("scheduler", config=cfg)
        .get_schedule(Name="recovery", GroupName="ai-interview-dev")
        .get("State")
        == "DISABLED"
    )
    checkpoint("live-stage")
    actual = api.get_stage(ApiId=m["api_id"], StageName="dev").get("AccessLogSettings", {})
    expected = state_resources(snapshot)[ADDRESS]["access_log_settings"][0]
    require(actual.get("DestinationArn") == expected["destination_arn"])
    require(actual.get("Format") == value["stage"]["format_after" if applied else "format_before"])
    operation = environment["P4_OPERATION"]
    checkpoint("readiness-readback")
    for name in ("dev-plan", "dev-apply"):
        response = github_json(f"environments/{name}/variables?per_page=100", environment)
        require(type(response.get("total_count")) is int and response["total_count"] <= 100)
        variables = {row["name"]: row["value"] for row in response["variables"]}
        expected_flag = "true" if name == "dev-" + operation else "false"
        require(
            all(
                variables.get(k) == expected_flag
                for k in ("P4_STANDARD_READY", "P4_AWS_EXECUTION_READY")
            )
        )


def envelope_recovery(envelope, binding, environment):
    """Existing standard Apply consent binds the exact new Plan/source/run, not old consent."""
    value = envelope.get("stage_recovery")
    require(binding.get("stage_recovery") == value)
    if value is None:
        require("stage_recovery" not in envelope and "stage_recovery" not in binding)
        return None
    require(
        environment.get("P4_STANDARD_ACTIVE") == "true"
        and environment.get("P4_OPERATION") == "apply"
    )
    value = validate(value, environment["AWS_DEV_ACCOUNT_ID"], environment["AWS_REGION"])
    require(envelope["package"] == value["artifact"])
    require(binding["state_identity"] == value["state_identity"])
    require(binding["code_sha"] == environment["P4_APPROVED_SOURCE_SHA"] == envelope["code_sha"])
    require(binding["plan_sha256"] == environment["P4_PLAN_HASH"] == envelope["plan_sha256"])
    require(envelope["run_id"] == environment["P4_PLAN_RUN_ID"] and envelope["run_attempt"] == "1")
    return value


def apply_process(command, directory, *, cwd, env):
    """Persist the actual Apply exit before receipts; never retry an uncertain child."""
    from ci_identity import standard_context

    def record(name, value):
        with (directory / name).open("x", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())

    standard_context(env, reserve=1320)
    record("recovery-process-started.private.json", {"operation": "apply", "one_use": True})
    process = None
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        started = time.monotonic()
        while True:
            standard_context(env, reserve=120)
            require(time.monotonic() - started < 1200)
            try:
                stdout, _ = process.communicate(timeout=1)
                break
            except subprocess.TimeoutExpired:
                continue
        record(
            "recovery-process-exit.private.json",
            {"operation": "apply", "returncode": process.returncode},
        )
        require(process.returncode == 0)
        standard_context(env, reserve=120)
        return stdout
    except BaseException:
        if process is not None and process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.communicate(timeout=120)
                record(
                    "recovery-process-interrupted.private.json",
                    {"returncode": process.returncode, "lock_verified": False},
                )
            except subprocess.TimeoutExpired:
                record(
                    "recovery-process-unknown.private.json",
                    {"status": "UNKNOWN", "retry_authorized": False},
                )
        raise
