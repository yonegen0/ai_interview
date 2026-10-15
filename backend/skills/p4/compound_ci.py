"""Plan-only compound CI adapter; called instead of ci_deploy.py directly.

No network/SDK on import. B is an explicit authorization change. This does not
claim a total provider/backend/Actions API cap or disable all provider waiters.
"""

import base64
import hashlib
import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def load(raw, environment, now):
    def unique(pairs):
        out = {}
        for k, v in pairs:
            need(k not in out, "CompoundDuplicateKey")
            out[k] = v
        return out

    def utc(s):
        need(
            type(s) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", s),
            "CompoundUtcRequired",
        )
        return datetime.fromisoformat(s.replace("Z", "+00:00"))

    need(
        environment.get("P4_OPERATION") == "plan"
        and environment.get("GITHUB_RUN_ATTEMPT") == "1"
        and environment.get("GITHUB_REF") == "refs/heads/main"
        and environment.get("P4_AWS_EXECUTION_READY") == "true",
        "CompoundPlanOnlyMainRequired",
    )
    digest = hashlib.sha256(raw).hexdigest()
    need(
        digest == environment.get("P4_COMPOUND_APPROVAL_SHA256") and len(raw) <= 48000,
        "CompoundWholeHashMismatch",
    )
    p = json.loads(raw, object_pairs_hook=unique)
    need(
        p["schema"] == 2
        and p["execution_ready"] is True
        and p["apply"] is False
        and p["mode"] == "B"
        and p["policy_b_accepted"] is True
        and p["full_api_count_guaranteed"] is False,
        "CompoundPolicyNotApproved",
    )
    need(
        p["repository"] == environment.get("GITHUB_REPOSITORY") == "yonegen0/ai_interview"
        and p["account_id"] == environment.get("AWS_DEV_ACCOUNT_ID") == "835384817629"
        and p["region"] == environment.get("AWS_REGION") == "ap-northeast-1",
        "CompoundTargetMismatch",
    )
    issued, expiry = utc(p["issued_at_utc"]), utc(p["expires_at_utc"])
    need(
        expiry - issued == timedelta(hours=72)
        and issued <= now
        and now + timedelta(seconds=120) < expiry,
        "CompoundExpiryInsufficient",
    )
    need(
        p["bindings"]["source_sha"] == environment.get("GITHUB_SHA")
        and p["bindings"]["artifact_sha256"] == environment.get("P4_PACKAGE_SHA256")
        and p["bindings"]["recipient_sha256"] == environment.get("P4_PLAN_EVIDENCE_CERT_SHA256"),
        "CompoundSourceArtifactRecipientMismatch",
    )
    need(
        p["findings"] == {"P0": 0, "P1": 0, "P2": 0}
        and all(type(v) is int for v in p["findings"].values()),
        "CompoundFindingsUnresolved",
    )
    # Remaining four existing Secrets must match the nested CI load checks too.
    plan = base64.b64decode(p["plan_package_base64"], validate=True)
    need(
        hashlib.sha256(plan).hexdigest()
        == p["plan_package_sha256"]
        == environment.get("P4_PLAN_APPROVAL_SHA256"),
        "CompoundNestedHashMismatch",
    )
    need(expiry == utc(environment["P4_PLAN_APPROVAL_EXPIRES_AT"]), "CompoundDeadlineMismatch")
    return plan, digest


def main():
    plan, fullsha = load(
        os.environ["P4_PLAN_APPROVAL_PACKAGE"].encode(), os.environ, datetime.now(UTC)
    )
    # Existing CI history guard rejects a second workflow attempt before AWS.
    # Exclusive marker rejects a second entrypoint in the same job workspace.
    path = Path(os.environ["RUNNER_TEMP"]) / ("compound-entry-" + fullsha)
    with path.open("xb") as f:
        os.chmod(path, 0o600)
        f.write(fullsha.encode())
        f.flush()
        os.fsync(f.fileno())
    os.environ["P4_PLAN_APPROVAL_PACKAGE"] = plan.decode("utf-8")
    os.environ["AWS_MAX_ATTEMPTS"] = "1"
    os.environ["AWS_RETRY_MODE"] = "standard"
    os.environ["TF_IN_AUTOMATION"] = "true"
    os.environ["P4_COMPOUND_ACTIVE"] = "true"
    import ci_deploy

    need(ci_deploy.main() == 0, "CompoundPlanFailedNoRetry")


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        print("CompoundCiStoppedNoRetry")
        raise SystemExit(1) from None
