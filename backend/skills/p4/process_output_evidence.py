"""Bounded output samples: plaintext stays in memory, journal stores CMS only."""

import base64
import hashlib
import json
from collections.abc import Mapping

from plan_evidence import certificate_der, encrypt

STDOUT_CAP = 8192
STDERR_CAP = 16384
PLAIN_CAP = 36 * 1024
CIPHER_CAP = 42 * 1024
RESERVE_SECONDS = 150  # Existing 120-second cleanup plus the 30-second crypto bound.
REASONS = frozenset(
    (
        "OutputEvidenceSealed",
        "OutputEvidenceNoContext",
        "OutputEvidenceInsufficientBudget",
        "OutputEvidenceEncryptionFailed",
        "OutputEvidenceInvalidInput",
        "OutputEvidenceCipherTooLarge",
    )
)


def sample(raw, cap):
    if type(raw) is not bytes:
        raise ValueError("OutputEvidenceInvalidInput")
    return raw if len(raw) <= cap else raw[: cap // 2] + raw[-cap // 2 :]


def stderr_sample(raw):
    if len(raw) <= STDERR_CAP:
        return raw, "complete"
    at = raw.find(b"Error:", 0, min(len(raw), 1024 * 1024))
    if at < 0:
        return sample(raw, STDERR_CAP), "prefix-suffix"
    # Encrypted only: retain the first error block even when it is in the
    # middle of a long progress log. Merge overlapping bounded ranges.
    start = max(0, at - 1024)
    ranges = sorted([(0, 4096), (start, min(len(raw), start + 8192)), (len(raw) - 4096, len(raw))])
    merged = []
    for begin, end in ranges:
        if merged and begin <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((begin, end))
    return b"".join(raw[begin:end] for begin, end in merged), "error-window-prefix-suffix"


def unavailable(reason):
    if reason not in REASONS or reason == "OutputEvidenceSealed":
        raise ValueError("InvalidOutputEvidenceReason")
    return {
        "schema_version": 1,
        "status": "unavailable",
        "reason_code": reason,
        "raw_plaintext_persisted": False,
    }


def seal(stdout, stderr, environment, directory, remaining):
    if not isinstance(environment, Mapping) or directory is None:
        return unavailable("OutputEvidenceNoContext")
    if remaining <= RESERVE_SECONDS:
        return unavailable("OutputEvidenceInsufficientBudget")
    if type(stdout) is not bytes or type(stderr) is not bytes:
        return unavailable("OutputEvidenceInvalidInput")
    out = sample(stdout, STDOUT_CAP)
    err, stderr_sampling = stderr_sample(stderr)
    payload = {
        "schema_version": 1,
        "format": "prefix-suffix-base64-v1",
        "stdout_base64": base64.b64encode(out).decode("ascii"),
        "stderr_base64": base64.b64encode(err).decode("ascii"),
        "stderr_sampling": stderr_sampling,
        "stdout_total_bytes": len(stdout),
        "stderr_total_bytes": len(stderr),
        "stdout_full_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_full_sha256": hashlib.sha256(stderr).hexdigest(),
        "stdout_truncated": len(stdout) > len(out),
        "stderr_truncated": len(stderr) > len(err),
    }
    plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(plaintext) > PLAIN_CAP:
        return unavailable("OutputEvidenceInvalidInput")
    try:
        certificate = certificate_der(environment)
        ciphertext = encrypt(plaintext, certificate, directory)
        # The pinned encrypt primitive produces DER CMS. Reject empty/non-DER
        # and a mistakenly returned plaintext payload without persisting it.
        if (
            type(ciphertext) is not bytes
            or not ciphertext.startswith(b"\x30")
            or len(ciphertext) < 16
        ):
            return unavailable("OutputEvidenceEncryptionFailed")
        if len(ciphertext) > CIPHER_CAP:
            return unavailable("OutputEvidenceCipherTooLarge")
    except Exception:
        return unavailable("OutputEvidenceEncryptionFailed")
    return {
        "schema_version": 1,
        "status": "available",
        "reason_code": "OutputEvidenceSealed",
        "ciphertext_base64": base64.b64encode(ciphertext).decode("ascii"),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
        "ciphertext_bytes": len(ciphertext),
        "recipient_der_sha256": hashlib.sha256(certificate).hexdigest(),
        "stdout_capture_bytes": len(out),
        "stderr_capture_bytes": len(err),
        "stdout_truncated": payload["stdout_truncated"],
        "stderr_truncated": payload["stderr_truncated"],
        "raw_plaintext_persisted": False,
    }


def public_status(evidence):
    if (
        not isinstance(evidence, dict)
        or evidence.get("schema_version") != 1
        or type(evidence.get("schema_version")) is not int
    ):
        raise ValueError("InvalidOutputEvidenceSchema")
    if evidence.get("raw_plaintext_persisted") is not False:
        raise ValueError("InvalidPlaintextClaim")
    status = evidence.get("status")
    reason = evidence.get("reason_code")
    if reason not in REASONS:
        raise ValueError("InvalidOutputEvidenceReason")
    if status == "unavailable":
        if (
            set(evidence) != {"schema_version", "status", "reason_code", "raw_plaintext_persisted"}
            or reason == "OutputEvidenceSealed"
        ):
            raise ValueError("InvalidUnavailableEvidence")
    elif status == "available":
        keys = {
            "schema_version",
            "status",
            "reason_code",
            "ciphertext_base64",
            "ciphertext_sha256",
            "ciphertext_bytes",
            "recipient_der_sha256",
            "stdout_capture_bytes",
            "stderr_capture_bytes",
            "stdout_truncated",
            "stderr_truncated",
            "raw_plaintext_persisted",
        }
        if set(evidence) != keys or reason != "OutputEvidenceSealed":
            raise ValueError("InvalidAvailableEvidence")
        if (
            not isinstance(evidence["ciphertext_base64"], str)
            or len(evidence["ciphertext_base64"]) > (CIPHER_CAP + 2) // 3 * 4
        ):
            raise ValueError("InvalidEvidenceCipherLength")
        cipher = base64.b64decode(evidence["ciphertext_base64"], validate=True)
        if (
            type(evidence["ciphertext_bytes"]) is not int
            or not 16 <= len(cipher) == evidence["ciphertext_bytes"] <= CIPHER_CAP
            or not cipher.startswith(b"\x30")
        ):
            raise ValueError("InvalidEvidenceCipher")
        if hashlib.sha256(cipher).hexdigest() != evidence["ciphertext_sha256"]:
            raise ValueError("InvalidEvidenceCipherHash")
        import re

        if (
            not isinstance(evidence["recipient_der_sha256"], str)
            or re.fullmatch("[0-9a-f]{64}", evidence["recipient_der_sha256"]) is None
        ):
            raise ValueError("InvalidEvidenceRecipient")
        for field, cap in (
            ("stdout_capture_bytes", STDOUT_CAP),
            ("stderr_capture_bytes", STDERR_CAP),
        ):
            if type(evidence[field]) is not int or not 0 <= evidence[field] <= cap:
                raise ValueError("InvalidCaptureLength")
        if any(type(evidence[k]) is not bool for k in ("stdout_truncated", "stderr_truncated")):
            raise ValueError("InvalidTruncationFlag")
    else:
        raise ValueError("InvalidEvidenceStatus")
    return {"status": status, "reason_code": reason}
