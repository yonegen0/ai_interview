"""New source inventories must remain bound to approval, Git and exact ZIP bytes."""

import base64
import io
import json
import zipfile

import pytest
from test_p4_tools import tool


@pytest.fixture
def module():
    return tool("upload_existing")


@pytest.fixture
def prepared(module, monkeypatch, tmp_path):
    source = tmp_path / "source"
    validation = source / "validation"
    validation.mkdir(parents=True)
    sha = "a" * 40
    app_path = "backend/src/interview_backend/__init__.py"
    app = b"new approved source"
    lock = b"locked dependencies"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("interview_backend/__init__.py", app)
        archive.writestr("dependency/metadata", b"metadata")
        archive.writestr("dependency/runtime", b"runtime")
    package = output.getvalue()
    manifest = {
        "code_sha": sha,
        "sha256": module.sha256(package),
        "runtime": "python3.14",
        "architecture": "x86_64",
        "lock_sha256": module.sha256(lock),
        "sha256_base64": base64.b64encode(bytes.fromhex(module.sha256(package))).decode(),
    }
    (source / "app.zip").write_bytes(package)
    (source / "reproduction.zip").write_bytes(package)
    (source / "package.json").write_text(json.dumps(manifest))
    binding = {
        "artifact_source_sha": sha,
        "zip_sha256": module.sha256(package),
        "zip_size": len(package),
        "manifest_sha256": module.sha256((source / "package.json").read_bytes()),
    }
    final = {
        "status": "P4_LAMBDA_ARTIFACT_READY",
        "code_sha": sha,
        "source_blob_matches": 3,
        "security": {
            "zip_sha256": binding["zip_sha256"],
            "manifest_sha256": binding["manifest_sha256"],
            "status": "LAMBDA_ARTIFACT_SECURITY_PASS",
            "unknown_findings": [],
            "entries_scanned": 3,
            "app_head_blob_matches": 1,
        },
    }
    (validation / "final.private.json").write_text(json.dumps(final))
    (validation / "baseline.private.json").write_text(
        json.dumps(
            {
                "binding": {
                    "code_sha": sha,
                    "official_origin_verified": True,
                    "source_and_builder_blobs_verified": True,
                }
            }
        )
    )
    approval = binding | {
        "schema_version": 2,
        "approved": True,
        "source_blob_count": 3,
        "zip_entry_count": 3,
    }
    provenance_path = tmp_path / "provenance.json"

    def bind():
        evidence = [*validation.iterdir(), source / "reproduction.zip"]
        provenance = binding | {
            "evidence_files": {
                p.relative_to(source).as_posix(): module.sha256(p.read_bytes()) for p in evidence
            }
        }
        provenance_path.write_text(json.dumps(provenance))
        approval["provenance_sha256"] = module.sha256(provenance_path.read_bytes())

    def git(root, *args):
        if args[0] == "ls-tree":
            paths = [app_path] if "--" in args else ["README.md", "backend/uv.lock", app_path]
            return ("\n".join(paths) + "\n").encode()
        return lock if args[-1].endswith("uv.lock") else app

    monkeypatch.setattr(module, "git", git)
    bind()
    return source, provenance_path, approval, final, bind, package


def test_new_inventory_accepted_without_legacy_counts(module, prepared, tmp_path):
    source, provenance, approval, _, _, package = prepared
    assert module.artifact(tmp_path, source, provenance, approval) == package


@pytest.mark.parametrize("count", [4, True, 0])
def test_source_inventory_must_match_actual_git(module, prepared, tmp_path, count):
    source, provenance, approval, _, _, _ = prepared
    approval["source_blob_count"] = count
    with pytest.raises(
        module.UploadError, match="SourceInventoryMismatch|ArtifactInventoryRequired"
    ):
        module.artifact(tmp_path, source, provenance, approval)


def test_actual_zip_inventory_cannot_be_changed_by_proof(module, prepared, tmp_path):
    source, provenance, approval, final, bind, _ = prepared
    approval["zip_entry_count"] = 4
    final["security"]["entries_scanned"] = 4
    (source / "validation/final.private.json").write_text(json.dumps(final))
    bind()
    with pytest.raises(module.UploadError, match="ZipEntrySetMismatch"):
        module.artifact(tmp_path, source, provenance, approval)


def test_reproduction_must_equal_the_approved_zip(module, prepared, tmp_path):
    source, provenance, approval, _, bind, _ = prepared
    (source / "reproduction.zip").write_bytes(b"different second build")
    bind()
    with pytest.raises(module.UploadError, match="ReproductionHashMismatch"):
        module.artifact(tmp_path, source, provenance, approval)


def test_new_evidence_tampering_still_rejected(module, prepared, tmp_path):
    source, provenance, approval, _, _, _ = prepared
    (source / "validation/final.private.json").write_text("{}")
    with pytest.raises(module.UploadError, match="EvidenceHashMismatch"):
        module.artifact(tmp_path, source, provenance, approval)


def test_new_app_source_must_match_git(module, prepared, tmp_path, monkeypatch):
    source, provenance, approval, _, _, _ = prepared
    original = module.git

    def changed(root, *args):
        if args[0] == "show" and args[-1].endswith("__init__.py"):
            return b"different Git source"
        return original(root, *args)

    monkeypatch.setattr(module, "git", changed)
    with pytest.raises(module.UploadError, match="SourceBlobMismatch"):
        module.artifact(tmp_path, source, provenance, approval)


@pytest.mark.parametrize("approved", [False, True])
def test_local_descriptor_requires_explicit_approval_and_exact_digest(module, tmp_path, approved):
    descriptor = tmp_path / "approval.json"
    descriptor.write_text(json.dumps({"schema_version": 2, "approved": approved}))
    environment = {
        "P4_UPLOAD_APPROVAL_PATH": str(descriptor.resolve()),
        "P4_APPROVED_ARTIFACT_APPROVAL_SHA256": module.sha256(descriptor.read_bytes()),
    }
    if approved:
        assert module.approved_configuration(environment)["approved"] is True
    else:
        with pytest.raises(module.UploadError, match="ExplicitArtifactApprovalRequired"):
            module.approved_configuration(environment)
    environment["P4_APPROVED_ARTIFACT_APPROVAL_SHA256"] = "0" * 64
    with pytest.raises(module.UploadError, match="ApprovalDigestMismatch"):
        module.approved_configuration(environment)


def test_missing_descriptor_digest_rejected(module, tmp_path):
    descriptor = tmp_path / "approval.json"
    descriptor.write_text(json.dumps({"schema_version": 2, "approved": True}))
    with pytest.raises(module.UploadError, match="ApprovalDigestRequired"):
        module.approved_configuration({"P4_UPLOAD_APPROVAL_PATH": str(descriptor.resolve())})


def test_schema_two_cannot_bypass_local_descriptor_digest(module, tmp_path, monkeypatch):
    monkeypatch.setattr(module, "__file__", str(tmp_path / "upload_existing.py"))
    (tmp_path / "upload_existing.approval.json").write_text(
        json.dumps({"schema_version": 2, "approved": True})
    )
    with pytest.raises(module.UploadError, match="LocalDescriptorRequired"):
        module.approved_configuration({})
