"""Preserve private process bytes and refuse unclassified material warnings."""

import re

COMMAND_KINDS = frozenset(("version", "init", "plan", "show", "build"))


class OutputRefusal(ValueError):
    """Only finite metadata; raw output remains in the private evidence."""

    reason_code = "CloudImportantWarningUnclassified"
    warning_class = "Unclassified"

    def __init__(self, kind, count):
        super().__init__(self.reason_code)
        self.command_kind = kind if kind in COMMAND_KINDS else "unknown"
        self.warning_count = count


def inspect(guard, kind, stdout, stderr):
    if kind not in COMMAND_KINDS:
        raise ValueError("InvalidOperation")
    if len(stdout) + len(stderr) > 64 * 1024 * 1024:
        raise ValueError("CloudOutputSizeExceeded")
    for label, raw in (("stdout", stdout), ("stderr", stderr)):
        with (guard.directory / f"process-{guard.sequence:04d}-{kind}-{label}.private.raw").open(
            "xb"
        ) as stream:
            stream.write(raw)
    text = re.sub(
        r"\x1b\[[0-9;]*m", "", (stdout + b"\n" + stderr).decode("utf-8", errors="replace")
    )
    count = len(re.findall(r"(?im)^\s*(?:│\s*)?warning\s*:", text))
    if count:
        # No unreviewed warning is declared harmless. No raw output is public.
        raise OutputRefusal(kind, count)
