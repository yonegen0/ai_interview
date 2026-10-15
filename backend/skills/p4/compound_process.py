"""Durable before-start guard for Plan-only CI subprocesses, mode B.

This guards invocation count and exit/timeout. It cannot observe provider/backend
wire sends or promise every native retry is disabled.
"""

import json
import os
from pathlib import Path


def admit(command, directory):
    if not command:
        raise ValueError("CompoundEmptyCommand")
    tool = Path(command[0]).name.lower()
    if tool not in {"terraform", "terraform.exe"}:
        # Existing build/git allowlists and sanitized child env remain in Guard.
        return
    if len(command) < 2 or command[1] not in {"version", "init", "plan", "show"}:
        raise ValueError("CompoundTerraformOperationForbidden")
    operation = command[1]
    if operation == "plan":
        required = {"-input=false", "-lock-timeout=0s", "-parallelism=2"}
        options = command[2:]
        if (
            not required.issubset(options)
            or len(options) != 4
            or len(set(options)) != 4
            or sum(type(x) is str and x.startswith("-out=") and len(x) > 5 for x in options) != 1
        ):
            raise ValueError("CompoundUnsafePlanArgument")
    if operation == "init":
        options = command[2:]
        required = {
            "-input=false",
            "-lockfile=readonly",
            "-backend-config=encrypt=true",
            "-backend-config=use_lockfile=true",
            "-backend-config=max_retries=0",
            "-backend-config=region=ap-northeast-1",
            '-backend-config=allowed_account_ids=["835384817629"]',
            "-backend-config=bucket=ai-interview-state-835384817629-ap-northeast-1",
            "-backend-config=key=dev/terraform.tfstate",
        }
        if set(options) != required or len(options) != len(required):
            raise ValueError("CompoundUnsafeInitArgument")
    if operation in {"init", "plan"}:
        path = Path(directory) / ("compound-" + operation + "-started.private.json")
        with path.open("x", encoding="utf-8") as f:
            os.chmod(path, 0o600)
            json.dump({"operation": operation, "max_attempts": 1, "retry": False}, f)
            f.flush()
            os.fsync(f.fileno())
