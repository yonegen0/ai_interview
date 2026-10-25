"""Probe boundaries fail before executing any unverified binary. No network."""

import hashlib
import subprocess

import pytest
from test_p4_tools import tool


@pytest.mark.parametrize(
    "same_namespace,interfaces",
    [(True, [(1, "lo")]), (False, [(1, "lo"), (2, "eth0")]), (False, [])],
)
def test_network_namespace_or_interfaces_fail_closed(monkeypatch, same_namespace, interfaces):
    m = tool("candidate_toolchain_probe")
    monkeypatch.setattr(m.sys, "platform", "linux")
    monkeypatch.setattr(
        m.os,
        "readlink",
        lambda path: "parent" if same_namespace or path == "/proc/1/ns/net" else "child",
    )
    monkeypatch.setattr(m.socket, "if_nameindex", lambda: interfaces)
    with pytest.raises(ValueError, match="NetworkIsolationRequiredHOLD"):
        m.require_isolation()


def test_child_namespace_with_only_loopback_is_required(monkeypatch):
    m = tool("candidate_toolchain_probe")
    monkeypatch.setattr(m.sys, "platform", "linux")
    monkeypatch.setattr(m.os, "readlink", lambda path: path)
    monkeypatch.setattr(m.socket, "if_nameindex", lambda: [(1, "lo")])
    m.require_isolation()


@pytest.mark.parametrize("mutation", ["cli", "provider", "version", "lock"])
def test_binary_version_and_lock_fail_before_any_subprocess(tmp_path, monkeypatch, mutation):
    m = tool("candidate_toolchain_probe")
    monkeypatch.setattr(m, "require_isolation", lambda: None)

    def forbidden(*args, **kwargs):
        raise AssertionError("Unverified binary must not execute")

    monkeypatch.setattr(subprocess, "run", forbidden)
    cli, provider = tmp_path / "terraform", tmp_path / "provider"
    cli.write_bytes(b"not executable")
    provider.write_bytes(b"not a provider")
    args = dict(
        version="1.16.7",
        cli_sha256=hashlib.sha256(cli.read_bytes()).hexdigest(),
        provider_sha256=hashlib.sha256(provider.read_bytes()).hexdigest(),
        provider_inventory_sha256="0" * 64,
        lock_bytes=b"invalid lock",
    )
    if mutation == "cli":
        args["cli_sha256"] = "0" * 64
    elif mutation == "provider":
        args["provider_sha256"] = "0" * 64
    elif mutation == "version":
        args["version"] = "1.14.9"
    with pytest.raises(ValueError):
        m.probe(cli, provider, **args)
