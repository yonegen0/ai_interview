"""Encrypt private runner evidence; publish only fixed summary and ciphertext."""

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

from plan_evidence import encrypt, validate_recipient


def main():
    os.umask(0o077)
    env = dict(os.environ)
    raw = env["P4_PLAN_APPROVAL_PACKAGE"]
    if hashlib.sha256(raw.encode()).hexdigest() != env["P4_CLOUD_PARENT_SHA256"]:
        raise ValueError("ParentChanged")
    parent = json.loads(raw)
    env["P4_PLAN_APPROVAL_EXPIRES_AT"] = parent["expires_at_utc"]
    root = Path(__file__).resolve().parents[3]
    run, attempt = env["GITHUB_RUN_ID"], env["GITHUB_RUN_ATTEMPT"]
    if not run.isdigit() or attempt != "1":
        raise ValueError("InvalidEvidenceRun")
    public = Path(env["RUNNER_TEMP"]) / "p4-public-evidence"
    public.mkdir(mode=0o700, exist_ok=False)
    status = "unavailable"
    try:
        private = Path(env["RUNNER_TEMP"]) / "p4-cloud-encryption"
        private.mkdir(mode=0o700, exist_ok=False)
        certificate = validate_recipient(env, private)
        allowed = [
            root / ".p4-artifacts" / f"plan-authorization-{run}-1",
            root / ".p4-artifacts" / f"cloud-read-{run}-1",
        ]
        audit_input = root / ".p4-artifacts" / f"ci-{run}-1/cloud-audit-input.private.json"
        files = [p for d in allowed for p in sorted(d.glob("*.private*"))]
        if audit_input.is_file():
            files.append(audit_input)
        if not files or len(files) > 5000:
            raise ValueError("EvidenceInventoryMissing")
        buffer = io.BytesIO()
        size = 0
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
            for p in files:
                if p.is_symlink() or any(a.is_symlink() for a in p.parents) or not p.is_file():
                    raise ValueError("EvidencePathMismatch")
                size += p.stat().st_size
                if size > 64 * 1024 * 1024:
                    raise ValueError("EvidenceSizeExceeded")
                archive.writestr(p.relative_to(root).as_posix(), p.read_bytes())
        ciphertext = encrypt(buffer.getvalue(), certificate, private)
        with (public / "journal.cms").open("xb") as stream:
            stream.write(ciphertext)
        status = "encrypted"
    except Exception:
        pass
    with (public / "summary.json").open("x") as stream:
        json.dump({"schema_version": 1, "evidence": status}, stream)
    return 0 if status == "encrypted" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit("CloudEvidenceUnavailable") from None
