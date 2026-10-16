"""Finite failure-only JSON. No raw output, exception text, or success authority."""

import json
import os
import re
from pathlib import Path

COMMANDS = frozenset(("unknown", "version", "init", "plan", "show", "build"))


def persist(stage, reason, command_kind, error):
    # Called only with source-pinned stage/reason from cloud_diagnostics.emit.
    from cloud_diagnostics import REASONS, STAGES

    if stage not in STAGES or reason not in REASONS:
        raise ValueError("FailureDiagnosticFiniteValuesInvalid")
    env = os.environ
    run, attempt = env.get("GITHUB_RUN_ID", ""), env.get("GITHUB_RUN_ATTEMPT", "")
    source, parent = env.get("GITHUB_SHA", ""), env.get("P4_CLOUD_PARENT_SHA256", "")
    if (
        not re.fullmatch(r"[1-9][0-9]*", run)
        or attempt != "1"
        or not re.fullmatch(r"[0-9a-f]{40}", source)
        or not re.fullmatch(r"[0-9a-f]{64}", parent)
        or env.get("GITHUB_REPOSITORY") != "yonegen0/ai_interview"
    ):
        raise ValueError("FailureDiagnosticBindingInvalid")
    # Do not invoke arbitrary exception properties here.
    from cloud_process_output import OutputRefusal, ProcessFailure

    warning_class, warning_count = "NotApplicable", 0
    if type(error) is OutputRefusal:
        command_kind = error.command_kind
        warning_class, warning_count = "Unclassified", error.warning_count
    if (
        command_kind not in COMMANDS
        or type(warning_count) is not int
        or not 0 <= warning_count <= 67108864
    ):
        raise ValueError("FailureDiagnosticShapeInvalid")
    value = {
        "schema_version": 1,
        "status": "FAILURE_DIAGNOSTIC_ONLY",
        "repository": "yonegen0/ai_interview",
        "run_id": run,
        "run_attempt": attempt,
        "source_sha": source,
        "parent_sha256": parent,
        "stage": stage,
        "reason_code": reason,
        "command_kind": command_kind,
        "warning_class": warning_class,
        "warning_count": warning_count,
    }
    schema = env.get("P4_CLOUD_FAILURE_JSON_SCHEMA", "1")
    if schema not in {"1", "2"}:
        raise ValueError("FailureDiagnosticShapeInvalid")
    if schema == "2":
        context = None
        if type(error) is ProcessFailure:
            from process_failure_contract import validate_context

            binding = {
                key: value[key]
                for key in ("run_id", "run_attempt", "source_sha", "parent_sha256")
            }
            context = validate_context(error.public_context, binding, command_kind)
            if reason != "PlanProcessFailed":
                raise ValueError("FailureDiagnosticShapeInvalid")
        if reason == "PlanProcessFailed" and context is None:
            raise ValueError("FailureDiagnosticShapeInvalid")
        value.update(schema_version=2, process_failure=context)
    root = Path(env["RUNNER_TEMP"])
    if root.is_symlink() or any(p.is_symlink() for p in root.parents):
        raise ValueError("FailureDiagnosticPathRejected")
    folder = root / "p4-public-diagnostic"
    folder.mkdir(mode=0o700, exist_ok=False)
    # Exclusive creation; a partial file is rejected by the consumer.
    with (folder / "diagnostic.json").open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, separators=(",", ":"))
        stream.flush()
        os.fsync(stream.fileno())
