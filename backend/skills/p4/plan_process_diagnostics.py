"""Fixed diagnostic hints, never raw Terraform output or exception text.

Markers are hints, not proof of a cause. Unknown output stays unclassified.
This module does not change exit-code acceptance, permissions or retry policy.
"""

import hashlib

MAX_CLASSIFY_BYTES = 1024 * 1024
MARKERS = (
    (
        "authorization-denied-marker",
        (b"AccessDenied", b"AccessDeniedException", b"UnauthorizedOperation"),
    ),
    ("state-lock-marker", (b"Error acquiring the state lock",)),
    ("expired-credentials-marker", (b"ExpiredToken", b"ExpiredTokenException")),
    ("invalid-provider-configuration-marker", (b"Invalid provider configuration",)),
)


def summarize_failure(returncode, stdout, stderr):
    if type(returncode) is not int or not -(2**31) <= returncode < 2**31:
        raise ValueError("InvalidProcessReturnCode")
    if type(stdout) is not bytes or type(stderr) is not bytes:
        raise ValueError("InvalidProcessOutput")
    markers = []
    if len(stderr) <= MAX_CLASSIFY_BYTES:
        for label, tokens in MARKERS:
            if any(token in stderr for token in tokens):
                markers.append(label)
    return {
        "schema_version": 1,
        "returncode": returncode,
        "stdout_bytes": len(stdout),
        "stderr_bytes": len(stderr),
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "diagnostic_hints": markers or ["unclassified"],
        "classification_complete": len(stderr) <= MAX_CLASSIFY_BYTES,
        "hints_are_root_cause_proof": False,
        "raw_output_preserved": False,
    }


SAFE_EXCEPTION_TYPES = frozenset(
    (
        "DeploymentError",
        "ClientError",
        "HTTPError",
        "RuntimeError",
        "ValueError",
        "KeyError",
        "TimeoutError",
        "OSError",
        "ImportError",
        "ModuleNotFoundError",
        "PermissionError",
        "FileNotFoundError",
        "KeyboardInterrupt",
        "SystemExit",
    )
)
PHASES = frozenset(("launch", "wait", "diagnostic", "admission"))
REASONS = frozenset(
    (
        "PlanProcessFailed",
        "PlanProcessDeadlineStop",
        "PlanProcessDiagnosticFailed",
        "PlanProcessJournalFailed",
        "PlanApprovalExpiredOrInsufficientTime",
        "PlanApprovalStopped",
        "PlanApprovalChangedDuringExecution",
    )
)


def safe_exception_type(error):
    name = type(error).__name__
    return name if name in SAFE_EXCEPTION_TYPES else "OtherException"


def summarize_exception(error, phase):
    if phase not in PHASES:
        raise ValueError("InvalidProcessPhase")
    reason = getattr(error, "reason_code", None)
    return {
        "schema_version": 1,
        "phase": phase,
        "exception_type": safe_exception_type(error),
        "reason_code": reason if reason in REASONS else "ExternalOrScopeFailure",
        "raw_exception_preserved": False,
    }
