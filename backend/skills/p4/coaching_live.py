"""Approval-only V2/IAM-through-business-API checks. Import/dry-run never contacts AWS."""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "backend/src"), str(Path(__file__).resolve().parent)]


class Run:
    def __init__(self, run_id, journal=None):
        if not re.fullmatch(r"[a-z0-9-]{1,24}", run_id):
            raise ValueError("UniqueRunIdRequired")
        self.run_id, self.journal, self.rows = run_id, journal, []

    def key(self, name):
        return str(uuid5(NAMESPACE_URL, self.run_id + ":" + name))

    def record(self, check, status="passed", **identifiers):
        if status not in {"passed", "failed", "not_run"} or set(identifiers) - {
            "session_id",
            "attempt_id",
            "evaluation_id",
            "request_key",
        }:
            raise ValueError("SafeEvidenceRequired")
        row = {"run_id": self.run_id, "check": check, "status": status, **identifiers}
        self.rows.append(row)
        if self.journal:
            self.journal.write(json.dumps(row) + "\n")
            self.journal.flush()
            os.fsync(self.journal.fileno())

    def expect(self, condition, name):
        self.record(name, "passed" if condition else "failed")
        if not condition:
            raise AssertionError("LiveValidationAssertionFailed")


def poll(api, eid, *, clock=time.monotonic, sleep=time.sleep, timeout=180):
    deadline = clock() + timeout
    while True:
        status, value, _ = api.call("GET", f"/evaluations/{eid}")
        if status != 200:
            raise AssertionError("EvaluationReadFailed")
        if value["status"] != "processing":
            return value
        if clock() >= deadline:
            raise TimeoutError("EvaluationDeadline")
        sleep(2)


def coaching_flow(a, b, run, *, expected_rounds=0, expected_failure=False, wait=poll):
    key = run.key("session")
    payload = {"mode": "category", "category": "career", "difficulty": "standard"}
    status, created, _ = a.call("POST", "/sessions", payload, key)
    run.expect(status == 201, "session-create")
    sid = created["sessionId"]
    run.record("created-session", session_id=sid, request_key=key)
    run.expect(a.call("POST", "/sessions", payload, key)[:2] == (201, created), "session-replay")
    run.expect(b.call("GET", f"/sessions/{sid}/question")[0] == 404, "other-owner-session")
    status, question, _ = a.call("GET", f"/sessions/{sid}/question")
    run.expect(status == 200, "question-read")
    qid = question["question"]["id"]
    path = f"/sessions/{sid}/answers"
    body = {"kind": "initial_answer", "questionId": qid, "answer": "検証用の本人回答です。"}
    key = run.key("answer-initial")
    status, accepted, _ = a.call("POST", path, body, key)
    run.expect(status == 202, "initial-accept")
    first = dict(accepted)
    for round_index in range(4):
        eid, aid = accepted["evaluationId"], accepted["attemptId"]
        run.record(
            "evaluation-created", session_id=sid, attempt_id=aid, evaluation_id=eid, request_key=key
        )
        run.expect(a.call("POST", path, body, key)[:2] == (202, accepted), "answer-replay")
        run.expect(b.call("GET", f"/evaluations/{eid}")[0] == 404, "other-owner-evaluation")
        run.expect(
            b.call("GET", f"/attempts/{aid}/feedback?evaluationId={eid}")[0] == 404,
            "other-owner-feedback",
        )
        outcome = wait(a, eid)
        if outcome["status"] == "failed":
            run.expect(expected_failure, "expected-provider-failure")
            run.record("provider-failed")
            retry = {"kind": "retry_evaluation", "attemptId": aid, "fromEvaluationId": eid}
            rk = run.key("evaluation-retry")
            rs, retried, _ = a.call("POST", path, retry, rk)
            run.expect(rs == 202 and retried["evaluationId"] != eid, "retry-evaluation-new-id")
            run.expect(a.call("POST", path, retry, rk)[:2] == (202, retried), "retry-replay")
            run.record(
                "retry-evaluation-created", evaluation_id=retried["evaluationId"], request_key=rk
            )
            retried_outcome = wait(a, retried["evaluationId"])
            run.expect(retried_outcome["status"] == "failed", "same-failure-config-retry-terminal")
            return
        run.expect(not expected_failure, "expected-provider-success")
        fs, feedback, _ = a.call("GET", f"/attempts/{aid}/feedback?evaluationId={eid}")
        run.expect(fs == 200 and feedback.get("feedbackVersion") == 2, "v2-feedback")
        run.expect(feedback["coachingCount"] == round_index, "coaching-count")
        run.expect(a.call("GET", f"/sessions/{sid}/question")[0] == 200, "reload-session")
        if feedback["result"]["status"] == "completed":
            run.expect(round_index == expected_rounds, "expected-completion-round")
            retry = {
                "kind": "retry_attempt",
                "questionId": qid,
                "answer": "検証用再挑戦です。",
                "fromAttemptId": aid,
                "fromEvaluationId": eid,
            }
            rk = run.key("attempt-retry")
            rs, retried, _ = a.call("POST", path, retry, rk)
            run.expect(rs == 202 and retried["attemptId"] != aid, "retry-attempt-new-id")
            run.record(
                "retry-attempt-created",
                attempt_id=retried["attemptId"],
                evaluation_id=retried["evaluationId"],
                request_key=rk,
            )
            run.expect(
                a.call("POST", path, retry, rk)[:2] == (202, retried), "retry-attempt-replay"
            )
            run.expect(
                a.call("GET", f"/attempts/{aid}/feedback?evaluationId={eid}")[0] == 200,
                "historical-feedback",
            )
            return
        run.expect(round_index < 3, "follow-up-limit")
        prior = accepted
        body = {
            "kind": "coaching_answer",
            "questionId": qid,
            "answer": "検証用の追加回答です。",
            "attemptId": aid,
            "fromEvaluationId": eid,
        }
        key = run.key("coaching-" + str(round_index))
        status, accepted, _ = a.call("POST", path, body, key)
        run.expect(status == 202 and accepted["attemptId"] == first["attemptId"], "coaching-accept")
        run.expect(
            a.call("POST", path, body, run.key("stale-" + str(round_index)))[0] == 409,
            "stale-origin-rejected",
        )
        run.expect(accepted["evaluationId"] != prior["evaluationId"], "new-evaluation-id")


def admin_flow(user, admin, run, *, writes=False):
    run.expect(user.call("GET", "/admin/question-bank")[0] == 403, "USER-admin-denied")
    status, bank, _ = admin.call("GET", "/admin/question-bank")
    run.expect(status == 200, "ADMIN-bank-read")
    if not writes:
        for name in ("admin-add", "admin-edit", "admin-delete", "admin-reorder", "admin-conflict"):
            run.record(name, "not_run")
        return
    # Caller must establish an exclusive test-user window first. Preserve all original questions.
    original = bank["questions"]
    own = {
        "id": run.key("bank-question"),
        "category": "career",
        "difficulty": "standard",
        "question": "検証専用質問 " + run.run_id,
    }
    current = bank
    try:
        for label, questions in (
            ("admin-add", original + [own]),
            ("admin-edit", original + [own | {"question": "検証専用編集 " + run.run_id}]),
            ("admin-reorder", [own] + original),
            ("admin-delete", original),
        ):
            expected = current["version"]
            payload = {"expectedVersion": expected, "questions": questions}
            key = run.key(label)
            status, receipt, _ = admin.call("POST", "/admin/question-bank", payload, key)
            run.expect(status == 200, label)
            run.record(label + "-record", request_key=key)
            run.expect(
                admin.call("POST", "/admin/question-bank", payload, key)[:2] == (200, receipt),
                label + "-replay",
            )
            run.expect(
                admin.call("POST", "/admin/question-bank", payload, run.key(label + "-conflict"))[0]
                == 409,
                label + "-conflict",
            )
            _, current, _ = admin.call("GET", "/admin/question-bank")
    finally:
        status, latest, _ = admin.call("GET", "/admin/question-bank")
        if status != 200 or latest["questions"] != original:
            # Never overwrite concurrent third-party changes. Restore only our exact fixture state.
            expected_variants = (
                original + [own],
                [own] + original,
                original + [own | {"question": "検証専用編集 " + run.run_id}],
            )
            if status != 200 or latest["questions"] not in expected_variants:
                run.record("admin-restore", "failed")
                raise AssertionError("AdminRestoreRequiresReview")
            result = admin.call(
                "POST",
                "/admin/question-bank",
                {
                    "expectedVersion": latest["version"],
                    "questions": original,
                },
                run.key("restore-bank"),
            )
            run.expect(result[0] == 200, "admin-restore")


def run_with_closure(test, close, run):
    """A failed test never skips the separately approved closure lifecycle callback."""
    try:
        test()
    finally:
        evidence = close()
        required = {
            "status": "CLOSED_READBACK_VERIFIED",
            "api_disabled": True,
            "worker_disabled": True,
            "streams_disabled": True,
            "scheduler_disabled": True,
            "validation_alarm_count": 0,
            "active_lock": False,
            "state_outside_dev_resources": 0,
        }
        if not isinstance(evidence, dict) or any(
            key not in evidence or type(evidence[key]) is not type(value) or evidence[key] != value
            for key, value in required.items()
        ):
            run.record("closed-readback", "failed")
            raise ValueError("VerifiedClosureReadbackRequired")
        run.record("closed-readback")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if not output.is_relative_to((ROOT / "backend/.p4-artifacts").resolve()) or output.exists():
        raise ValueError("FreshPrivateJournalRequired")
    run = Run(args.run_id)
    # Deliberately preparation-only CLI: live operator wires approved auth/closure adapters.
    report = {
        "status": "AWS_LIVE_VALIDATION_PREPARED_NOT_EXECUTED",
        "run_id": run.run_id,
        "available_flows": ["coaching_flow", "admin_flow", "run_with_closure"],
        "authentication_adapter": "existing auth_e2e.login/Api; tokens remain memory-only",
        "remaining_live_checks": [
            "EMAIL_OTP/refresh/logout/actual JWT expiry using auth_e2e",
            "Recovery and delivery observation",
            "runtime IAM transaction outcomes",
        ],
        "closure": "Requires approved audited closure callback; no raw apply embedded",
        "cleanup": "Journal owned session/attempt/evaluation/request IDs; no scan/delete",
        "resources_created": 0,
        "API_requests": 0,
        "live_result": None,
    }
    with output.open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(json.dumps({"status": report["status"], "run_id": args.run_id, "API_requests": 0}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("LiveValidationPreparationFailed") from None
