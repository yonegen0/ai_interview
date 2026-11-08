"""ADMIN-only question management; never accept caller-provided role or owner."""

import base64
import json
import re

from interview_backend.api.admin_users import normalize_nickname
from interview_backend.api.handler import error, parse_body, reject_json_constant, response
from interview_backend.application.service import Application, request_model
from interview_backend.models.internal import BusinessError, Reply
from interview_backend.models.public import (
    BankSaveRequest,
    InvalidIdentifier,
    Question,
    validate_id,
)


def is_admin(groups):
    if isinstance(groups, str):
        groups = groups.strip()
        if groups.startswith("["):
            try:
                groups = json.loads(groups)
            except ValueError:
                # HTTP API JWT claims can contain Go-style lists, e.g. [USER ADMIN].
                name = r"[\w+=.@-]+"
                if not re.fullmatch(rf"\[\s*{name}(?:(?:\s*,\s*|\s+){name})*\s*\]", groups):
                    return False
                groups = re.split(r"[\s,]+", groups[1:-1].strip())
        else:
            groups = [value.strip() for value in groups.split(",")]
    return isinstance(groups, list) and all(type(g) is str for g in groups) and "ADMIN" in groups


class AdminHandler:
    def __init__(self, repository, defaults, users=None):
        self.repository, self.defaults, self.users = repository, defaults, users

    def __call__(self, event, context=None):
        try:
            claims = (
                ((event.get("requestContext") or {}).get("authorizer") or {}).get("jwt") or {}
            ).get("claims") or {}
            owner = claims.get("sub")
            if not isinstance(owner, str) or not owner.strip():
                return error(401, "UNAUTHORIZED")
            if not is_admin(claims.get("cognito:groups")):
                return error(403, "FORBIDDEN")
            path = event.get("rawPath")
            method = (event.get("requestContext") or {}).get("http", {}).get("method")
            if isinstance(path, str) and (
                path == "/admin/users" or path.startswith("/admin/users/")
            ):
                return self._users(event, path, method)
            if path != "/admin/question-bank":
                return error(404, "NOT_FOUND")
            method = (event["requestContext"].get("http") or {}).get("method")
            if method == "GET":
                result = response(Reply(200, self.repository.get_question_bank(self.defaults)))
                result["headers"]["Cache-Control"] = "no-store"
                return result
            if method != "POST":
                result = error(405, "METHOD_NOT_ALLOWED")
                result["headers"]["Allow"] = "GET, POST"
                return result
            headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
            key = validate_id(headers.get("idempotency-key"))
            raw = event.get("body")
            if not isinstance(raw, str):
                raise BusinessError(400, "VALIDATION_ERROR")
            if event.get("isBase64Encoded"):
                if len(raw) > (1024 * 1024 + 2) // 3 * 4:
                    raise BusinessError(413, "REQUEST_TOO_LARGE")
                body = base64.b64decode(raw, validate=True)
            else:
                body = raw.encode("utf-8")
            if len(body) > 1024 * 1024:
                raise BusinessError(413, "REQUEST_TOO_LARGE")
            payload = json.loads(body, parse_constant=reject_json_constant)
            if not isinstance(payload, dict):
                raise BusinessError(400, "VALIDATION_ERROR")
            parsed = request_model(BankSaveRequest, payload)
            fingerprint = Application._fingerprint("/admin/question-bank", parsed.wire())
            return response(
                self.repository.save_question_bank_once(
                    owner,
                    key,
                    fingerprint,
                    parsed.expectedVersion,
                    tuple(Question(**q.wire()) for q in parsed.questions),
                    self.defaults,
                )
            )
        except BusinessError as exc:
            return error(exc.status, exc.code)
        except InvalidIdentifier, ValueError, UnicodeError:
            return error(400, "VALIDATION_ERROR")
        except Exception:
            return error(500, "INTERNAL_SERVER_ERROR")

    def _users(self, event, path, method):
        if self.users is None:
            return error(500, "INTERNAL_SERVER_ERROR")
        target = re.fullmatch(r"/admin/users/([^/]+)", path)
        history = re.fullmatch(r"/admin/users/([^/]+)/history", path)
        feedback = re.fullmatch(r"/admin/users/([^/]+)/attempts/([^/]+)/feedback", path)
        nickname = re.fullmatch(r"/admin/users/([^/]+)/nickname", path)
        expected = "PUT" if nickname else "GET"
        if not (path == "/admin/users" or target or history or feedback or nickname):
            return error(404, "NOT_FOUND")
        if method != expected:
            result = error(405, "METHOD_NOT_ALLOWED")
            result["headers"]["Allow"] = expected
            return result
        try:
            if path == "/admin/users":
                query = event.get("queryStringParameters") or {}
                if not isinstance(query, dict) or set(query) - {"limit", "cursor"}:
                    raise BusinessError(400, "VALIDATION_ERROR")
                value = query.get("limit", "60")
                if (
                    not isinstance(value, str)
                    or not value.isascii()
                    or not value.isdecimal()
                    or len(value) > 2
                ):
                    raise BusinessError(400, "VALIDATION_ERROR")
                limit = int(value)
                cursor = query.get("cursor")
                if not 1 <= limit <= 60 or (cursor is not None and (
                    not isinstance(cursor, str)
                    or not 1 <= len(cursor) <= 256
                    or any(char.isspace() for char in cursor)
                )):
                    raise BusinessError(400, "VALIDATION_ERROR")
                return response(Reply(200, self.users.list_users(limit, cursor)))
            user_id = validate_id((history or feedback or nickname or target).group(1))
            if history:
                query = event.get("queryStringParameters") or {}
                if not isinstance(query, dict):
                    raise BusinessError(400, "VALIDATION_ERROR")
                return response(self.repository.history(user_id, query))
            if feedback:
                attempt_id = validate_id(feedback.group(2))
                query = event.get("queryStringParameters") or {}
                if not isinstance(query, dict) or set(query) - {
                    "evaluationId", "includeFollowUpReviews"
                } or query.get("includeFollowUpReviews") not in {None, "1"}:
                    raise BusinessError(400, "VALIDATION_ERROR")
                evaluation_id = query.get("evaluationId")
                if evaluation_id is not None:
                    evaluation_id = validate_id(evaluation_id)
                return response(self.repository.get_feedback(
                    user_id, attempt_id, evaluation_id,
                    query.get("includeFollowUpReviews") == "1",
                ))
            if nickname:
                payload = parse_body(event)
                if set(payload) != {"nickname"}:
                    raise BusinessError(400, "VALIDATION_ERROR")
                return response(Reply(
                    200,
                    self.users.update_nickname(user_id, normalize_nickname(payload["nickname"])),
                ))
            return error(404, "NOT_FOUND")
        except BusinessError as exc:
            return error(exc.status, exc.code)
        except InvalidIdentifier, ValueError, UnicodeError:
            return error(400, "VALIDATION_ERROR")
        except Exception:
            return error(500, "INTERNAL_SERVER_ERROR")
