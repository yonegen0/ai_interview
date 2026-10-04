"""Deterministic, retry-free model; all AWS latency inputs are assumptions."""

import heapq
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Assumptions:
    quota: int = 1000
    other_concurrency: int = 4  # dispatcher/recovery and other workloads
    sdk_seconds: float = 0.010
    network_seconds: float = 0.050
    init_seconds: float = 0.660624  # local import proxy, NOT AWS Init Duration
    delivery_seconds: float = 1.0
    cpu_multiplier: float = 1.0
    warm: bool = False
    rate: float = 20.0
    burst: int = 30
    account_rate: float = 10000.0  # unverified account throttle assumption
    account_burst: int = 5000


class Bucket:
    def __init__(self, rate, burst):
        self.rate, self.burst, self.tokens, self.at = rate, burst, float(burst), 0.0

    def available(self, at):
        self.tokens = min(self.burst, self.tokens + (at - self.at) * self.rate)
        self.at = at
        return self.tokens >= 1 - 1e-9

    def take(self):
        self.tokens -= 1


class LambdaPool:
    def __init__(self, capacity, warm=False):
        self.capacity = capacity
        self.created = capacity if warm else 0
        self.ready = self.created
        self.running = []
        self.peak = self.cold = 0

    def invoke(self, at, duration, init):
        while self.running and self.running[0] <= at + 1e-9:
            heapq.heappop(self.running)
            self.ready += 1
        if self.ready:
            self.ready -= 1
        elif self.created < self.capacity:
            self.created += 1
            self.cold += 1
            duration += init
        else:
            return None
        heapq.heappush(self.running, at + duration)
        self.peak = max(self.peak, len(self.running))
        return at + duration


def simulate(answer_arrivals=(), *, plain_requests=(), assumptions=None):
    a = assumptions or Assumptions()
    # Reserve both worker lanes plus explicitly supplied other occupied capacity.
    pool = LambdaPool(max(0, a.quota - a.other_concurrency - 2), a.warm)
    route_buckets = {}
    account = Bucket(a.account_rate, a.account_burst)
    events, serial = [], 0

    def enqueue(at, route, evaluation=None):
        nonlocal serial
        serial += 1
        heapq.heappush(events, (at, serial, route, evaluation))

    for i, at in enumerate(answer_arrivals):
        enqueue(at, "answer", i)
    for at, route in plain_requests:
        enqueue(at, route)
    workers = [(0.0, 0), (0.0, 1)]
    heapq.heapify(workers)
    initialized = {0: a.warm, 1: a.warm}
    terminals, observed = {}, {}
    latencies = []
    rejected = {"route_429": 0, "account_429": 0, "lambda_throttle": 0}
    route_counts = {}
    worker_duration = 0.012602 * a.cpu_multiplier + 10 * a.sdk_seconds
    while events:
        at, _, route, evaluation = heapq.heappop(events)
        bucket = route_buckets.setdefault(route, Bucket(a.rate, a.burst))
        if not bucket.available(at):
            rejected["route_429"] += 1
            continue
        if not account.available(at):
            rejected["account_429"] += 1
            continue
        bucket.take()
        account.take()
        sdk_calls = 3 if route == "answer" else 1
        cpu = (0.002309 if route == "answer" else 0.002393) * a.cpu_multiplier
        # Network time affects client latency, not Lambda concurrency occupancy.
        end = pool.invoke(at, cpu + sdk_calls * a.sdk_seconds, 0 if a.warm else a.init_seconds)
        if end is None:
            rejected["lambda_throttle"] += 1
            continue
        response = end + a.network_seconds
        latencies.append(response - at)
        route_counts[route] = route_counts.get(route, 0) + 1
        if route == "answer":
            available, lane = heapq.heappop(workers)
            dispatch = 0.002393 * a.cpu_multiplier + 4 * a.sdk_seconds
            start = max(available, end + dispatch + a.delivery_seconds)
            initialization = 0 if initialized[lane] else a.init_seconds
            initialized[lane] = True
            terminal = start + initialization + worker_duration
            terminals[evaluation] = terminal
            heapq.heappush(workers, (terminal, lane))
            enqueue(response, "evaluation", evaluation)  # immediate GET
        elif route == "evaluation" and evaluation is not None:
            if at >= terminals[evaluation]:
                enqueue(response, "feedback", evaluation)
            else:
                enqueue(response + 2, "evaluation", evaluation)
        elif route == "feedback" and evaluation is not None:
            observed[evaluation] = response
            enqueue(response, "session")
            enqueue(response, "next_question")
    latencies.sort()
    p95 = latencies[math.ceil(len(latencies) * 0.95) - 1] if latencies else None
    completed = len(observed)
    elapsed = max(observed.values()) - min(answer_arrivals) if observed else None
    reasons = [key for key, value in rejected.items() if value]
    if p95 is not None and p95 > 2:
        reasons.append("api_p95_above_2_seconds")
    if answer_arrivals and (completed != len(answer_arrivals) or elapsed > 30):
        reasons.append("all_results_not_received_within_30_seconds")
    return {
        "verdict": "MODEL_FAIL" if reasons else "MODEL_PASS_WITH_ASSUMPTIONS",
        "failure_reasons": reasons,
        "rejections": rejected,
        "accepted_requests": len(latencies),
        "route_requests": route_counts,
        "api_p95_seconds": p95,
        "results_received": completed,
        "all_results_seconds": elapsed,
        "cold_api_environments": pool.cold,
        "peak_concurrency_bound": pool.peak + 2 + a.other_concurrency,
        "quota_headroom": a.quota - pool.peak - 2 - a.other_concurrency,
        "retry_count": 0,
        "retry_free_request_success_ratio": len(latencies)
        / (len(latencies) + sum(rejected.values()))
        if latencies or any(rejected.values())
        else 1.0,
    }


def scenarios():
    return {
        "normal_5rps_60s": ([], [(i / 5, "session") for i in range(300)]),
        "30_people_polling_60s": (
            [],
            [(t + i / 30, "evaluation") for t in range(0, 60, 2) for i in range(30)],
        ),
        "30_answers_1s": ([i / 30 for i in range(30)], []),
        "30_answers_2s": ([i / 15 for i in range(30)], []),
        "mixed": (
            [i / 10 for i in range(10)],
            [(t + i / 10, "evaluation") for t in range(0, 10, 2) for i in range(10)]
            + [
                (i / 10, route)
                for i in range(10)
                for route in ("feedback", "session", "next_question")
            ],
        ),
        "exact_simultaneous_stress": ([0.0] * 30, []),
    }
