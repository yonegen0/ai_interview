"""Reviewed callback binding for a successful enablement; no implicit AWS execution."""

import hashlib
import inspect
import json
import os
from pathlib import Path

from coaching_live import Run, admin_flow, coaching_flow, run_with_closure


def authenticate_existing(client, manifest, email):
    """Use existing EMAIL_OTP login and server GetUser, without persisting tokens.

    The reviewed authenticate callback supplies the approved label's hidden email.
    This helper must only be called inside the authorized lifecycle callback.
    """
    from auth_e2e import Api, login

    tokens = login(client, manifest["client_id"], email)
    try:
        user = client.get_user(AccessToken=tokens["AccessToken"])
        subject = next(a["Value"] for a in user["UserAttributes"] if a["Name"] == "sub")
        return Api(manifest["api_endpoint"], tokens["AccessToken"]), subject
    finally:
        tokens.clear()


def approval_binding(raw, digest, manifest_raw, *, run_id, account, callbacks):
    """Validate immutable inputs before auth, HTTP, or closure callbacks can run."""
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("ApprovalHashMismatch")
    approval = json.loads(raw)
    manifest = json.loads(manifest_raw)
    Run(run_id)
    required = {
        "live_authorized": True,
        "conditional_closure_authorized": True,
        "enablement_succeeded": True,
        "run_id": run_id,
        "account_id": account,
        "region": "ap-northeast-1",
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
    }
    if any(type(approval.get(k)) is not type(v) or approval[k] != v for k, v in required.items()):
        raise ValueError("ExplicitLiveBindingRequired")
    if (
        manifest.get("account_id") != account
        or manifest.get("region") != "ap-northeast-1"
        or manifest.get("environment") != "dev"
        or any(
            manifest.get("configuration", {}).get(k) is not True
            for k in ("api_enabled", "worker_enabled", "streams_enabled", "scheduler_enabled")
        )
    ):
        raise ValueError("ActiveDevManifestRequired")
    subjects = approval.get("subjects", {})
    if (
        set(subjects) != {"USER_A", "USER_B", "ADMIN"}
        or any(not isinstance(s, str) or not s for s in subjects.values())
        or len(set(subjects.values())) != 3
    ):
        raise ValueError("DistinctApprovedSubjectsRequired")
    if approval.get("provider") not in {"fake", "openai"}:
        raise ValueError("ExplicitProviderRequired")
    from interview_backend.evaluation.selection import checked_provider_environment

    environment = checked_provider_environment(
        manifest.get("worker_ai_environment", {}), account, "ap-northeast-1"
    )
    if environment.get("INTERVIEW_AI_PROVIDER", "fake") != approval["provider"]:
        raise ValueError("ProviderManifestMismatch")
    if approval["provider"] == "openai" and approval.get("paid_calls_authorized") is not True:
        raise ValueError("PaidCallsNotApproved")
    if type(approval.get("expected_rounds")) is not int or approval["expected_rounds"] not in (
        0,
        3,
    ):
        raise ValueError("ApprovedRoundsRequired")
    if type(approval.get("admin_writes")) is not bool:
        raise ValueError("ExplicitAdminScopeRequired")
    if approval["admin_writes"] and approval.get("exclusive_test_window_verified") is not True:
        raise ValueError("ExclusiveAdminWindowRequired")
    # These files are reviewed Python adapters, never arbitrary shell hooks.
    if set(callbacks) != {"audit", "authenticate", "close"}:
        raise ValueError("ReviewedCallbacksRequired")
    for name, path in callbacks.items():
        if (
            approval.get("callback_sha256", {}).get(name)
            != hashlib.sha256(Path(path).read_bytes()).hexdigest()
        ):
            raise ValueError("CallbackHashMismatch")
    return approval, manifest


def execute_bound(
    raw,
    digest,
    manifest_raw,
    journal,
    *,
    run_id,
    account,
    callbacks,
    audit,
    authenticate,
    close,
    wait=None,
):
    """Check binding before callbacks; audit must fail closed on unsafe State.

    authenticate returns (Api, server-verified Cognito subject) for each label.
    audit verifies successful apply receipt, latest State/manifest, lock, namespaces,
    provider configuration and exclusive window. Partial apply stops before closure.
    """
    approval, manifest = approval_binding(
        raw, digest, manifest_raw, run_id=run_id, account=account, callbacks=callbacks
    )
    for name, callback in {"audit": audit, "authenticate": authenticate, "close": close}.items():
        source = inspect.getsourcefile(callback)
        if source is None or Path(source).resolve() != Path(callbacks[name]).resolve():
            raise ValueError("CallbackSourceMismatch")
    if audit(manifest, approval) is not True:
        raise ValueError("SafeSuccessfulEnablementAuditRequired")
    path = Path(journal).resolve()
    private = (Path(__file__).resolve().parents[2] / ".p4-artifacts").resolve()
    if not path.is_relative_to(private):
        raise ValueError("PrivateJournalRequired")
    # Atomic creation blocks repeat execution even after an unknown HTTP outcome.
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps({"status": "STARTED", "run_id": approval["run_id"]}) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
        run = Run(approval["run_id"], stream)

        def test():
            apis = {}
            try:
                for label, subject in approval["subjects"].items():
                    api, actual = authenticate(label, manifest)
                    apis[label] = api
                    if actual != subject:
                        raise ValueError("AuthenticatedSubjectMismatch")
                options = {"expected_rounds": approval["expected_rounds"]}
                if wait is not None:
                    options["wait"] = wait
                coaching_flow(apis["USER_A"], apis["USER_B"], run, **options)
                admin_flow(apis["USER_A"], apis["ADMIN"], run, writes=approval["admin_writes"])
            except Exception:
                run.record("suite", "failed")
                raise
            finally:
                for api in apis.values():
                    api.token = None

        run_with_closure(test, lambda: close(manifest, approval), run)
        return run.rows


def cleanup_candidates(rows, owner, read_exact):
    """Read exact native keys only. Return inventory, never delete or query/scan.

    ProviderUsage counters deliberately remain; reservations are never refunded.
    Auxiliary items not derivable from recorded IDs remain for explicit review.
    """
    from interview_backend.repositories.codec import key

    kinds = {"session_id": "Session", "attempt_id": "Attempt", "evaluation_id": "Evaluation"}
    found = []
    seen = set()
    for row in rows:
        for field, kind in kinds.items():
            if field not in row:
                continue
            native = key(kind, owner, row[field])
            pair = (native["PK"], native["SK"])
            if pair in seen:
                continue
            seen.add(pair)
            item = read_exact(native)
            if item is not None:
                if any(item.get(k) != v for k, v in native.items()):
                    raise ValueError("CleanupExactKeyMismatch")
                found.append(native)
    return found
