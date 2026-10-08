"""Concrete manifest/receipt audit and Cognito adapter, separated by provider scenario."""

import getpass
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from closure_adapter import bind_enablement, require_snapshot
from closure_aws import TerraformAWS


def validate_scenario(approval, environment):
    scenario = approval.get("scenario", "fake_normal")
    expected = {
        "fake_normal": ("fake", None, 0),
        "fake_three": ("fake", "coaching_three", 3),
        "fake_failure": ("fake", "provider_failure", 0),
        "openai": ("openai", None, approval["expected_rounds"]),
    }
    if scenario not in expected:
        raise ValueError("SeparateApprovedScenarioRequired")
    provider, fake, rounds = expected[scenario]
    if (
        approval["provider"] != provider
        or environment.get("INTERVIEW_FAKE_SCENARIO") != fake
        or approval["expected_rounds"] != rounds
    ):
        raise ValueError("ScenarioManifestMismatch")
    if fake:
        allowed = set(environment.get("INTERVIEW_VALIDATION_OWNER_HASHES", "").split(","))
        if environment.get("INTERVIEW_VALIDATION_ONLY") != "true" or allowed != {
            hashlib.sha256(approval["subjects"]["USER_A"].encode()).hexdigest()
        }:
            raise ValueError("ExactValidationOwnerRequired")


class SuiteAudit:
    def __init__(self, close):
        self.close = close
        self.before_cursors = None
        self.driver = None

    def __call__(self, manifest, live_approval):
        raw = self.close.approval_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != self.close.approval_sha256:
            raise ValueError("ClosureApprovalHashMismatch")
        closure_approval = json.loads(raw)
        receipt = json.loads(Path(self.close.receipt_path).read_bytes())
        _, active = bind_enablement(
            closure_approval,
            receipt,
            Path(self.close.inputs_path).read_bytes(),
            Path(self.close.manifest_path).read_bytes(),
            Path(self.close.enablement_plan_path).read_bytes(),
        )
        if (
            active != manifest
            or live_approval.get("closure_approval_sha256") != self.close.approval_sha256
        ):
            raise ValueError("ActiveLiveBindingMismatch")
        driver = TerraformAWS(self.close.terraform_root, closure_approval, self.close.environment)
        self.driver = driver
        require_snapshot(driver.snapshot(manifest), receipt, manifest)
        if self.before_cursors is None:
            from runtime_receipts import cursor_revisions

            self.before_cursors = cursor_revisions(
                driver.client("dynamodb"), manifest["table_name"]
            )
        if live_approval["admin_writes"]:
            now = datetime.now(UTC)
            if (
                not datetime.fromisoformat(live_approval["window_start"])
                <= now
                < datetime.fromisoformat(live_approval["window_end"])
            ):
                raise ValueError("ApprovedExclusiveWindowExpired")
            # Shared bank writes require all enabled users to be dedicated approved users.
            users = (
                driver.client("cognito-idp")
                .get_paginator("list_users")
                .paginate(UserPoolId=manifest["user_pool_id"])
            )
            enabled = {
                a["Value"]
                for page in users
                for u in page["Users"]
                if u.get("Enabled")
                for a in u["Attributes"]
                if a["Name"] == "sub"
            }
            if enabled != set(live_approval["subjects"].values()):
                raise ValueError("ExclusiveTestUsersRequired")
        return True

    def observe_transactions(self, manifest, approval, run):
        from runtime_receipts import collect

        collect(self.driver.client("dynamodb"), manifest, approval, run, self.before_cursors)


class CognitoAuthenticate:
    def __init__(self, client):
        self.client = client

    def __call__(self, label, manifest):
        from coaching_binding import authenticate_existing

        email = getpass.getpass(f"Approved {label} email (hidden): ")
        return authenticate_existing(self.client, manifest, email)


def observe_runtime(client, manifest, start, end, run, *, exclusive_window):
    """Read exact function/alias metrics; invocation is not a ConditionCheck proof."""
    for label, role, alias in (
        ("worker", "worker", "live"),
        ("streams", "dispatcher", "streams"),
        ("recovery", "dispatcher", "recovery"),
    ):
        if not exclusive_window:
            run.record(label + "-invocation-observed", "not_run")
            continue
        name = "ai-interview-dev-" + role
        metrics = client.get_metric_statistics(
            Namespace="AWS/Lambda",
            MetricName="Invocations",
            Dimensions=[
                {"Name": "FunctionName", "Value": name},
                {"Name": "Resource", "Value": name + ":" + alias},
            ],
            StartTime=start,
            EndTime=end,
            Period=60,
            Statistics=["Sum"],
        )
        count = sum(p["Sum"] for p in metrics["Datapoints"])
        run.record(label + "-invocation-observed", "passed" if count > 0 else "not_run")
    # Separate approved transaction/fault scenarios are required for these.
    run.record("IAM-ConditionCheck-runtime-case", "not_run")
    run.record("Recovery-reclaimed-transaction-case", "not_run")
