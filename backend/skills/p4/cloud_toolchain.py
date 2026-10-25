"""Credential-free installed toolchain verification before the first OIDC call."""

import json
import os
import re
import shutil
import subprocess
import sys

EXPECTED_UV_VERSION = "0.13.5"
# PR B proposal only: adoption remains HOLD until separately approved merge.
# Historical maintenance/recovery readers keep their independent immutable pins.
NEW_EXECUTION_TERRAFORM_VERSION = "1.16.7"
NEW_EXECUTION_TERRAFORM_PLATFORM = "linux_amd64"
EXPECTED_TERRAFORM_VERSION = NEW_EXECUTION_TERRAFORM_VERSION
MIN_PYTHON_VERSION = (3, 14, 9)


def assert_execution_version(value):
    if (
        not isinstance(value, dict)
        or value.get("terraform_version") != NEW_EXECUTION_TERRAFORM_VERSION
        or value.get("platform") != NEW_EXECUTION_TERRAFORM_PLATFORM
        or ("format_version" in value and value["format_version"] != "1.0")
    ):
        raise ValueError("CloudTerraformVersionMismatch")


def qualify():
    if sys.version_info[:2] != (3, 14) or sys.version_info[:3] < MIN_PYTHON_VERSION:
        raise ValueError("CloudPythonVersionMismatch")
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("AWS_", "ACTIONS_", "GH_", "GITHUB_", "P4_", "TF_"))
    }
    env["CHECKPOINT_DISABLE"] = "1"
    result = {}
    for name, args in (("terraform", ["version", "-json"]), ("uv", ["--version"])):
        executable = shutil.which(name)
        if not executable:
            raise ValueError("CloudToolMissing")
        try:
            process = subprocess.run([executable, *args], env=env, capture_output=True, timeout=15)
        except OSError, subprocess.TimeoutExpired:
            raise ValueError("CloudToolQualificationFailed") from None
        if process.returncode != 0:
            raise ValueError("CloudToolQualificationFailed")
        if name == "terraform":
            try:
                value = json.loads(process.stdout)
            except ValueError, AttributeError, UnicodeError:
                raise ValueError("CloudTerraformVersionMismatch") from None
            assert_execution_version(value)
        elif not re.fullmatch(
            rb"uv " + re.escape(EXPECTED_UV_VERSION.encode("ascii")) + rb" \([^\r\n()]+\)\r?\n?",
            process.stdout,
        ):
            raise ValueError("CloudUvVersionMismatch")
        result[name] = True
    return result
