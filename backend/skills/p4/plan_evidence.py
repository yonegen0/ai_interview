"""Recipient-pinned encrypted evidence; no plaintext public artifact or AWS API."""

import hashlib
import io
import json
import os
import re
import ssl
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from interview_backend.deployment import DeploymentError


def openssl(arguments, raw):
    # No inherited credentials, OpenSSL configuration or custom provider paths.
    environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT") if key in os.environ}
    result = subprocess.run(
        ["openssl", *arguments], input=raw, capture_output=True, timeout=30, env=environment
    )
    if result.returncode:
        raise DeploymentError("EvidenceEncryptionUnavailable")
    return result.stdout


def certificate_der(environment):
    pem = environment.get("P4_PLAN_EVIDENCE_CERT_PEM", "")
    try:
        if pem.count("-----BEGIN CERTIFICATE-----") != 1 or "PRIVATE KEY" in pem:
            raise ValueError
        raw = ssl.PEM_cert_to_DER_cert(pem)
        expected = environment.get("P4_PLAN_EVIDENCE_CERT_SHA256", "")
        if (
            not re.fullmatch(r"[0-9a-f]{64}", expected)
            or hashlib.sha256(raw).hexdigest() != expected
        ):
            raise ValueError
        return raw
    except Exception:
        raise DeploymentError("EvidenceRecipientMismatch") from None


def encrypt(raw, certificate, directory):
    path = directory / "recipient.pem"
    pem = ssl.DER_cert_to_PEM_cert(certificate).encode("ascii")
    if not path.exists():
        with path.open("xb") as stream:
            os.chmod(path, 0o600)
            stream.write(pem)
    elif path.is_symlink() or path.read_bytes() != pem:
        raise DeploymentError("EvidenceRecipientMismatch")
    # CMS AuthEnvelopedData authenticates ciphertext; RSA OAEP wraps the content key.
    return openssl(
        [
            "cms",
            "-encrypt",
            "-binary",
            "-outform",
            "DER",
            "-aes-256-gcm",
            "-keyid",
            "-recip",
            str(path),
            "-keyopt",
            "rsa_padding_mode:oaep",
            "-keyopt",
            "rsa_oaep_md:sha256",
            "-keyopt",
            "rsa_mgf1_md:sha256",
        ],
        raw,
    )


def validate_recipient(environment, directory):
    certificate = certificate_der(environment)
    public = openssl(["x509", "-inform", "DER", "-pubkey", "-noout"], certificate)
    details = openssl(["rsa", "-pubin", "-text", "-noout"], public).decode("ascii")
    bits = re.search(r"Public-Key: \((\d+) bit\)", details)
    if not bits or int(bits[1]) < 3072:
        raise DeploymentError("EvidenceRecipientKeyTooWeak")
    # CMS must expose only a derived key identifier, never issuer DN/serial/PII.
    key_der = openssl(["rsa", "-pubin", "-RSAPublicKey_out", "-outform", "DER"], public)
    identifier = openssl(
        ["x509", "-inform", "DER", "-ext", "subjectKeyIdentifier", "-noout"], certificate
    ).decode("ascii")
    match = re.fullmatch(r"X509v3 Subject Key Identifier:\s*\n\s*([0-9A-F:]+)\s*", identifier)
    if (
        not match
        or match[1].replace(":", "").lower()
        != hashlib.sha1(key_der, usedforsecurity=False).hexdigest()
    ):
        raise DeploymentError("EvidenceRecipientIdentifierMismatch")
    dates = openssl(["x509", "-inform", "DER", "-dates", "-noout"], certificate).decode("ascii")
    validity = {}
    for line in dates.splitlines():
        label, value = line.split("=", 1)
        validity[label] = datetime.strptime(value, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
    expiry = datetime.fromisoformat(
        environment["P4_PLAN_APPROVAL_EXPIRES_AT"].replace("Z", "+00:00")
    )
    if validity["notBefore"] > datetime.now(UTC) or validity["notAfter"] <= expiry:
        raise DeploymentError("EvidenceRecipientValidityMismatch")
    if not encrypt(b"P4 encryption preflight; no private data", certificate, directory):
        raise DeploymentError("EvidenceEncryptionUnavailable")
    return certificate


def preserve(environment, project, runner_temp):
    """Publish fixed status and encrypted bytes only; retain private originals."""
    output = Path(runner_temp) / "p4-public-evidence"
    output.mkdir(mode=0o700, exist_ok=False)
    status = "unavailable"
    try:
        run, attempt = environment["GITHUB_RUN_ID"], environment["GITHUB_RUN_ATTEMPT"]
        if not re.fullmatch(r"[0-9]+", run) or attempt != "1":
            raise ValueError
        private = Path(runner_temp) / "p4-evidence-encryption"
        private.mkdir(mode=0o700, exist_ok=False)
        certificate = validate_recipient(environment, private)
        journal = Path(project) / ".p4-artifacts" / f"plan-authorization-{run}-{attempt}"
        files = sorted(journal.glob("[0-9][0-9][0-9][0-9].private.json"))
        first = Path(runner_temp) / "p4-plan-approval-job-start.private.json"
        if first.exists():
            files.append(first)
        if not files or len(files) > 256:
            raise ValueError
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
                    raise ValueError
                raw = path.read_bytes()
                json.loads(raw)  # Fail closed on unexpected/torn journals.
                archive.writestr(path.name, raw)
        encrypted = encrypt(buffer.getvalue(), certificate, private)
        if not encrypted:
            raise ValueError
        with (output / "journal.cms").open("xb") as stream:
            stream.write(encrypted)
        status = "encrypted"
    except Exception:
        # No exceptions, paths, identifiers, private fields or fallback files in public output.
        pass
    with (output / "summary.json").open("x", encoding="utf-8") as stream:
        json.dump({"schema_version": 1, "evidence": status}, stream)
    return status == "encrypted"


def main():
    project = Path(__file__).resolve().parents[3]
    return 0 if preserve(os.environ, project, os.environ["RUNNER_TEMP"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
