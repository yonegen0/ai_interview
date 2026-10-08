"""Offline corpus/aggregation and explicitly gated paid runner. No live call by default."""

import argparse
import hashlib
import json
import os
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_budget import (  # noqa: E402
    Budget,
    ReservedTransport,
    bind_authentication,
    checked_pricing,
    count_request,
    money,
    pricing_hash,
    request_payload,
    sha,
)

from interview_backend.assets import load_questions  # noqa: E402
from interview_backend.evaluation.openai_provider import (  # noqa: E402
    OpenAIProvider,
    ProviderFailure,
)
from interview_backend.evaluation.provider import build_coaching_prompt  # noqa: E402
from interview_backend.evaluation.selection import select_provider  # noqa: E402
from interview_backend.models.public import CoachingHistoryItem, CoachingInput  # noqa: E402


def corpus():
    labels = json.loads((ROOT / "contracts/gpt6-luna-eval.json").read_bytes())
    facts = json.loads((ROOT / "contracts/coaching-v2-fixtures.json").read_bytes())["facts"]
    rows = labels["scored_cases"] + facts
    result = []
    for r in rows:
        history = tuple(CoachingHistoryItem(**h) for h in r.get("history", []))
        context = CoachingInput(
            question=load_questions()[0].model_copy(
                update={
                    "category": "motivation",
                    "question": "志望する仕事と、その理由・本人の経験を教えてください。",
                }
            ),
            initial_answer=r["initial"],
            coaching_history=history,
            latest_answer=history[-1].answer if history else r["initial"],
            coaching_count=len(history),
            can_ask_follow_up=len(history) < 3,
            unavailable_questions=tuple(r.get("unavailable", [])),
        )
        result.append((r, build_coaching_prompt(context)))
    return result


def cost(usage):
    if not isinstance(usage, dict) or not all(
        k in usage for k in ("input_tokens", "output_tokens")
    ):
        return None
    input_tokens, output_tokens = usage["input_tokens"], usage["output_tokens"]
    cached = usage.get("cached_tokens", 0)
    reasoning = usage.get("reasoning_tokens", 0)
    if not 0 <= cached <= input_tokens or not 0 <= reasoning <= output_tokens:
        raise ValueError("InvalidUsage")
    # Reasoning is already part of output_tokens: never count it twice.
    return ((input_tokens - cached) * 0.10 + cached * 0.01 + output_tokens * 0.50) / 1_000_000


def aggregate(rows):
    score = [r["score_within_one"] for r in rows if r.get("score_within_one") is not None]
    status = [r["status_matches"] for r in rows if r.get("status_matches") is not None]
    result = {
        "evaluations": len(rows),
        "score_within_one_rate": statistics.mean(score) if score else None,
        "status_agreement_rate": statistics.mean(status) if status else None,
        "latency_mean_ms": statistics.mean([r["latency_ms"] for r in rows]) if rows else None,
        "cost_usd_total": sum(r["cost_usd"] for r in rows if r.get("cost_usd") is not None),
        "usage_coverage": sum(r.get("usage") is not None for r in rows),
        "semantic_metrics_require_manual_annotation": True,
    }
    for label in (
        "unnecessary_question",
        "semantic_duplicate",
        "invented_or_misread_fact",
        "correction_or_withdrawal_respected",
    ):
        values = [
            r["annotation"][label] for r in rows if type(r.get("annotation", {}).get(label)) is bool
        ]
        result[label + "_rate"] = statistics.mean(values) if values else None
        result[label + "_coverage"] = len(values)
    return result


def evaluate_one(provider, fixture, prompt, annotation=None):
    began = monotonic()
    try:
        result = provider.evaluate(prompt)
        expected = fixture.get("scores")
        scores = [result[n] for n in ("conclusion_score", "specificity_score", "reasoning_score")]
        row = {
            "case": fixture["name"],
            "result": "completed_call",
            "scores": scores,
            "status": result["status"],
            "score_within_one": all(abs(a - b) <= 1 for a, b in zip(scores, expected, strict=True))
            if expected
            else None,
            "status_matches": result["status"] == fixture["status"]
            if fixture.get("status")
            else None,
        }
    except ProviderFailure as error:
        row = {
            "case": fixture["name"],
            "result": "failed_call",
            "failure": error.kind,
            "score_within_one": False if fixture.get("scores") else None,
            "status_matches": False if fixture.get("status") else None,
        }
    safe_annotation = {
        name: value
        for name, value in (annotation or {}).items()
        if name
        in {
            "unnecessary_question",
            "semantic_duplicate",
            "invented_or_misread_fact",
            "correction_or_withdrawal_respected",
        }
        and type(value) is bool
    }
    row.update(
        latency_ms=(monotonic() - began) * 1000,
        usage=provider.last_observation,
        cost_usd=cost(provider.last_observation),
        annotation=safe_annotation,
    )
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--approval")
    parser.add_argument("--approval-sha256")
    parser.add_argument("--annotations")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    private = ROOT / "backend/.p4-artifacts"
    if not output.is_relative_to(private.resolve()) or output.exists():
        raise ValueError("FreshPrivateOutputRequired")
    cases = corpus()
    if not args.live:
        report = {
            "status": "OFFLINE_CORPUS_READY_NOT_LIVE_EVAL",
            "cases": [r[0]["name"] for r in cases],
            "efforts": ["low", "medium"],
            "paid_calls": 0,
            "reference_labels": "Proposals requiring human calibration",
            "live_results": None,
            "pricing_sha256": pricing_hash(),
            "budget_control": (
                "count exact messages/schema, reserve all calls, stop on unknown usage"
            ),
        }
        with output.open("x", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(json.dumps({"status": report["status"], "cases": len(cases), "paid_calls": 0}))
        return
    if not args.approval or not args.approval_sha256:
        raise ValueError("ExplicitPaidEvaluationApprovalRequired")
    raw = Path(args.approval).read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.approval_sha256:
        raise ValueError("ApprovalHashMismatch")
    approval = json.loads(raw)
    if (
        approval.get("model") != "gpt-6-luna"
        or approval.get("paid_eval_authorized") is not True
        or type(approval.get("max_calls")) is not int
        or not 2 * len(cases) <= approval["max_calls"] <= 38
        or approval.get("token_count_authorized") is not True
        or approval.get("max_count_requests") != 2 * len(cases)
        or not 0 < money(approval.get("max_cost_usd")) <= money("1.00")
    ):
        raise ValueError("ExplicitPaidEvaluationApprovalRequired")
    if approval.get("pricing_verified_on") != datetime.now(UTC).date().isoformat():
        raise ValueError("SameDayOfficialPricingReviewRequired")
    checked_pricing(approval.get("pricing_sha256"))
    mapping_raw = Path(approval["authentication_readback_path"]).read_bytes()
    if hashlib.sha256(mapping_raw).hexdigest() != approval.get(
        "authentication_readback_sha256"
    ) or json.loads(mapping_raw) != approval.get("authentication"):
        raise ValueError("ObservedApprovedAuthenticationRequired")
    if approval["authentication"].get("mode") == "wif":
        smoke_raw = Path(approval["worker_smoke_readback_path"]).read_bytes()
        smoke = json.loads(smoke_raw)
        account = approval.get("account_id")
        expected_subject = f"arn:aws:iam::{account}:role/ai-interview-dev-worker-runtime"
        if (
            hashlib.sha256(smoke_raw).hexdigest() != approval.get("worker_smoke_readback_sha256")
            or smoke.get("status") != "WORKER_WIF_SMOKE_VERIFIED"
            or smoke.get("openai_exchange_verified") is not True
            or smoke.get("paid_responses_calls") != 0
            or smoke.get("subject") != expected_subject
            or smoke.get("issuer") != approval["authentication"].get("issuer")
            or not approval["authentication"]
            .get("subject", "")
            .startswith(f"arn:aws:iam::{account}:")
            or approval.get("region") != "ap-northeast-1"
        ):
            raise ValueError("SuccessfulSameAccountWorkerWIFSmokeRequired")
    providers, payloads = {}, []
    for effort in ("low", "medium"):
        provider = select_provider(dict(os.environ, INTERVIEW_OPENAI_EFFORT=effort))
        if not isinstance(provider, OpenAIProvider):
            raise ValueError("ExplicitOpenAISelectionRequired")
        providers[effort] = provider
        bind_authentication(provider.authentication, approval["authentication"])
        payloads.extend(request_payload(provider, prompt) for _, prompt in cases)
    if approval.get("requests_sha256") != sha(payloads):
        raise ValueError("ApprovedCorpusRequestsRequired")
    annotations = json.loads(Path(args.annotations).read_bytes()) if args.annotations else {}
    rows = []
    budget_directory = private / "eval-budgets"
    budget_directory.mkdir(exist_ok=True)
    budget_path = budget_directory / (args.approval_sha256 + ".jsonl")
    # One durable ledger per exact approval, independent of selected result path.
    with budget_path.open("x", encoding="utf-8") as ledger:
        ledger.write(
            json.dumps(
                {"status": "TOKEN_PREFLIGHT_STARTED", "approval_sha256": args.approval_sha256}
            )
            + "\n"
        )
        ledger.flush()
        os.fsync(ledger.fileno())
        counts = []
        for index, payload in enumerate(payloads):
            effort = "low" if index < len(cases) else "medium"
            count = count_request(payload, providers[effort].authentication)
            counts.append(count)
            ledger.write(json.dumps({"token_count": count}) + "\n")
            ledger.flush()
            os.fsync(ledger.fileno())
        budget = Budget(
            ledger, payloads, counts, approval["max_cost_usd"], max_calls=approval["max_calls"]
        )
        for provider in providers.values():
            provider.transport = ReservedTransport(budget, provider.transport)
        run_reserved(output, cases, providers, budget, annotations, rows)


def run_reserved(output, cases, providers, budget, annotations, rows):
    # An exclusive started journal prevents replay after an uncertain paid run.
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps({"status": "STARTED", "max_calls": 2 * len(cases)}) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
        for effort in ("low", "medium"):
            provider = providers[effort]
            for fixture, prompt in cases:
                stream.write(json.dumps({"started": fixture["name"], "effort": effort}) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                row = evaluate_one(
                    provider, fixture, prompt, annotations.get(fixture["name"] + ":" + effort)
                )
                row["effort"] = effort
                rows.append(row)
                stream.write(json.dumps(row) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                # Auth/HTTP/refusal failures with missing numeric usage halt remaining calls.
                if budget.pending is None:
                    budget.frozen = True
                    budget.record("NO_GENERATION_USAGE_STOP")
                    raise ValueError("NoObservedPaidCallNoFurtherCalls")
                budget.settle(provider.last_observation)
        stream.write(
            json.dumps(
                {
                    "summary": {
                        e: aggregate([r for r in rows if r["effort"] == e])
                        for e in ("low", "medium")
                    }
                }
            )
            + "\n"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(
            "ProviderEvalFailed; private journal preserved, no automatic replay"
        ) from None
