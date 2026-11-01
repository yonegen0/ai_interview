"""HTTP parsing, safe error mapping and demo smoke tests."""

import base64
import json

import pytest
from conftest import uid

from interview_backend.demo import demo_event, main

CREATE = {"category": "job_change", "difficulty": "standard"}


def body(reply):
    return json.loads(reply["body"])


@pytest.mark.parametrize("encoded", [False, True])
def test_case_insensitive_header_and_base64(runtime, encoded):
    event = demo_event("POST", "/sessions", CREATE, uid(100))
    event["headers"] = {"iDeMpOtEnCy-KeY": uid(100)}
    if encoded:
        event["body"] = base64.b64encode(event["body"].encode()).decode()
        event["isBase64Encoded"] = True
    first = runtime.handler(event)
    assert first["statusCode"] == 201
    assert runtime.handler(event) == first


@pytest.mark.parametrize(
    "raw,encoded",
    [
        (None, False),
        ("{", False),
        ("[]", False),
        ("null", False),
        ("42", False),
        ('{"category":NaN}', False),
        ("!not-base64!", True),
        ("/w==", True),
    ],
)
def test_bad_body_returns_fixed_400(runtime, raw, encoded):
    event = demo_event("POST", "/sessions", CREATE, uid(100))
    event.update(body=raw, isBase64Encoded=encoded)
    result = runtime.handler(event)
    assert result["statusCode"] == 400
    assert body(result) == {"code": "VALIDATION_ERROR", "message": "Invalid request."}
    assert not runtime.repository.snapshot().requests


@pytest.mark.parametrize("encoded", [False, True])
def test_oversized_normal_post_rejected_before_json_decode_or_storage(runtime, encoded):
    event = demo_event("POST", "/sessions", CREATE, uid(100))
    raw = json.dumps({**CREATE, "irrelevant": "x" * (350 * 1024)})
    event["body"] = base64.b64encode(raw.encode()).decode() if encoded else raw
    event["isBase64Encoded"] = encoded

    result = runtime.handler(event)
    assert result["statusCode"] == 413
    assert body(result) == {"code": "REQUEST_TOO_LARGE", "message": "Request too large."}
    assert not runtime.repository.snapshot().sessions
    assert not runtime.repository.snapshot().requests


@pytest.mark.parametrize("key", [None, "", "not-a-uuid", 1])
def test_missing_or_bad_idempotency_key(runtime, key):
    event = demo_event("POST", "/sessions", CREATE, key)
    assert runtime.handler(event)["statusCode"] == 400


@pytest.mark.parametrize("owner", [None, "", "  ", 42])
def test_only_authorizer_sub_is_identity(runtime, owner):
    event = demo_event("POST", "/sessions", {**CREATE, "sub": "forged"}, uid(100), owner)
    event["headers"]["Authorization"] = "Bearer fake"
    event["headers"]["sub"] = "forged"
    result = runtime.handler(event)
    assert result["statusCode"] == 401
    assert body(result)["code"] == "UNAUTHORIZED"
    assert not runtime.repository.snapshot().sessions


@pytest.mark.parametrize(
    "method,path,status,code",
    [
        ("GET", "/unknown", 404, "NOT_FOUND"),
        ("GET", "/sessions", 405, "METHOD_NOT_ALLOWED"),
        ("DELETE", f"/evaluations/{uid(999)}", 405, "METHOD_NOT_ALLOWED"),
        ("GET", "/sessions/bad/question", 400, "VALIDATION_ERROR"),
        ("GET", f"/sessions/{uid(999)}/question", 404, "SESSION_NOT_FOUND"),
        ("GET", f"/evaluations/{uid(999)}", 404, "ATTEMPT_NOT_FOUND"),
        ("GET", f"/attempts/{uid(999)}/feedback", 404, "ATTEMPT_NOT_FOUND"),
    ],
)
def test_routing_errors(runtime, method, path, status, code):
    reply = runtime.handler(demo_event(method, path))
    assert reply["statusCode"] == status
    assert body(reply)["code"] == code


@pytest.mark.parametrize("exception", [RuntimeError, ValueError])
def test_internal_error_does_not_leak_or_become_input_error(
    runtime, monkeypatch, exception, capsys
):
    def fail(*_):
        raise exception("secret token and raw answer")

    monkeypatch.setattr(runtime.repository, "create_once", fail)
    result = runtime.handler(demo_event("POST", "/sessions", CREATE, uid(100)))
    assert result["statusCode"] == 500
    assert body(result) == {
        "code": "INTERNAL_SERVER_ERROR",
        "message": "An internal error occurred.",
    }
    captured = capsys.readouterr()
    assert not captured.out and not captured.err


def test_demo_no_sensitive_output(capsys):
    main()
    output = capsys.readouterr().out
    assert "Demo completed" in output
    assert "processing" in output and "completed" in output and "404" in output
    assert "経験を活かし" not in output
    assert "サンプル評価" not in output


def test_invalid_generated_id_is_internal_failure_and_rolls_back(runtime):
    runtime.application.new_id = lambda: "invalid-generated-id"
    result = runtime.handler(demo_event("POST", "/sessions", CREATE, uid(100)))
    assert result["statusCode"] == 500
    assert not runtime.repository.snapshot().sessions
    assert not runtime.repository.snapshot().requests


@pytest.mark.parametrize(
    "path,allowed",
    [
        ("/sessions", "POST"),
        (f"/sessions/{uid(1)}/question", "GET"),
        (f"/sessions/{uid(1)}/answers", "POST"),
        (f"/evaluations/{uid(1)}", "GET"),
        (f"/attempts/{uid(1)}/feedback", "GET"),
        (f"/sessions/{uid(1)}/questions/next", "POST"),
    ],
)
def test_method_not_allowed_header(runtime, path, allowed):
    result = runtime.handler(demo_event("DELETE", path))
    assert result["statusCode"] == 405
    assert result["headers"] == {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
        "Allow": allowed,
    }
    assert json.loads(result["body"]) == {
        "code": "METHOD_NOT_ALLOWED",
        "message": "Method not allowed.",
    }


def test_allow_header_is_not_added_to_other_responses(runtime):
    for event in [
        demo_event("GET", "/unknown"),
        demo_event("POST", "/sessions", {"category": "career", "difficulty": "standard"}, uid(99)),
        {"rawPath": "/sessions", "requestContext": {"http": {"method": "DELETE"}}},
    ]:
        assert "Allow" not in runtime.handler(event)["headers"]


def test_authenticated_api_json_responses_are_not_cacheable(runtime):
    created = runtime.handler(demo_event("POST", "/sessions", CREATE, uid(901)))
    assert created["statusCode"] == 201
    session_id = body(created)["sessionId"]
    responses = (
        created,
        runtime.handler(demo_event("GET", f"/sessions/{session_id}/question")),
        runtime.handler(demo_event("GET", f"/evaluations/{uid(999)}")),
        runtime.handler(demo_event("GET", "/unknown")),
        runtime.handler(demo_event("GET", "/practice-options")),
        runtime.handler(demo_event("DELETE", "/sessions")),
    )
    assert responses[1]["statusCode"] == 200
    for reply in responses:
        assert reply["headers"]["Content-Type"] == "application/json"
        assert reply["headers"].get("Cache-Control") == "no-store"


def test_session_creation_limit_http_contract_and_atomicity(runtime, monkeypatch):
    from interview_backend.repositories import domain

    monkeypatch.setattr(domain, "SESSION_CREATION_MONTHLY_LIMIT", 1)
    first_event = demo_event("POST", "/sessions", CREATE, uid(200))
    first = runtime.handler(first_event)
    assert first["statusCode"] == 201
    assert runtime.handler(first_event) == first
    different = demo_event("POST", "/sessions", CREATE, uid(201))
    limited = runtime.handler(different)
    assert limited["statusCode"] == 429
    assert body(limited) == {
        "code": "SESSION_CREATION_LIMIT",
        "message": "Monthly session creation limit reached.",
    }
    assert "owner" not in limited["body"] and "count" not in limited["body"]
    state = runtime.repository.snapshot()
    assert len(state.sessions) == len(state.requests) == 1
    assert next(iter(state.session_creation_budgets.values())).count == 1
    assert runtime.handler(first_event) == first
    changed = demo_event(
        "POST", "/sessions", {"category": "motivation", "difficulty": "standard"}, uid(200)
    )
    conflict = runtime.handler(changed)
    assert conflict["statusCode"] == 409
    assert body(conflict)["code"] == "IDEMPOTENCY_CONFLICT"
    other = runtime.handler(demo_event("POST", "/sessions", CREATE, uid(202), "independent-owner"))
    assert other["statusCode"] == 201
    final = runtime.repository.snapshot()
    assert len(final.sessions) == len(final.requests) == 2
    assert sorted(b.count for b in final.session_creation_budgets.values()) == [1, 1]
