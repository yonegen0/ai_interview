"""Plan-only approval binding, deadline admission and append-only private journal.

No credentials or raw API exceptions are written. GitHub run history is the
durable cross-run consumption record; local journals additionally reject process
restarts. Missing/incomplete history is a refusal, never permission to retry.
"""

import hashlib
import json
import math
import os
import re
import signal
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from approval_validity import validate_window
from plan_evidence import certificate_der, validate_recipient
from plan_process_diagnostics import safe_exception_type, summarize_exception, summarize_failure
from process_output_evidence import seal

from interview_backend.deployment import DeploymentError

START = "<!-- P4_PLAN_AUTHORIZATION_START -->\n```json\n"
END = "\n```\n<!-- P4_PLAN_AUTHORIZATION_END -->"
LIMITS = {"plan": 3, "artifact": 2}
REPOSITORY = "yonegen0/ai_interview"
CLEANUP_SECONDS = 120
BUDGETS = {"oidc": 20, "sts": 25, "put": 60, "build": 600, "init": 300, "plan": 1200}
CURRENT = None


def utc(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|\+00:00)", value
    ):
        raise DeploymentError("ApprovalUtcDeadlineRequired")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise DeploymentError("InvalidApprovalDeadline") from None


def canonical_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def session_policy(expiry):
    """Intersect existing Role permissions; explicitly deny at server expiry.

    This is a temporary session restriction, not an IAM Role/policy mutation.
    Normal unlock must finish before expiry. Unknown locks are never repaired.
    """
    utc(expiry)
    if os.environ.get("P4_CLOUD_ACTIVE") == "true":
        from cloud_ci import policy

        return policy(expiry)
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "PreserveExistingRoleCeiling",
                "Effect": "Allow",
                "Action": "*",
                "Resource": "*",
            },
            {
                "Sid": "AbsoluteApprovalExpiry",
                "Effect": "Deny",
                "Action": "*",
                "Resource": "*",
                "Condition": {"DateGreaterThanEquals": {"aws:CurrentTime": expiry}},
            },
        ],
    }


def load(environment):
    raw = environment.get("P4_PLAN_APPROVAL_PACKAGE", "")
    digest = environment.get("P4_PLAN_APPROVAL_SHA256", "")
    if not raw or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise DeploymentError("PlanApprovalPackageRequired")
    if len(raw.encode()) > 60000 or hashlib.sha256(raw.encode()).hexdigest() != digest:
        raise DeploymentError("PlanApprovalHashMismatch")
    if raw.count(START) != 1 or raw.count(END) != 1:
        raise DeploymentError("PlanApprovalDescriptorRequired")
    try:

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError
                result[key] = value
            return result

        package = json.loads(raw.split(START)[1].split(END)[0], object_pairs_hook=unique)
        expiry = utc(package["expires_at_utc"])
        if "operator_execution" in package:
            validate_window(package)
        if environment.get("P4_PLAN_APPROVAL_EXPIRES_AT") != package["expires_at_utc"]:
            raise DeploymentError("PlanApprovalDeadlineMismatch")
        integer_fields = ("schema_version", "duration_seconds", "s3_put_limit", "cleanup_seconds")
        if any(type(package[key]) is not int for key in integer_fields) or any(
            type(value) is not int
            for key in ("oidc_limits", "sts_limits", "operation_budgets_seconds")
            for value in package[key].values()
        ):
            raise DeploymentError("PlanApprovalScopeMismatch")
        if (
            package["schema_version"] != 1
            or package["operation"] != "plan"
            or package["execution_ready"] is not True
            or package["repository"] != "yonegen0/ai_interview"
            or package["source_sha"] != environment.get("GITHUB_SHA")
            or not re.fullmatch(r"[0-9a-f]{40}", package["source_sha"])
            or package["account_id"] != environment.get("AWS_DEV_ACCOUNT_ID")
            or package["region"] != "ap-northeast-1"
            or package["region"] != environment.get("AWS_REGION")
            or package["oidc_subject"] != environment.get("P4_OIDC_SUBJECT")
            or not package["oidc_subject"]
            or package["oidc_limits"] != LIMITS
            or package["sts_limits"] != LIMITS
            or package["duration_seconds"] != 3600
            or package["artifact_sha256"] != environment.get("P4_PACKAGE_SHA256")
            or not re.fullmatch(r"[0-9a-f]{64}", package["artifact_sha256"])
            or package["configuration_sha256"]
            != canonical_hash(json.loads(environment["P4_DEPLOY_INPUTS"]))
            or package["s3_put_limit"] != 6
            or package["cleanup_seconds"] != CLEANUP_SECONDS
            or package["deadline_policy"] != "no-new-operations;cleanup-before-expiry"
            or package["session_policy_sha256"]
            != canonical_hash(session_policy(package["expires_at_utc"]))
            or package["operation_budgets_seconds"] != BUDGETS
            or package["evidence_recipient_sha256"]
            != hashlib.sha256(certificate_der(environment)).hexdigest()
            or environment.get("GITHUB_RUN_ATTEMPT") != "1"
            or environment.get("GITHUB_REF") != "refs/heads/main"
            or environment.get("GITHUB_REPOSITORY") != package["repository"]
            or not re.fullmatch(r"[0-9]+", environment.get("GITHUB_RUN_ID", ""))
        ):
            raise DeploymentError("PlanApprovalScopeMismatch")
    except DeploymentError:
        raise
    except Exception:
        raise DeploymentError("InvalidPlanApprovalPackage") from None
    return package, expiry, digest


def verify_run_history(package_hash, environment, github_get):
    """First matching dispatch consumes approval, including queued/failed runs.

    Read *all* pages, without status/head-SHA filters that could hide a previous
    failure. GitHub's 1000-result ceiling is a refusal, not partial proof.
    Deleting/renaming approval run records is forbidden by the approval scope.
    """
    title = f"P4 plan approval-{package_hash}"
    workflow = (
        "p4-compound.yml" if environment.get("P4_COMPOUND_ACTIVE") == "true" else "p4-deploy.yml"
    )
    if environment.get("P4_CLOUD_ACTIVE") == "true":
        title = f"P4 cloud plan approval-{environment['P4_CLOUD_PARENT_SHA256']}"
        workflow = "p4-cloud-plan.yml"
    matches = []
    total = None
    seen = set()
    for page in range(1, 11):
        data = github_get(
            f"actions/workflows/{workflow}/runs?event=workflow_dispatch&per_page=100&page={page}",
            environment,
        )
        if total is None:
            total = data.get("total_count")
            if type(total) is not int or not 0 < total < 1000:
                raise DeploymentError("ApprovalRunHistoryIncomplete")
        elif data.get("total_count") != total:
            raise DeploymentError("ApprovalRunHistoryChanged")
        for run in data.get("workflow_runs", []):
            identity = run.get("id")
            if type(identity) is not int or identity in seen:
                raise DeploymentError("ApprovalRunHistoryIncomplete")
            seen.add(identity)
            if run.get("display_title") == title:
                matches.append(run)
        if len(seen) >= total:
            break
    if len(seen) != total or not matches:
        raise DeploymentError("ApprovalRunHistoryIncomplete")
    first = min(matches, key=lambda item: item["id"])
    if (
        str(first["id"]) != environment["GITHUB_RUN_ID"]
        or first.get("run_attempt") != 1
        or first.get("head_sha") != environment["GITHUB_SHA"]
        or first.get("head_branch") != "main"
        or first.get("event") != "workflow_dispatch"
        or first.get("path") != ".github/workflows/" + workflow
        or first.get("repository", {}).get("full_name") != REPOSITORY
    ):
        raise DeploymentError("PlanApprovalAlreadyConsumed")
    return str(first["id"])


class Guard:
    def __init__(
        self,
        environment,
        directory,
        *,
        clock=None,
        monotonic=None,
        github_get=None,
        recipient_check=None,
    ):
        self.environment = environment
        self.package, self.expiry, self.digest = load(environment)
        self.clock = clock or (lambda: datetime.now(UTC))
        self.monotonic = monotonic or time.monotonic
        self.started = self.clock()
        self.tick = self.monotonic()
        self.latest = self.started
        self.stopped = False
        self.sequence = 0
        self.counts = {kind: {role: 0 for role in LIMITS} for kind in ("oidc", "sts")}
        self.puts = set()
        self.plan_started = False
        if "operator_execution" in self.package:
            issued, _ = validate_window(self.package)
            if self.started < issued:
                raise DeploymentError("PlanApprovalNotYetIssued")
        self.directory = Path(directory)
        # Exclusive namespace: process restarts cannot reset counters.
        self.directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.record(
            "approval-started",
            approval_sha256=self.digest,
            expires_at_utc=self.package["expires_at_utc"],
            run_id=environment["GITHUB_RUN_ID"],
            run_attempt="1",
        )
        try:
            self.check("ci-start", 0)
            self.job_started = float(environment["P4_PLAN_JOB_STARTED_MONOTONIC"])
            if not math.isfinite(self.job_started) or not 0 <= self.job_started <= self.tick:
                raise DeploymentError("PlanJobStartTimeRequired")
            self.check("ci-job-budget", 0)
            forbidden = (
                "AWS_PROFILE",
                "AWS_DEFAULT_PROFILE",
                "AWS_ROLE_ARN",
                "AWS_WEB_IDENTITY_TOKEN_FILE",
                "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
                "AWS_CONTAINER_CREDENTIALS_FULL_URI",
                "AWS_SHARED_CREDENTIALS_FILE",
                "AWS_CONFIG_FILE",
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "AWS_SESSION_TOKEN",
            )
            if any(environment.get(key) for key in forbidden) or any(
                key.startswith("AWS_ENDPOINT_URL") for key in environment
            ):
                raise DeploymentError("PlanCredentialSourceConflict")
            (recipient_check or validate_recipient)(environment, self.directory)
            if github_get is None:
                from github_control import github_json

                github_get = github_json
            verify_run_history(self.digest, environment, github_get)
            self.record("run-bound")
        except Exception as error:
            self.fail(error)
            raise

    def record(self, stage, **safe):
        self.sequence += 1
        record = {"stage": stage, "utc": self.clock().isoformat(), **safe}
        path = self.directory / f"{self.sequence:04d}.private.json"
        with path.open("x", encoding="utf-8") as stream:
            os.chmod(path, 0o600)
            json.dump(record, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())

    def fail(self, error):
        if not self.stopped:
            self.stopped = True
            # Do not include exception text: SDK/HTTP errors may contain secrets.
            reason = getattr(error, "reason_code", None)
            safe_reasons = {
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
            }
            self.record(
                "stopped-outcome-not-success",
                exception_type=safe_exception_type(error),
                reason_code=reason if reason in safe_reasons else "ExternalOrScopeFailure",
            )

    def remaining(self):
        observed = self.clock()
        projected = self.started + timedelta(seconds=max(0, self.monotonic() - self.tick))
        self.latest = max(self.latest, observed, projected)
        remaining = (self.expiry - self.latest).total_seconds()
        if hasattr(self, "job_started"):
            # Leave 3 minutes before the outer 55-minute cancellation for cleanup
            # and safe journal upload. The start marker precedes checkout/setup.
            remaining = min(remaining, self.job_started + 52 * 60 - self.monotonic())
        return remaining

    def check(self, stage, maximum_seconds):
        if self.stopped:
            raise DeploymentError("PlanApprovalStopped")
        try:
            _, _, current = load(self.environment)
            if current != self.digest:
                raise DeploymentError("PlanApprovalChangedDuringExecution")
            if self.remaining() <= maximum_seconds:
                raise DeploymentError("PlanApprovalExpiredOrInsufficientTime")
        except Exception as error:
            self.record("admission-refused", operation=stage)
            self.fail(error)
            raise

    def authenticate(self, kind, role, action):
        self.check(f"{kind}-{role}", BUDGETS[kind])
        if role not in LIMITS or self.counts[kind][role] >= LIMITS[role]:
            error = DeploymentError("PlanAuthenticationLimitExceeded")
            self.fail(error)
            raise error
        self.counts[kind][role] += 1
        return self.call(f"{kind}-{role}", action, count=self.counts[kind][role])

    def call(self, stage, action, **safe):
        self.record(stage + "-started", **safe)
        try:
            result = action()
            self.check(stage + "-completed", 0)
        except BaseException as error:
            self.fail(error)
            raise
        self.record(stage + "-completed", **safe)
        return result

    def put(self, bucket, key, action):
        self.check("s3-put", BUDGETS["put"])
        account = self.package["account_id"]
        run = self.environment["GITHUB_RUN_ID"]
        allowed = {f"lambda/{self.package['source_sha']}/{run}/1/app.zip"} | {
            f"plans/{run}/1/{name}"
            for name in (
                "dev.tfplan",
                "plan.json",
                "summary.json",
                "review.private.json",
                "envelope.json",
            )
        }
        if (
            bucket != f"ai-interview-artifacts-{account}-ap-northeast-1"
            or key not in allowed
            or key in self.puts
            or len(self.puts) >= 6
            or (key.endswith("/envelope.json") and len(self.puts) != 5)
        ):
            error = DeploymentError("PlanS3ScopeOrCountMismatch")
            self.fail(error)
            raise error
        self.puts.add(key)
        return self.call("s3-put", action, bucket=bucket, key=key, attempt=len(self.puts))

    def process(self, command, *, cwd, env, accepted=(0,)):
        """Bound execution; interrupt once, reserve cleanup before expiry.

        Never SIGKILL/force-unlock/re-plan. If graceful exit cannot be confirmed,
        preserve journal and fail; the outer 55-minute job limit remains a final
        safety device, so State/lock must be treated as unknown in that case.
        """
        terraform = command[:1] == ["terraform"]
        kind = command[1] if terraform and len(command) > 1 else "build"
        budget = BUDGETS.get(kind, 60)
        self.check("process-" + kind, budget + CLEANUP_SECONDS)
        if self.environment.get("P4_COMPOUND_ACTIVE") == "true":
            from compound_process import admit

            if (
                terraform
                and kind in {"init", "plan"}
                and (accepted != (0,) or any(type(c) is not int for c in accepted))
            ):
                raise DeploymentError("CompoundNonzeroExitAcceptanceForbidden")
            admit(command, self.directory)
        if kind == "plan":
            if self.plan_started:
                error = DeploymentError("FormalPlanAlreadyStarted")
                self.fail(error)
                raise error
            self.plan_started = True
        self.record("process-started", operation=kind, maximum_seconds=budget)
        process = None
        phase = "launch"
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            started = self.monotonic()
            phase = "wait"
            while True:
                if self.monotonic() - started >= budget or self.remaining() <= CLEANUP_SECONDS:
                    raise DeploymentError("PlanProcessDeadlineStop")
                try:
                    stdout, stderr = process.communicate(timeout=1)
                    break
                except subprocess.TimeoutExpired:
                    continue
            phase = "diagnostic"
            self.record("process-exit-observed", operation=kind, returncode=process.returncode)
            if process.returncode not in accepted:
                try:
                    diagnostic = summarize_failure(process.returncode, stdout, stderr)
                except Exception:
                    raise DeploymentError("PlanProcessDiagnosticFailed") from None
                evidence = seal(
                    stdout,
                    stderr,
                    getattr(self, "environment", None),
                    getattr(self, "directory", None),
                    self.remaining(),
                )
                self.record(
                    "process-failed",
                    operation=kind,
                    diagnostics=diagnostic,
                    encrypted_output_evidence=evidence,
                )
                raise DeploymentError("PlanProcessFailed")
            phase = "admission"
            if self.environment.get("P4_CLOUD_ACTIVE") == "true":
                from cloud_process_output import inspect

                inspect(self, kind, stdout, stderr)
            self.check("process-completed", 0)
            # Even success records the code; raw output never enters the journal.
            self.record("process-completed", operation=kind, returncode=process.returncode)
            return stdout
        except BaseException as error:
            journal_failed = False
            try:
                self.record(
                    "process-exception",
                    operation=kind,
                    diagnostics=summarize_exception(error, phase),
                )
                self.fail(error)
            except Exception:
                # A journal error must never bypass interruption or permit retry.
                self.stopped = True
                journal_failed = True
            if process is not None and process.poll() is None:
                try:
                    self.record("graceful-interrupt-requested", operation=kind)
                except Exception:
                    journal_failed = True
                process.send_signal(signal.SIGINT)
                try:
                    stdout, stderr = process.communicate(timeout=CLEANUP_SECONDS)
                    try:
                        self.record(
                            "process-exit-observed", operation=kind, returncode=process.returncode
                        )
                        self.record(
                            "interrupted-process-exited",
                            operation=kind,
                            returncode=process.returncode,
                            lock_state="unverified",
                        )
                        self.record(
                            "process-failed",
                            operation=kind,
                            diagnostics=summarize_failure(process.returncode, stdout, stderr),
                            encrypted_output_evidence=seal(
                                stdout,
                                stderr,
                                getattr(self, "environment", None),
                                getattr(self, "directory", None),
                                self.remaining(),
                            ),
                        )
                    except Exception:
                        journal_failed = True
                except subprocess.TimeoutExpired:
                    try:
                        self.record("process-and-lock-outcome-unknown", operation=kind)
                    except Exception:
                        journal_failed = True
            if journal_failed:
                raise DeploymentError("PlanProcessJournalFailed") from None
            raise


def initialize(environment, directory):
    global CURRENT
    if CURRENT is not None:
        raise DeploymentError("PlanAuthorizationProcessAlreadyStarted")
    CURRENT = Guard(environment, directory)
    return CURRENT


def required_guard():
    if CURRENT is None:
        raise DeploymentError("PlanAuthorizationNotInitialized")
    return CURRENT


def active_guard():
    if CURRENT is not None or os.environ.get("P4_OPERATION") == "plan":
        return required_guard()
    return None
