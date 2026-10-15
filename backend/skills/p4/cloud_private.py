"""Standard POSIX private directory qualification on a fresh hosted runner."""

import errno
import os
import stat
import tempfile
from pathlib import Path


def qualify(root):
    root = Path(root)
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError("PrivateParentSymlink")
    if root.stat().st_uid != os.getuid():
        raise ValueError("RunnerOwnerMismatch")
    # New private directory, exclusive no-follow file, symlink rejection and rename.
    directory = Path(tempfile.mkdtemp(prefix="p4-private-qualification-", dir=root))
    if stat.S_IMODE(directory.stat().st_mode) != 0o700:
        raise ValueError("PrivateDirectoryModeMismatch")
    target = directory / "probe"
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(b"public qualification probe")
    if stat.S_IMODE(target.stat().st_mode) != 0o600:
        raise ValueError("PrivateFileModeMismatch")
    link = directory / "link"
    link.symlink_to(target)
    try:
        os.open(link, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        if error.errno != errno.ELOOP:
            raise
    else:
        raise ValueError("NoFollowQualificationFailed")
    renamed = directory / "renamed"
    target.rename(renamed)
    # Rename by the trusted UID is normal. Untrusted same-UID code is excluded
    # by pinned source and fresh single-job runner; modes isolate other UIDs.
    return {
        "posix_modes": True,
        "no_follow": True,
        "fresh_job_uid_boundary": True,
        "rename_same_uid": "permitted",
        "other_user_probe": "SKIP; effective mode bits checked",
        "same_uid_or_root_compromise": "outside protection guarantee",
    }
