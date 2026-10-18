"""Validate control-state consistency and exclude text from immutable receipts."""

import re

from interview_backend.models.internal import IntegrityError
from interview_backend.star_assist.models import (
    CATEGORIES,
    AnswerContext,
    AnswerDraft,
    StarDraft,
    StarGeneration,
    StarQuota,
    StarRequest,
    TargetCategoryPreference,
    TargetDetailsPreference,
    text,
)


def validate_star(record):
    if isinstance(record, TargetCategoryPreference) and record.target_category not in CATEGORIES:
        raise IntegrityError("star_category")
    if isinstance(record, TargetDetailsPreference):
        text(record.industry, 100)
        text(record.company, 200)
    if isinstance(record, (AnswerDraft, StarDraft)):
        if record.status not in {"ACTIVE", "COMPLETED", "DISCARDED"} or record.version < 1:
            raise IntegrityError("star_draft_state")
        if isinstance(record, AnswerDraft):
            text(record.answer, 16000)
            if record.status != "ACTIVE" and (record.answer or record.application_id):
                raise IntegrityError("star_closed_text")
        elif record.status != "ACTIVE" and (
            any(record.value.notes.model_dump().values()) or record.value.candidates
        ):
            raise IntegrityError("star_closed_text")
    if isinstance(record, AnswerContext) and (
        record.status not in {"ACTIVE", "COMPLETED"}
        or record.operation_kind not in {"initial_answer", "coaching_answer", "retry_attempt"}
        or not re.fullmatch(r"[0-9a-f]{64}", record.question_hash)
    ):
        raise IntegrityError("star_context")
    if isinstance(record, StarQuota) and (
        not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", record.month)
        or record.reserved + record.consumed
        > (600 if type(record).__name__ == "GlobalStarQuota" else 20)
    ):
        raise IntegrityError("star_quota")
    if isinstance(record, StarGeneration):
        terminal = record.status in {
            "SUCCEEDED",
            "NEEDS_INFORMATION",
            "CANCELLED",
            "FAILED_BEFORE_START",
            "FAILED_AFTER_START",
            "OUTCOME_UNKNOWN",
        }
        before = record.status in {"CANCELLED", "FAILED_BEFORE_START"}
        expected = {
            "QUEUED": ("pending", "reserved", False),
            "PREPARED": ("running", "reserved", False),
            "STARTED": ("running", "consumed", True),
        }
        state = (record.worker_state, record.quota_state, record.call_started)
        if (
            record.provider_id != "fake"
            or (record.status in expected and state != expected[record.status])
            or (
                terminal and state != ("terminal", "released" if before else "consumed", not before)
            )
        ):
            raise IntegrityError("star_generation_transition")
        if record.status in {"SUCCEEDED", "NEEDS_INFORMATION"} and (
            record.result is None
            or record.result.status
            != ("ready" if record.status == "SUCCEEDED" else "needs_information")
        ):
            raise IntegrityError("star_terminal_result")
        if record.status not in {"SUCCEEDED", "NEEDS_INFORMATION"} and record.result is not None:
            raise IntegrityError("star_unexpected_result")
        if terminal and (record.lock_owner is not None or record.lock_expires_at is not None):
            raise IntegrityError("star_terminal_lease")
        if (
            record.worker_state not in {"pending", "running", "terminal"}
            or record.quota_state not in {"reserved", "consumed", "released"}
            or record.status
            not in {
                "QUEUED",
                "PREPARED",
                "STARTED",
                "SUCCEEDED",
                "NEEDS_INFORMATION",
                "CANCELLED",
                "FAILED_BEFORE_START",
                "FAILED_AFTER_START",
                "OUTCOME_UNKNOWN",
            }
        ):
            raise IntegrityError("star_generation_state")
        if record.call_started != (record.quota_state == "consumed"):
            raise IntegrityError("star_call_quota")
        if (record.lock_owner is not None and record.lock_expires_at is not None) != (
            record.worker_state == "running"
        ):
            raise IntegrityError("star_lease")
        if (record.finished_at is not None and record.expires_at is not None) != (
            record.worker_state == "terminal"
        ):
            raise IntegrityError("star_terminal")
        if record.result is not None and (
            not record.call_started or record.worker_state != "terminal"
        ):
            raise IntegrityError("star_result")
    if isinstance(record, StarRequest):
        if record.status not in {200, 201, 202} or not re.fullmatch(
            r"[0-9a-f]{64}", record.fingerprint
        ):
            raise IntegrityError("star_receipt")

        def safe(value):
            if isinstance(value, dict):
                if set(value) & {
                    "answer",
                    "text",
                    "notes",
                    "input",
                    "candidates",
                    "company",
                    "industry",
                }:
                    raise IntegrityError("star_receipt_text")
                for child in value.values():
                    safe(child)
            elif isinstance(value, list):
                for child in value:
                    safe(child)

        safe(record.receipt)
