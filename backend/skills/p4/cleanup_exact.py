"""Explicitly approved, conditional exact-key cleanup; no Scan/Query/batch reset."""

import hashlib
import json
import os
from pathlib import Path

from botocore.config import Config
from closure_adapter import write

from interview_backend.repositories.codec import from_wire, to_wire

PREFIXES = {"session_id": "SESSION", "attempt_id": "ATTEMPT", "evaluation_id": "EVALUATION"}


def candidates(rows, subject):
    return {
        ("USER#" + subject, PREFIXES[k] + "#" + row[k])
        for row in rows
        for k in PREFIXES
        if k in row
    }


def delete_approved(session, table, rows, subject, approval_raw, approved_sha, journal):
    if hashlib.sha256(approval_raw).hexdigest() != approved_sha:
        raise ValueError("CleanupApprovalHashMismatch")
    approval = json.loads(approval_raw)
    if (
        approval.get("cleanup_authorized") is not True
        or approval.get("table_name") != table
        or approval.get("subject") != subject
        or approval.get("closed_readback_verified") is not True
    ):
        raise ValueError("ExplicitClosedExactCleanupRequired")
    if approval.get("region") != "ap-northeast-1" or session.client(
        "sts", region_name="ap-northeast-1"
    ).get_caller_identity()["Account"] != approval.get("account_id"):
        raise ValueError("CleanupAccountRegionMismatch")
    closed_raw = Path(approval["closed_readback_path"]).read_bytes()
    closed = json.loads(closed_raw)
    if (
        hashlib.sha256(closed_raw).hexdigest() != approval.get("closed_readback_sha256")
        or closed.get("status") != "CLOSED_READBACK_VERIFIED"
        or closed.get("active_lock") is not False
        or closed.get("state_outside_dev_resources") != 0
    ):
        raise ValueError("RealClosedReadbackRequired")
    if not rows or any(r.get("run_id") != approval.get("run_id") for r in rows):
        raise ValueError("ApprovedCleanupRunRequired")
    client = session.client(
        "dynamodb",
        region_name="ap-northeast-1",
        config=Config(retries={"total_max_attempts": 1}, connect_timeout=5, read_timeout=15),
    )
    allowed = candidates(rows, subject)
    records = approval.get("records", [])
    if (
        not records
        or len({(r["PK"], r["SK"]) for r in records}) != len(records)
        or any((r["PK"], r["SK"]) not in allowed for r in records)
    ):
        raise ValueError("ApprovedRunJournalKeysRequired")
    path = Path(journal).resolve()
    private = (Path(__file__).resolve().parents[2] / ".p4-artifacts").resolve()
    if not path.is_relative_to(private):
        raise ValueError("PrivateCleanupJournalRequired")
    attempts = private / "cleanup-attempts"
    attempts.mkdir(exist_ok=True)
    write(attempts / (approved_sha + ".json"), {"status": "STARTED", "journal": str(path)})
    with path.open("x", encoding="utf-8") as stream:
        for expected in records:
            key = {k: expected[k] for k in ("PK", "SK")}
            result = client.get_item(TableName=table, Key=to_wire(key), ConsistentRead=True)
            native = from_wire(result["Item"]) if "Item" in result else None
            if native is None or any(native.get(k) != v for k, v in key.items()):
                raise ValueError("ApprovedCleanupItemMissingOrDifferent")
            raw = json.dumps(native, sort_keys=True, separators=(",", ":"), default=str).encode()
            if (
                hashlib.sha256(raw).hexdigest() != expected.get("item_sha256")
                or native.get("rev") != expected.get("rev")
                or not isinstance(native.get("data"), str)
            ):
                raise ValueError("CleanupSnapshotChangedStop")
            data = json.loads(native["data"])
            if native.get("kind") == "Evaluation" and data.get("status") not in {
                "completed",
                "failed",
            }:
                raise ValueError("ProcessingEvaluationCleanupForbidden")
            stream.write(json.dumps({"status": "DELETE_STARTED", **key}) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            client.delete_item(
                TableName=table,
                Key=to_wire(key),
                ConditionExpression="#r = :r AND #d = :d",
                ExpressionAttributeNames={"#r": "rev", "#d": "data"},
                ExpressionAttributeValues=to_wire({":r": native["rev"], ":d": native["data"]}),
            )
            stream.write(json.dumps({"status": "DELETE_CONFIRMED", **key}) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    return {
        "deleted": len(records),
        "auxiliary_records": "not included; retain and inventory separately",
    }
