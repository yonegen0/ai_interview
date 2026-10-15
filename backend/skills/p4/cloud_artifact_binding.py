"""Fail-closed local binding and bounded, private historical Artifact diagnostics."""

import base64
import json
import os
import re
from pathlib import Path

from cloud_controller_core import Refusal, digest, require

MAX = 32 * 1024 * 1024
REASONS = frozenset(
    (
        "HistoricalArtifactBindingRejected",
        "HistoricalArtifactApiFailed",
        "HistoricalArtifactBodyReadFailed",
        "HistoricalArtifactResponseUnknown",
        "HistoricalArtifactVersionMismatch",
        "HistoricalArtifactEncryptionMismatch",
        "HistoricalArtifactLengthMismatch",
        "HistoricalArtifactDigestMismatch",
        "HistoricalArtifactDiagnosticWriteFailed",
    )
)


def sha_hex(value):
    try:
        raw = base64.b64decode(value, validate=True)
        require(
            len(raw) == 32 and base64.b64encode(raw).decode() == value,
            "HistoricalArtifactBindingRejected",
        )
        return raw.hex()
    except ValueError, TypeError:
        raise Refusal("HistoricalArtifactBindingRejected") from None


def validate_binding(x, state=None):
    b = x.get("historical_artifact_binding")
    require(isinstance(b, dict), "HistoricalArtifactBindingRejected")
    require(
        b.get("schema") == 1
        and b.get("normalization") == "strict-base64-32-bytes-to-lowercase-hex-v1",
        "HistoricalArtifactBindingRejected",
    )
    old = b.get("artifact", {})
    expected = x.get("historical_artifact_sha256")
    require(isinstance(old, dict), "HistoricalArtifactBindingRejected")
    require(
        isinstance(expected, str) and re.fullmatch("[0-9a-f]{64}", expected) is not None,
        "HistoricalArtifactBindingRejected",
    )
    require(
        expected == b.get("sha256") == sha_hex(old.get("sha256_base64"))
        and b.get("state_identity") == x.get("dev_state_identity"),
        "HistoricalArtifactBindingRejected",
    )
    require(
        all(isinstance(old.get(k), str) and old[k] for k in ("bucket", "key", "version"))
        and old["version"] != "null",
        "HistoricalArtifactBindingRejected",
    )
    require(
        type(b.get("size")) is int and 0 < b["size"] <= MAX, "HistoricalArtifactBindingRejected"
    )
    package = {
        f"artifact_{k}": old[f]
        for k, f in (
            ("bucket", "bucket"),
            ("key", "key"),
            ("version", "version"),
            ("sha256_base64", "sha256_base64"),
        )
    }
    require(
        x.get("configuration_contract", {}).get("baseline_artifact_inputs") == package,
        "HistoricalArtifactBindingRejected",
    )
    if state is not None:
        require(
            state["lineage"] == b["state_identity"]["lineage"]
            and state["serial"] == b["state_identity"]["serial"]
            and state["outputs"]["manifest"]["value"]["artifact"] == old,
            "HistoricalArtifactBindingRejected",
        )
        n = 0
        for r in state["resources"]:
            if r.get("mode") == "managed" and r["type"] == "aws_lambda_function":
                for i in r["instances"]:
                    v = i["attributes"]
                    n += 1
                    require(
                        v["source_code_hash"] == old["sha256_base64"]
                        and (v["s3_bucket"], v["s3_key"], v["s3_object_version"])
                        == (old["bucket"], old["key"], old["version"]),
                        "HistoricalArtifactBindingRejected",
                    )
        require(n == 4, "HistoricalArtifactBindingRejected")
    return b


def preflight(a, bundle):
    b = validate_binding(a.x)
    folder = Path(bundle)
    saved = json.loads((folder / "historical-artifact-binding.private.json").read_bytes())
    require(saved == b, "HistoricalArtifactBindingRejected")
    # Fresh issuance copies a hash-bound baseline State into its private release.
    raw = (folder / "baseline-dev-state.raw.private").read_bytes()
    require(digest(raw) == b["state_identity"]["sha256"], "HistoricalArtifactBindingRejected")
    validate_binding(a.x, json.loads(raw))
    receipt = Path(b["provenance_receipt_path"])
    require(
        digest(receipt.read_bytes()) == b["provenance_receipt_sha256"],
        "HistoricalArtifactBindingRejected",
    )
    r = json.loads(receipt.read_bytes())
    old = b["artifact"]
    require(
        (r["bucket"], r["key"], r["version_id"], r["sha256"], r["size"], r["encryption"])
        == (old["bucket"], old["key"], old["version"], b["sha256"], b["size"], "AES256")
        and r["version_pinned_get_hash_match"] is True,
        "HistoricalArtifactBindingRejected",
    )
    require(len(b["local_binary_proofs"]) >= 2, "HistoricalArtifactBindingRejected")
    for row in b["local_binary_proofs"]:
        p = Path(row["path"])
        require(
            p.is_file()
            and not p.is_symlink()
            and not p.is_junction()
            and p.stat().st_size == row["bytes"] == b["size"],
            "HistoricalArtifactBindingRejected",
        )
        require(
            digest(p.read_bytes()) == row["sha256"] == b["sha256"],
            "HistoricalArtifactBindingRejected",
        )
    return True


def verify_artifact(s3, old, x, journal, label, state_identity):
    b = validate_binding(x)
    require(
        old == b["artifact"] and state_identity == b["state_identity"],
        "HistoricalArtifactBindingRejected",
    )
    report = {
        "check": "historical-artifact",
        "normalization": b["normalization"],
        "state_identity": state_identity,
        "api": "not-started",
        "body": "not-started",
        "sdk_exception_type": None,
        "safe_sdk_code": None,
        "reason": None,
    }
    legacy = None
    binary = None
    reason = None
    try:
        try:
            legacy = s3.get_object(
                Bucket=old["bucket"],
                Key=old["key"],
                VersionId=old["version"],
                ExpectedBucketOwner="835384817629",
            )
        except Exception as e:
            report["api"] = "failed"
            report["sdk_exception_type"] = (
                type(e).__name__
                if type(e).__module__.startswith(("botocore.", "builtins"))
                else "OtherException"
            )
            code = getattr(e, "response", {}).get("Error", {}).get("Code")
            report["safe_sdk_code"] = (
                code
                if code
                in {
                    "AccessDenied",
                    "NoSuchKey",
                    "NoSuchVersion",
                    "ExpiredToken",
                    "SlowDown",
                    "InternalError",
                    "ServiceUnavailable",
                }
                else "OtherOrUnknown"
            )
            raise Refusal("HistoricalArtifactApiFailed") from None
        report["api"] = "succeeded"
        require(isinstance(legacy, dict), "HistoricalArtifactResponseUnknown")
        version = legacy.get("VersionId")
        enc = legacy.get("ServerSideEncryption")
        length = legacy.get("ContentLength")
        report.update(
            returned_version=version if isinstance(version, str) and len(version) < 1024 else None,
            returned_encryption=enc
            if enc in {"AES256", "aws:kms", "aws:kms:dsse"}
            else "OtherOrUnknown",
            content_length=length if type(length) is int else None,
        )
        try:
            with legacy["Body"] as body:
                binary = body.read(MAX + 1)
        except Exception as e:
            report["body"] = "failed"
            report["body_exception_type"] = (
                type(e).__name__
                if type(e).__module__.startswith(("botocore.", "builtins"))
                else "OtherException"
            )
            raise Refusal("HistoricalArtifactBodyReadFailed") from None
        report["body"] = "completed"
        require(type(binary) is bytes, "HistoricalArtifactResponseUnknown")
        report.update(
            observed_sha256=digest(binary),
            observed_bytes=len(binary),
            conditions={
                "version": version == old["version"],
                "encryption": enc == "AES256",
                "length": type(length) is int
                and len(binary) == length == b["size"]
                and len(binary) <= MAX,
                "digest": digest(binary) == b["sha256"],
            },
        )
        for field, code in (
            ("version", "HistoricalArtifactVersionMismatch"),
            ("encryption", "HistoricalArtifactEncryptionMismatch"),
            ("length", "HistoricalArtifactLengthMismatch"),
            ("digest", "HistoricalArtifactDigestMismatch"),
        ):
            require(report["conditions"][field], code)
        reason = "HistoricalArtifactVerified"
    except Refusal as e:
        reason = str(e)
        raise
    except Exception:
        reason = "HistoricalArtifactResponseUnknown"
        raise Refusal(reason) from None
    finally:
        report["reason"] = reason or "HistoricalArtifactResponseUnknown"
        try:
            with (journal.path / f"historical-artifact-{label}.private.json").open(
                "x", encoding="utf-8"
            ) as f:
                json.dump(report, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            journal.record(
                "historical-artifact-result",
                check="historical-artifact",
                reason=report["reason"],
                api=report["api"],
                body=report["body"],
            )
        except Exception:
            raise Refusal("HistoricalArtifactDiagnosticWriteFailed") from None
    return report
