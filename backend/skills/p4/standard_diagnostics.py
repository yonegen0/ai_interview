"""Finite standard-CI diagnostics, independent of admission and private evidence.

No exception text, command arguments, State, identifiers or SDK responses leave
this module. Unknown values stay unknown. Import performs no IO.
"""

import json
from contextvars import ContextVar

from plan_process_diagnostics import safe_exception_type

CURRENT = ContextVar("standard_failure_diagnostic", default=None)
STAGES = frozenset(
    {
        "preflight",
        "authorization",
        "source-check",
        "state-preflight",
        "artifact-binding",
        "artifact-build",
        "artifact-upload",
        "terraform-execution",
        "terraform-version",
        "terraform-identity",
        "state-read",
        "live-readback",
        "live-api",
        "live-worker",
        "live-streams",
        "live-scheduler",
        "live-stage",
        "readiness-readback",
        "terraform-init",
        "terraform-plan",
        "terraform-show",
        "plan-audit",
        "post-plan-state-read",
        "plan-transport",
    }
)
REASONS = frozenset(
    {
        "PlanApprovalHashMismatch",
        "PlanApprovalAlreadyConsumed",
        "PlanApprovalExpiredOrInsufficientTime",
        "PlanApprovalChangedDuringExecution",
        "PlanApprovalStopped",
        "ApprovalRunHistoryIncomplete",
        "ApprovalRunHistoryChanged",
        "OidcAuthenticationFailed",
        "PlanAuthenticationScopeMismatch",
        "PlanAuthenticationLimitExceeded",
        "PlanCredentialSourceConflict",
        "TerraformVersionMismatch",
        "StateReadbackChanged",
        "StateChangedDuringPlan",
        "StageRecoveryScopeMismatch",
        "StageRecoverySdkBudgetExceeded",
        "StageRecoveryHttpBudgetOrRetryRejected",
        "PlanS3ScopeOrCountMismatch",
        "PlanProcessFailed",
        "PlanProcessDeadlineStop",
        "PlanProcessDiagnosticFailed",
        "PlanProcessJournalFailed",
        "FormalPlanAlreadyStarted",
        "EvidenceRecipientMismatch",
        "EvidenceEncryptionUnavailable",
        "GitHubControlPlaneUnavailable",
        "GitHubEnvironmentVariablesReadDenied",
    }
)
COMMANDS = frozenset({"version", "init", "plan", "show", "build"})


class Diagnostic:
    def __init__(self):
        self.stage = "preflight"
        self.command = "unknown"
        self.started = False
        self.exited = False

    def projection(self, error):
        reason = "ExternalOrScopeFailure"
        try:
            candidate = getattr(error, "reason_code", None)
            if type(candidate) is str and candidate in REASONS:
                reason = candidate
            elif type(error) in (ValueError, RuntimeError) and len(error.args) == 1:
                candidate = error.args[0]
                if type(candidate) is str and candidate in REASONS:
                    reason = candidate
        except BaseException:  # noqa: BLE001 - hostile properties cannot leak exceptions
            pass
        return {
            "schema_version": 1,
            "failure_stage": self.stage if self.stage in STAGES else "unknown",
            "failure_class": safe_exception_type(error),
            "reason_code": reason,
            "process_started": self.started is True,
            "process_exit_observed": self.exited is True,
            "terraform_command_kind": self.command if self.command in COMMANDS else "unknown",
        }

    def emit(self, error):
        try:
            print("P4_STANDARD_FAILURE " + json.dumps(self.projection(error), sort_keys=True))
        except BaseException:  # noqa: BLE001, S110 - a broken sink never prints exception chains
            pass


def checkpoint(stage):
    current = CURRENT.get()
    if current is not None:
        current.stage = stage if stage in STAGES else "unknown"


def process_event(kind, event):
    current = CURRENT.get()
    if current is None:
        return
    if event == "admission":
        current.command = kind if kind in COMMANDS else "unknown"
        current.started = current.exited = False
        if kind in {"version", "init", "plan", "show"}:
            checkpoint("terraform-" + kind)
    elif event == "launched":
        current.started = True
    elif event == "exit-observed":
        current.exited = True
