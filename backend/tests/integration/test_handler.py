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
    assert result["headers"] == {"Content-Type": "application/json", "Allow": allowed}
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
