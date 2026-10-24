"""Fail-closed checks for manual Stage2 Apply package comparison wiring."""

from pathlib import Path

import pytest
from test_p4_tools import tool


ROOT = Path(__file__).resolve().parents[3]


def test_apply_passes_required_base_to_reusable_offline_workflow():
    text = (ROOT / ".github/workflows/p4-standard-apply.yml").read_text(encoding="utf-8")
    assert "      package_base_sha:\n        description:" in text
    assert "        required: true" in text.split("      package_base_sha:", 1)[1].split("\n      ", 1)[0]
    assert (
        "    uses: ./.github/workflows/p4-static.yml\n"
        "    with:\n"
        "      package_base_sha: ${{ inputs.package_base_sha }}\n"
    ) in text


def test_manual_comparison_cannot_use_head_as_base(tmp_path):
    mod = tool("package_changes")
    sha = "a" * 40
    with pytest.raises(ValueError, match="PackageComparisonBaseMustPrecedeHead"):
        mod.decision(tmp_path, {}, "workflow_dispatch", sha, sha)


def test_explicit_ancestor_is_compared_and_package_changes_are_preserved(tmp_path, monkeypatch):
    mod = tool("package_changes")
    base, head = "a" * 40, "b" * 40
    calls = []

    def fake_git(root, *arguments):
        calls.append(arguments)
        if arguments[:2] == ("diff", "--no-renames"):
            return "backend/src/interview_backend/aws_runtime.py\\0"
        return ""

    monkeypatch.setattr(mod, "git", fake_git)
    result = mod.decision(tmp_path, {}, "workflow_dispatch", head, base)
    assert result["base"] == base
    assert result["head"] == head
    assert result["build_package"] is True
    assert ("merge-base", "--is-ancestor", base, head) in calls
