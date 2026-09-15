"""Deterministic same-process demo; prints IDs/status only, never answer or prompt."""

import json
from datetime import UTC, datetime
from itertools import count

from interview_backend.bootstrap import build_runtime


def demo_event(
    method: str,
    path: str,
    payload: dict | None = None,
    key: str | None = None,
    owner: str = "local-demo-user",
) -> dict:
    return {
        "version": "2.0",
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {"jwt": {"claims": {"sub": owner}}},
        },
        "headers": {"Idempotency-Key": key} if key else {},
        "body": json.dumps(payload, ensure_ascii=True) if payload is not None else None,
        "isBase64Encoded": False,
    }


def main() -> None:
    ids = count(1)
    runtime = build_runtime(
        new_id=lambda: f"10000000-0000-4000-8000-{next(ids):012d}",
        clock=lambda: datetime(2026, 9, 11, tzinfo=UTC),
    )

    def call(event: dict, expected: int) -> dict:
        reply = runtime.handler(event)
        if reply["statusCode"] != expected:
            raise RuntimeError("Demo status mismatch")
        body = json.loads(reply["body"])
        print(
            event["requestContext"]["http"]["method"],
            event["rawPath"],
            reply["statusCode"],
            body.get("status", body.get("code", "ok")),
        )
        return body

    session = call(
        demo_event(
            "POST",
            "/sessions",
            {"category": "job_change", "difficulty": "standard"},
            "20000000-0000-4000-8000-000000000001",
        ),
        201,
    )["sessionId"]
    question_path = f"/sessions/{session}/question"
    question = call(demo_event("GET", question_path), 200)["question"]
    request = demo_event(
        "POST",
        f"/sessions/{session}/answers",
        {"questionId": question["id"], "answer": "経験を活かし、新しい業務に挑戦したいです。"},
        "20000000-0000-4000-8000-000000000002",
    )
    accepted = call(request, 202)
    evaluation_path = f"/evaluations/{accepted['evaluationId']}"
    if call(demo_event("GET", evaluation_path), 200)["status"] != "processing":
        raise RuntimeError("Worker must not have run")
    runtime.dispatcher.dispatch("local-demo-user", accepted["evaluationId"], 1)
    for event in runtime.publisher.events:
        runtime.worker.run(event["ownerSub"], event["evaluationId"], event["dispatchVersion"])
    if call(demo_event("GET", evaluation_path), 200)["status"] != "completed":
        raise RuntimeError("Worker did not complete")
    call(demo_event("GET", f"/attempts/{accepted['attemptId']}/feedback"), 200)
    if call(request, 202) != accepted:
        raise RuntimeError("Replay differs")
    call(
        demo_event(
            "POST",
            f"/sessions/{session}/questions/next",
            {"fromAttemptId": accepted["attemptId"]},
            "20000000-0000-4000-8000-000000000003",
        ),
        200,
    )
    call(demo_event("GET", question_path, owner="other-user"), 404)
    print("Demo completed: local memory + Fake Provider only.")


if __name__ == "__main__":
    main()
