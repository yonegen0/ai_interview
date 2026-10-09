"""Validation consumes actual business records and current session contracts offline."""

import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_provider_validation_tools import LocalApi, tool

from interview_backend.assets import load_questions
from interview_backend.repositories.codec import encode, from_wire, to_wire


@pytest.mark.parametrize("bad", [None, "missing", "owner", "key", "schema", "reply", "failed-run"])
def test_admin_receipt_exact_real_record(runtime, monkeypatch, bad):
    monkeypatch.syspath_prepend("skills/p4")
    live, receipts = tool("coaching_live"), tool("runtime_receipts")
    request_key = str(uuid4())
    admin = LocalApi(runtime, "admin", True)
    status, _, _ = admin.call(
        "POST",
        "/admin/question-bank",
        {"expectedVersion": 0, "questions": [load_questions()[0].wire()]},
        request_key,
    )
    assert status == 200
    record = next(iter(runtime.repository.snapshot().question_bank_changes.values()))
    native = encode("QuestionBankChange", record, 0)
    data = json.loads(native["data"])
    if bad in {"owner", "key"}:
        data[bad] = "other" if bad == "owner" else str(uuid4())
    if bad == "reply":
        data["reply"]["status"] = 500
    native["data"] = json.dumps(data)
    if bad == "schema":
        native["schema_version"] = 900
    seen = []

    def get_item(**kwargs):
        key = from_wire(kwargs["Key"])
        seen.append(key)
        if key["PK"] == "SYSTEM#QUESTION_BANK" and bad != "missing":
            return {"Item": to_wire(native)}
        return {}

    run = live.Run("admin-receipt-offline")
    run.record("admin-add", "failed" if bad == "failed-run" else "passed")
    run.record(
        "admin-add-record", "failed" if bad == "failed-run" else "passed", request_key=request_key
    )
    receipts.collect(
        SimpleNamespace(get_item=get_item),
        {"table_name": "offline"},
        {"subjects": {"USER_A": "user", "ADMIN": "admin"}},
        run,
        None,
    )
    observed = next(
        r for r in run.rows if r["check"] == "ADMIN-QuestionBankChange-business-record-observed"
    )
    assert observed["status"] == (
        "passed" if bad is None else "not_run" if bad in {"missing", "failed-run"} else "failed"
    )
    if bad != "failed-run":
        assert {"PK": "SYSTEM#QUESTION_BANK", "SK": f"OP#admin#{request_key}"} in seen
    assert not any(k["SK"].startswith("IDEMPOTENCY#") for k in seen)
    assert (
        next(r for r in run.rows if r["check"] == "IAM-ConditionCheck1-independent-case")["status"]
        == "not_run"
    )


class CompletedApi(LocalApi):
    def __init__(self, runtime, bad=None):
        super().__init__(runtime, "user")
        self.calls, self.bad = [], bad

    def call(self, method, path, payload=None, key=None, headers=None):
        if path.startswith("/evaluations/"):
            self.runtime.worker.run(self.owner, path.rsplit("/", 1)[1])
        result = super().call(method, path, payload, key)
        if method == "POST" and path.endswith("/questions/next") and self.bad:
            result = (
                (200, {"questionNumber": 2}, {})
                if self.bad == "unexpected-success"
                else (500, {"code": "INTERNAL_SERVER_ERROR"}, {})
            )
        self.calls.append((method, path, deepcopy(result)))
        return result


@pytest.mark.parametrize("count", [1, 2, 3])
def test_auth_flow_single_and_multiple_questions(runtime, monkeypatch, count):
    monkeypatch.syspath_prepend("skills/p4")
    admin = LocalApi(runtime, "admin", True)
    assert (
        admin.call(
            "POST",
            "/admin/question-bank",
            {"expectedVersion": 0, "questions": [q.wire() for q in load_questions()[:count]]},
            str(uuid4()),
        )[0]
        == 200
    )
    api = CompletedApi(runtime)
    sid, accepted = tool("auth_e2e").flow(api)
    assert sid and accepted
    transitions = [r for m, p, r in api.calls if m == "POST" and p.endswith("/questions/next")]
    assert transitions[0][0] == (409 if count == 1 else 200)
    assert transitions[1][:2] == transitions[0][:2]
    assert any(p == "/unknown" for _, p, _ in api.calls)
    other = LocalApi(runtime, "other")
    for path in (
        f"/sessions/{sid}/question",
        f"/evaluations/{accepted['evaluationId']}",
        f"/attempts/{accepted['attemptId']}/feedback",
    ):
        assert other.call("GET", path)[0] == 404


def test_auth_unavailable_category_checks_exact_backend_error(runtime, monkeypatch):
    monkeypatch.syspath_prepend("skills/p4")
    admin = LocalApi(runtime, "admin", True)
    admin.call(
        "POST",
        "/admin/question-bank",
        {"expectedVersion": 0, "questions": [load_questions()[0].wire()]},
        str(uuid4()),
    )
    api = CompletedApi(runtime)
    assert tool("auth_e2e").flow(api, category="career") == (None, None)
    assert api.calls[-1][2][0] == 409
    assert api.calls[-1][2][1]["code"] == "CATEGORY_UNAVAILABLE"


@pytest.mark.parametrize("bad", ["unexpected-success", "internal-error"])
def test_auth_never_accepts_incorrect_terminal_or_retry_reply(runtime, monkeypatch, bad):
    monkeypatch.syspath_prepend("skills/p4")
    with pytest.raises(AssertionError):
        tool("auth_e2e").flow(CompletedApi(runtime, bad), category="career")
