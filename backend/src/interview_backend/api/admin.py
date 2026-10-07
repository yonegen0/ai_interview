"""ADMIN-only question management; never accept caller-provided role or owner."""

import base64
import json
import re

from interview_backend.api.handler import error, reject_json_constant, response
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
    def __init__(self, repository, defaults):
        self.repository, self.defaults = repository, defaults

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
            if event.get("rawPath") != "/admin/question-bank":
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
