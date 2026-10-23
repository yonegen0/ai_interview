"""Failure artifacts stay bounded even when diagnostics grow or contain symlinks."""

import json
import runpy
import zipfile
from pathlib import Path

import pytest


def reporter():
    return runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "frontend/scripts/bounded_report.py")
    )


def test_report_caps_files_bytes_and_retains_diagnostic_manifest(tmp_path):
    module = reporter()
    root = tmp_path / "frontend/playwright-report"
    root.mkdir(parents=True)
    for index in range(140):
        (root / f"report-{index:03}.txt").write_bytes(b"x" * 100000)
    (root / "too-large.txt").write_bytes(b"x" * (module["MAX_FILE_BYTES"] + 1))
    output = tmp_path / "report.zip"
    assert module["build_report"](tmp_path, output) <= module["MAX_ARCHIVE_BYTES"]
    with zipfile.ZipFile(output) as archive:
        manifest = json.loads(archive.read("report-limits.json"))
        assert manifest["partial_report"] is True
        assert manifest["included_files"] <= module["MAX_FILES"]
        assert manifest["included_bytes"] <= module["MAX_INPUT_BYTES"]
        assert all("too-large" not in name for name in archive.namelist())


def test_report_excludes_symlink_targets_and_does_not_overwrite(tmp_path):
    module = reporter()
    root = tmp_path / "frontend/test-results"
    root.mkdir(parents=True)
    secret = tmp_path / "not-a-report.txt"
    secret.write_text("sentinel-secret")
    try:
        (root / "linked.txt").symlink_to(secret)
    except OSError:
        pytest.skip("Host does not allow symlinks; Linux CI verifies this boundary")
    output = tmp_path / "report.zip"
    module["build_report"](tmp_path, output)
    with zipfile.ZipFile(output) as archive:
        assert (
            "sentinel-secret" not in b"".join(archive.read(n) for n in archive.namelist()).decode()
        )
    with pytest.raises(FileExistsError):
        module["build_report"](tmp_path, output)
