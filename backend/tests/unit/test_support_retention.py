"""Advance the runtime clock past 90 days; do not mistake timestamp arithmetic for a read."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from conftest import uid
from test_events import accepted

from interview_backend.bootstrap import build_runtime
from interview_backend.repositories.codec import decode, encode, from_wire, hydrate, to_wire
from interview_backend.support_history import read_summary


@pytest.mark.parametrize("days", [91, 120, 365])
@pytest.mark.parametrize("legacy,failed", [(False, False), (True, False), (False, True)])
def test_old_exact_owner_read_and_retirement_preserves_only_existing_data(
    days, legacy, failed, capsys
):
    from itertools import count

    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    ids = count(1)
    runtime = build_runtime(new_id=lambda: uid(next(ids)), clock=lambda: now[0])
    message = accepted(runtime)
    runtime.worker.run(message["ownerSub"], message["evaluationId"], 1)
    evaluation = next(iter(runtime.repository.snapshot().evaluations.values()))
    native = encode("Evaluation", evaluation, 0)
    data = json.loads(native["data"])
    if legacy:
        data.pop("execution_config", None)
        data.update(
            status="failed",
            failure_reason="PREPARATION_FAILED",
            feedback=None,
            error={"code": "EVALUATION_FAILED", "message": "Evaluation could not be completed."},
            lock_owner=None,
            lock_expires_at=None,
            call_phase="not_started",
            call_started_at=None,
        )
    if failed:
        data.update(
            status="failed",
            failure_reason="OUTCOME_UNKNOWN",
            feedback=None,
            error={"code": "EVALUATION_FAILED", "message": "Evaluation could not be completed."},
        )
    native = encode(
        "Evaluation", hydrate("Evaluation", {k: v for k, v in data.items() if v is not None}), 0
    )
    decode(native)  # Every legacy/failed fixture obeys the actual stored schema.
    now[0] += timedelta(days=days)
    before = runtime.repository.snapshot()
    calls = []
    records = {evaluation.owner: native}

    def get_item(**kwargs):
        calls.append(kwargs)
        key = from_wire(kwargs["Key"])
        row = records.get(key["PK"].removeprefix("USER#"))
        return {"Item": to_wire(row)} if row else {}

    client = SimpleNamespace(get_item=get_item)
    summary = read_summary(
        client, "existing-table", owner=evaluation.owner, evaluation_id=evaluation.id
    )
    assert int(now[0].timestamp() * 1000) - summary["requestedAtEpochMs"] >= days * 86400000
    assert summary["status"] == ("failed" if failed or legacy else "completed")
    assert summary["providerId"] == ("unknown" if legacy else "fake")
    assert calls[0]["ConsistentRead"] is True
    assert from_wire(calls[0]["Key"]) == {
        "PK": f"USER#{evaluation.owner}",
        "SK": f"EVALUATION#{evaluation.id}",
    }
    with pytest.raises(ValueError, match="Unavailable"):
        read_summary(client, "existing-table", owner="other-user", evaluation_id=evaluation.id)
    # Cognito deletion does not erase the independent stored item; no active-user auth is bypassed.
    # If an administrator actually deletes the DDB item, history is unavailable, not synthesized.
    records.clear()
    with pytest.raises(ValueError, match="Unavailable"):
        read_summary(client, "existing-table", owner=evaluation.owner, evaluation_id=evaluation.id)
    assert runtime.repository.snapshot() == before
    assert not any(k.lower() in {"ttl", "expires_at", "answer", "feedback"} for k in summary)
    assert "ttl" not in native
    assert capsys.readouterr().out == ""
