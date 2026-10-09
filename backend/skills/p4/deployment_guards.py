"""Private approvals bound to immutable remote State; never infer approval from observations."""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from botocore.exceptions import ClientError


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical_hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def approved_json(path, approved_hash, private):
    from bootstrap_state import private_path

    target = private_path(path, Path(private).resolve())
    raw = target.read_bytes()
    if not re.fullmatch(r"[0-9a-f]{64}", approved_hash or "") or sha256(raw) != approved_hash:
        raise ValueError("PrivateApprovalHashMismatch")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("PrivateApprovalObjectRequired")
    return raw, value


def read_state_snapshot(session, account, region, state_key, *, allow_absent=False):
    """Read a fixed S3 VersionId, and reject a lock or a concurrently changed State."""
    if not re.fullmatch(r"[0-9]{12}", account) or region != "ap-northeast-1":
        raise ValueError("StateAccountRegionMismatch")
    if state_key != "dev/terraform.tfstate" and not re.fullmatch(
        r"test/[a-z0-9-]{1,24}/terraform[.]tfstate", state_key
    ):
        raise ValueError("CanonicalStateKeyRequired")
    s3 = session.client("s3", region_name=region)
    args = {
        "Bucket": f"ai-interview-state-{account}-{region}",
        "Key": state_key,
        "ExpectedBucketOwner": account,
    }
    try:
        s3.head_object(**(args | {"Key": state_key + ".tflock"}))
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in {"404", "NoSuchKey", "NotFound"}:
            raise ValueError("StateLockReadUnavailable") from None
    else:
        raise ValueError("ActiveStateLock")
    try:
        head = s3.head_object(**args)
    except ClientError as exc:
        if allow_absent and exc.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}:
            return {"identity": None, "state": {"resources": []}, "manifest": None}
        raise ValueError("AuthoritativeStateUnavailable") from None
    version = head.get("VersionId")
    if not version or version == "null":
        raise ValueError("VersionedStateRequired")
    obj = s3.get_object(**args, VersionId=version)
    with obj["Body"] as body:
        raw = body.read()
    if (
        obj.get("VersionId") != version
        or obj.get("ServerSideEncryption") != "AES256"
        or s3.head_object(**args).get("VersionId") != version
    ):
        raise ValueError("StateReadbackChanged")
    state = json.loads(raw)
    if (
        not isinstance(state.get("lineage"), str)
        or not state["lineage"]
        or type(state.get("serial")) is not int
        or state["serial"] < 0
    ):
        raise ValueError("StateIdentityRequired")
    manifest = state["outputs"]["manifest"]["value"]
    expected_run = "" if state_key == "dev/terraform.tfstate" else state_key.split("/")[1]
    if (
        manifest.get("account_id") != account
        or manifest.get("region") != region
        or manifest.get("run_id") != expected_run
    ):
        raise ValueError("StateManifestNamespaceMismatch")
    return {
        "identity": {
            "lineage": state["lineage"],
            "serial": state["serial"],
            "version_id": version,
            "sha256": sha256(raw),
        },
        "state": state,
        "manifest": manifest,
    }


def require_bound(value, manifest, snapshot, now, *, lifetime=900):
    """The caller supplies current AWS State, not a claimed serial in an input file."""
    if (
        any(value.get(k) != manifest[k] for k in ("account_id", "region", "run_id"))
        or value.get("manifest_sha256") != canonical_hash(manifest)
        or value.get("state_identity") != snapshot["identity"]
        or snapshot["manifest"] != manifest
        or type(value.get("issued_at_epoch")) is not int
        or type(value.get("expires_at_epoch")) is not int
        or not value["issued_at_epoch"] <= now < value["expires_at_epoch"]
        or not 0 < value["expires_at_epoch"] - value["issued_at_epoch"] <= lifetime
    ):
        raise ValueError("FreshStateBoundEvidenceRequired")
    for name in ("issued_at", "expires_at"):
        if (
            name in value
            and int(datetime.fromisoformat(value[name].replace("Z", "+00:00")).timestamp())
            != value[name + "_epoch"]
        ):
            raise ValueError("EvidenceTimestampMismatch")


LOG_ADDRESSES = {
    f'module.service.aws_cloudwatch_log_group.lambda["{role}"]'
    for role in ("api", "admin", "worker", "dispatcher")
} | {"module.service.aws_cloudwatch_log_group.api"}


def retention_changes(review):
    changes = []
    seen = set()
    for entry in review.get("resource_changes", []):
        if entry.get("type") != "aws_cloudwatch_log_group":
            continue
        address, change = entry["address"], entry["change"]
        if address not in LOG_ADDRESSES or address in seen:
            raise ValueError("FiveStableLogGroupAddressesRequired")
        seen.add(address)
        before, after = change.get("before"), change.get("after")
        if before is None and change["actions"] == ["create"]:
            continue  # Initial provision is not retention shortening.
        if (
            not isinstance(before, dict)
            or not isinstance(after, dict)
            or change["actions"] not in (["no-op"], ["update"])
            or before.get("name") != after.get("name")
            or change.get("after_unknown", {}).get("retention_in_days")
        ):
            raise ValueError("LogGroupReplaceDestroyOrRenameForbidden")
        old, new = before.get("retention_in_days"), after.get("retention_in_days")
        if type(old) is not int or type(new) is not int or new < 1:
            raise ValueError("KnownLogRetentionRequired")
        if old == 0 or new < old:
            changes.append(
                {"address": address, "name": before["name"], "before_days": old, "after_days": new}
            )
    if seen != LOG_ADDRESSES:
        raise ValueError("FullFiveLogGroupPlanRequired")
    return sorted(changes, key=lambda item: item["address"])


def audit_retention(review, manifest, snapshot, approval_path, approval_hash, private, *, now):
    changes = retention_changes(review)
    if not changes:
        return None
    _, approval = approved_json(approval_path, approval_hash, private)
    require_bound(approval, manifest, snapshot, now, lifetime=86400)
    if (
        approval.get("operation") != "LOG_RETENTION_SHORTENING"
        or approval.get("changes") != changes
        or not approval.get("approved_by")
        or approval.get("approved_by") == approval.get("reviewed_by")
        or not approval.get("reviewed_by")
    ):
        raise ValueError("ExplicitRetentionShorteningApprovalRequired")
    if set(approval.get("impact_reviews", {})) != {"incidents", "support", "audit"}:
        raise ValueError("AllRetentionImpactsMustBeReviewed")
    for domain, reference in approval["impact_reviews"].items():
        _, evidence = approved_json(reference["path"], reference["sha256"], private)
        if (
            evidence.get("domain") != domain
            or evidence.get("status") != "PRESERVED_OR_NO_OPEN_ITEMS"
            or any(
                evidence.get(k) != approval.get(k)
                for k in ("account_id", "region", "run_id", "manifest_sha256", "state_identity")
            )
        ):
            raise ValueError("RetentionEvidencePreservationRequired")
        # Every retained export is hashed and private; no claim of preservation without files.
        open_items = evidence.get("open_items")
        preserved = evidence.get("preserved_artifacts", [])
        if (
            type(open_items) is not int
            or open_items < 0
            or not isinstance(preserved, list)
            or open_items
            and not preserved
        ):
            raise ValueError("RetentionEvidencePreservationRequired")
        for artifact in preserved:
            from bootstrap_state import private_path

            path = private_path(artifact["path"], Path(private).resolve())
            if sha256(path.read_bytes()) != artifact["sha256"]:
                raise ValueError("PreservedArtifactHashMismatch")
    return approval_hash
