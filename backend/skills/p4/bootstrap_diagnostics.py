"""Exclusive local diagnostics; Terraform output never crosses the public boundary."""

import json
import os
import subprocess
import uuid
from contextvars import ContextVar
from pathlib import Path

from interview_backend.deployment import DeploymentError

ACTIVE = ContextVar("bootstrap_diagnostic_context", default=None)

# Fixed classifications only. Never use regex sanitization of arbitrary exception text.
REASONS = frozenset(
    """
LocalBootstrapRequired BootstrapExecutionPrerequisitesUnconfirmed AwsEndpointOverrideForbidden
PrivateBootstrapPathsRequired InvalidBootstrapOperation InvalidBootstrapAttempt
InvalidLocalSettingsSyntax DuplicateLocalSetting LocalSettingsUnavailable InvalidDevAccount
InvalidDevRegion ConflictingDevAccount ConflictingDevRegion ConflictingCredentialProfile
BootstrapInputsUnavailable ExplicitBootstrapInputsRequired VerifiedOidcSubjectsRequired
OidcProviderMismatch InvalidSesIdentity BootstrapConfigurationInvalid TerraformSettingConflict
UnexpectedTerraformVariable TerraformWorkspaceForbidden TerraformArgumentsForbidden
TerraformRuntimeOverrideForbidden TerraformAutoloadForbidden CleanCommittedMainRequired
RepositoryMismatch BootstrapRunRequired BootstrapConfigurationChanged
BootstrapBackendConfigurationConflict BootstrapApplyAlreadyAttempted
BootstrapApplyConfirmationRequired BootstrapMigrationAlreadyAttempted
BootstrapMigrationAttemptRequired BootstrapOperationLocked BootstrapLockReleaseFailed
BootstrapOperationAndLockReleaseFailed TerraformVersionMismatch BootstrapPlanBindingMismatch
ApprovedPlanHashRequired BootstrapAttemptSuperseded NewBootstrapAttemptRequired
BootstrapReplanNotAllowed BootstrapStateDestinationUnconfirmed BootstrapRemoteStateUnbound
BootstrapRemoteStateMissing BootstrapBackupMismatch BootstrapStateUnbound TerraformStateInvalid
BootstrapReadbackFailed BootstrapOutputInvalid BootstrapMigrationResumeNotAllowed
MigratedStateReadbackFailed MigratedStateMismatch BootstrapReceiptMismatch VersionedStateRequired
BootstrapStateBucketMismatch BootstrapStateRegionMismatch BootstrapStateAlreadyExists
AwsIdentityUnavailable AwsAccountMismatch ShortTermCredentialsRequired SsoTokenUnavailable
AwsConnectionFailed AwsAuthenticationRejected CredentialRetrievalFailed PartialCredentials
MixedCredentialSources CredentialProfileConflict TerraformOperationFailed TerraformNonZeroExit
TerraformStartFailed DiagnosticStorageFailed DiagnosticPermissionsFailed
BootstrapSourceTransitionInvalid BootstrapAttemptIncomplete UnexpectedBootstrapFailure
""".split()
)


class BootstrapFailure(DeploymentError):
    """Safe metadata only; no original exception or subprocess output is retained."""

    def __init__(self, reason, stage, *, return_code=None, diagnostic_id=None):
        reason = reason if reason in REASONS else "UnexpectedBootstrapFailure"
        super().__init__(reason, reason_code=reason)
        self.stage = stage
        self.return_code = return_code
        self.diagnostic_id = diagnostic_id


def stage(value):
    context = ACTIVE.get()
    if context is not None:
        context["stage"] = value


def safe_failure(error, context):
    if isinstance(error, BootstrapFailure):
        failure = error
    else:
        reason = (
            getattr(error, "reason_code", str(error))
            if isinstance(error, DeploymentError)
            else "UnexpectedBootstrapFailure"
        )
        failure = BootstrapFailure(reason, context["stage"])
    if context.get("diagnostics"):
        failure.diagnostic_id = context["diagnostics"].path.name
    return failure


def no_links(path):
    if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise BootstrapFailure("DiagnosticPermissionsFailed", "diagnostic_storage")


def windows_private(path):
    """Set and verify a protected DACL using SIDs, without exposing its contents."""
    script = r"""
$ErrorActionPreference = 'Stop'
$p = $env:P4_DIAGNOSTIC_DIRECTORY
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = New-Object System.Security.AccessControl.DirectorySecurity
$acl.SetOwner($sid)
$acl.SetAccessRuleProtection($true, $false)
$ids = @($sid.Value, 'S-1-5-18', 'S-1-5-32-544') | Select-Object -Unique
foreach ($id in $ids) {
    $s = New-Object System.Security.Principal.SecurityIdentifier($id)
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $s, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
}
(Get-Item -LiteralPath $p).SetAccessControl($acl)
$actual = Get-Acl -LiteralPath $p
if (-not $actual.AreAccessRulesProtected) { throw 'invalid' }
$owner = $actual.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
if ($owner -ne $sid.Value) { throw 'invalid' }
$rules = @($actual.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
if ($rules.Count -ne $ids.Count) { throw 'invalid' }
foreach ($id in $ids) {
    $r = @($rules | Where-Object { $_.IdentityReference.Value -eq $id })
    if ($r.Count -ne 1 -or $r[0].IsInherited -or $r[0].AccessControlType -ne 'Allow' -or
        $r[0].FileSystemRights -ne 'FullControl' -or
        $r[0].InheritanceFlags -ne 'ContainerInherit,ObjectInherit' -or
        $r[0].PropagationFlags -ne 'None') { throw 'invalid' }
}
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env=dict(os.environ) | {"P4_DIAGNOSTIC_DIRECTORY": str(path)},
        capture_output=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise BootstrapFailure("DiagnosticPermissionsFailed", "diagnostic_storage")


def secure_directory(path):
    no_links(path)
    path.mkdir(mode=0o700, exist_ok=False)
    if os.name == "nt":
        windows_private(path)
    else:
        path.chmod(0o700)
        if path.stat().st_mode & 0o777 != 0o700 or path.stat().st_uid != os.getuid():
            raise BootstrapFailure("DiagnosticPermissionsFailed", "diagnostic_storage")


def exclusive(path):
    no_links(path)
    return os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb")


class Diagnostics:
    def __init__(self, directory, operation, attempt, source_sha):
        self.path = None
        self.sequence = 0
        try:
            parent = Path(directory) / "diagnostics"
            no_links(parent)
            parent.mkdir(mode=0o700, exist_ok=True)
            self.path = parent / uuid.uuid4().hex
            secure_directory(self.path)
            self.record(
                "context.json",
                {
                    "schema_version": 1,
                    "operation": operation,
                    "attempt": attempt,
                    "source_sha": source_sha,
                },
            )
        except BootstrapFailure:
            raise
        except OSError:
            raise BootstrapFailure("DiagnosticStorageFailed", "diagnostic_storage") from None

    def record(self, name, value):
        try:
            with exclusive(self.path / name) as stream:
                stream.write(json.dumps(value, sort_keys=True).encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
        except OSError:
            raise BootstrapFailure("DiagnosticStorageFailed", "diagnostic_storage") from None

    def run(self, command, *, cwd, env):
        operation = command[1]
        if operation not in {"version", "init", "plan", "show", "apply", "output", "state"}:
            raise BootstrapFailure("InvalidBootstrapOperation", "prerequisites")
        stage_name = {"output": "readback", "state": "migration_state_pull"}.get(
            operation, "terraform_" + operation
        )
        if operation == "init" and any(c in command for c in ("-migrate-state", "-reconfigure")):
            stage_name = "migration_init"
        stage(stage_name)
        self.sequence += 1
        prefix = f"{self.sequence:03d}-{stage_name.replace('_', '-')}"
        out_name, err_name = prefix + ".stdout.private", prefix + ".stderr.private"
        try:
            with exclusive(self.path / out_name) as out, exclusive(self.path / err_name) as err:
                try:
                    result = subprocess.run(
                        command, cwd=cwd, env=env, stdout=out, stderr=err, check=False
                    )
                except OSError:
                    self.record(
                        prefix + "-result.json",
                        {"stage": stage_name, "reason_code": "TerraformStartFailed"},
                    )
                    raise BootstrapFailure("TerraformStartFailed", stage_name) from None
                out.flush()
                err.flush()
                os.fsync(out.fileno())
                os.fsync(err.fileno())
            self.record(
                prefix + "-result.json",
                {
                    "stage": stage_name,
                    "return_code": result.returncode,
                    "status": "failed" if result.returncode else "success",
                    "stdout": out_name,
                    "stderr": err_name,
                },
            )
            if result.returncode:
                raise BootstrapFailure(
                    "TerraformNonZeroExit", stage_name, return_code=result.returncode
                )
            return (self.path / out_name).read_bytes()
        except OSError:
            raise BootstrapFailure("DiagnosticStorageFailed", "diagnostic_storage") from None


def public_failure(error):
    reason = error.reason_code
    compatibility = {
        "TerraformNonZeroExit": "TerraformOperationFailed",
        "TerraformStartFailed": "TerraformOperationFailed",
    }
    legacy = {
        "BootstrapApplyAlreadyAttempted": "inspect",
        "BootstrapMigrationAlreadyAttempted": "inspect",
        "BootstrapOperationLocked": "stop",
        "TerraformOperationFailed": "inspect",
        "BootstrapReadbackFailed": "verify",
        "MigratedStateReadbackFailed": "inspect",
        "BootstrapBackupMismatch": "stop",
        "BootstrapStateDestinationUnconfirmed": "inspect",
    }
    failure = compatibility.get(reason, reason)
    return {
        "status": "failed",
        "failure": failure if failure in legacy else "BootstrapStateMigrationFailed",
        "next_operation": legacy.get(failure, "stop"),
        "stage": error.stage,
        "reason_code": reason,
        "diagnostic_id": error.diagnostic_id,
        **({"return_code": error.return_code} if error.return_code is not None else {}),
    }
