"""Separate credential-free full saved-binary audit; never Plan or Apply."""

import ctypes
import errno
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


def deny_network():
    """Linux seccomp: retain local provider IPC, reject new INET/INET6 sockets.

    No namespace privileges or elevation. Filter is inherited by all children.
    Tested in the actual runner before the first OIDC acquisition.
    """
    if sys.platform != "linux" or platform.machine() != "x86_64":
        raise ValueError("LinuxX64Required")

    class Filter(ctypes.Structure):
        _fields_ = [
            ("code", ctypes.c_ushort),
            ("jt", ctypes.c_ubyte),
            ("jf", ctypes.c_ubyte),
            ("k", ctypes.c_uint),
        ]

    class Program(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ushort), ("filter", ctypes.POINTER(Filter))]

    # Reject foreign syscall architectures. socket=41; socket argument0 at16.
    instructions = [
        (0x20, 0, 0, 4),
        (0x15, 1, 0, 0xC000003E),
        (0x06, 0, 0, 0x80000000),
        (0x20, 0, 0, 0),
        (0x35, 0, 1, 0x40000000),
        (0x06, 0, 0, 0x80000000),
        (0x15, 0, 4, 41),
        (0x20, 0, 0, 16),
        (0x15, 1, 0, 2),
        (0x15, 0, 1, 10),
        (0x06, 0, 0, 0x00050000 | errno.EPERM),
        (0x06, 0, 0, 0x7FFF0000),
    ]
    array = (Filter * len(instructions))(*(Filter(*v) for v in instructions))
    program = Program(len(array), array)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0 or libc.prctl(22, 2, ctypes.byref(program), 0, 0) != 0:
        raise ValueError("NetworkFilterUnavailable")
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            s = socket.socket(family, socket.SOCK_STREAM)
        except OSError as error:
            if error.errno != errno.EPERM:
                raise
        else:
            s.close()
            raise ValueError("NetworkFilterFailed")
    local = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    local.close()


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--qualification":
        deny_network()
        return 0
    private, tf = map(Path, sys.argv[1:])
    if any(
        k.startswith(
            ("ACTIONS_", "GH_TOKEN", "AWS_ACCESS", "AWS_SECRET", "AWS_SESSION", "P4_DEPLOY_INPUTS")
        )
        for k in os.environ
    ):
        raise ValueError("AuditCredentialEnvironmentRejected")
    data = json.loads(private.read_bytes())
    binary = (tf / "dev.tfplan").read_bytes()
    if hashlib.sha256(binary).hexdigest() != data["envelope"]["plan_sha256"]:
        raise ValueError("AuditSavedPlanMismatch")
    deny_network()
    # Same pinned provider directory, credential-free; cannot reach AWS endpoints.
    process = subprocess.run(
        ["terraform", "show", "-json", str((tf / "dev.tfplan").resolve())],
        cwd=Path(__file__).resolve().parents[3] / "terraform/environments/dev",
        capture_output=True,
        timeout=120,
    )
    if process.returncode != 0 or len(process.stdout) > 64 * 1024 * 1024:
        raise ValueError("IndependentShowFailed")
    plan = json.loads(process.stdout)
    if plan != json.loads((tf / "review.private.json").read_bytes()):
        raise ValueError("ProducerIndependentShowMismatch")
    from cloud_controller_core import audit_plan

    approval = SimpleNamespace(x=data["x"])
    binding = json.loads((tf / "plan.json").read_bytes())
    report = audit_plan(
        plan,
        binding,
        data["envelope"],
        binary,
        approval,
        data["envelope"]["run_id"],
        data["snapshot"],
    )
    if not report["passed"]:
        raise ValueError("FullPlanAuditRejected")
    # Explicit public whitelist: no resource values/after_unknown/output data.
    safe = {
        "passed": True,
        "apply_authorized": False,
        "plan_sha256": report["plan_sha256"],
        "counts": report["counts"],
        "changes": [
            {"address": r["address"], "type": r["type"], "action": r["category"]}
            for r in report["entries"]
            if r["category"] not in ("no_op", "read")
        ],
        "independent_show": True,
        "network_denied": True,
        "credential_free": True,
        "create_replace_destroy_iam_changes": 0,
        "retention_exception": "exact five 7-to-14 day updates; Apply separately approved",
    }
    with (tf / "cloud-audit.public.json").open("x") as stream:
        json.dump(safe, stream, sort_keys=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit("IndependentCloudAuditRefused") from None
