"""The fresh-process proxy must isolate credentials and preserve auth rejection."""

import json
import subprocess
import sys
from pathlib import Path

from cold_start_benchmark import CHILD, environment


def test_proxy_environment_excludes_inherited_credentials(monkeypatch):
    monkeypatch.setenv("AWS_PROFILE", "synthetic-private-profile")
    monkeypatch.setenv("INTERVIEW_OPENAI_ENABLED", "true")
    monkeypatch.setenv("P4_AWS_EXECUTION_READY", "true")
    monkeypatch.setenv("GH_TOKEN", "synthetic-token")
    root = Path(__file__).resolve().parents[3]
    env = environment(root)
    assert "AWS_PROFILE" not in env
    assert "INTERVIEW_OPENAI_ENABLED" not in env
    assert "P4_AWS_EXECUTION_READY" not in env
    assert "GH_TOKEN" not in env


def test_fresh_proxy_can_compose_and_reject_auth_without_sdk_client():
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, "-B", "-c", CHILD],
        cwd=root,
        env=environment(root),
        capture_output=True,
        check=True,
        timeout=30,
    )
    sample = json.loads(result.stdout)
    assert sample["import_ms"] > 0
    assert sample["combined_proxy_ms"] >= sample["import_ms"]
