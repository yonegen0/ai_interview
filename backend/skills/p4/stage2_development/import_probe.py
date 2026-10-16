"""Import-only child. No user environment, credentials, writes or external I/O."""

import contextlib
import importlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_policy import Policy


def main():
    request = json.loads(sys.stdin.read())
    roots = [Path(p).resolve() for p in request["roots"]]
    allowed = roots + [
        Path(sys.base_prefix).resolve(),
        Path(sys.prefix).resolve(),
        Path(__file__).resolve().parent,
    ]
    sys.path[:0] = [str(p) for p in roots]
    sys.dont_write_bytecode = True
    policy = Policy(request.get("dependency_roots", []))
    denied = set()
    diagnostics = []
    allowed_initializers = set()
    known_events = {
        "socket.__new__",
        "socket.bind",
        "socket.connect",
        "socket.getaddrinfo",
        "socket.gethostbyname",
        "socket.sendto",
        "socket.sendmsg",
        "subprocess.Popen",
        "ctypes.dlopen",
        "ctypes.dlsym",
        "open",
        "open-private",
        "open-write",
        "open-file-descriptor",
        "os.system",
        "os.posix_spawn",
        "os.spawn",
        "os.startfile",
        "os.remove",
        "os.rename",
        "os.mkdir",
        "os.rmdir",
        "os.putenv",
        "os.unsetenv",
    }

    class Discard:
        def write(self, value):
            return len(value)

        def flush(self):
            pass

    def finite_event(event):
        return event if event in known_events else "other-prohibited-event"

    def record(event, category):
        # Finite classes only: never publish a path, argument or exception text.
        kinds = set()
        frame = sys._getframe(2)
        while frame:
            name = frame.f_globals.get("__name__", "")
            if name == "random":
                kinds.add("stdlib-random")
            elif name == "multiprocessing.process":
                kinds.add("stdlib-process-initialization")
            elif name == "urllib3.util.connection":
                kinds.add("dependency-ipv6-probe")
            frame = frame.f_back
        item = {
            "event": finite_event(event),
            "category": category,
            "caller_classes": sorted(kinds) or ["other"],
        }
        if item not in diagnostics:
            diagnostics.append(item)

    def audit(event, args):
        if event.startswith("socket.") and policy.socket(event, args):
            allowed_initializers.add("dependency-ipv6-loopback")
            return
        if event.startswith(
            ("socket.", "subprocess.", "ctypes.", "winreg.", "urllib.")
        ) or event in {
            "os.system",
            "os.posix_spawn",
            "os.spawn",
            "os.startfile",
            "os.remove",
            "os.rename",
            "os.mkdir",
            "os.rmdir",
            "os.putenv",
            "os.unsetenv",
        }:
            denied.add(finite_event(event))
            record(
                event,
                "socket-operation"
                if event.startswith("socket.")
                else "prohibited-side-effect",
            )
            raise PermissionError("ImportSideEffectDenied")
        if event == "open":
            path, mode, flags = args
            if isinstance(path, (str, bytes)):
                kind = policy.entropy(os.fsdecode(path), mode, flags)
                if kind:
                    allowed_initializers.add(kind)
                    return
            if not isinstance(path, (str, bytes, os.PathLike)):
                denied.add("open-file-descriptor")
                record("open", "file-descriptor")
                raise PermissionError("ImportFileDescriptorDenied")
            if (mode and any(c in mode for c in "wax+")) or flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
            ):
                denied.add("open-write")
                record("open", "file-change")
                raise PermissionError("ImportWriteDenied")
            p = Path(os.fsdecode(path)).resolve()
            if not any(p.is_relative_to(r) for r in allowed) or any(
                part.lower() in {".aws", ".ssh", "private", "decrypted"}
                or part.lower().startswith(".env")
                or ".key." in part.lower()
                for part in p.parts
            ):
                denied.add("open-private")
                record(
                    "open",
                    "os-entropy" if str(p) == "/dev/urandom" else "outside-or-private",
                )
                raise PermissionError("ImportPrivateReadDenied")

    sys.addaudithook(audit)
    imported, issues = [], []
    for module in request["entries"]:
        try:
            with (
                contextlib.redirect_stdout(Discard()),
                contextlib.redirect_stderr(Discard()),
            ):
                importlib.import_module(module)
            imported.append(module)
        except BaseException as exc:  # noqa: BLE001 - catch SystemExit; never expose error text.
            issues.append(
                {
                    "module": module,
                    "exception_type": type(exc).__name__
                    if type(exc).__name__
                    in {
                        "PermissionError",
                        "ModuleNotFoundError",
                        "ImportError",
                        "ValueError",
                        "TypeError",
                        "RuntimeError",
                        "AssertionError",
                        "SystemExit",
                        "SyntaxError",
                        "OSError",
                    }
                    else "OtherImportError",
                }
            )
    print(
        json.dumps(
            {
                "passed": not issues and not denied,
                "issues": issues,
                "imported": imported,
                "denied_events": sorted(denied),
                "event_diagnostics": diagnostics,
                "allowed_initializers": sorted(allowed_initializers),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
