"""Immutable parent-approved, hosted Linux, Plan-only entry point.

Import performs no IO. A derived descriptor is an execution record under the
parent approval, never a new user approval or a fabricated consent receipt.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

PARENT = None
SESSIONS = {}
READER = None
BEFORE = None
WIRE_COUNT = 0


def canonical(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "DuplicateField")
        result[key] = value
    return result


def validate_parent(raw, digest, env, tree, now=None):
    need(
        len(raw.encode()) < 48000
        and re.fullmatch("[a-f0-9]{64}", digest or "")
        and hashlib.sha256(raw.encode()).hexdigest() == digest,
        "CloudParentHashMismatch",
    )
    p = json.loads(raw, object_pairs_hook=unique)
    need(
        p["schema"] == 1
        and p["profile"] == "hosted-linux-plan-only-v1"
        and p["execution_ready"] is True
        and p["apply"] is False,
        "CloudParentProfileMismatch",
    )
    issued = datetime.fromisoformat(p["issued_at_utc"].replace("Z", "+00:00"))
    expiry = datetime.fromisoformat(p["expires_at_utc"].replace("Z", "+00:00"))
    now = now or datetime.now(UTC)
    need(
        issued.utcoffset() == expiry.utcoffset() == timedelta(0)
        and expiry - issued == timedelta(seconds=259200)
        and issued <= now
        and now + timedelta(minutes=60) < expiry,
        "CloudParentWindowInvalid",
    )
    need(
        p["repository"] == "yonegen0/ai_interview"
        and p["account_id"] == "835384817629"
        and p["region"] == "ap-northeast-1",
        "CloudTargetMismatch",
    )
    need(
        env.get("GITHUB_REPOSITORY") == p["repository"]
        and env.get("GITHUB_REPOSITORY_ID") == "1361325921"
        and env.get("GITHUB_REPOSITORY_OWNER_ID") == "76547980",
        "CloudRepositoryMismatch",
    )
    need(
        env.get("GITHUB_REF") == "refs/heads/main"
        and env.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and env.get("GITHUB_RUN_ATTEMPT") == "1"
        and env.get("GITHUB_ACTOR_ID") == "76547980"
        and env.get("GITHUB_ACTOR") == "yonegen0",
        "CloudRunMismatch",
    )
    need(
        re.fullmatch("[0-9]+", env.get("GITHUB_RUN_ID", ""))
        and re.fullmatch("[a-f0-9]{40}", env.get("GITHUB_SHA", "")),
        "CloudRunIdentityMissing",
    )
    need(
        p["source_tree"] == tree and p["base_commit"] == "4a31727a7c2eb361c0e9609bf4e51be00524547a",
        "CloudSourceMismatch",
    )
    need(
        env.get("AWS_DEV_ACCOUNT_ID") == p["account_id"]
        and env.get("AWS_REGION") == p["region"]
        and env.get("P4_AWS_EXECUTION_READY") == "true",
        "CloudExecutionGateClosed",
    )
    need(
        env.get("P4_OIDC_SUBJECT")
        == "repo:yonegen0@76547980/ai_interview@1361325921:environment:dev",
        "CloudSubjectMismatch",
    )
    need(
        p["plan_max"] == p["dispatch_max"] == p["run_attempt"] == 1
        and p["artifact_sha256"]
        == "cc067d535699792204e4ec038b45a19b0d018536355a49b4e0f8ce4377a8ef6d",
        "CloudLimitsMismatch",
    )
    need(
        p["s3_put_max"] == 6
        and p["sdk_request_max"] == 1500
        and p["oidc_sts_each"] == {"plan": 1, "artifact": 1}
        and p["role_duration_seconds"] == 3600,
        "CloudCredentialLimitsMismatch",
    )
    need(
        p["linux_private_profile_accepted"] is True
        and p["v6_historical_risk_accepted"] is True
        and p["limited_existing_role_profile_accepted"] is True
        and p["bootstrap_namespace_history_unconfirmed_accepted"] is True
        and p["mode"] == "B"
        and p["hard_billing_cap_guaranteed"] is False,
        "CloudRiskDispositionMissing",
    )
    return p


def policy(expiry):
    """Session intersection: read APIs, normal dev lock, six guarded transports."""
    source = os.environ["GITHUB_SHA"]
    run = os.environ["GITHUB_RUN_ID"]
    state = "arn:aws:s3:::ai-interview-state-835384817629-ap-northeast-1"
    artifact = "arn:aws:s3:::ai-interview-artifacts-835384817629-ap-northeast-1"
    read = [
        "s3:Get*",
        "s3:List*",
        "iam:Get*",
        "iam:List*",
        "lambda:Get*",
        "lambda:List*",
        "apigateway:GET",
        "dynamodb:Describe*",
        "dynamodb:List*",
        "sqs:Get*",
        "sqs:List*",
        "sns:Get*",
        "sns:List*",
        "cognito-idp:Describe*",
        "cognito-idp:List*",
        "cognito-idp:Get*",
        "scheduler:Get*",
        "scheduler:List*",
        "logs:Describe*",
        "logs:List*",
        "cloudwatch:Describe*",
        "cloudwatch:List*",
        "ses:Get*",
        "budgets:ViewBudget",
        "budgets:ListTagsForResource",
        "sts:GetCallerIdentity",
    ]
    value = {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": read, "Resource": "*"},
            {
                "Effect": "Allow",
                "Action": ["s3:PutObject", "s3:DeleteObject"],
                "Resource": state + "/dev/terraform.tfstate.tflock",
            },
            {
                "Effect": "Allow",
                "Action": "s3:PutObject",
                "Resource": [
                    artifact + f"/lambda/{source}/{run}/1/app.zip",
                    artifact + f"/plans/{run}/1/*",
                ],
            },
            {
                "Effect": "Deny",
                "Action": "*",
                "Resource": "*",
                "Condition": {"DateGreaterThanEquals": {"aws:CurrentTime": expiry}},
            },
        ],
    }
    need(len(json.dumps(value, separators=(",", ":"))) <= 2048, "SessionPolicySizeExceeded")
    return value


def prepare(env):
    global PARENT
    need(
        sys.platform == "linux" and env.get("RUNNER_ENVIRONMENT") == "github-hosted",
        "FreshHostedLinuxRequired",
    )
    os.umask(0o077)
    from cloud_toolchain import qualify as qualify_toolchain

    qualify_toolchain()
    from cloud_private import qualify

    qualify(env["RUNNER_TEMP"])
    qualification_env = {
        k: v
        for k, v in env.items()
        if not k.startswith(("AWS_", "ACTIONS_", "GH_", "P4_", "GITHUB_", "TF_"))
    }
    check = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("cloud_independent_audit.py")),
            "--qualification",
        ],
        env=qualification_env,
        capture_output=True,
        timeout=15,
    )
    need(check.returncode == 0, "CloudAuditIsolationUnavailable")
    root = Path(__file__).resolve().parents[3]
    for part in (root, *root.parents):
        need(not part.is_symlink(), "SourceSymlinkRejected")
    need(
        not subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, timeout=15
        ).strip(),
        "CloudCleanSourceRequired",
    )
    actual_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, timeout=15
    ).strip()
    need(actual_sha == env["GITHUB_SHA"], "CloudCheckoutShaMismatch")
    tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True, timeout=15
    ).strip()
    PARENT = validate_parent(
        env["P4_PLAN_APPROVAL_PACKAGE"], env["P4_CLOUD_PARENT_SHA256"], env, tree
    )
    env["P4_CLOUD_ACTIVE"] = "true"
    need(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", PARENT["base_commit"], "HEAD"],
            cwd=root,
            capture_output=True,
            timeout=15,
        ).returncode
        == 0,
        "ApprovedBaseNotAncestor",
    )
    baseline = json.loads(Path(__file__).with_name("cloud_baseline.json").read_bytes())
    need(canonical(baseline) == PARENT["baseline_sha256"], "CloudBaselineMismatch")
    config = json.loads(env["P4_DEPLOY_INPUTS"], object_pairs_hook=unique)
    need(
        canonical(config) == baseline["configuration_contract"]["raw_configuration_sha256"],
        "ExistingSecretConfigurationMismatch",
    )
    from plan_authorization import BUDGETS, END, LIMITS, START
    from plan_evidence import certificate_der

    need(
        hashlib.sha256(certificate_der(env)).hexdigest()
        == baseline["recipient_sha256"]
        == PARENT["recipient_sha256"],
        "ExistingRecipientMismatch",
    )
    child = {
        "schema_version": 1,
        "operation": "plan",
        "execution_ready": True,
        "repository": PARENT["repository"],
        "source_sha": env["GITHUB_SHA"],
        "account_id": PARENT["account_id"],
        "region": PARENT["region"],
        "oidc_subject": env["P4_OIDC_SUBJECT"],
        "oidc_limits": LIMITS,
        "sts_limits": LIMITS,
        "duration_seconds": 3600,
        "artifact_sha256": PARENT["artifact_sha256"],
        "configuration_sha256": canonical(config),
        "s3_put_limit": 6,
        "cleanup_seconds": 120,
        "deadline_policy": "no-new-operations;cleanup-before-expiry",
        "session_policy_sha256": canonical(policy(PARENT["expires_at_utc"])),
        "operation_budgets_seconds": BUDGETS,
        "evidence_recipient_sha256": PARENT["recipient_sha256"],
        "expires_at_utc": PARENT["expires_at_utc"],
        "cloud_parent_sha256": env["P4_CLOUD_PARENT_SHA256"],
    }
    raw = (
        "Derived execution descriptor under approved cloud parent; not new consent.\n"
        + START
        + json.dumps(child, sort_keys=True)
        + END
        + "\n"
    )
    env["P4_PLAN_APPROVAL_PACKAGE"] = raw
    env["P4_PLAN_APPROVAL_SHA256"] = hashlib.sha256(raw.encode()).hexdigest()
    env["P4_PLAN_APPROVAL_EXPIRES_AT"] = PARENT["expires_at_utc"]
    env["P4_PACKAGE_SHA256"] = PARENT["artifact_sha256"]
    env["P4_OPERATION"] = "plan"
    env["P4_CLOUD_ACTIVE"] = "true"
    need(float(env["P4_PLAN_JOB_STARTED_MONOTONIC"]) <= time.monotonic(), "JobClockMissing")
    return baseline, config


def session(role, account, region, required_seconds=120):
    global WIRE_COUNT
    need(
        PARENT is not None
        and role in {"plan", "artifact"}
        and account == PARENT["account_id"]
        and region == PARENT["region"],
        "CloudRoleScopeMismatch",
    )
    if role not in SESSIONS:
        need(WIRE_COUNT < 1500, "CloudSdkLimit")
        WIRE_COUNT += 1  # reserve checked_session caller-identity before observer installation
        from ci_identity import assume

        SESSIONS[role] = assume(
            role, account, region, expected_subject=os.environ["P4_OIDC_SUBJECT"]
        )
        expiration = getattr(SESSIONS[role], "p4_expiration", None)
        need(
            expiration is not None and expiration > datetime.now(UTC) + timedelta(minutes=35),
            "CloudCredentialTimeInsufficient",
        )

        def before_send(request, **kwargs):
            global WIRE_COUNT
            need(datetime.now(UTC) + timedelta(seconds=25) < expiration, "CloudCredentialsExpiring")
            from plan_authorization import active_guard

            active_guard().check("cloud-sdk-admission", 25)
            need(
                WIRE_COUNT < 1500
                and not re.search(
                    r"attempt=(?:[2-9]|[0-9]{2,})", str(request.headers.get("amz-sdk-request", ""))
                ),
                "CloudSdkLimitOrRetransmission",
            )
            WIRE_COUNT += 1

        SESSIONS[role].events.register("before-send.*.*", before_send)
    expiration = SESSIONS[role].p4_expiration
    need(
        datetime.now(UTC) + timedelta(seconds=required_seconds) < expiration,
        "CloudCredentialsExpiring",
    )
    # SDK and Terraform use the same static Plan session; cached calls restore it.
    credentials = SESSIONS[role].get_credentials().get_frozen_credentials()
    os.environ.update(
        AWS_ACCESS_KEY_ID=credentials.access_key,
        AWS_SECRET_ACCESS_KEY=credentials.secret_key,
        AWS_SESSION_TOKEN=credentials.token,
    )
    return SESSIONS[role]


class Journal:
    def __init__(self, path):
        self.path = path
        self.path.mkdir(mode=0o700, exist_ok=False)
        self.seq = 0

    def admit(self, seconds):
        from plan_authorization import active_guard

        active_guard().check("cloud-read-admission", seconds)

    def record(self, stage, **safe):
        self.seq += 1
        with (self.path / f"{self.seq:04d}.private.json").open("x") as stream:
            json.dump(
                {"stage": stage, "utc": datetime.now(UTC).isoformat(), **safe},
                stream,
                sort_keys=True,
            )


def before_plan(guard):
    global READER, BEFORE
    from cloud_dev_reader import DevReader
    from cloud_read_scope import Scope

    baseline = json.loads(Path(__file__).with_name("cloud_baseline.json").read_bytes())
    raw = json.loads(os.environ["P4_DEPLOY_INPUTS"])
    x = baseline | {
        "configuration": raw,
        "process_exit_evidence_required": True,
        "retention_exception": __import__("cloud_retention_policy").POLICY,
    }
    approval = SimpleNamespace(x=x, a=guard.package, sha=guard.digest, expiry=guard.expiry)
    journal = Journal(guard.directory.parent / f"cloud-read-{os.environ['GITHUB_RUN_ID']}-1")
    scope = Scope(approval, journal)
    scope.run_id = os.environ["GITHUB_RUN_ID"]
    READER = DevReader(
        session("plan", PARENT["account_id"], PARENT["region"]),
        scope,
        Path(__file__).resolve().parents[3],
    )
    BEFORE = READER.snapshot("before")
    # First snapshot is a comparison to immutable V6 baseline, never an inferred approval.
    from cloud_controller_core import check_snapshot

    check_snapshot(BEFORE, approval)


def after_plan(guard, directory, envelope):
    after = READER.snapshot("after")
    independent = READER.snapshot("independent")
    need(after == BEFORE == independent, "StateOrLiveReadbackChanged")
    records = [
        json.loads(p.read_bytes())
        for p in sorted(guard.directory.glob("[0-9][0-9][0-9][0-9].private.json"))
    ]
    from cloud_journal_audit import audit

    journal = audit(records, READER.scope.a, os.environ["GITHUB_RUN_ID"])
    tf = directory / "terraform"
    private = directory / "cloud-audit-input.private.json"
    private.write_text(
        json.dumps(
            {"snapshot": BEFORE, "x": READER.scope.a.x, "envelope": envelope, "parent": PARENT}
        ),
        encoding="utf-8",
    )
    child = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("AWS_", "ACTIONS_", "GH_", "P4_", "GITHUB_", "TF_"))
    }
    child.update(
        GITHUB_SHA=os.environ["GITHUB_SHA"],
        AWS_EC2_METADATA_DISABLED="true",
        TF_DATA_DIR=str(tf / ".terraform"),
        TF_WORKSPACE="default",
        PYTHONNOUSERSITE="1",
        PYTHONDONTWRITEBYTECODE="1",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("cloud_independent_audit.py")),
            str(private),
            str(tf),
        ],
        env=child,
        capture_output=True,
        timeout=180,
    )
    need(result.returncode == 0, "IndependentPlanAuditFailed")
    report = json.loads((tf / "cloud-audit.public.json").read_bytes())
    need(
        report["passed"] is True and report["apply_authorized"] is False,
        "IndependentPlanAuditRejected",
    )
    guard.check("cloud-audit-completed", 120)
    receipt = {
        "schema": 1,
        "status": "PLAN_AUDITED_GATE_CLOSURE_PENDING",
        "parent_sha256": os.environ["P4_CLOUD_PARENT_SHA256"],
        "source_sha": os.environ["GITHUB_SHA"],
        "source_tree": PARENT["source_tree"],
        "artifact_sha256": PARENT["artifact_sha256"],
        "run_id": os.environ["GITHUB_RUN_ID"],
        "run_attempt": "1",
        "saved_plan_sha256": envelope["plan_sha256"],
        "state_identity": BEFORE["dev"]["identity"],
        "bootstrap_state_identity": {
            "status": "UNCONFIRMED",
            "expected": READER.scope.a.x["bootstrap_state_identity"],
        },
        "outside_dev_resource_inventory": "UNCONFIRMED",
        "all_state_version_inventory": "UNCONFIRMED",
        "audit": report,
        "journal": journal,
        "sdk_requests": WIRE_COUNT,
        "state_unchanged": True,
        "active_lock": False,
        "apply_executed": False,
        "gate_closed": False,
        "requires_independent_gate_readback": True,
        "artifact_binding": envelope["package"],
        "saved_plan_version_id": envelope["plan_version"],
        "plan_binding_version_id": envelope["binding_version"],
    }
    public = Path(os.environ["RUNNER_TEMP"]) / "p4-cloud-result"
    public.mkdir(mode=0o700, exist_ok=False)
    (public / "result.json").write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")


def main():
    try:
        prepare(os.environ)
        from ci_deploy import main as plan

        need(plan() == 0, "CloudPlanFailed")
        return 0
    except Exception:
        print("P4CloudPlanRefused", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.modules["cloud_ci"] = sys.modules[__name__]
    raise SystemExit(main())
