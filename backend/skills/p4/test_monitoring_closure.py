"""Read-only test drain evidence. Never disable resources, purge queues, or apply."""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from bootstrap_state import private_path
from cost_controls import FLAGS
from deployment_guards import read_state_snapshot
from manifest import read_manifest, verify_live_manifest

from interview_backend.deployment import checked_session, require_aws_execution
from interview_backend.repositories.codec import PARTITIONS


def verify_idle(session, manifest, *, sleep=time.sleep):
    if manifest["schema_version"] != 4 or manifest["environment"] != "test":
        raise ValueError("Schema4DedicatedTestRequired")
    if any(manifest["configuration"][key] for key in FLAGS):
        raise ValueError("FourClosedFlagsRequired")
    if not manifest["configuration"]["test_monitoring_enabled"]:
        raise ValueError("KeepAlarmsDuringDrainRequired")
    verify_live_manifest(session, manifest, require_api_enabled=False)
    # Two observations separated by the longest function timeout. All writers must be quiescent.
    for sample in range(2):
        sqs = session.client("sqs", region_name=manifest["region"])
        for key in ("queue_url", "worker_dlq_url", "stream_failure_url"):
            names = [
                "ApproximateNumberOfMessagesVisible",
                "ApproximateNumberOfMessagesNotVisible",
                "ApproximateNumberOfMessagesDelayed",
            ]
            attrs = sqs.get_queue_attributes(QueueUrl=manifest[key], AttributeNames=names)[
                "Attributes"
            ]
            if any(attrs.get(name) != "0" for name in names):
                raise ValueError("ResidualQueueWorkOrUnknown")
        ddb = session.client("dynamodb", region_name=manifest["region"])
        for partition in PARTITIONS:
            result = ddb.query(
                TableName=manifest["table_name"],
                IndexName="WorkIndex",
                KeyConditionExpression="work_pk = :partition",
                ExpressionAttributeValues={":partition": {"S": partition}},
                Select="COUNT",
                Limit=1,
            )
            if result.get("Count") != 0 or result.get("LastEvaluatedKey"):
                raise ValueError("ResidualEvaluationWorkOrUnknown")
        if sample == 0:
            sleep(60)
    return {
        "status": "TEST_DRAIN_OBSERVED",
        "closure_eligible": False,
        "limitations": [
            "SQS_APPROXIMATE_COUNTS",
            "EVENTUALLY_CONSISTENT_GSI",
            "INFLIGHT_OR_FUTURE_WORK_UNPROVEN",
        ],
        "account_id": manifest["account_id"],
        "region": manifest["region"],
        "run_id": manifest["run_id"],
        "observed_at_epoch": int(time.time()),
        "samples": 2,
        "interval_seconds": 60,
        "monitoring_kept": True,
        "manifest_sha256": hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    require_aws_execution()
    manifest = read_manifest(args.manifest, args.account, args.region, require_test=True)
    private = (Path(__file__).resolve().parents[2] / ".p4-artifacts").resolve()
    output = private_path(args.output, private)
    if not output.parent.is_dir():
        raise ValueError("ExistingPrivateOutputDirectoryRequired")
    session = checked_session(args.account, args.region)
    state_key = f"test/{manifest['run_id']}/terraform.tfstate"
    before = read_state_snapshot(session, args.account, args.region, state_key)
    if before["manifest"] != manifest:
        raise ValueError("CurrentTestStateManifestRequired")
    result = verify_idle(session, manifest)
    if read_state_snapshot(session, args.account, args.region, state_key) != before:
        raise ValueError("TestStateChangedDuringDrainObservation")
    issued = result["observed_at_epoch"]
    result.update(
        state_identity=before["identity"],
        issued_at_epoch=issued,
        expires_at_epoch=issued + 900,
        issued_at=datetime.fromtimestamp(issued, UTC).isoformat(),
        expires_at=datetime.fromtimestamp(issued + 900, UTC).isoformat(),
    )
    with os.fdopen(
        os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8"
    ) as stream:
        json.dump(result, stream, sort_keys=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("TestDrainObservationFailed", file=sys.stderr)
        raise SystemExit(1) from None
