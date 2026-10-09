"""Artifact settings must fail offline before Terraform or AWS operations."""

import base64
import hashlib
import json
from pathlib import Path

import pytest
from test_p4_tools import tool


def valid_inputs():
    return {
        "log_usage": "developer",
        "artifact_bucket": "ai-interview-artifacts-123456789012-ap-northeast-1",
        "artifact_key": "lambda/preflight/app.zip",
        "artifact_version": "preflight",
        "artifact_sha256_base64": "A" * 43 + "=",
        "boundary_arn": "arn:aws:iam::123456789012:policy/ai-interview-runtime-boundary",
        "ses_email": "sender@example.invalid",
        "ses_identity_arn": (
            "arn:aws:ses:ap-northeast-1:123456789012:identity/sender@example.invalid"
        ),
        "alarm_email": "alarm@example.invalid",
        "jpy_per_usd": "160",
        "budget_rate_date": "2026-09-17",
        "worker_enabled": False,
        "streams_enabled": False,
        "scheduler_enabled": False,
        "api_enabled": False,
    }


@pytest.mark.parametrize(
    ("key", "value", "error"),
    [
        ("artifact_key", "", "InvalidArtifactKey"),
        ("artifact_key", "other/app.zip", "InvalidArtifactKey"),
        ("artifact_key", "lambda/app.txt", "InvalidArtifactKey"),
        ("artifact_key", "lambda/REPLACE_ME.zip", "InvalidArtifactKey"),
        ("artifact_key", None, "InvalidArtifactKey"),
        ("artifact_key", 123, "InvalidArtifactKey"),
        ("artifact_key", {}, "InvalidArtifactKey"),
        ("artifact_key", True, "InvalidArtifactKey"),
        ("artifact_version", "", "VersionedArtifactRequired"),
        ("artifact_version", " ", "VersionedArtifactRequired"),
        ("artifact_version", " v1", "VersionedArtifactRequired"),
        ("artifact_version", "v1 ", "VersionedArtifactRequired"),
        ("artifact_version", "null", "VersionedArtifactRequired"),
        ("artifact_version", "REPLACE_ME_VERSION", "VersionedArtifactRequired"),
        ("artifact_version", None, "VersionedArtifactRequired"),
        ("artifact_version", 123, "VersionedArtifactRequired"),
        ("artifact_version", {}, "VersionedArtifactRequired"),
        ("artifact_version", True, "VersionedArtifactRequired"),
        ("artifact_sha256_base64", "REPLACE_ME", "InvalidArtifactDigest"),
        (
            "artifact_sha256_base64",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "InvalidArtifactDigest",
        ),
        (
            "artifact_sha256_base64",
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            "InvalidArtifactDigest",
        ),
        (
            "artifact_sha256_base64",
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!=",
            "InvalidArtifactDigest",
        ),
        ("artifact_sha256_base64", None, "InvalidArtifactDigest"),
        ("artifact_sha256_base64", 123, "InvalidArtifactDigest"),
        ("artifact_sha256_base64", {}, "InvalidArtifactDigest"),
        ("artifact_sha256_base64", True, "InvalidArtifactDigest"),
    ],
)
def test_invalid_artifact_is_redacted(key, value, error):
    values = valid_inputs() | {key: value}
    with pytest.raises(ValueError) as caught:
        tool("terraform_dev").validate_inputs(values, "123456789012", "ap-northeast-1")
    assert str(caught.value) == error
    assert values[key] == value


@pytest.mark.parametrize("version", ["preflight", "synthetic-version", "v1.+/=_-"])
def test_valid_artifact_and_budget(version):
    values = valid_inputs() | {"artifact_version": version}
    result = tool("terraform_dev").validate_inputs(values, "123456789012", "ap-northeast-1")
    assert result["monthly_budget_usd"] == "18.75"
    assert result["artifact_version"] == version
    assert result["artifact_key"] == values["artifact_key"]
    assert result["artifact_sha256_base64"] == values["artifact_sha256_base64"]


def test_validation_preset_preserves_explicit_artifact_and_budget():
    preset = Path(__file__).resolve().parents[3] / (
        "terraform/environments/dev/validation.example.tfvars.json"
    )
    flags = json.loads(preset.read_text(encoding="utf-8"))
    assert flags == dict.fromkeys(
        ("api_enabled", "worker_enabled", "streams_enabled", "scheduler_enabled"), True
    )
    base = valid_inputs()
    enabled = tool("terraform_dev").validate_inputs(base | flags, "123456789012", "ap-northeast-1")
    closed = tool("terraform_dev").validate_inputs(base, "123456789012", "ap-northeast-1")
    assert all(enabled[key] and not closed[key] for key in flags)
    assert {key: value for key, value in enabled.items() if key not in flags} == {
        key: value for key, value in closed.items() if key not in flags
    }


def test_closure_preset_reverses_only_validation_flags():
    dev = Path(__file__).resolve().parents[3] / "terraform/environments/dev"
    enablement = json.loads((dev / "validation.example.tfvars.json").read_text(encoding="utf-8"))
    closure = json.loads((dev / "closure.example.tfvars.json").read_text(encoding="utf-8"))
    assert closure == dict.fromkeys(enablement, False)
    base = valid_inputs()
    inputs = tool("terraform_dev")
    active_inputs = base | enablement
    active = inputs.validate_inputs(active_inputs, "123456789012", "ap-northeast-1")
    restored = inputs.validate_inputs(active_inputs | closure, "123456789012", "ap-northeast-1")
    assert restored == inputs.validate_inputs(base, "123456789012", "ap-northeast-1")
    assert {key for key in active if active[key] != restored[key]} == set(closure)


def test_closure_after_artifact_update_keeps_latest_deployment():
    dev = Path(__file__).resolve().parents[3] / "terraform/environments/dev"
    enablement = json.loads((dev / "validation.example.tfvars.json").read_text(encoding="utf-8"))
    closure = json.loads((dev / "closure.example.tfvars.json").read_text(encoding="utf-8"))
    initial = valid_inputs()
    corrected = initial | {
        "artifact_key": "lambda/corrected-build/app.zip",
        "artifact_version": "corrected-immutable-version",
        "artifact_sha256_base64": base64.b64encode(
            hashlib.sha256(b"corrected build").digest()
        ).decode(),
    }
    inputs = tool("terraform_dev")
    active = inputs.validate_inputs(corrected | enablement, "123456789012", "ap-northeast-1")
    closed = inputs.validate_inputs(
        corrected | enablement | closure, "123456789012", "ap-northeast-1"
    )
    assert closed == inputs.validate_inputs(corrected, "123456789012", "ap-northeast-1")
    assert {key for key in active if active[key] != closed[key]} == set(closure)
    for key in ("artifact_key", "artifact_version", "artifact_sha256_base64"):
        assert closed[key] == corrected[key] != initial[key]
