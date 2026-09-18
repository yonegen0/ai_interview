"""Artifact settings must fail offline before Terraform or AWS operations."""

import pytest
from test_p4_tools import tool


def valid_inputs():
    return {
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
