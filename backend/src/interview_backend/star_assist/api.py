"""Additive authenticated helper routes; mutation replies contain receipts only."""

import hashlib
import json
import re

from pydantic import ValidationError

from interview_backend.models.internal import BusinessError, ItemTooLarge, Reply
from interview_backend.models.public import validate_id
from interview_backend.star_assist.models import (
    CATEGORIES,
    AnswerUpdate,
    AnswerValue,
    ApplyRequest,
    ContextRequest,
    GenerateRequest,
    PreferencesRequest,
    StarInput,
    StarUpdate,
    Versioned,
)

ROUTES = (
    ("GET", r"/star-assist/options", None, "options"),
    ("GET", r"/star-assist/preferences", None, "preferences"),
    ("PUT", r"/star-assist/preferences", PreferencesRequest, "save_preferences"),
    ("POST", r"/sessions/([^/]+)/answer-contexts", ContextRequest, "context"),
    ("GET", r"/answer-contexts/([^/]+)/drafts", None, "drafts"),
    ("POST", r"/answer-contexts/([^/]+)/answer-drafts", AnswerValue, "create_answer"),
    ("POST", r"/answer-contexts/([^/]+)/star-drafts", StarInput, "create_star"),
    ("PUT", r"/answer-drafts/([^/]+)", AnswerUpdate, "update_answer"),
    ("PUT", r"/star-drafts/([^/]+)", StarUpdate, "update_star"),
    ("POST", r"/answer-drafts/([^/]+)/discard", Versioned, "discard_answer"),
    ("POST", r"/star-drafts/([^/]+)/discard", Versioned, "discard_star"),
    ("POST", r"/star-assist/generations", GenerateRequest, "generate"),
    ("GET", r"/star-assist/generations/([^/]+)", None, "generation"),
    ("GET", r"/star-assist/quota", None, "quota"),
    ("POST", r"/star-drafts/([^/]+)/applications", ApplyRequest, "apply"),
    ("GET", r"/star-assist/requests/([^/]+)", None, "request"),
)


def handle(repository, owner, method, path, headers, payload):
    matches = [
        (m, schema, action, re.fullmatch(pattern, path))
        for m, pattern, schema, action in ROUTES
        if re.fullmatch(pattern, path)
    ]
    if not matches:
        return None
    route = next((r for r in matches if r[0] == method), None)
    if route is None:
        raise BusinessError(405, "METHOD_NOT_ALLOWED")
    _, schema, action, match = route
    args = match.groups()
    for identifier in args:
        validate_id(identifier)
    identifier = args[0] if args else None
    if schema is None:
        if action == "options":
            return Reply(
                200,
                {
                    "categories": [{"id": k, "label": v} for k, v in CATEGORIES.items()],
                    "userMonthlyLimit": 20,
                    "globalMonthlyLimit": 600,
                },
            )
        return {
            "preferences": lambda: repository.star_preferences(owner),
            "drafts": lambda: repository.star_drafts(owner, identifier),
            "quota": lambda: repository.star_quota(owner),
            "generation": lambda: repository.star_generation(owner, identifier),
            "request": lambda: repository.star_request(owner, identifier),
        }[action]()
    try:
        body = schema.model_validate(payload)
    except ValidationError as exc:
        raise BusinessError(400, "VALIDATION_ERROR") from exc
    key = validate_id(headers.get("idempotency-key"))
    fingerprint = hashlib.sha256(
        json.dumps(
            [method, path, body.model_dump(exclude_unset=True)], sort_keys=True, ensure_ascii=True
        ).encode("ascii")
    ).hexdigest()

    def operation(tx, now, new):
        if action == "save_preferences":
            return repository.star_save_preferences(tx, owner, body, now, new)
        if action == "context":
            return repository.star_create_context(tx, owner, identifier, body)
        if action.startswith("create_"):
            return repository.star_create_draft(
                tx,
                owner,
                identifier,
                "AnswerDraft" if action == "create_answer" else "StarDraft",
                body,
                now,
                new,
            )
        if action.startswith(("update_", "discard_")):
            return repository.star_update_draft(
                tx,
                owner,
                identifier,
                "AnswerDraft" if action.endswith("answer") else "StarDraft",
                body,
                now,
                discard=action.startswith("discard_"),
            )
        if action == "generate":
            return repository.star_generate(tx, owner, body, now, new)
        return repository.star_apply(tx, owner, identifier, body, now, new)

    try:
        return repository.star_post(owner, key, fingerprint, method, path, operation)
    except ItemTooLarge as exc:
        raise BusinessError(413, "REQUEST_TOO_LARGE") from exc
