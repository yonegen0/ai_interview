"""Narrow, byte-checked exceptions for dependency import initialization.

No SDK import runs outside the audit hook. These exceptions authorize entropy
initialization and an IPv6 loopback bind only, never connection or name lookup.
"""

import hashlib
import os
import stat
import sys
import types
from pathlib import Path

# Reviewed local bytes from the locked urllib3 2.7.0 distribution. A different
# release or modified source fails closed; this is a security policy input.
IPV6_SOURCE_SHA256 = "2633bbdb69731e5ccb5cf4e4afd65605d86c7979cc5633126f50c92d5ad74a74"


def function_code(path, names):
    code = compile(path.read_bytes(), str(path), "exec")
    for name in names:
        matches = [
            c
            for c in code.co_consts
            if isinstance(c, types.CodeType) and c.co_name == name
        ]
        if len(matches) != 1:
            raise ValueError("UnrecognizedImportInitializer")
        code = matches[0]
    return code


class Policy:
    def __init__(self, dependency_roots):
        self.codes = {}
        self.sockets = set()
        if sys.platform != "linux" or sys.version_info[:2] != (3, 14):
            return
        stdlib = Path(sys.base_prefix).resolve() / "lib/python3.14"
        for kind, relative, names in (
            ("stdlib-random", "random.py", ("Random", "seed")),
            (
                "stdlib-process-initialization",
                "multiprocessing/process.py",
                ("_MainProcess", "__init__"),
            ),
        ):
            path = stdlib / relative
            self.codes[kind] = (path, function_code(path, names))
        for root in dependency_roots:
            path = Path(root).resolve() / "urllib3/util/connection.py"
            if (
                path.is_file()
                and hashlib.sha256(path.read_bytes()).hexdigest() == IPV6_SOURCE_SHA256
            ):
                self.codes["dependency-ipv6-probe"] = (
                    path,
                    function_code(path, ("_has_ipv6",)),
                )
                break
        info = os.stat("/dev/urandom", follow_symlinks=False)
        self.entropy_device = (
            stat.S_ISCHR(info.st_mode)
            and os.major(info.st_rdev) == 1
            and os.minor(info.st_rdev) == 9
        )

    def caller(self, kind):
        expected = self.codes.get(kind)
        if expected is None:
            return None
        path, code = expected
        frame = sys._getframe(1)
        for _ in range(12):
            if frame is None:
                break
            # Code-object equality includes all bytecode/constants. A module
            # name, caller filename or line number alone cannot grant access.
            if frame.f_code == code and frame.f_globals.get("__file__") == str(path):
                return frame
            frame = frame.f_back
        return None

    def entropy(self, path, mode, flags):
        if not getattr(self, "entropy_device", False) or path != "/dev/urandom":
            return None
        if mode not in (None, "r", "rb") or flags & (
            os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        ):
            return None
        for kind in ("stdlib-random", "stdlib-process-initialization"):
            if self.caller(kind) is not None:
                return kind
        return None

    def socket(self, event, args):
        frame = self.caller("dependency-ipv6-probe")
        if frame is None or frame.f_locals.get("host") != "::1":
            return False
        # Linux AF_INET6=10; SOCK_STREAM=1; protocol default=0. Never allow
        # connect, DNS, listen, accept, send, arbitrary bind or descriptor reuse.
        if event == "socket.__new__" and len(args) == 4 and args[1:] == (10, 1, 0):
            self.sockets.add(id(args[0]))
            return True
        return (
            event == "socket.bind"
            and len(args) == 2
            and id(args[0]) in self.sockets
            and args[1] == ("::1", 0)
        )
