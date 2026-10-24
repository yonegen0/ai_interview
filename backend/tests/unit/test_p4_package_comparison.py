"""Fail-closed checks for manual Stage2 Apply package comparison wiring."""

import re
from pathlib import Path

import pytest
from test_p4_tools import tool

ROOT = Path(__file__).resolve().parents[3]


def _mapping_block(document, indent, key):
    """Extract an exact YAML mapping entry's children, not a prefix-indented match."""
    prefix = " " * indent
    matches = list(re.finditer(rf"(?m)^{re.escape(prefix + key)}:[ \t]*$", document))
    assert len(matches) == 1, f"Expected one {key!r} mapping at indent {indent}"
    tail = document[matches[0].end() :]
    next_peer_or_parent = re.search(rf"(?m)^ {{0,{indent}}}\S", tail)
    return tail[: next_peer_or_parent.start()] if next_peer_or_parent else tail


def _assert_apply_package_base_contract(text):
    on = _mapping_block(text, 0, "on")
    dispatch = _mapping_block(on, 2, "workflow_dispatch")
    inputs = _mapping_block(dispatch, 4, "inputs")
    package_base = _mapping_block(inputs, 6, "package_base_sha")
    types = re.findall(r"(?m)^        type:[ \t]*([^\n]*?)[ \t]*$", package_base)
    required_values = re.findall(r"(?m)^        required:[ \t]*([^\n]*?)[ \t]*$", package_base)
    assert types == ["string"]
    assert required_values == ["true"]

    jobs = _mapping_block(text, 0, "jobs")
    offline = _mapping_block(jobs, 2, "offline")
    uses = re.findall(r"(?m)^    uses:[ \t]*([^\n]*?)[ \t]*$", offline)
    assert uses == ["./.github/workflows/p4-static.yml"]
    with_inputs = _mapping_block(offline, 4, "with")
    forwarded = re.findall(r"(?m)^      package_base_sha:[ \t]*([^\n]*?)[ \t]*$", with_inputs)
    assert forwarded == ["${{ inputs.package_base_sha }}"]


def test_apply_passes_required_base_to_reusable_offline_workflow():
    text = (ROOT / ".github/workflows/p4-standard-apply.yml").read_text(encoding="utf-8")
    _assert_apply_package_base_contract(text)


@pytest.mark.parametrize(
    ("original", "replacement"),
    [
        ("      package_base_sha:\n        description:", "      other_input:\n        description:"),
        ("        required: true\npermissions:", "        required: false\npermissions:"),
        (
            "        required: true\npermissions:",
            "        required: true\n        required: false\npermissions:",
        ),
        (
            "      package_base_sha: ${{ inputs.package_base_sha }}\n",
            "      unrelated_base: ${{ inputs.package_base_sha }}\n",
        ),
        (
            "      package_base_sha: ${{ inputs.package_base_sha }}\n",
            "      package_base_sha: ${{ github.sha }}\n",
        ),
    ],
)
def test_apply_package_base_contract_rejects_broken_wiring(original, replacement):
    text = (ROOT / ".github/workflows/p4-standard-apply.yml").read_text(encoding="utf-8")
    assert text.count(original) == 1
    with pytest.raises(AssertionError):
        _assert_apply_package_base_contract(text.replace(original, replacement, 1))


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
            return "backend/src/interview_backend/aws_runtime.py\0"
        return ""

    monkeypatch.setattr(mod, "git", fake_git)
    result = mod.decision(tmp_path, {}, "workflow_dispatch", head, base)
    assert result["base"] == base
    assert result["head"] == head
    assert result["build_package"] is True
    assert ("merge-base", "--is-ancestor", base, head) in calls
