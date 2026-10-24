"""Credential-free workflow/toolchain drift checks for security-pinned CI."""

import re
from pathlib import Path

from test_p4_tools import tool

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"
ACTION = "astral-sh/setup-uv@07a047e608db84b3d8c06cd9a7c7dcc9c355c18e"


def test_all_setup_uv_workflows_pin_verified_action_and_uv_python():
    files = sorted(WORKFLOWS.glob("*.yml"))
    users = [p for p in files if "astral-sh/setup-uv@" in p.read_text(encoding="utf-8")]
    assert len(users) == 11
    for path in users:
        content = path.read_text(encoding="utf-8")
        assert content.count(ACTION) == 1, path
        assert len(re.findall(r"astral-sh/setup-uv@", content)) == 1, path
        assert re.search(r"(?m)^\s+version: ['\"]?0\.13\.5['\"]?$", content), path
        assert re.search(r"(?m)^\s+python-version: ['\"]?3\.14\.9['\"]?$", content), path
        assert not re.search(r"--python 3\.14(?!\.9)(?!\d)", content), path


def test_workflows_match_credential_free_cloud_toolchain_contract():
    m = tool("cloud_toolchain")
    assert m.EXPECTED_UV_VERSION == "0.13.5"
    assert m.EXPECTED_TERRAFORM_VERSION == "1.14.9"
    assert m.MIN_PYTHON_VERSION == (3, 14, 9)
    for path in WORKFLOWS.glob("*.yml"):
        content = path.read_text(encoding="utf-8")
        for version in re.findall(r"(?m)^\s+terraform_version:\s*['\"]?([\d.]+)", content):
            assert version == m.EXPECTED_TERRAFORM_VERSION, path
    static = (WORKFLOWS / "p4-static.yml").read_text(encoding="utf-8")
    oidc = (WORKFLOWS / "p4-oidc-discovery.yml").read_text(encoding="utf-8")
    assert static.count("--python 3.14.9 ") == 4
    assert oidc.count("--python 3.14.9 ") == 1
    backend = (WORKFLOWS / "backend.yml").read_text(encoding="utf-8")
    assert "uv run --locked python --version" in backend
    assert "sys.version_info[:3] == (3, 14, 9)" in backend
