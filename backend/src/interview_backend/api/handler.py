"""Authorizer-event adapter only: do not expose this as a public unauthenticated server."""

import base64
import binascii
import json
import re

from interview_backend.application.service import Application
from interview_backend.models.internal import BusinessError, Reply
from interview_backend.models.public import InvalidIdentifier

ROUTES = (
    ("GET", re.compile(r"^/practice-options$"), "practice_options"),
    ("POST", re.compile(r"^/sessions$"), "create"),
    ("GET", re.compile(r"^/sessions/([^/]+)/question$"), "question"),
    ("POST", re.compile(r"^/sessions/([^/]+)/answers$"), "submit"),
    ("GET", re.compile(r"^/evaluations/([^/]+)$"), "evaluation"),
    ("GET", re.compile(r"^/attempts/([^/]+)/feedback$"), "feedback"),
    ("POST", re.compile(r"^/sessions/([^/]+)/questions/next$"), "next_question"),
)
MESSAGES = {
    "STAR_REQUEST_NOT_FOUND": "Request not found.",
    "STAR_CONTEXT_NOT_FOUND": "Context not found.",
    "STAR_DRAFT_NOT_FOUND": "Draft not found.",
    "STAR_APPLICATION_NOT_FOUND": "Application not found.",
    "STAR_GENERATION_NOT_FOUND": "Generation not found.",
    "DRAFT_VERSION_CONFLICT": "Draft changed.",
    "DRAFT_CLOSED": "Draft closed.",
    "STAR_GENERATION_IN_PROGRESS": "Generation in progress.",
    "STAR_QUOTA_EXCEEDED": "Generation quota exceeded.",
    "VALIDATION_ERROR": "Invalid request.",
    "FORBIDDEN": "Access denied.",
    "QUESTION_BANK_CONFLICT": "Question bank changed.",
    "QUESTION_BANK_TOO_LARGE": "Question bank too large.",
    "CATEGORY_UNAVAILABLE": "Category unavailable.",
    "SESSION_COMPLETED": "Practice completed.",
    "SESSION_CREATION_LIMIT": "Monthly session creation limit reached.",
    "REQUEST_TOO_LARGE": "Request too large.",
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
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
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
    # API Gateway permits much larger requests than any normal mutation needs.
    # Reject oversized JSON (including base64 wire bodies) before parsing it.
    if len(raw.encode("utf-8", errors="surrogatepass")) > 350 * 1024:
        raise BusinessError(413, "REQUEST_TOO_LARGE")
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
        star_path = False

        def failed(status, code):
            result = error(status, code)
            if star_path:
                result["headers"]["Cache-Control"] = "no-store"
            return result

        try:
            path = event.get("rawPath", "")
            star_path = isinstance(path, str) and path.startswith(
                ("/star-assist/", "/answer-contexts/", "/answer-drafts/", "/star-drafts/")
            )
            request_context = event.get("requestContext") or {}
            owner = (
                ((request_context.get("authorizer") or {}).get("jwt") or {}).get("claims") or {}
            ).get("sub")
            if not isinstance(owner, str) or not owner.strip():
                return failed(401, "UNAUTHORIZED")
            method = (request_context.get("http") or {}).get("method", "")
            path = event.get("rawPath", "")
            from interview_backend.star_assist.api import ROUTES as STAR_ROUTES
            from interview_backend.star_assist.api import handle

            if any(re.fullmatch(pattern, path) for _, pattern, _, _ in STAR_ROUTES):
                star_path = True
                headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
                raw = event.get("body")
                if (
                    method in {"POST", "PUT"}
                    and isinstance(raw, str)
                    and len(raw.encode("utf-8", errors="surrogatepass")) > 350 * 1024
                ):
                    raise BusinessError(413, "REQUEST_TOO_LARGE")
                payload = parse_body(event) if method in {"POST", "PUT"} else None
                try:
                    reply = handle(
                        self.application.repository, owner, method, path, headers, payload
                    )
                except InvalidIdentifier as exc:
                    raise BusinessError(400, "VALIDATION_ERROR") from exc
                result = response(reply)
                result["headers"]["Cache-Control"] = "no-store"
                return result
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
                if action == "feedback":
                    query = event.get("queryStringParameters") or {}
                    if "evaluationId" in query:
                        if not isinstance(query["evaluationId"], str):
                            raise BusinessError(400, "VALIDATION_ERROR")
                        args.append(query["evaluationId"])
                if method == "POST":
                    args.append(parse_body(event))
                # Application validation failures only; unrelated ValueError is a 500.
                try:
                    if action == "submit":
                        headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
                        reply = self.application.submit(
                            *args, application_id=headers.get("x-star-application-id")
                        )
                    else:
                        reply = getattr(self.application, action)(*args)
                except InvalidIdentifier as exc:
                    raise BusinessError(400, "VALIDATION_ERROR") from exc
                result = response(reply)
                if action == "practice_options":
                    result["headers"]["Cache-Control"] = "no-store"
                return result
            if allowed_methods:
                result = error(405, "METHOD_NOT_ALLOWED")
                result["headers"]["Allow"] = ", ".join(sorted(allowed_methods))
                return result
            return error(404, "NOT_FOUND")
        except BusinessError as exc:
            return failed(exc.status, exc.code)
        except Exception:
            # Do not log the event, exception message, credentials or answer text.
            return failed(500, "INTERNAL_SERVER_ERROR")
