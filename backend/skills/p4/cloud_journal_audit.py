"""Success: exact auth/identity pairs and process start/exit-zero/completion."""

from datetime import datetime

from cloud_controller_core import ACCOUNT, BUDGETS, LIMITS, MAIN, REGION, require


def audit(records, approval, run_id):
    require(records and len(records) <= 256, "PrivateJournalIncomplete")
    first = records[0]
    require(
        first["stage"] == "approval-started"
        and first["approval_sha256"] == approval.sha
        and first["run_id"] == str(run_id)
        and first["run_attempt"] == "1"
        and first["expires_at_utc"] == approval.a["expires_at_utc"],
        "JournalApprovalMismatch",
    )
    require(
        approval.x.get("process_exit_evidence_required") is True,
        "ProcessExitEvidencePolicyRequired",
    )
    counts = {k: {r: 0 for r in LIMITS} for k in ("oidc", "sts")}
    keys = {f"lambda/{MAIN}/{run_id}/1/app.zip"} | {
        f"plans/{run_id}/1/{n}"
        for n in ("dev.tfplan", "plan.json", "summary.json", "review.private.json", "envelope.json")
    }
    bucket = f"ai-interview-artifacts-{ACCOUNT}-{REGION}"
    puts = set()
    processes = {}
    pending = None
    last = None
    bound = 0
    observed = False
    sts_seen = False
    awaiting_identity = False
    identities = 0
    for index, row in enumerate(records):
        stamp = datetime.fromisoformat(row["utc"].replace("Z", "+00:00"))
        require(
            stamp.tzinfo is not None
            and stamp.utcoffset().total_seconds() == 0
            and stamp < approval.expiry
            and (last is None or stamp >= last),
            "JournalTimeMismatch",
        )
        last = stamp
        stage = row["stage"]
        if stage == "approval-started":
            require(index == 0, "DuplicateJournalApproval")
            continue
        if stage == "run-bound":
            require(index == 1 and bound == 0, "JournalRunBindingOrder")
            bound = 1
            continue
        if stage == "plan-transport-completed":
            require(
                index == len(records) - 1 and pending is None and not awaiting_identity,
                "JournalTransportOrder",
            )
            continue
        if stage == "process-exit-observed":
            require(
                pending is not None
                and pending[0] == "process"
                and not observed
                and row["operation"] == pending[1]["operation"]
                and type(row.get("returncode")) is int
                and row["returncode"] == 0,
                "ProcessExitEvidenceMismatch",
            )
            observed = True
            continue
        if stage == "sts-response":
            require(
                pending is not None
                and pending[0].startswith("sts-")
                and not sts_seen
                and row.get("role") == pending[0].split("-", 1)[1]
                and isinstance(row.get("request_id"), str)
                and 0 < len(row["request_id"]) <= 128,
                "StsResponseBindingMismatch",
            )
            sts_seen = True
            continue
        require(
            bound == 1 and stage.endswith(("-started", "-completed")),
            "UnknownOrFailureJournalStage",
        )
        start = stage.endswith("-started")
        stem = stage.rsplit("-", 1)[0]
        if start:
            require(pending is None, "JournalUnpairedStart")
            require(
                not awaiting_identity or stem == "caller-identity", "CallerIdentityOrderMismatch"
            )
            if stem.startswith(("oidc-", "sts-")):
                kind, role = stem.split("-", 1)
                require(role in LIMITS, "UnexpectedAuthenticationRole")
                counts[kind][role] += 1
                require(
                    counts[kind][role] <= LIMITS[role]
                    and type(row["count"]) is int
                    and row["count"] == counts[kind][role],
                    "JournalAuthenticationCounterMismatch",
                )
                sts_seen = False
            elif stem == "caller-identity":
                require(awaiting_identity, "UnexpectedCallerIdentity")
            elif stem == "s3-put":
                key = row["key"]
                require(
                    row["bucket"] == bucket
                    and key in keys
                    and key not in puts
                    and type(row["attempt"]) is int
                    and row["attempt"] == len(puts) + 1,
                    "JournalPutScopeOrCounterMismatch",
                )
                if key.endswith("/envelope.json"):
                    require(len(puts) == 5, "EnvelopeMustBeLast")
                puts.add(key)
            elif stem == "process":
                op = row["operation"]
                require(
                    op in {"build", "version", "init", "plan", "show"}, "UnexpectedTerraformProcess"
                )
                require(
                    type(row["maximum_seconds"]) is int
                    and row["maximum_seconds"] == BUDGETS.get(op, 60),
                    "ProcessBudgetMismatch",
                )
                processes[op] = processes.get(op, 0) + 1
                observed = False
                require(processes[op] <= (64 if op == "build" else 1), "RepeatedFormalProcess")
            else:
                raise RuntimeError("UnknownJournalOperation")
            pending = (stem, row)
        else:
            require(pending is not None and pending[0] == stem, "JournalCompletionMissingStart")
            expected = pending[1]
            fields = (
                ("count",)
                if stem.startswith(("oidc-", "sts-"))
                else ("bucket", "key", "attempt")
                if stem == "s3-put"
                else ("operation",)
                if stem == "process"
                else ()
            )
            require(
                all(row.get(k) == expected.get(k) for k in fields), "JournalCompletionPairMismatch"
            )
            if stem == "process":
                require(observed, "MissingProcessExitEvidence")
            if stem.startswith("sts-"):
                require(sts_seen, "MissingStsResponse")
                awaiting_identity = True
            if stem == "caller-identity":
                awaiting_identity = False
                identities += 1
            pending = None
    require(
        records[-1]["stage"] == "plan-transport-completed"
        and pending is None
        and not awaiting_identity
        and counts["oidc"] == counts["sts"] == {"plan": 1, "artifact": 1}
        and identities == 2
        and puts == keys
        and all(processes.get(k) == 1 for k in ("version", "init", "plan", "show")),
        "ProducerJournalIncomplete",
    )
    return {
        "oidc": counts["oidc"],
        "sts": counts["sts"],
        "transport_puts": len(puts),
        "formal_plans": processes["plan"],
        "process_counts": processes,
        "paired_completions_verified": True,
        "exact_put_scope_verified": True,
    }
