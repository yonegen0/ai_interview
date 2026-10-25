"""Supplemental OFFLINE candidate evidence gates; never an execution controller.

These checks cannot authenticate Git, approval signatures, Terraform binaries,
provider checksums, State, or the filesystem hosting the ledger. A successful
result is NOT authorization to contact AWS or run Terraform.
"""

import hashlib
import json
import os
import re
import stat
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

import candidate_bootstrap_preflight as preflight

HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MAX_TTL = timedelta(hours=1)
MAX_CLOCK_SKEW = timedelta(minutes=5)
REVIEW_FIELDS = {
    "schema_version",
    "kind",
    "namespace",
    "source_sha",
    "approval_id",
    "attempt_id",
    "terraform_sources_sha256",
    "issued_at",
    "expires_at",
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def encoded(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def source_inventory_digest(tracked_paths, checkout_files):
    """Bind ALL tracked Terraform bytes, not only six main.tf/versions.tf + locks.

    tracked_paths MUST come from a separately authenticated Git tree. A caller
    supplying both sides of this comparison can forge them; no trust is inferred.
    """
    require(
        type(tracked_paths) in {set, frozenset}
        and type(checkout_files) is dict
        and tracked_paths == set(checkout_files),
        "CandidateSourceInventoryMismatch",
    )
    for path in tracked_paths:
        require(
            type(path) is str
            and path.startswith("terraform/")
            and path == str(PurePosixPath(path))
            and "\\" not in path
            and not any(part in {"..", ".", ".git", ".terraform"} for part in path.split("/"))
            and all(part for part in path.split("/")),
            "CandidateSourcePathInvalid",
        )
        require(type(checkout_files[path]) is bytes, "CandidateSourceBytesRequired")
    required = {
        f"terraform/{scope}/{name}"
        for scope, filename in preflight.ROOTS.items()
        for name in (filename, ".terraform.lock.hcl")
    }
    require(required <= tracked_paths, "CandidateSourceRequiredFileMissing")
    require(
        any(name.endswith(".tf") for name in tracked_paths),
        "CandidateTerraformHclMissing",
    )
    return hashlib.sha256(
        encoded(
            {
                name: hashlib.sha256(checkout_files[name]).hexdigest()
                for name in sorted(tracked_paths)
            }
        )
    ).hexdigest()


def _git_read(root, *args):
    """Read local Git objects only. Does not authenticate origin or fetch remotely."""
    environment = os.environ.copy()
    environment.update(
        GIT_NO_REPLACE_OBJECTS="1",
        GIT_NO_LAZY_FETCH="1",
        GIT_OPTIONAL_LOCKS="0",
        GIT_TERMINAL_PROMPT="0",
    )
    try:
        return subprocess.run(
            ["git", "-C", str(root), "-c", "core.fsmonitor=false", *args],
            check=True,
            capture_output=True,
            timeout=15,
            env=environment,
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError("CandidateGitReadFailed") from error


def verified_git_source_inventory(repo_root, source_sha):
    """Compare *local* HEAD Git tree/blob IDs with an entirely clean Terraform checkout.

    Only SHA-1 Git repositories are supported. The returned bytes may be used for
    OFFLINE review, never as a signed commit, trusted remote origin, or a
    TOCTOU-safe source-to-execution/Plan binding.
    """
    require(
        type(source_sha) is str and HEX40.fullmatch(source_sha) is not None,
        "CandidateGitCommitInvalid",
    )
    root = Path(repo_root)
    require(root.is_absolute() and not root.is_symlink(), "CandidateGitRootInvalid")
    root = root.resolve(strict=True)
    top = _git_read(root, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    require(Path(top).resolve() == root, "CandidateGitRootMismatch")
    head = _git_read(root, "rev-parse", "HEAD").decode("ascii").strip()
    require(head == source_sha, "CandidateGitHeadMismatch")
    tree_sha = _git_read(root, "rev-parse", "HEAD^{tree}").decode("ascii").strip()
    require(HEX40.fullmatch(tree_sha) is not None, "CandidateGitTreeInvalid")
    raw_tree = _git_read(root, "ls-tree", "-r", "-z", "--full-tree", source_sha, "--", "terraform")
    expected = {}
    for entry in raw_tree.split(b"\0"):
        if not entry:
            continue
        meta, separator, filename = entry.partition(b"\t")
        fields = meta.split()
        require(separator and len(fields) == 3, "CandidateGitTreeMalformed")
        mode, kind, blob_sha = fields
        require(
            mode in {b"100644", b"100755"}
            and kind == b"blob"
            and re.fullmatch(rb"[0-9a-f]{40}", blob_sha) is not None,
            "CandidateGitNonregularFile",
        )
        try:
            name = filename.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("CandidateSourcePathInvalid") from error
        require(
            name.startswith("terraform/")
            and name == str(PurePosixPath(name))
            and "\\" not in name
            and all(
                part and part not in {".", "..", ".git", ".terraform"} for part in name.split("/")
            )
            and name not in expected,
            "CandidateSourcePathInvalid",
        )
        expected[name] = blob_sha.decode("ascii")

    source_dir = root / "terraform"
    require(source_dir.is_dir() and not source_dir.is_symlink(), "CandidateGitTerraformRootMissing")
    found = set()
    # Do not ignore Git-ignored files: extra HCL, tfvars, generated overrides
    # and any unexpected path require an explicit review of a sterile checkout.
    for directory, directories, filenames in os.walk(source_dir, followlinks=False):
        for name in directories:
            require(
                not (Path(directory) / name).is_symlink(),
                "CandidateGitSymlinkForbidden",
            )
        for name in filenames:
            path = Path(directory) / name
            require(not path.is_symlink(), "CandidateGitSymlinkForbidden")
            relative = path.relative_to(root).as_posix()
            require(relative in expected, "CandidateGitUntrackedFile")
            found.add(relative)
    require(found == set(expected), "CandidateGitTrackedFileMissing")

    checkout = {}
    for name, blob_sha in expected.items():
        fd = os.open(root / name, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            require(stat.S_ISREG(os.fstat(fd).st_mode), "CandidateGitNonregularFile")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read()
        finally:
            os.close(fd)
        git_blob_sha = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        require(git_blob_sha == blob_sha, "CandidateGitBlobMismatch")
        checkout[name] = data
    digest = source_inventory_digest(set(expected), checkout)
    return {
        "commit_sha": source_sha,
        "git_tree_sha": tree_sha,
        "terraform_sources_sha256": digest,
        "tracked_paths": set(expected),
        "checkout_files": checkout,
        "git_origin_authenticated": False,
        "authorized": False,
    }


def review_git_checkout_offline(repo_root, *, source_sha, **kwargs):
    """Bind offline review to locally verified Git bytes, not caller-supplied lists."""
    require(
        "tracked_paths" not in kwargs and "checkout_files" not in kwargs,
        "CandidateGitSourceOverrideForbidden",
    )
    bundle = kwargs.get("bundle")
    require(
        type(bundle) is dict and bundle.get("source_sha") == source_sha,
        "CandidateGitManifestCommitMismatch",
    )
    inventory = verified_git_source_inventory(repo_root, source_sha)
    result = review_offline(
        **kwargs,
        tracked_paths=inventory["tracked_paths"],
        checkout_files=inventory["checkout_files"],
    )
    require(result.get("authorized") is False, "CandidatePreflightMustNotAuthorize")
    return {
        **result,
        "git_tree_sha": inventory["git_tree_sha"],
        "git_origin_authenticated": False,
        "authorized": False,
    }


def parse_instant(value):
    require(type(value) is str, "CandidateReviewTimeInvalid")
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("CandidateReviewTimeInvalid") from error
    require(
        moment.tzinfo is not None and moment.utcoffset() is not None,
        "CandidateReviewTimeInvalid",
    )
    return moment.astimezone(UTC)


def inspect_review(review, bundle, approval, source_hash, *, now):
    """Check freshness and full source-tree binding, NOT approval authenticity."""
    require(type(review) is dict and set(review) == REVIEW_FIELDS, "CandidateReviewFields")
    require(
        type(review["schema_version"]) is int
        and review["schema_version"] == 3
        and review["kind"] == "p4-bootstrap-candidate-offline-review-v3"
        and review["namespace"] == preflight.NAMESPACE
        and review["namespace"] == bundle.get("namespace")
        and review["source_sha"] == bundle.get("source_sha")
        and type(review["source_sha"]) is str
        and HEX40.fullmatch(review["source_sha"]) is not None
        and review["approval_id"] == approval.get("approval_id")
        and review["attempt_id"] == approval.get("attempt_id")
        and type(review["approval_id"]) is str
        and HEX40.fullmatch(review["approval_id"]) is not None
        and type(review["attempt_id"]) is str
        and HEX40.fullmatch(review["attempt_id"]) is not None
        and type(review["terraform_sources_sha256"]) is str
        and HEX64.fullmatch(review["terraform_sources_sha256"]) is not None
        and review["terraform_sources_sha256"] == source_hash,
        "CandidateReviewBindingMismatch",
    )
    require(isinstance(now, datetime) and now.tzinfo is not None, "CandidateClockRequired")
    issued, expires = parse_instant(review["issued_at"]), parse_instant(review["expires_at"])
    now = now.astimezone(UTC)
    require(
        issued <= expires
        and expires - issued <= MAX_TTL
        and issued <= now + MAX_CLOCK_SKEW
        and now < expires,
        "CandidateReviewExpiredOrInvalid",
    )


def review_offline(
    bundle,
    version_json,
    configurations,
    *,
    binary,
    approval,
    journal,
    tracked_paths,
    checkout_files,
    review,
    now,
    saved_plan=None,
    saved_plan_binary=None,
    saved_plan_approval=None,
):
    """Order: full source inventory -> review expiry -> old offline validator.

    No SDK, credentials, subprocess, backend or remote State. Cannot authorize.
    """
    source_hash = source_inventory_digest(tracked_paths, checkout_files)
    required = {
        f"terraform/{scope}/{name}"
        for scope, filename in preflight.ROOTS.items()
        for name in (filename, ".terraform.lock.hcl")
    }
    require(
        type(configurations) is dict
        and set(configurations) == required
        and all(
            type(raw) is bytes and checkout_files[name] == raw
            for name, raw in configurations.items()
        ),
        "CandidateReviewedConfigurationMismatch",
    )
    inspect_review(review, bundle, approval, source_hash, now=now)
    result = preflight.verify(
        bundle,
        version_json,
        configurations,
        binary=binary,
        approval=approval,
        journal=journal,
        saved_plan=saved_plan,
        saved_plan_binary=saved_plan_binary,
        saved_plan_approval=saved_plan_approval,
    )
    require(result.get("authorized") is False, "CandidatePreflightMustNotAuthorize")
    return {
        "status": "OFFLINE_CANDIDATE_REVIEW_ONLY",
        "authorized": False,
        "aws_operations": 0,
        "terraform_sources_sha256": source_hash,
    }


def protected_directory(path):
    """Only permit an owned, private, real directory on the Linux candidate host."""
    path = Path(path)
    require(path.is_absolute(), "CandidateLedgerAbsolutePathRequired")
    info = path.lstat()
    require(
        stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and info.st_mode & 0o077 == 0,
        "CandidateLedgerDirectoryUnsafe",
    )
    return path


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def private_subdirectory(parent, child):
    require(child not in {"", ".", ".."} and "/" not in child, "CandidateLedgerPathInvalid")
    destination = parent / child
    try:
        os.mkdir(destination, 0o700)
        sync_directory(parent)
    except FileExistsError:
        pass
    return protected_directory(destination)


def exclusive_marker(directory, key, receipt):
    """Create-only and fsynced; a failed write is a permanent stop, not a retry."""
    require(type(key) is str and HEX40.fullmatch(key) is not None, "CandidateLedgerKeyInvalid")
    target = directory / (key + ".json")
    fd = os.open(
        target,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
    )
    try:
        payload = encoded(receipt)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        # fdopen closed the descriptor even when writing failed.
        pass
    sync_directory(directory)


def reserve_offline_attempt(root, *, approval_id, attempt_id, approval_sha256):
    """Reserve a fresh local attempt, without granting or starting AWS execution.

    Requires a caller-provisioned private local root. The approval marker is
    written FIRST so a crash before the attempt marker burns approval reuse.
    A STARTED marker is treated as UNKNOWN on restart, never as retryable.
    The ledger is not tamper/rollback proof and is NOT an authority source.
    """
    require(os.name == "posix", "CandidateLinuxLedgerOnly")
    require(
        type(approval_sha256) is str and HEX64.fullmatch(approval_sha256) is not None,
        "CandidateLedgerDigestInvalid",
    )
    root = protected_directory(root)
    namespace = private_subdirectory(root, preflight.NAMESPACE)
    approvals = private_subdirectory(namespace, "approvals")
    attempts = private_subdirectory(namespace, "attempts")
    exclusive_marker(
        approvals,
        approval_id,
        {
            "namespace": preflight.NAMESPACE,
            "approval_sha256": approval_sha256,
            "attempt_id": attempt_id,
        },
    )
    exclusive_marker(
        attempts,
        attempt_id,
        {
            "namespace": preflight.NAMESPACE,
            "approval_id": approval_id,
            "state": "STARTED_UNKNOWN_ON_RESTART",
        },
    )
    return {"status": "LOCAL_RESERVATION_ONLY", "authorized": False, "aws_operations": 0}
