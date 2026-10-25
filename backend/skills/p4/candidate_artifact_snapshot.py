"""Local byte snapshots and change detection; no immutable execution guarantee.

Double observation narrows races but does not freeze a checkout, authenticate
Git origin, or bind a future Terraform process/opened Plan descriptor.
"""

import hashlib
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

import candidate_offline_controller as local


@dataclass(frozen=True)
class SourceSnapshot:
    root: Path
    root_identity: tuple[int, int]
    source_sha: str
    git_tree_sha: str
    inventory_sha256: str
    files: tuple[tuple[str, bytes], ...]
    authorized: bool = field(default=False, init=False)
    git_origin_authenticated: bool = field(default=False, init=False)
    immutable_execution_snapshot_verified: bool = field(default=False, init=False)


def _identity(root: Path) -> tuple[int, int]:
    local.require(not local.linked_component(root), "CandidateSnapshotLinkedRootHOLD")
    info = root.stat()
    local.require(stat.S_ISDIR(info.st_mode), "CandidateSnapshotRootHOLD")
    return info.st_dev, info.st_ino


def capture_source(root: Path, source_sha: str) -> SourceSnapshot:
    local.require(hasattr(os, "O_NOFOLLOW"), "CandidateSnapshotPlatformUnsupportedHOLD")
    root = Path(root)
    identity = _identity(root)
    inventory = local.verified_git_source_inventory(root, source_sha)
    snapshot = SourceSnapshot(
        root,
        identity,
        source_sha,
        inventory["git_tree_sha"],
        inventory["terraform_sources_sha256"],
        tuple(sorted(inventory["checkout_files"].items())),
    )
    assert_source_unchanged(snapshot)
    return snapshot


def assert_source_unchanged(snapshot: SourceSnapshot) -> None:
    local.require(type(snapshot) is SourceSnapshot, "CandidateSnapshotTypeHOLD")
    local.require(
        _identity(snapshot.root) == snapshot.root_identity, "CandidateSnapshotReplacedHOLD"
    )
    observed = local.verified_git_source_inventory(snapshot.root, snapshot.source_sha)
    local.require(
        _identity(snapshot.root) == snapshot.root_identity
        and observed["git_tree_sha"] == snapshot.git_tree_sha
        and observed["terraform_sources_sha256"] == snapshot.inventory_sha256
        and tuple(sorted(observed["checkout_files"].items())) == snapshot.files,
        "CandidateSnapshotChangedHOLD",
    )


def read_plan_snapshot(
    path: Path, expected_sha256: str, *, max_bytes: int = 64 * 1024 * 1024
) -> bytes:
    """Return exact immutable Python bytes, not identity of a future executed file."""
    local.require(hasattr(os, "O_NOFOLLOW"), "CandidateSnapshotPlatformUnsupportedHOLD")
    path = Path(path)
    local.require(
        path.is_absolute()
        and not local.linked_component(path)
        and type(expected_sha256) is str
        and local.HEX64.fullmatch(expected_sha256)
        and type(max_bytes) is int
        and 0 < max_bytes <= 64 * 1024 * 1024,
        "CandidatePlanSnapshotInputHOLD",
    )
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        local.require(stat.S_ISREG(before.st_mode), "CandidatePlanSnapshotFileHOLD")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(max_bytes + 1)
        after = os.fstat(descriptor)
        leaf = path.stat()
        local.require(
            not local.linked_component(path)
            and 0 < len(raw) <= max_bytes
            and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            == (leaf.st_dev, leaf.st_ino, leaf.st_size, leaf.st_mtime_ns)
            and hashlib.sha256(raw).hexdigest() == expected_sha256,
            "CandidatePlanSnapshotChangedHOLD",
        )
        return raw
    finally:
        os.close(descriptor)
