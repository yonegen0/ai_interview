"""Pre-OIDC toolchain failures never enter the cloud authentication path."""

from types import SimpleNamespace

import pytest
from test_p4_tools import tool


def test_installed_tools_are_checked_without_credential_environment(monkeypatch):
    m = tool("cloud_toolchain")
    seen = []
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic-secret")
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "synthetic-token")
    monkeypatch.setattr(m.shutil, "which", lambda name: name)

    def run(args, **kw):
        assert not any(k.startswith(("AWS_", "ACTIONS_")) for k in kw["env"])
        seen.append(args[0])
        return SimpleNamespace(
            returncode=0,
            stdout=(
                b'{"terraform_version":"1.14.9"}' if args[0] == "terraform" else b"uv 0.11.8 (test)"
            ),
        )

    monkeypatch.setattr(m.subprocess, "run", run)
    assert m.qualify() == {"terraform": True, "uv": True}
    assert seen == ["terraform", "uv"]


def test_wrong_terraform_is_rejected_before_oidc(monkeypatch):
    m = tool("cloud_toolchain")
    monkeypatch.setattr(m.shutil, "which", lambda name: name)
    monkeypatch.setattr(
        m.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=b'{"terraform_version":"0.0.0"}'),
    )
    with pytest.raises(ValueError, match="CloudTerraformVersionMismatch"):
        m.qualify()


def test_missing_tool_is_rejected_before_oidc(monkeypatch):
    m = tool("cloud_toolchain")
    monkeypatch.setattr(m.shutil, "which", lambda name: None)
    with pytest.raises(ValueError, match="CloudToolMissing"):
        m.qualify()
