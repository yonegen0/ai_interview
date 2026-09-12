"""Same JSON corpus as frontend Zod, plus exact real Handler response comparison."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from interview_backend.demo import demo_event
from interview_backend.models.public import (
    ActiveAttempt,
    Created,
    CreateRequest,
    ErrorBody,
    EvaluationResult,
    Feedback,
    NextRequest,
    SessionResponse,
    SubmitRequest,
    evaluation_adapter,
)

FIXTURES = json.loads(
    (Path(__file__).parents[3] / "contracts/backend-fixtures.json").read_text(encoding="utf-8")
)
MODELS = {
    "attempt": ActiveAttempt,
    "create": CreateRequest,
    "created": Created,
    "error": ErrorBody,
    "feedback": Feedback,
    "next": NextRequest,
    "session": SessionResponse,
    "submit": SubmitRequest,
}


def validate(schema, value):
    if schema == "evaluation":
        return evaluation_adapter.validate_python(value)
    return MODELS[schema].model_validate(value)


@pytest.mark.parametrize("case", FIXTURES["cases"], ids=lambda case: case["label"])
def test_shared_validation(case):
    if case["valid"]:
        validate(case["schema"], case["value"])
    else:
        with pytest.raises(ValidationError):
            validate(case["schema"], case["value"])


@pytest.mark.parametrize("case", FIXTURES["scoreCases"], ids=lambda case: case["label"])
def test_score_json_compatibility(runtime, case):
    score = json.loads(case["scoreJson"])
    value = {"score": score, "summary": "", "strengths": [], "improvements": []}
    feedback = next(item["value"] for item in FIXTURES["cases"] if item["schema"] == "feedback")
    for model, payload in [(EvaluationResult, value), (Feedback, {**feedback, "score": score})]:
        if case["valid"]:
            result = model.model_validate(payload).wire()
            assert type(result["score"]) is int
            assert result["score"] == score
        else:
            with pytest.raises(ValidationError):
                model.model_validate(payload)

    created = runtime.handler(
        demo_event(
            "POST",
            "/sessions",
            {"category": "career", "difficulty": "standard"},
            "20000000-0000-4000-8000-000000000001",
        )
    )
    session_id = json.loads(created["body"])["sessionId"]
    session = runtime.handler(demo_event("GET", f"/sessions/{session_id}/question"))
    question_id = json.loads(session["body"])["question"]["id"]
    reply = runtime.handler(
        demo_event(
            "POST",
            f"/sessions/{session_id}/answers",
            {"questionId": question_id, "answer": "回答"},
            "20000000-0000-4000-8000-000000000002",
        )
    )
    accepted = json.loads(reply["body"])
    runtime.provider.behavior = lambda _: value
    runtime.worker.run(accepted["evaluationId"])
    state = runtime.handler(demo_event("GET", f"/evaluations/{accepted['evaluationId']}"))
    assert json.loads(state["body"])["status"] == ("completed" if case["valid"] else "failed")
    if case["valid"]:
        response = runtime.handler(demo_event("GET", f"/attempts/{accepted['attemptId']}/feedback"))
        assert type(json.loads(response["body"])["score"]) is int


def test_handler_fixture_flow(runtime):
    for step in FIXTURES["steps"]:
        if "worker" in step:
            if step.get("fail"):
                runtime.provider.behavior = lambda _: {"score": True}
            assert runtime.worker.run(step["worker"])
            continue
        result = runtime.handler(
            demo_event(step["method"], step["path"], step.get("request"), step.get("key"))
        )
        assert result["statusCode"] == step["status"]
        assert result["headers"]["Content-Type"] == "application/json"
        body = json.loads(result["body"])
        assert body == step["body"]
        validate(step["schema"], body)


@pytest.mark.parametrize(
    "case",
    [case for case in FIXTURES["cases"] if case["schema"] in {"create", "submit"}],
    ids=lambda case: case["label"],
)
def test_input_fixtures_through_json_handler(runtime, case):
    if case["schema"] == "create":
        event = demo_event(
            "POST", "/sessions", case["value"], "20000000-0000-4000-8000-000000000001"
        )
    else:
        session = runtime.handler(
            demo_event(
                "POST",
                "/sessions",
                {"category": "job_change", "difficulty": "standard"},
                "20000000-0000-4000-8000-000000000001",
            )
        )
        session_id = json.loads(session["body"])["sessionId"]
        event = demo_event(
            "POST",
            f"/sessions/{session_id}/answers",
            case["value"],
            "20000000-0000-4000-8000-000000000002",
        )
    result = runtime.handler(event)
    assert (result["statusCode"] < 300) == case["valid"]
    if not case["valid"]:
        assert result["statusCode"] == 400
    elif case["schema"] == "submit":
        accepted = json.loads(result["body"])
        runtime.worker.run(accepted["evaluationId"])
        feedback = runtime.handler(demo_event("GET", f"/attempts/{accepted['attemptId']}/feedback"))
        assert feedback["statusCode"] == 200
        assert json.loads(feedback["body"])["answer"] == case["value"]["answer"]
