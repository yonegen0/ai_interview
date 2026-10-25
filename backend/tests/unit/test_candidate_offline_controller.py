"""Candidate-only local evidence and durable no-retry marker tests (no AWS)."""

import shutil
import subprocess
from datetime import UTC, datetime, timedelta

import pytest
from test_p4_tools import tool


@pytest.fixture
def sample():
    m = tool("candidate_offline_controller")
    tracked = {
        f"terraform/{scope}/{name}"
        for scope, filename in m.preflight.ROOTS.items()
        for name in (filename, ".terraform.lock.hcl")
    }
    tracked.add("terraform/bootstrap/variables.tf")
    files = {name: name.encode() for name in tracked}
    source_hash = m.source_inventory_digest(tracked, files)
    now = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    bundle = {"namespace": m.preflight.NAMESPACE, "source_sha": "a" * 40}
    approval = {"approval_id": "b" * 40, "attempt_id": "c" * 40}
    review = {
        "schema_version": 3,
        "kind": "p4-bootstrap-candidate-offline-review-v3",
        "namespace": m.preflight.NAMESPACE,
        "source_sha": bundle["source_sha"],
        **approval,
        "terraform_sources_sha256": source_hash,
        "issued_at": (now - timedelta(minutes=10)).isoformat(),
        "expires_at": (now + timedelta(minutes=20)).isoformat(),
    }
    return m, tracked, files, now, bundle, approval, review


def test_all_tracked_source_bytes_bound_including_non_root_hcl(sample):
    m, tracked, files, *_ = sample
    original = m.source_inventory_digest(tracked, files)
    altered = files | {"terraform/bootstrap/variables.tf": b"changed"}
    assert m.source_inventory_digest(tracked, altered) != original
    with pytest.raises(ValueError, match="CandidateSourceInventoryMismatch"):
        m.source_inventory_digest(tracked, {**files, "terraform/bootstrap/new.tf": b"extra"})
    with pytest.raises(ValueError, match="CandidateSourceInventoryMismatch"):
        m.source_inventory_digest(tracked | {"terraform/bootstrap/new.tf"}, files)
    with pytest.raises(ValueError, match="CandidateSourceInventoryMismatch"):
        m.source_inventory_digest(tracked - {"terraform/bootstrap/main.tf"}, files)


@pytest.mark.parametrize(
    "name",
    [
        "terraform/../etc/passwd",
        "terraform//bootstrap/main.tf",
        "terraform/./bootstrap/main.tf",
        "terraform/\\bootstrap/main.tf",
        "terraform/.terraform/provider.tf",
        "terraform/.git/config",
    ],
)
def test_source_inventory_rejects_unsafe_paths(sample, name):
    m, tracked, files, *_ = sample
    tracked.add(name)
    files[name] = b"malicious"
    with pytest.raises(ValueError, match="CandidateSourcePathInvalid"):
        m.source_inventory_digest(tracked, files)


@pytest.mark.parametrize(
    "mutation",
    [
        "namespace",
        "source",
        "approval-id",
        "attempt-id",
        "checksum",
        "future",
        "expired",
        "unbounded",
        "naive",
        "missing",
    ],
)
def test_review_is_fresh_and_bound_but_not_authenticated(sample, mutation):
    m, tracked, files, now, bundle, approval, review = sample
    if mutation == "namespace":
        review["namespace"] = "legacy"
    elif mutation == "source":
        review["source_sha"] = "0" * 40
    elif mutation == "approval-id":
        review["approval_id"] = "0" * 40
    elif mutation == "attempt-id":
        review["attempt_id"] = "0" * 40
    elif mutation == "checksum":
        review["terraform_sources_sha256"] = "0" * 64
    elif mutation == "future":
        review["issued_at"] = (now + timedelta(minutes=6)).isoformat()
    elif mutation == "expired":
        review["expires_at"] = now.isoformat()
    elif mutation == "unbounded":
        review["expires_at"] = (now + timedelta(hours=2)).isoformat()
    elif mutation == "naive":
        review["issued_at"] = "2026-10-25T11:59:00"
    elif mutation == "missing":
        del review["expires_at"]
    with pytest.raises(ValueError):
        m.inspect_review(
            review, bundle, approval, m.source_inventory_digest(tracked, files), now=now
        )


def test_review_gate_order_and_non_authorization(sample, monkeypatch):
    m, tracked, files, now, bundle, approval, review = sample
    calls = []

    def checked_verify(*args, **kwargs):
        calls.append("preflight")
        return {"authorized": False, "aws_operations": 0}

    monkeypatch.setattr(m.preflight, "verify", checked_verify)
    args = {
        "bundle": bundle,
        "version_json": {},
        "configurations": {
            name: files[name]
            for scope, filename in m.preflight.ROOTS.items()
            for name in (
                f"terraform/{scope}/{filename}",
                f"terraform/{scope}/.terraform.lock.hcl",
            )
        },
        "binary": b"synthetic",
        "approval": approval,
        "journal": {},
        "tracked_paths": tracked,
        "checkout_files": files,
        "review": review,
        "now": now,
    }
    result = m.review_offline(**args)
    assert result["authorized"] is False
    assert result["aws_operations"] == 0
    assert calls == ["preflight"]
    calls.clear()
    with pytest.raises(ValueError, match="CandidateSourceInventoryMismatch"):
        m.review_offline(**(args | {"checkout_files": files | {"terraform/new.tf": b"x"}}))
    assert not calls
    with pytest.raises(ValueError, match="CandidateReviewExpiredOrInvalid"):
        m.review_offline(**(args | {"now": now + timedelta(hours=1)}))
    assert not calls
    with pytest.raises(ValueError, match="CandidateReviewedConfigurationMismatch"):
        m.review_offline(
            **(
                args
                | {
                    "configurations": {
                        **args["configurations"],
                        "terraform/new.tf": b"x",
                    }
                }
            )
        )
    assert not calls
    monkeypatch.setattr(m.preflight, "verify", lambda *a, **kw: {"authorized": True})
    with pytest.raises(ValueError, match="CandidatePreflightMustNotAuthorize"):
        m.review_offline(**args)


@pytest.mark.skipif(__import__("os").name != "posix", reason="Linux-only private fsync ledger")
def test_local_ledger_is_create_only_and_blocks_reuse(tmp_path, sample):
    m = sample[0]
    root = tmp_path / "ledger"
    root.mkdir(mode=0o700)
    result = m.reserve_offline_attempt(
        root, approval_id="a" * 40, attempt_id="b" * 40, approval_sha256="c" * 64
    )
    assert result == {"status": "LOCAL_RESERVATION_ONLY", "authorized": False, "aws_operations": 0}
    ns = root / m.preflight.NAMESPACE
    assert (ns / "approvals" / ("a" * 40 + ".json")).is_file()
    assert (ns / "attempts" / ("b" * 40 + ".json")).is_file()
    with pytest.raises(FileExistsError):
        m.reserve_offline_attempt(
            root, approval_id="a" * 40, attempt_id="d" * 40, approval_sha256="c" * 64
        )


@pytest.mark.skipif(__import__("os").name != "posix", reason="Linux-only private fsync ledger")
def test_unknown_crash_burns_approval_and_denies_recovery(tmp_path, sample, monkeypatch):
    m = sample[0]
    root = tmp_path / "ledger"
    root.mkdir(mode=0o700)
    original = m.exclusive_marker
    calls = []

    def simulate_crash(directory, key, receipt):
        calls.append(key)
        if len(calls) == 2:
            raise OSError("synthetic-crash-before-attempt-marker")
        return original(directory, key, receipt)

    monkeypatch.setattr(m, "exclusive_marker", simulate_crash)
    with pytest.raises(OSError, match="synthetic-crash"):
        m.reserve_offline_attempt(
            root, approval_id="a" * 40, attempt_id="b" * 40, approval_sha256="c" * 64
        )
    monkeypatch.setattr(m, "exclusive_marker", original)
    with pytest.raises(FileExistsError):
        m.reserve_offline_attempt(
            root, approval_id="a" * 40, attempt_id="b" * 40, approval_sha256="c" * 64
        )


@pytest.mark.skipif(__import__("os").name != "posix", reason="Linux-only private fsync ledger")
def test_ledger_rejects_world_readable_and_symlink(tmp_path, sample):
    m = sample[0]
    root = tmp_path / "ledger"
    root.mkdir(mode=0o700)
    root.chmod(0o755)
    with pytest.raises(ValueError, match="CandidateLedgerDirectoryUnsafe"):
        m.reserve_offline_attempt(
            root, approval_id="a" * 40, attempt_id="b" * 40, approval_sha256="c" * 64
        )
    root.chmod(0o700)
    link = tmp_path / "alias"
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="CandidateLedgerDirectoryUnsafe"):
        m.reserve_offline_attempt(
            link, approval_id="a" * 40, attempt_id="b" * 40, approval_sha256="c" * 64
        )


def test_legacy_terraform_contract_untouched(sample):
    assert sample[0].preflight.CLI == "1.16.7"
    assert tool("maintenance_contract").TF_VERSION == "1.14.9"
    assert tool("cloud_toolchain").EXPECTED_TERRAFORM_VERSION == "1.14.9"



@pytest.fixture
def synthetic_git_checkout(tmp_path, sample):
    if shutil.which("git") is None:
        pytest.skip("Local read-only Git qualification requires Git")
    root = tmp_path / "checkout"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    tracked, contents = sample[1], sample[2]
    for filename in tracked:
        path = root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents[filename])
    subprocess.run(["git", "-C", str(root), "add", "--", "terraform"], check=True)
    subprocess.run(
        [
            "git", "-C", str(root), "-c", "user.name=Offline Test",
            "-c", "user.email=offline@example.invalid", "commit", "-q", "-m", "fixture",
        ],
        check=True,
    )
    sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"]).decode().strip()
    return root, sha


def test_git_tree_source_verifies_real_blobs_and_detects_checkout_mutation(
    synthetic_git_checkout, sample
):
    root, source_sha = synthetic_git_checkout
    m = sample[0]
    verified = m.verified_git_source_inventory(root, source_sha)
    assert verified["commit_sha"] == source_sha
    assert verified["terraform_sources_sha256"] == m.source_inventory_digest(sample[1], sample[2])
    assert verified["git_origin_authenticated"] is False
    assert verified["authorized"] is False
    changed = root / "terraform/bootstrap/variables.tf"
    changed.write_bytes(b"modified")
    with pytest.raises(ValueError, match="CandidateGitBlobMismatch"):
        m.verified_git_source_inventory(root, source_sha)
    changed.write_bytes(sample[2]["terraform/bootstrap/variables.tf"])
    (root / "terraform/bootstrap/override.tf").write_text('terraform {}')
    with pytest.raises(ValueError, match="CandidateGitUntrackedFile"):
        m.verified_git_source_inventory(root, source_sha)


def test_git_checkout_rejects_missing_files_wrong_sha_and_symlinks(synthetic_git_checkout, sample):
    root, source_sha = synthetic_git_checkout
    m = sample[0]
    with pytest.raises(ValueError, match="CandidateGitHeadMismatch"):
        m.verified_git_source_inventory(root, "0" * 40)
    candidate = root / "terraform/bootstrap/variables.tf"
    candidate.unlink()
    with pytest.raises(ValueError, match="CandidateGitTrackedFileMissing"):
        m.verified_git_source_inventory(root, source_sha)
    candidate.symlink_to(root / "terraform/bootstrap/main.tf")
    with pytest.raises(ValueError, match="CandidateGitSymlinkForbidden"):
        m.verified_git_source_inventory(root, source_sha)


def test_git_review_cannot_override_checkout_inventory(synthetic_git_checkout, sample, monkeypatch):
    root, source_sha = synthetic_git_checkout
    m = sample[0]
    def fake_review(**kwargs):
        assert kwargs["bundle"]["source_sha"] == source_sha
        assert kwargs["checkout_files"] == sample[2]
        return {"status": "MOCK_OFFLINE", "authorized": False, "aws_operations": 0}

    monkeypatch.setattr(m, "review_offline", fake_review)
    result = m.review_git_checkout_offline(
        root, source_sha=source_sha, bundle={"source_sha": source_sha}
    )
    assert result["authorized"] is False
    assert result["git_origin_authenticated"] is False
    with pytest.raises(ValueError, match="CandidateGitSourceOverrideForbidden"):
        m.review_git_checkout_offline(
            root, source_sha=source_sha, bundle={"source_sha": source_sha}, checkout_files={}
        )
