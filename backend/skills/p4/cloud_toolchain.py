"""Credential-free installed toolchain verification before the first OIDC call."""

import json
import os
import shutil
import subprocess
import sys


def qualify():
    if sys.version_info[:3] < (3, 14, 9) or sys.version_info[:2] != (3, 14):
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
        process = subprocess.run([executable, *args], env=env, capture_output=True, timeout=15)
        if process.returncode != 0:
            raise ValueError("CloudToolQualificationFailed")
        if name == "terraform":
            if json.loads(process.stdout).get("terraform_version") != "1.14.9":
                raise ValueError("CloudTerraformVersionMismatch")
        elif not process.stdout.decode().startswith("uv 0.13.5 "):
            raise ValueError("CloudUvVersionMismatch")
        result[name] = True
    return result
