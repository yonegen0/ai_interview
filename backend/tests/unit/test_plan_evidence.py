"""Real local CMS roundtrip and fail-closed public evidence; no external API."""

import hashlib
import io
import json
import shutil
import ssl
import subprocess
import textwrap
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


@pytest.fixture
def recipient(tmp_path):
    import plan_evidence as module

    if not shutil.which("openssl"):
        pytest.fail("OpenSSL required for encryption regression")
    key, cert = tmp_path / "test-key.pem", tmp_path / "test-cert.pem"
    command = [
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:3072",
        "-nodes",
        "-days",
        "2",
        "-subj",
        "/CN=synthetic-offline-test",
        "-keyout",
        str(key),
        "-out",
        str(cert),
    ]
    result = subprocess.run(command, capture_output=True, timeout=30)
    assert result.returncode == 0
    pem = cert.read_text()
    digest = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
    env = {
        "P4_PLAN_EVIDENCE_CERT_PEM": pem,
        "P4_PLAN_EVIDENCE_CERT_SHA256": digest,
        "P4_PLAN_APPROVAL_EXPIRES_AT": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
    }
    directory = tmp_path / "encryption"
    directory.mkdir()
    module.validate_recipient(env, directory)
    return module, env, key, cert


def decrypt(raw, key, cert):
    return subprocess.run(
        [
            "openssl",
            "cms",
            "-decrypt",
            "-binary",
            "-inform",
            "DER",
            "-recip",
            str(cert),
            "-inkey",
            str(key),
        ],
        input=raw,
        capture_output=True,
        timeout=30,
    )


def test_real_cms_roundtrip_public_outputs_and_authentication(recipient, tmp_path):
    module, env, key, cert = recipient
    project, runner = tmp_path / "project", tmp_path / "runner"
    runner.mkdir()
    journal = project / ".p4-artifacts/plan-authorization-123-1"
    journal.mkdir(parents=True)
    sensitive = {"bucket": "private-account-bucket", "key": "private/key", "request_id": "internal"}
    raw = json.dumps(sensitive).encode()
    original = journal / "0001.private.json"
    original.write_bytes(raw)
    assert module.preserve(env, project, runner)
    output = runner / "p4-public-evidence"
    assert {p.name for p in output.iterdir()} == {"summary.json", "journal.cms"}
    assert json.loads((output / "summary.json").read_text()) == {
        "schema_version": 1,
        "evidence": "encrypted",
    }
    encrypted = (output / "journal.cms").read_bytes()
    assert b"private-account-bucket" not in encrypted and b"private/key" not in encrypted
    assert b"synthetic-offline-test" not in encrypted  # Issuer/subject stays private.
    result = decrypt(encrypted, key, cert)
    assert result.returncode == 0
    with zipfile.ZipFile(io.BytesIO(result.stdout)) as archive:
        assert archive.read("0001.private.json") == raw
    tampered = encrypted[:-1] + bytes([encrypted[-1] ^ 1])
    assert decrypt(tampered, key, cert).returncode != 0
    assert original.read_bytes() == raw  # No deletion, truncation or overwrite.


@pytest.mark.parametrize("fault", ["missing", "wrong-hash", "invalid", "private-key"])
def test_bad_recipient_has_no_plaintext_fallback(tmp_path, fault):
    import plan_evidence as module

    env = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}
    if fault != "missing":
        env["P4_PLAN_EVIDENCE_CERT_PEM"] = "PRIVATE KEY" if fault == "private-key" else "invalid"
        env["P4_PLAN_EVIDENCE_CERT_SHA256"] = "a" * 64
    assert not module.preserve(env, tmp_path / "project", tmp_path)
    output = tmp_path / "p4-public-evidence"
    assert [p.name for p in output.iterdir()] == ["summary.json"]
    assert json.loads((output / "summary.json").read_text()) == {
        "schema_version": 1,
        "evidence": "unavailable",
    }


@pytest.mark.parametrize("fault", ["symlink", "oversize", "torn", "timeout"])
def test_failed_archive_or_encrypt_never_publishes_detail(recipient, tmp_path, monkeypatch, fault):
    module, env, *_ = recipient
    journal = tmp_path / "project/.p4-artifacts/plan-authorization-123-1"
    journal.mkdir(parents=True)
    path = journal / "0001.private.json"
    path.write_bytes(b"{" if fault == "torn" else b" " * 65537 if fault == "oversize" else b"{}")
    if fault == "symlink":
        monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == path.name)
    if fault == "timeout":

        def fail(*args):
            raise subprocess.TimeoutExpired("SECRET", 30)

        monkeypatch.setattr(module, "encrypt", fail)
    runner = tmp_path / "runner"
    runner.mkdir()
    assert not module.preserve(env, tmp_path / "project", runner)
    assert [p.name for p in (runner / "p4-public-evidence").iterdir()] == ["summary.json"]
    assert path.exists()


def test_recipient_expiration_before_approval_refused(recipient, tmp_path):
    module, env, *_ = recipient
    env["P4_PLAN_APPROVAL_EXPIRES_AT"] = "2099-01-01T00:00:00Z"
    with pytest.raises(ValueError, match="ValidityMismatch"):
        module.validate_recipient(env, tmp_path)


def test_plan_workflow_has_secret_only_private_inputs_and_explicit_upload_paths():
    workflow = (Path(__file__).parents[3] / ".github/workflows/p4-deploy.yml").read_text()
    inputs = workflow.split("permissions:", 1)[0]
    assert "plan_approval_package:" not in inputs
    assert "P4_PLAN_APPROVAL_PACKAGE: ${{ secrets.P4_PLAN_APPROVAL_PACKAGE }}" in workflow
    plan = workflow.split("- name: Guarded Plan", 1)[1].split("- name:", 1)[0]
    for name in ("AWS_DEV_ACCOUNT_ID", "P4_OIDC_SUBJECT", "P4_DEPLOY_INPUTS"):
        assert f"${{{{ secrets.{name} }}}}" in plan
        assert f"${{{{ vars.{name} }}}}" not in plan
        assert f"${{{{ vars.{name} }}}}" not in workflow
    upload = workflow.split("- name: Preserve public summary", 1)[1].split("upload_existing:", 1)[0]
    assert "*.private.json" not in upload and "include-hidden-files" not in upload
    assert "p4-public-evidence/summary.json" in upload
    assert "p4-public-evidence/journal.cms" in upload
    assert "p4-public-fallback/summary.json" in upload


@pytest.mark.parametrize("fault", ["weak-key", "missing-ski", "arbitrary-ski"])
def test_recipient_weak_key_or_private_identifier_is_refused(
    recipient, tmp_path, monkeypatch, fault
):
    module, env, *_ = recipient
    original = module.openssl

    def fake(arguments, raw):
        if fault == "weak-key" and arguments == ["rsa", "-pubin", "-text", "-noout"]:
            return b"Public-Key: (2048 bit)\n"
        if "subjectKeyIdentifier" in arguments:
            return b"" if fault == "missing-ski" else b"X509v3 Subject Key Identifier:\n 00:01\n"
        return original(arguments, raw)

    monkeypatch.setattr(module, "openssl", fake)
    with pytest.raises(ValueError, match="KeyTooWeak|IdentifierMismatch"):
        module.validate_recipient(env, tmp_path)


def test_fixed_fallback_summary_survives_no_checkout_or_uv(tmp_path, monkeypatch):
    workflow = (Path(__file__).parents[3] / ".github/workflows/p4-deploy.yml").read_text()
    block = workflow.split("- name: Preserve fixed failure summary", 1)[1]
    script = textwrap.dedent(block.split("python3 - <<'PY'\n", 1)[1].split("          PY\n", 1)[0])
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    exec(compile(script, "fallback-summary", "exec"), {})
    assert json.loads((tmp_path / "p4-public-fallback/summary.json").read_text()) == {
        "schema_version": 1,
        "evidence": "unavailable",
    }
