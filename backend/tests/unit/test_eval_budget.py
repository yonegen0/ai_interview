"""Actual provider requests and ledger boundaries, with all external sends mocked."""

import json
from datetime import date
from decimal import Decimal

import pytest
from test_provider_validation_tools import tool


@pytest.fixture
def budget_tool():
    tool("provider_eval")
    return tool("eval_budget")


def payload():
    return {
        "model": "gpt-6-luna",
        "max_output_tokens": 4096,
        "tools": [],
        "input": [{"role": "user", "content": "合成検証"}],
        "text": {"format": {"type": "json_schema"}},
    }


def make_budget(module, tmp_path, *, limit="1.00", number=2):
    stream = (tmp_path / "budget.jsonl").open("x", encoding="utf-8")
    requests = [payload()] * number
    counts = [{"request_sha256": module.sha(p), "input_tokens": 100} for p in requests]
    return module.Budget(stream, requests, counts, limit), stream


def test_exact_budget_and_one_nano_over_boundary(budget_tool, tmp_path):
    p = payload()
    c = {"request_sha256": budget_tool.sha(p), "input_tokens": 100}
    upper = budget_tool.maximum(c, p)
    limit = str(Decimal(upper) / budget_tool.NANO_USD)
    with (tmp_path / "exact").open("x", encoding="utf-8") as stream:
        b = budget_tool.Budget(stream, [p], [c], limit)
        assert b.reserved == b.limit
    with (tmp_path / "over").open("x", encoding="utf-8") as stream:
        with pytest.raises(ValueError, match="BudgetWouldBeExceeded"):
            budget_tool.Budget(stream, [p], [c], str(Decimal(upper - 1) / budget_tool.NANO_USD))


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"input_tokens": True, "output_tokens": 0},
        {"input_tokens": 1, "output_tokens": -1},
    ],
)
def test_unknown_usage_holds_reservation_and_stops(budget_tool, tmp_path, usage):
    b, stream = make_budget(budget_tool, tmp_path)
    try:
        held = b.reserved
        b.start(payload())
        with pytest.raises(ValueError, match="UsageUnknown"):
            b.settle(usage)
        assert b.reserved == held and b.used == 0
        with pytest.raises(ValueError, match="NoFurtherPaidCalls"):
            b.start(payload())
    finally:
        stream.close()


def test_accounting_prevents_duplicate_call_and_overrun(budget_tool, tmp_path):
    b, stream = make_budget(budget_tool, tmp_path)
    try:
        b.start(payload())
        with pytest.raises(ValueError, match="NoFurtherPaidCalls"):
            b.start(payload())
        b.settle({"input_tokens": 100, "output_tokens": 10})
        assert b.used == 100 * 550 + 10 * 1650
        assert b.reserved == b.reservations[1]
        b.start(payload())
        b.settle({"input_tokens": 100, "output_tokens": 10})
        with pytest.raises(ValueError, match="NoFurtherPaidCalls"):
            b.start(payload())
        assert b.reserved == 0 and b.calls == 2
        rows = [json.loads(line) for line in (tmp_path / "budget.jsonl").read_text().splitlines()]
        assert rows[0]["budget_status"] == "ALL_REQUESTS_RESERVED"
    finally:
        stream.close()


def test_actual_over_reservation_freezes(budget_tool, tmp_path):
    b, stream = make_budget(budget_tool, tmp_path)
    try:
        b.start(payload())
        with pytest.raises(ValueError, match="ReservationExceeded"):
            b.settle({"input_tokens": 101, "output_tokens": 4096})
        assert b.frozen
        with pytest.raises(ValueError):
            b.start(payload())
    finally:
        stream.close()


def test_pricing_stale_hash_and_invalid_count_rejected(budget_tool, tmp_path):
    budget_tool.checked_pricing(budget_tool.pricing_hash(), date(2026, 10, 8))
    for hash_value, day in (
        ("bad", date(2026, 10, 8)),
        (budget_tool.pricing_hash(), date(2026, 10, 16)),
    ):
        with pytest.raises(ValueError, match="CurrentApprovedPricingRequired"):
            budget_tool.checked_pricing(hash_value, day)
    for c in (
        {"request_sha256": "bad", "input_tokens": 1},
        {"request_sha256": budget_tool.sha(payload()), "input_tokens": True},
    ):
        with pytest.raises(ValueError, match="TokenCountBindingMismatch"):
            budget_tool.maximum(c, payload())
    with (tmp_path / "calls").open("x", encoding="utf-8") as stream:
        with pytest.raises(ValueError, match="Maximum38CallsRequired"):
            budget_tool.Budget(stream, [payload()] * 39, [{}] * 39, "1.00", max_calls=39)


def test_count_uses_exact_messages_schema_no_generation(budget_tool):
    from test_openai_provider import Authentication, Transport

    t = Transport(value={"object": "response.input_tokens", "input_tokens": 100})
    count = budget_tool.count_request(payload(), Authentication(), transport=t)
    assert count["request_sha256"] == budget_tool.sha(payload())
    assert t.requests[0][:2] == ("api.openai.com", "/v1/responses/input_tokens")
    assert t.requests[0][2] == {k: payload()[k] for k in ("model", "input", "text", "tools")}


@pytest.mark.parametrize("unknown_usage", [False, True])
def test_reserved_runner_actual_provider_stops_on_missing_usage(
    tmp_path, budget_tool, unknown_usage
):
    from test_openai_provider import Authentication, Transport, context, response

    from interview_backend.evaluation.openai_provider import OpenAIProvider, OpenAISettings
    from interview_backend.evaluation.provider import build_coaching_prompt

    evaluation = tool("provider_eval")
    prompt = build_coaching_prompt(context())
    usage = {} if unknown_usage else {"usage": {"input_tokens": 100, "output_tokens": 10}}
    transport = Transport(value=response(**usage))
    providers = {
        e: OpenAIProvider(Authentication(), transport=transport, settings=OpenAISettings(effort=e))
        for e in ("low", "medium")
    }
    payloads = [budget_tool.request_payload(p, prompt) for p in providers.values()]
    counts = [{"request_sha256": budget_tool.sha(p), "input_tokens": 100} for p in payloads]
    with (tmp_path / "ledger").open("x", encoding="utf-8") as stream:
        b = budget_tool.Budget(stream, payloads, counts, "1.00")
        for p in providers.values():
            p.transport = budget_tool.ReservedTransport(b, transport)
        if unknown_usage:
            with pytest.raises(ValueError, match="UsageUnknown"):
                evaluation.run_reserved(
                    tmp_path / "results", [({"name": "synthetic"}, prompt)], providers, b, {}, []
                )
            assert len(transport.requests) == 1 and b.frozen
        else:
            evaluation.run_reserved(
                tmp_path / "results", [({"name": "synthetic"}, prompt)], providers, b, {}, []
            )
            assert len(transport.requests) == 2 and b.reserved == 0


def test_runner_stale_pricing_approval_stops_before_auth(tmp_path, monkeypatch):
    import hashlib
    import sys
    from pathlib import Path
    from uuid import uuid4

    evaluation = tool("provider_eval")
    approval = {
        "model": "gpt-6-luna",
        "paid_eval_authorized": True,
        "max_calls": 38,
        "token_count_authorized": True,
        "max_count_requests": 38,
        "max_cost_usd": "1.00",
        "pricing_verified_on": "2000-01-01",
    }
    raw = json.dumps(approval).encode()
    path = tmp_path / "approval"
    path.write_bytes(raw)
    output = Path(__file__).parents[2] / ".p4-artifacts" / (str(uuid4()) + ".json")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "provider_eval",
            "--live",
            "--output",
            str(output),
            "--approval",
            str(path),
            "--approval-sha256",
            hashlib.sha256(raw).hexdigest(),
        ],
    )
    monkeypatch.setattr(
        evaluation,
        "select_provider",
        lambda env: pytest.fail("No auth/provider creation permitted"),
    )
    with pytest.raises(ValueError, match="SameDayOfficialPricingReviewRequired"):
        evaluation.main()
    assert not output.exists()


def test_runner_failed_worker_smoke_stops_before_local_auth(tmp_path, monkeypatch):
    import hashlib
    import sys
    from datetime import UTC, datetime
    from pathlib import Path
    from uuid import uuid4

    evaluation = tool("provider_eval")
    monkeypatch.setattr(evaluation, "checked_pricing", lambda value: None)
    budget = tool("eval_budget")
    auth = {"mode": "wif", "issuer": "observed", "subject": "arn:aws:iam::123456789012:role/eval"}
    auth_path, smoke_path = tmp_path / "auth", tmp_path / "smoke"
    auth_raw, smoke_raw = json.dumps(auth).encode(), json.dumps({"status": "FAILED"}).encode()
    auth_path.write_bytes(auth_raw)
    smoke_path.write_bytes(smoke_raw)
    approval = {
        "model": "gpt-6-luna",
        "paid_eval_authorized": True,
        "max_calls": 38,
        "token_count_authorized": True,
        "max_count_requests": 38,
        "max_cost_usd": "1.00",
        "pricing_verified_on": datetime.now(UTC).date().isoformat(),
        "pricing_sha256": budget.pricing_hash(),
        "authentication": auth,
        "authentication_readback_path": str(auth_path),
        "authentication_readback_sha256": hashlib.sha256(auth_raw).hexdigest(),
        "worker_smoke_readback_path": str(smoke_path),
        "worker_smoke_readback_sha256": hashlib.sha256(smoke_raw).hexdigest(),
        "account_id": "123456789012",
        "region": "ap-northeast-1",
    }
    raw = json.dumps(approval).encode()
    path = tmp_path / "approval"
    path.write_bytes(raw)
    output = Path(__file__).parents[2] / ".p4-artifacts" / (str(uuid4()) + ".json")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "provider_eval",
            "--live",
            "--output",
            str(output),
            "--approval",
            str(path),
            "--approval-sha256",
            hashlib.sha256(raw).hexdigest(),
        ],
    )
    monkeypatch.setattr(
        evaluation,
        "select_provider",
        lambda env: pytest.fail("No auth permitted after failed Worker Smoke"),
    )
    with pytest.raises(ValueError, match="SuccessfulSameAccountWorkerWIFSmokeRequired"):
        evaluation.main()
    assert not output.exists()
