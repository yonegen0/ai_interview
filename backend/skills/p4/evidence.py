"""Durable, allowlisted evidence; this module performs no AWS operations."""

import json
import os
import re
from datetime import datetime
from pathlib import Path

from interview_backend.deployment import DeploymentError

FIELDS = frozenset(
    {
        "test_id",
        "run_id",
        "source_sha",
        "manifest_version",
        "started_at",
        "finished_at",
        "result",
        "failure",
        "cleanup",
    }
)
FAILURES = frozenset(
    {
        "none",
        "prerequisite",
        "assertion",
        "timeout",
        "storage",
        "identity",
        "readback",
        "observation",
        "cleanup",
        "interrupted",
    }
)


def validate(record):
    try:
        if not isinstance(record, dict) or record.keys() != FIELDS:
            raise ValueError
        if (
            re.fullmatch(
                r"(?:DB-(?:0[1-9]|1[0-9]|20)|AS-(?:0[1-9]|1[0-8])|AU-(?:0[1-9]|1[0-5])|OP-[0-9]{2})",
                record["test_id"],
            )
            is None
        ):
            raise ValueError
        if re.fullmatch(r"[a-z0-9-]{1,24}", record["run_id"]) is None:
            raise ValueError
        if re.fullmatch(r"[a-f0-9]{40}", record["source_sha"]) is None:
            raise ValueError
        if type(record["manifest_version"]) is not int or record["manifest_version"] < 1:
            raise ValueError
        start, finish = (
            datetime.fromisoformat(record[key]) for key in ("started_at", "finished_at")
        )
        if start.utcoffset() is None or finish.utcoffset() is None or finish < start:
            raise ValueError
        if record["result"] not in {"passed", "failed", "not_run"}:
            raise ValueError
        if record["failure"] not in FAILURES:
            raise ValueError
        if record["cleanup"] not in {"passed", "failed", "not_required", "not_run"}:
            raise ValueError
        if record["result"] == "passed" and (
            record["failure"] != "none" or record["cleanup"] not in {"passed", "not_required"}
        ):
            raise ValueError
        if record["result"] == "failed" and record["failure"] == "none":
            raise ValueError
    except ValueError, TypeError, KeyError, AttributeError:
        raise DeploymentError("InvalidEvidenceRecord") from None
    return dict(record)


def append(path, record, *, private_root):
    record = validate(record)
    path, root = Path(path).resolve(), Path(private_root).resolve()
    if not path.is_relative_to(root) or path == root or not path.parent.is_dir():
        raise DeploymentError("PrivateEvidencePathRequired")
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def outcome(records, required_ids):
    """Missing and unexecuted mandatory evidence can never make a run pass."""
    rows = [validate(record) for record in records]
    ids = [row["test_id"] for row in rows]
    identities = {(row["run_id"], row["source_sha"], row["manifest_version"]) for row in rows}
    if len(ids) != len(set(ids)) or len(identities) > 1:
        raise DeploymentError("ConflictingEvidence")
    if set(ids) != set(required_ids):
        return "failed"
    return "passed" if rows and all(row["result"] == "passed" for row in rows) else "failed"
