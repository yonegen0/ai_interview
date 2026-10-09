"""Synthetic HTTP-contract campaign plus offline Fake/Memory driver; no live CLI."""

import argparse
import json
import math
import statistics
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from time import monotonic, sleep
from uuid import uuid4

from interview_backend.bootstrap import build_runtime
from interview_backend.demo import demo_event
from interview_backend.evaluation.provider import FakeProvider


class CampaignFailure(Exception):
    pass


def campaign(clients, *, after_submit=lambda rows: None, timeout=30, poll_seconds=2):
    """Caller supplies already-approved synthetic clients. Never login/enable/retry POST.

    Live use is an AWS write and may charge AI. This function has no live CLI path.
    The approved runner must verify current manifest/State, owner allowlist, source,
    concurrency, budgets, and authorization before supplying auth_e2e.Api clients.
    """
    if not 2 <= len(clients) <= 30 or not 0 < timeout <= 30 or not 0 < poll_seconds <= 2:
        raise ValueError("InvalidCampaignBounds")
    latency = []
    latency_lock = Lock()

    def call(client, method, path, payload=None, key=None):
        at = monotonic()
        result = client.call(method, path, payload, key)
        with latency_lock:
            latency.append((monotonic() - at) * 1000)
        return result

    prepared = []
    for client in clients:
        status, body, _ = call(
            client,
            "POST",
            "/sessions",
            {"mode": "category", "category": "job_change", "difficulty": "standard"},
            str(uuid4()),
        )
        if status != 201:
            raise CampaignFailure("SessionPreparationFailed")
        session = body["sessionId"]
        status, question, _ = call(client, "GET", f"/sessions/{session}/question")
        if status != 200:
            raise CampaignFailure("QuestionPreparationFailed")
        prepared.append((client, session, question["question"]["id"], str(uuid4())))
    barrier = Barrier(len(clients))
    started = monotonic()

    def submit(row):
        client, session, question, key = row
        barrier.wait(timeout=15)
        status, accepted, _ = call(
            client,
            "POST",
            f"/sessions/{session}/answers",
            {
                "kind": "initial_answer",
                "questionId": question,
                "answer": "検証用です。担当案件で問題を整理し、関係者へ提案して改善しました。",
            },
            key,
        )
        if status != 202:
            raise CampaignFailure("AnswerAcceptanceFailed")
        return {"client": client, "accepted": accepted, "submitted_at": monotonic()}

    with ThreadPoolExecutor(max_workers=len(clients)) as pool:
        rows = list(pool.map(submit, prepared))
    accepted_at = monotonic() - started
    after_submit(rows)

    def observe(row):
        client, accepted = row["client"], row["accepted"]
        polls = 0
        while monotonic() - started <= timeout:
            status, result, _ = call(client, "GET", f"/evaluations/{accepted['evaluationId']}")
            polls += 1
            if status != 200 or result.get("status") not in {"processing", "completed", "failed"}:
                raise CampaignFailure("EvaluationReadFailed")
            if result["status"] != "processing":
                feedback_status = None
                if result["status"] == "completed":
                    feedback_status, _, _ = call(
                        client, "GET", f"/attempts/{accepted['attemptId']}/feedback"
                    )
                return {
                    "status": result["status"],
                    "polls": polls,
                    "observed_seconds": monotonic() - started,
                    "feedback_status": feedback_status,
                }
            sleep(poll_seconds)
        return {"status": "not_observed_by_gate", "polls": polls, "feedback_status": None}

    with ThreadPoolExecutor(max_workers=len(clients)) as pool:
        outcomes = list(pool.map(observe, rows))
    latency.sort()
    return {
        "status": "CAMPAIGN_OBSERVED",
        "participants": len(clients),
        "accepted": len(rows),
        "acceptance_batch_seconds": accepted_at,
        "completed": sum(row["status"] == "completed" for row in outcomes),
        "failed": sum(row["status"] == "failed" for row in outcomes),
        "unobserved": sum(row["status"] == "not_observed_by_gate" for row in outcomes),
        "feedback_ok": sum(row["feedback_status"] == 200 for row in outcomes),
        "all_results_seconds": max(row.get("observed_seconds", timeout) for row in outcomes),
        "api_proxy_p95_ms": latency[math.ceil(len(latency) * 0.95) - 1],
        "api_proxy_median_ms": statistics.median(latency),
        "poll_requests": sum(row["polls"] for row in outcomes),
        "outcomes": outcomes,
        "request_retries": 0,
    }


def wave_sensitivity():
    """Lower bound only: exclude delivery/init/storage/network/retries/poll latency."""
    return [
        {
            "worker_seconds_assumed": duration,
            "participants": 30,
            "worker_lanes": 2,
            "last_terminal_lower_bound_seconds": 15 * duration,
            "completion_30s_possible_before_overheads": 15 * duration < 30,
            "sustainable_evaluations_per_minute_upper_bound": 120 / duration,
        }
        for duration in (0.5, 1, 2, 5, 20, 40)
    ]


def offline(*, participants=30, provider_delay=0.02, poll_seconds=0.05):
    if not 0 <= provider_delay <= 1:
        raise ValueError("OfflineDelayOutOfRange")
    guard = Lock()
    active = peak = 0
    template = FakeProvider()

    def behavior(prompt):
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        try:
            sleep(provider_delay)
            return template.evaluate(prompt)
        finally:
            with guard:
                active -= 1

    provider = FakeProvider(behavior)
    runtime = build_runtime(provider=provider)

    class Client:
        def __init__(self, owner):
            self.owner = owner

        def call(self, method, path, payload=None, key=None):
            reply = runtime.handler(demo_event(method, path, payload, key, self.owner))
            return reply["statusCode"], json.loads(reply["body"]), reply.get("headers", {})

    clients = [Client(f"synthetic-load-{index:02d}") for index in range(participants)]
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = []

        def dispatch(rows):
            for row in rows:
                runtime.dispatcher.dispatch(row["client"].owner, row["accepted"]["evaluationId"], 1)
            for event in runtime.publisher.events:
                futures.append(
                    workers.submit(
                        runtime.worker.run,
                        event["ownerSub"],
                        event["evaluationId"],
                        event["dispatchVersion"],
                    )
                )

        observed = campaign(clients, after_submit=dispatch, poll_seconds=poll_seconds)
        assert all(future.result() for future in futures)
    observed.update(
        status="OFFLINE_FAKE_MEMORY_ONLY",
        provider_calls=provider.calls,
        peak_provider_concurrency=peak,
        worker_lanes=2,
        sdk_requests=0,
        paid_ai_calls=0,
        sensitivity=wave_sensitivity(),
        limitations=[
            "NO_GATEWAY_THROTTLING",
            "NO_DDB_NETWORK",
            "NO_SQS_DELIVERY_OR_DLQ",
            "NO_REAL_PROVIDER",
            "FASTER_POLLING_THAN_LIVE",
            "NO_FORMAL_PERFORMANCE_GATE_PASS",
        ],
    )
    return observed


def main():
    import socket

    import boto3.session
    import botocore.httpsession

    def forbidden(*args, **kwargs):
        raise RuntimeError("OfflineBoundaryViolation")

    socket.socket.connect = forbidden
    socket.socket.connect_ex = forbidden
    socket.create_connection = forbidden
    botocore.httpsession.URLLib3Session.send = forbidden
    boto3.session.Session.client = forbidden

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--participants", type=int, default=30)
    parser.add_argument("--provider-delay", type=float, default=0.02)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = offline(participants=args.participants, provider_delay=args.provider_delay)
    with open(args.output, "x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "status",
                    "accepted",
                    "completed",
                    "failed",
                    "unobserved",
                    "peak_provider_concurrency",
                    "all_results_seconds",
                    "api_proxy_p95_ms",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
