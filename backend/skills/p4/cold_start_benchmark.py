"""Interleaved fresh-process import/composition proxy; never an AWS performance Gate."""

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
from pathlib import Path

CHILD = r"""
import contextlib, io, json, socket, sys, time
from types import SimpleNamespace
def forbidden(*args, **kwargs):
    raise RuntimeError("OfflineBoundaryViolation")
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
socket.create_connection = forbidden
started = time.perf_counter()
from interview_backend import aws_runtime
imported = time.perf_counter()
worker_imported = "interview_backend.evaluation.worker" in sys.modules
aws_runtime.client_for = lambda region: object()
entry = aws_runtime.build_entry("api")
built = time.perf_counter()
ctx = SimpleNamespace(
    invoked_function_arn="arn:aws:lambda:ap-northeast-1:123456789012:function:ai-interview-dev-api:live",
    get_remaining_time_in_millis=lambda: 60000,
)
with contextlib.redirect_stdout(io.StringIO()):
    response = entry({"version": "2.0", "requestContext": {}}, ctx)
assert response["statusCode"] == 401
ended = time.perf_counter()
print(json.dumps({"import_ms": (imported-started)*1000,
    "composition_ms": (built-imported)*1000, "first_auth_rejection_ms": (ended-built)*1000,
    "combined_proxy_ms": (ended-started)*1000, "worker_imported_before_api": worker_imported}))
"""


def environment(source, dependencies=None):
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.upper().startswith(
            ("AWS_", "TF_", "P4_", "GH_", "GITHUB_", "INTERVIEW_", "PYTHON")
        )
    }
    env.update(
        PYTHONPATH=os.pathsep.join(
            [str(source / "backend/src")] + ([str(dependencies)] if dependencies else [])
        ),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONNOUSERSITE="1",
        AWS_EC2_METADATA_DISABLED="true",
        INTERVIEW_COMPONENT="api",
        INTERVIEW_ACCOUNT_ID="123456789012",
        INTERVIEW_REGION="ap-northeast-1",
        INTERVIEW_TABLE_NAME="ai-interview-dev-main",
        INTERVIEW_FUNCTION_NAME="ai-interview-dev-api",
        INTERVIEW_QUEUE_ARN="arn:aws:sqs:ap-northeast-1:123456789012:ai-interview-dev-main",
        INTERVIEW_QUEUE_URL="https://sqs.ap-northeast-1.amazonaws.com/123456789012/ai-interview-dev-main",
        INTERVIEW_STREAM_ARN="arn:aws:dynamodb:ap-northeast-1:123456789012:table/ai-interview-dev-main/stream/2026-09-13T00:00:00.000",
        INTERVIEW_SCHEDULE_ARN="arn:aws:scheduler:ap-northeast-1:123456789012:schedule/ai-interview-dev/recovery",
        INTERVIEW_CLIENT_ID="testclient123",
        INTERVIEW_USER_POOL_ID="ap-northeast-1_test123",
        INTERVIEW_API_ID="testapi123",
        INTERVIEW_STAGE="dev",
    )
    return env


def summarize(samples):
    result = {}
    for key in ("import_ms", "composition_ms", "first_auth_rejection_ms", "combined_proxy_ms"):
        values = sorted(sample[key] for sample in samples)
        result[key] = {
            "median": statistics.median(values),
            "p95": values[math.ceil(len(values) * 0.95) - 1],
        }
    return result


def compare(baseline, candidate, *, rounds=20, dependencies=None):
    if not 5 <= rounds <= 100:
        raise ValueError("BenchmarkRoundsOutOfRange")
    samples = {"baseline": [], "candidate": []}
    roots = {"baseline": Path(baseline).resolve(), "candidate": Path(candidate).resolve()}
    for index in range(rounds):
        order = ("baseline", "candidate") if index % 2 == 0 else ("candidate", "baseline")
        for label in order:
            root = roots[label]
            child = subprocess.run(
                [sys.executable, "-B", "-c", CHILD],
                cwd=root,
                env=environment(root, dependencies),
                capture_output=True,
                check=True,
                timeout=30,
            )
            samples[label].append(json.loads(child.stdout))
    return {
        "status": "LOCAL_PROXY_ONLY",
        "rounds_per_source": rounds,
        "python": sys.version.split()[0],
        "summaries": {label: summarize(rows) for label, rows in samples.items()},
        "samples": samples,
        "aws_requests": 0,
        "limitations": [
            "SDK_FACTORY_STUBBED",
            "AUTH_REJECTION_NOT_SUCCESSFUL_BUSINESS_REQUEST",
            "NO_LAMBDA_CPU_OR_NETWORK_MEASUREMENT",
            "OFFICIAL_COLD_START_GATE_UNCHANGED",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument(
        "--dependencies", help="Optional verified Linux expanded ZIP dependency path"
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = compare(
        args.baseline, args.candidate, rounds=args.rounds, dependencies=args.dependencies
    )
    with Path(args.output).open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({"status": result["status"], "summaries": result["summaries"]}))


if __name__ == "__main__":
    main()
