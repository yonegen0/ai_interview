"""Package synthetic CI failure reports with a finite upload size and no symlink traversal."""

import json
import os
import stat
import zipfile
from pathlib import Path

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 10 * 1024 * 1024
MAX_FILES = 128
MAX_VISITED = 1024


def build_report(workspace, destination):
    workspace = Path(workspace).resolve()
    destination = Path(destination)
    included = total = visited = omitted = 0
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_STORED) as archive:
        for name in ("playwright-report", "test-results"):
            root = workspace / "frontend" / name
            if not root.exists() or root.is_symlink() or root.is_junction():
                continue
            if not root.resolve().is_relative_to(workspace):
                continue
            for parent, dirs, files in root.walk(follow_symlinks=False):
                dirs[:] = sorted(d for d in dirs if not (parent / d).is_symlink())
                if len(parent.relative_to(root).parts) > 8 or visited >= MAX_VISITED:
                    dirs[:] = []
                    omitted += 1
                    continue
                for filename in sorted(files):
                    visited += 1
                    if visited > MAX_VISITED or included >= MAX_FILES:
                        omitted += 1
                        break
                    path = parent / filename
                    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                        omitted += 1
                        continue
                    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                    try:
                        info = os.fstat(descriptor)
                        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
                            omitted += 1
                            continue
                        with os.fdopen(descriptor, "rb", closefd=False) as stream:
                            raw = stream.read(MAX_FILE_BYTES + 1)
                    finally:
                        os.close(descriptor)
                    if len(raw) > MAX_FILE_BYTES or total + len(raw) > MAX_INPUT_BYTES:
                        omitted += 1
                        continue
                    relative = path.relative_to(workspace).as_posix()
                    if len(relative.encode()) > 512:
                        omitted += 1
                        continue
                    archive.writestr(relative, raw)
                    included += 1
                    total += len(raw)
        archive.writestr(
            "report-limits.json",
            json.dumps(
                {
                    "included_files": included,
                    "included_bytes": total,
                    "omitted_entries": omitted,
                    "max_archive_bytes": MAX_ARCHIVE_BYTES,
                    "partial_report": omitted > 0,
                }
            ),
        )
    if destination.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("FailureReportArchiveTooLarge")
    return destination.stat().st_size


def main():
    target = Path(os.environ["RUNNER_TEMP"]) / "frontend-test-results.zip"
    build_report(Path.cwd(), target)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        stream.write("ready=true\n")


if __name__ == "__main__":
    main()
