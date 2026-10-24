"""Pre-OIDC toolchain failures never enter the cloud authentication path."""

import subprocess
from types import SimpleNamespace

import pytest
from test_p4_tools import tool


def _fake_tools(monkeypatch, *, uv=b"uv 0.13.5 (test)", tf=b'{"terraform_version":"1.14.9"}'):
    m = tool("cloud_toolchain")
    calls = []
    monkeypatch.setattr(m.shutil, "which", lambda name: name)

    def run(args, **kw):
        calls.append(args[0])
        assert kw["timeout"] == 15
        assert kw["capture_output"] is True
        assert not any(
            k.startswith(("AWS_", "ACTIONS_", "GH_", "GITHUB_", "P4_", "TF_")) for k in kw["env"]
        )
        return SimpleNamespace(returncode=0, stdout=tf if args[0] == "terraform" else uv)

    monkeypatch.setattr(m.subprocess, "run", run)
    return m, calls


def test_installed_tools_are_checked_without_credential_environment(monkeypatch):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic-secret")
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "synthetic-token")
    m, calls = _fake_tools(monkeypatch)
    assert m.qualify() == {"terraform": True, "uv": True}
    assert calls == ["terraform", "uv"]


@pytest.mark.parametrize(
    ("version", "accepted"),
    [
        ((3, 14, 8), False),
        ((3, 14, 9), True),
        ((3, 14, 10), True),
        ((3, 15, 0), False),
        ((3, 13, 99), False),
    ],
)
def test_python_version_boundary(monkeypatch, version, accepted):
    m, calls = _fake_tools(monkeypatch)
    monkeypatch.setattr(m, "sys", SimpleNamespace(version_info=version))
    if accepted:
        assert m.qualify() == {"terraform": True, "uv": True}
        assert calls == ["terraform", "uv"]
    else:
        with pytest.raises(ValueError, match="CloudPythonVersionMismatch"):
            m.qualify()
        assert calls == []


@pytest.mark.parametrize(
    ("output", "accepted"),
    [
        (b"uv 0.13.4 (test)", False),
        (b"uv 0.13.5 (test)", True),
        (b"uv 0.13.6 (test)", False),
        (b"uv 0.13.5 (46776a95d 2026-10-21)\n", True),
        (b"uv 0.13.5 garbage", False),
        (b"uv 0.13.5 (test)\nunsafe", False),
        (b"uv 0.13.5", False),
        (b"", False),
        (b"\xff\xfe", False),
    ],
)
def test_uv_version_boundary(monkeypatch, output, accepted):
    m, calls = _fake_tools(monkeypatch, uv=output)
    if accepted:
        assert m.qualify() == {"terraform": True, "uv": True}
    else:
        with pytest.raises(ValueError, match="CloudUvVersionMismatch"):
            m.qualify()
    assert calls == ["terraform", "uv"]


@pytest.mark.parametrize("output", [b'{"terraform_version":"1.14.8"}', b"{}", b"garbage", b"[]"])
def test_terraform_version_and_format_are_rejected(monkeypatch, output):
    m, calls = _fake_tools(monkeypatch, tf=output)
    with pytest.raises(ValueError, match="CloudTerraformVersionMismatch"):
        m.qualify()
    assert calls == ["terraform"]


@pytest.mark.parametrize("missing", ["terraform", "uv"])
def test_missing_tool_is_rejected_before_oidc(monkeypatch, missing):
    m, calls = _fake_tools(monkeypatch)
    monkeypatch.setattr(m.shutil, "which", lambda name: None if name == missing else name)
    with pytest.raises(ValueError, match="CloudToolMissing"):
        m.qualify()
    assert calls == ([] if missing == "terraform" else ["terraform"])


@pytest.mark.parametrize("failure", ["exit", "missing-executable", "timeout"])
def test_subprocess_failure_stops_before_authentication(monkeypatch, failure):
    m, _ = _fake_tools(monkeypatch)
    calls = []

    def fail(args, **kwargs):
        calls.append(args[0])
        if failure == "exit":
            return SimpleNamespace(returncode=1, stdout=b"")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])
        raise FileNotFoundError("synthetic")

    monkeypatch.setattr(m.subprocess, "run", fail)
    with pytest.raises(ValueError, match="CloudToolQualificationFailed"):
        m.qualify()
    assert calls == ["terraform"]
