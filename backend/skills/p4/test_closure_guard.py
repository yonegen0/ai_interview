"""Fresh, independently approved test closure; observation alone is never authorization.

All functions are offline-testable. Call guard immediately before the saved-plan
apply. Missing permissions, evidence, or readbacks fail closed. Never auto-retry.
"""

import json
import time

from botocore.exceptions import ClientError
from closure_adapter import state_instances, unknown
from deployment_guards import approved_json, canonical_hash, require_bound, sha256
from manifest_alarms import expected_alarms
from test_monitoring_closure import verify_idle

from interview_backend.models.internal import Dispatch, Evaluation
from interview_backend.repositories.codec import decode, from_wire


def evidence_files(proof, private):
    """Reviewed artifacts, not boolean claims, must substantiate every boundary."""
    required = {"external_writers", "queue_ledger", "incident_resolution"}
    files = proof.get("reviewed_evidence", {})
    if (
        set(files) != required
        or proof.get("approved_by") == proof.get("observed_by")
        or not proof.get("approved_by")
        or not proof.get("observed_by")
    ):
        raise ValueError("IndependentDrainApprovalRequired")
    for kind in required:
        reference = files[kind]
        _, document = approved_json(reference["path"], reference["sha256"], private)
        if (
            document.get("status") != "RECONCILED"
            or type(document.get("remaining")) is not int
            or document.get("remaining") != 0
            or any(
                document.get(k) != proof.get(k)
                for k in ("account_id", "region", "run_id", "manifest_sha256", "state_identity")
            )
        ):
            raise ValueError("ReconciledDrainEvidenceRequired")
        observed = document.get("observed_at_epoch")
        if (
            type(observed) is not int
            or not proof["issued_at_epoch"] - 60 <= observed <= proof["issued_at_epoch"]
        ):
            raise ValueError("StaleDrainBoundaryEvidence")
        if kind == "incident_resolution" and document.get(
            "resolved_outcome_unknown", []
        ) != proof.get("resolved_outcome_unknown", []):
            raise ValueError("OutcomeUnknownResolutionMismatch")


def verify_quiescent(session, manifest, proof, *, now):
    stopped = proof.get("writers_stopped_at_epoch")
    if type(stopped) is not int or stopped < 0 or stopped > now:
        raise ValueError("WriterQuiescenceUnknown")
    # Four disabled entry paths are checked by verify_idle. Independently reviewed
    # external-writer/queue ledgers bind the last possible invocation to `stopped`.
    # Wait the entire async lifetime plus timeout; a momentary zero metric cannot
    # prove absence of an in-flight invocation or an asynchronous retry.
    client = session.client("lambda", region_name=manifest["region"])
    for alias in manifest["aliases"].values():
        name, qualifier = alias.rsplit(":", 1)
        config = client.get_function_configuration(FunctionName=name, Qualifier=qualifier)
        if (
            client.get_function_concurrency(FunctionName=name).get(
                "ReservedConcurrentExecutions", -1
            )
            != -1
        ):
            raise ValueError("LambdaConcurrencyInvariantChanged")
        try:
            asynchronous = client.get_function_event_invoke_config(
                FunctionName=name, Qualifier=qualifier
            )
            age = asynchronous["MaximumEventAgeInSeconds"]
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ResourceNotFoundException":
                raise
            age = 21600  # Lambda's default asynchronous event lifetime: six hours.
        timeout = config.get("Timeout")
        if (
            type(age) is not int
            or not 60 <= age <= 21600
            or type(timeout) is not int
            or not 1 <= timeout <= 900
            or now - stopped < age + timeout
        ):
            raise ValueError("InflightOrAsyncRetryWindowNotDrained")
    ddb = session.client("dynamodb", region_name=manifest["region"])
    args = {"TableName": manifest["table_name"], "ConsistentRead": True}
    seen_cursors = set()
    while True:
        result = ddb.scan(**args)  # Never rely on an eventually consistent GSI.
        if not isinstance(result.get("Items"), list):
            raise ValueError("StrongWorkInventoryUnavailable")
        for item in result["Items"]:
            record, _ = decode(from_wire(item))
            if (
                isinstance(record, Evaluation)
                and (record.status == "processing" or record.worker_state != "terminal")
                or isinstance(record, Dispatch)
                and record.status != "DONE"
            ):
                raise ValueError("ResidualIncludingFutureWork")
            if (
                isinstance(record, Evaluation)
                and record.failure_reason == "OUTCOME_UNKNOWN"
                and {"owner": record.owner, "evaluation_id": record.id}
                not in proof.get("resolved_outcome_unknown", [])
            ):
                raise ValueError("UnresolvedOutcomeUnknown")
        if not result.get("LastEvaluatedKey"):
            break
        cursor = canonical_hash(result["LastEvaluatedKey"])
        if cursor in seen_cursors:
            raise ValueError("StrongInventoryPaginationCycle")
        seen_cursors.add(cursor)
        args["ExclusiveStartKey"] = result["LastEvaluatedKey"]


def audit_plan(review, snapshot, manifest):
    if review.get("errored") or review.get("resource_drift") or review.get("deferred_changes"):
        raise ValueError("TestPlanDriftOrDeferredChange")
    before = state_instances(snapshot["state"])
    alarms = expected_alarms(manifest, f"ai-interview-test-{manifest['run_id']}")
    addresses = {
        address
        for address, attrs in before.items()
        if address.startswith("module.service.aws_cloudwatch_metric_alarm.")
    }
    if (
        len(alarms) != 39
        or len(addresses) != 39
        or {before[a].get("alarm_name") for a in addresses} != set(alarms)
    ):
        raise ValueError("Exact39TestAlarmsRequired")
    entries = review.get("resource_changes", [])
    if len(entries) != len(before) or {e["address"] for e in entries} != set(before):
        raise ValueError("CompleteTestPlanInventoryRequired")
    for entry in entries:
        address, change = entry["address"], entry["change"]
        if (
            change.get("before") != before[address]
            or change.get("replace_paths")
            or unknown(change.get("after_unknown"))
            or change.get("actions") != (["delete"] if address in addresses else ["no-op"])
            or address not in addresses
            and change.get("after") != before[address]
        ):
            raise ValueError("OnlyApprovedTestAlarmDeletesAllowed")
    expected = json.loads(json.dumps(manifest))
    expected["configuration"].update(test_monitoring_enabled=False, test_closure_confirmed=True)
    after = review.get("output_changes", {}).get("manifest", {}).get("after")
    output_changes = review.get("output_changes", {})
    if (
        set(output_changes) != {"manifest"}
        or output_changes["manifest"].get("before") != manifest
        or unknown(output_changes["manifest"].get("after_unknown"))
    ):
        raise ValueError("ExactTestManifestOutputAuditRequired")
    if not isinstance(after, dict):
        raise ValueError("ClosedTestOutputRequired")
    expected["test_closure_evidence_sha256"] = after.get("test_closure_evidence_sha256")
    if (
        not isinstance(expected["test_closure_evidence_sha256"], str)
        or len(expected["test_closure_evidence_sha256"]) != 64
        or after != expected
    ):
        raise ValueError("ClosedTestOutputMismatch")
    return {a: v for a, v in before.items() if a not in addresses}, expected


def guard(
    session,
    manifest,
    snapshot,
    review,
    proof_path,
    proof_hash,
    private,
    *,
    now=None,
    sleep=time.sleep,
):
    live_clock = now is None
    now = int(time.time()) if live_clock else now
    raw, proof = approved_json(proof_path, proof_hash, private)
    require_bound(proof, manifest, snapshot, now)
    if proof.get("status") != "APPROVED_TEST_DRAIN" or proof.get("alarm_count") != 39:
        raise ValueError("ApprovedTestDrainRequired")
    evidence_files(proof, private)
    verify_quiescent(session, manifest, proof, now=now)
    observation = verify_idle(session, manifest, sleep=sleep)
    inventory, expected = audit_plan(review, snapshot, manifest)
    if expected["test_closure_evidence_sha256"] != sha256(raw):
        raise ValueError("PlanDrainEvidenceMismatch")
    require_bound(proof, manifest, snapshot, int(time.time()) if live_clock else now)
    return inventory, expected, observation


def apply_once(
    driver, directory, manifest, review, proof_path, proof_hash, private, *, now=time.time
):
    """Driver performs live reads/apply; mock drivers are the only Cloud test callers."""
    from bootstrap_state import write_record

    global_attempt = private / ("test-closure-" + proof_hash + "-attempt.json")
    if (directory / "test-apply-attempt.json").exists() or global_attempt.exists():
        raise ValueError("TestApplyAlreadyAttempted")
    first = driver.snapshot()
    inventory, expected, _ = guard(
        driver.session,
        manifest,
        first,
        review,
        proof_path,
        proof_hash,
        private,
        now=int(now()),
        sleep=driver.sleep,
    )
    current = driver.snapshot()
    if current != first:
        raise ValueError("TestStateChangedBeforeApply")
    # Recheck approval lifetime and artifact hashes after observation and before apply.
    _, proof = approved_json(proof_path, proof_hash, private)
    require_bound(proof, manifest, current, int(now()))
    evidence_files(proof, private)
    write_record(
        global_attempt, {"proof_sha256": proof_hash, "review_sha256": canonical_hash(review)}
    )
    write_record(
        directory / "test-apply-attempt.json",
        {"proof_sha256": proof_hash, "review_sha256": canonical_hash(review)},
    )
    driver.apply(review)
    after = driver.snapshot()
    if (
        state_instances(after["state"]) != inventory
        or after["manifest"] != expected
        or after["identity"]["lineage"] != first["identity"]["lineage"]
        or after["identity"]["serial"] <= first["identity"]["serial"]
        or after["identity"]["version_id"] == first["identity"]["version_id"]
    ):
        raise ValueError("ClosedTestReadbackMismatch")
    driver.verify(expected)
    write_record(directory / "test-apply-completed.json", {"proof_sha256": proof_hash})


def require_reopen(snapshot, *, enabling):
    """Restore/verify all 39 alarms with entry flags closed before any enablement."""
    manifest = snapshot["manifest"]
    if enabling:
        alarms = expected_alarms(manifest, f"ai-interview-test-{manifest['run_id']}")
        actual = {
            v.get("alarm_name")
            for a, v in state_instances(snapshot["state"]).items()
            if a.startswith("module.service.aws_cloudwatch_metric_alarm.")
        }
        if (
            not manifest["configuration"]["test_monitoring_enabled"]
            or len(alarms) != 39
            or actual != set(alarms)
        ):
            raise ValueError("RestoreAndReadback39BeforeTestEnablement")
