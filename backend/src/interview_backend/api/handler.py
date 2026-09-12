"""Authorizer-event adapter only: do not expose this as a public unauthenticated server."""

import base64
import binascii
import json
import re

from interview_backend.application.service import Application
from interview_backend.models.internal import BusinessError, Reply
from interview_backend.models.public import InvalidIdentifier

ROUTES = (
    ("POST", re.compile(r"^/sessions$"), "create"),
    ("GET", re.compile(r"^/sessions/([^/]+)/question$"), "question"),
    ("POST", re.compile(r"^/sessions/([^/]+)/answers$"), "submit"),
    ("GET", re.compile(r"^/evaluations/([^/]+)$"), "evaluation"),
    ("GET", re.compile(r"^/attempts/([^/]+)/feedback$"), "feedback"),
    ("POST", re.compile(r"^/sessions/([^/]+)/questions/next$"), "next_question"),
)
MESSAGES = {
    "VALIDATION_ERROR": "Invalid request.",
    "UNAUTHORIZED": "Authentication required.",
    "SESSION_NOT_FOUND": "Session not found.",
    "ATTEMPT_NOT_FOUND": "Attempt not found.",
    "SESSION_STATE_CONFLICT": "Session state conflicts with this operation.",
    "IDEMPOTENCY_CONFLICT": "Idempotency key conflicts with this request.",
    "EVALUATION_NOT_COMPLETED": "Evaluation is not completed.",
    "NOT_FOUND": "Route not found.",
    "METHOD_NOT_ALLOWED": "Method not allowed.",
    "INTERNAL_SERVER_ERROR": "An internal error occurred.",
}


def response(reply: Reply) -> dict:
    return {
        "statusCode": reply.status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(reply.body, ensure_ascii=True, allow_nan=False),
    }


def error(status: int, code: str) -> dict:
    return response(Reply(status, {"code": code, "message": MESSAGES[code]}))


def reject_json_constant(value: str) -> None:
    raise ValueError("Non-JSON numeric constant")


def parse_body(event: dict) -> dict:
    raw = event.get("body")
    if not isinstance(raw, str):
        raise BusinessError(400, "VALIDATION_ERROR")
    try:
        if event.get("isBase64Encoded", False):
            raw = base64.b64decode(raw, validate=True).decode("utf-8")
        payload = json.loads(raw, parse_constant=reject_json_constant)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise BusinessError(400, "VALIDATION_ERROR") from exc
    if not isinstance(payload, dict):
        raise BusinessError(400, "VALIDATION_ERROR")
    return payload


class Handler:
    def __init__(self, application: Application):
        self.application = application

    def __call__(self, event: dict, context: object = None) -> dict:
        try:
            request_context = event.get("requestContext") or {}
            owner = (
                ((request_context.get("authorizer") or {}).get("jwt") or {}).get("claims") or {}
            ).get("sub")
            if not isinstance(owner, str) or not owner.strip():
                return error(401, "UNAUTHORIZED")
            method = (request_context.get("http") or {}).get("method", "")
            path = event.get("rawPath", "")
            allowed_methods: set[str] = set()
            for expected_method, pattern, action in ROUTES:
                match = pattern.fullmatch(path)
                if not match:
                    continue
                allowed_methods.add(expected_method)
                if method != expected_method:
                    continue
                args = [owner]
                if method == "POST":
                    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
                    args.append(headers.get("idempotency-key"))
                args.extend(match.groups())
                if method == "POST":
                    args.append(parse_body(event))
                # Application validation failures only; unrelated ValueError is a 500.
                try:
                    reply = getattr(self.application, action)(*args)
                except InvalidIdentifier as exc:
                    raise BusinessError(400, "VALIDATION_ERROR") from exc
                return response(reply)
            if allowed_methods:
                result = error(405, "METHOD_NOT_ALLOWED")
                result["headers"]["Allow"] = ", ".join(sorted(allowed_methods))
                return result
            return error(404, "NOT_FOUND")
        except BusinessError as exc:
            return error(exc.status, exc.code)
        except Exception:
            # Do not log the event, exception message, credentials or answer text.
            return error(500, "INTERNAL_SERVER_ERROR")
