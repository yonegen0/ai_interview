"""Preserve private process bytes and refuse unclassified material warnings."""

import re


def inspect(guard, kind, stdout, stderr):
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
    if re.search(r"(?im)^\s*(?:│\s*)?warning\s*:", text):
        # No unreviewed warning is declared harmless. No raw output is public.
        raise ValueError("CloudImportantWarningUnclassified")
