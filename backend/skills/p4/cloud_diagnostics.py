"""Finite public failure codes. Never publish exception text or resource values.

The byte-identical module is used by the Windows controller to parse annotations.
Import performs no IO. Diagnostics are informational and cannot grant execution.
"""

import re

STAGES = frozenset(
    (
        "entry",
        "toolchain",
        "private-controls",
        "audit-isolation",
        "checkout",
        "parent-binding",
        "configuration-binding",
        "recipient-binding",
        "descriptor",
        "deploy-import",
        "deploy-preflight",
        "authorization",
        "state-before",
        "source-check",
        "state-preflight",
        "artifact-build",
        "artifact-binding",
        "artifact-upload",
        "terraform-plan",
        "plan-transport",
        "state-after",
        "independent-plan-audit",
        "public-receipt",
        "complete",
    )
)
REASONS = frozenset(
    (
        "ExternalOrScopeFailure",
        "Interrupted",
        "ModuleLoadFailed",
        "CloudPythonVersionMismatch",
        "CloudToolMissing",
        "CloudToolQualificationFailed",
        "CloudTerraformVersionMismatch",
        "CloudUvVersionMismatch",
        "PrivateParentSymlink",
        "RunnerOwnerMismatch",
        "PrivateDirectoryModeMismatch",
        "PrivateFileModeMismatch",
        "NoFollowQualificationFailed",
        "CloudAuditIsolationUnavailable",
        "SourceSymlinkRejected",
        "CloudCleanSourceRequired",
        "CloudCheckoutShaMismatch",
        "CloudParentHashMismatch",
        "CloudParentProfileMismatch",
        "CloudParentWindowInvalid",
        "CloudTargetMismatch",
        "CloudRepositoryMismatch",
        "CloudRunMismatch",
        "CloudRunIdentityMissing",
        "CloudSourceMismatch",
        "CloudExecutionGateClosed",
        "CloudSubjectMismatch",
        "CloudLimitsMismatch",
        "CloudCredentialLimitsMismatch",
        "CloudRiskDispositionMissing",
        "CloudBaselineMismatch",
        "ApprovedBaseNotAncestor",
        "ExistingSecretConfigurationMismatch",
        "ExistingRecipientMismatch",
        "SessionPolicySizeExceeded",
        "JobClockMissing",
        "CloudCredentialTimeInsufficient",
        "CloudCredentialsExpiring",
        "CloudRoleScopeMismatch",
        "CloudSdkLimit",
        "CloudSdkLimitOrRetransmission",
        "StateOrLiveReadbackChanged",
        "IndependentPlanAuditFailed",
        "IndependentPlanAuditRejected",
        "CloudPlanFailed",
        "CloudImportantWarningUnclassified",
        "CloudOutputSizeExceeded",
        "ClosedExistingStateRequired",
        "ClosedInitialDeploymentRequired",
        "InvalidOperation",
        "ExplicitDeploymentInputsRequired",
        "ApprovedArtifactDigestRequired",
        "UnexpectedTerraformVariable",
        "InvalidRunIdentity",
        "PlanFirstAttemptRequired",
        "ApprovedArtifactDigestMismatch",
        "StateChangedBeforeArtifactUpload",
        "ArtifactOverrideForbidden",
        "VersionedArtifactRequired",
        "ArtifactReadbackMismatch",
        "PlanObjectSizeLimitExceeded",
        "ArtifactVersionMismatch",
        "ArtifactEncryptionMismatch",
        "ArtifactSizeMismatch",
        "PlanApprovalExpiredOrInsufficientTime",
        "PlanApprovalStopped",
        "PlanApprovalChangedDuringExecution",
        "PlanAuthenticationLimitExceeded",
        "PlanAuthenticationScopeMismatch",
        "PlanCredentialSourceConflict",
        "PlanS3ScopeOrCountMismatch",
        "PlanProcessDeadlineStop",
        "PlanProcessFailed",
        "PlanProcessDiagnosticFailed",
        "PlanProcessJournalFailed",
        "PlanApprovalAlreadyConsumed",
        "ApprovalRunHistoryIncomplete",
        "ApprovalRunHistoryChanged",
        "FormalPlanAlreadyStarted",
        "AwsAccountMismatch",
        "EvidenceRecipientMismatch",
        "EvidenceRecipientValidityMismatch",
        "EvidenceEncryptionUnavailable",
        "StateClosedLockOrLiveMismatch",
        "PinnedDevStateIdentityMismatch",
        "PinnedCurrentVersionProofMissing",
        "StateLockExists",
        "AccessDenied",
        "AccessDeniedException",
        "ExpiredToken",
        "ExpiredTokenException",
        "ActiveStateLock",
        "StateLockReadUnavailable",
        "PinnedDevStateChanged",
        "CloudActorMismatch",
        "ReadbackImplementationContractFailure",
        "LiveDeploymentReadbackFailed",
        "StateManifestContractRejected",
        "StateManifestConfigurationContractMismatch",
        "NormalizedConfigurationContractMismatch",
        "AwsOperationForbidden",
        "UnknownReadScopeParameter",
        "ExactS3VersionRequired",
        "CleanCommittedSourceRequired",
        "GitHubControlPlaneUnavailable",
        "CurrentMainRevisionRequired",
        "PlanApprovalScopeMismatch",
        "InvalidPlanApprovalPackage",
        "PlanApprovalPackageRequired",
        "PlanApprovalHashMismatch",
        "PlanApprovalDeadlineMismatch",
        "PlanJobStartTimeRequired",
    )
)
CURRENT = "entry"
REPORTED = False
CURRENT_COMMAND = "unknown"


def process_kind(kind):
    global CURRENT_COMMAND
    CURRENT_COMMAND = kind if kind in {"version", "init", "plan", "show", "build"} else "unknown"


def checkpoint(stage):
    global CURRENT
    if stage not in STAGES:
        raise ValueError("InvalidDiagnosticStage")
    CURRENT = stage


def code(error):
    if isinstance(error, (KeyboardInterrupt, SystemExit)):
        return "Interrupted"
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        return "ModuleLoadFailed"
    # Access only known finite fields; never stringify an arbitrary SDK exception.
    for name in ("reason_code", "reason"):
        value = getattr(error, name, None)
        if type(value) is str and value in REASONS:
            return value
    # ValueError/RuntimeError are also raised with fixed literals by pinned code.
    local_refusal = (
        type(error).__name__ == "Refusal" and type(error).__module__ == "cloud_controller_core"
    )
    if (type(error) in (ValueError, RuntimeError) or local_refusal) and len(error.args) == 1:
        value = error.args[0]
        if type(value) is str and value in REASONS:
            return value
    return "ExternalOrScopeFailure"


def emit(error):
    global REPORTED
    if not REPORTED:
        REPORTED = True
        # Every character comes from finite, source-pinned literals.
        try:
            reason = code(error)
        except BaseException:  # noqa: BLE001 - never expose a hostile exception property
            reason = "ExternalOrScopeFailure"
        stage = CURRENT if CURRENT in STAGES else "entry"
        # Separate artifact file avoids dependence on log/annotation masking.
        # Saving can never turn the enclosing failure into success.
        import os

        if os.environ.get("P4_CLOUD_FAILURE_JSON") == "true":
            try:
                from cloud_failure_json import persist

                persist(stage, reason, CURRENT_COMMAND, error)
            except BaseException:  # noqa: BLE001 - suppress private exception chains
                try:
                    print("P4FailureDiagnosticUnavailable", flush=True)
                except BaseException:  # noqa: BLE001, S110 - broken output cannot leak chaining
                    pass
        try:
            print(
                f"::error title=P4_STAGE2_DIAGNOSTIC::P4D1|stage={stage}|reason={reason}",
                flush=True,
            )
        except BaseException:  # noqa: BLE001, S110 - suppress private exception chaining
            # A diagnostic IO failure must not reveal the original exception
            # through Python's implicit exception chaining.
            pass


def parse(message):
    if type(message) is not str:
        return None
    match = re.fullmatch(r"P4D1\|stage=([a-z-]+)\|reason=([A-Za-z0-9]+)", message)
    if match and match[1] in STAGES and match[2] in REASONS:
        return {"stage": match[1], "reason_code": match[2]}
    return None
