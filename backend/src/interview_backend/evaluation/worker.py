"""Lease-fenced single Provider call; only storage may be retried after starting."""

import logging
from dataclasses import replace
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from pydantic import ValidationError

from interview_backend.evaluation.coaching import InvalidCoachingResult, validate_coaching_result
from interview_backend.evaluation.provider import (
    COACHING_PROMPT_VERSION,
    PROMPT_VERSION,
    build_coaching_prompt,
    build_prompt,
)
from interview_backend.models.internal import ExecutionConfig
from interview_backend.models.public import CoachingResult, EvaluationResult, Feedback, FeedbackV2
from interview_backend.repositories.budget import invocation_budget
from interview_backend.repositories.domain import utc_ms
from interview_backend.text_limits import score_values


class Worker:
    def __init__(
        self,
        repository,
        provider,
        clock=utc_ms,
        monotonic_clock=monotonic,
        new_execution_id=lambda: str(uuid4()),
        config=None,
        metric=lambda classification: None,
    ):
        self.repository, self.provider, self.clock = repository, provider, clock
        self.monotonic, self.new_execution_id = monotonic_clock, new_execution_id
        self.config = config or ExecutionConfig(
            provider_id=getattr(provider, "provider_id", "fake"),
            model_id=getattr(provider, "model_id", "fake"),
            prompt_version=PROMPT_VERSION,
        )
        self.coaching_config = replace(
            self.config, prompt_version=COACHING_PROMPT_VERSION, result_schema_version=2
        )
        self.metric = metric

    @invocation_budget(60000)
    def run(self, owner, evaluation_id, generation=1, remaining_ms=None):
        entered = False
        started = self.monotonic()
        remaining = remaining_ms or (
            lambda: max(0, 60000 - int((self.monotonic() - started) * 1000))
        )
        version = self.repository.evaluation_contract_version(owner, evaluation_id)
        config = self.coaching_config if version == 2 else self.config
        claim = self.repository.claim(
            owner, evaluation_id, generation, self.new_execution_id(), config
        )
        if claim.status == "deadline_due":
            self.repository.recover(owner, evaluation_id)
            return False
        if claim.status != "acquired":
            if claim.status == "missing":
                self.metric("MissingEvaluation")
            return False
        lease = claim.lease

        def enough():
            return (
                min(remaining(), lease.expires_at - self.clock(), lease.deadline_at - self.clock())
                >= 50000
            )

        try:
            if (
                lease.execution_config != config
                or config.prompt_version
                != (COACHING_PROMPT_VERSION if version == 2 else PROMPT_VERSION)
                or config.provider_id != getattr(self.provider, "provider_id", "fake")
                or config.model_id != getattr(self.provider, "model_id", "fake")
            ):
                raise ValueError("execution_config")
            prompt = (
                build_coaching_prompt(lease.coaching_input)
                if version == 2
                else build_prompt(lease.attempt.question, lease.attempt.answer)
            )
            if hasattr(self.provider, "authorize_owner"):
                self.provider.authorize_owner(lease.owner)
        except Exception:
            return self.repository.finish(lease, reason="PREPARATION_FAILED").status in {
                "applied",
                "already_terminal",
            }
        if not enough():
            return self.repository.finish(lease, reason="PREPARATION_FAILED").status in {
                "applied",
                "already_terminal",
            }
        if config.provider_id.startswith("openai"):
            quota = self.repository.reserve_provider_call(
                lease,
                self.provider.settings.monthly_user_limit,
                self.provider.settings.monthly_global_limit,
            )
            if quota.status == "limited":
                return self.repository.finish(lease, reason="PREPARATION_FAILED").status in {
                    "applied",
                    "already_terminal",
                }
            if quota.status not in {"reserved", "already_reserved"}:
                return False
        marked = self.repository.mark_call_started(lease)
        if marked.status not in {"applied", "confirmed_same_execution"}:
            return False
        if not enough():
            return self.repository.finish(lease, reason="PREPARATION_FAILED").status in {
                "applied",
                "already_terminal",
            }
        feedback, reason = None, "PROVIDER_FAILED"
        try:
            if entered:
                raise RuntimeError("already_called")
            entered = True
            called_at = self.monotonic()
            if config.provider_id.startswith("openai"):
                from interview_backend.evaluation.openai_provider import Deadline

                budget = min(
                    config.provider_timeout_ms,
                    remaining() - 10000,
                    lease.expires_at - self.clock() - 10000,
                    lease.deadline_at - self.clock() - 10000,
                )
                raw = self.provider.evaluate_with_deadline(
                    prompt, Deadline(called_at + budget / 1000, self.monotonic)
                )
            elif hasattr(self.provider, "evaluate_for_owner"):
                raw = self.provider.evaluate_for_owner(prompt, lease.owner)
            else:
                raw = self.provider.evaluate(prompt)
            if (self.monotonic() - called_at) * 1000 >= config.provider_timeout_ms:
                raise TimeoutError
            result = (CoachingResult if version == 2 else EvaluationResult).model_validate(raw)
            created_at = (
                datetime.fromtimestamp(self.clock() / 1000, UTC).isoformat().replace("+00:00", "Z")
            )
            if version == 2:
                validate_coaching_result(result, lease.coaching_input)
                context = lease.coaching_input
                feedback = FeedbackV2(
                    feedbackVersion=2,
                    attemptId=lease.attempt.id,
                    evaluationId=evaluation_id,
                    sessionId=lease.attempt.session_id,
                    question=lease.attempt.question,
                    questionNumber=lease.attempt.question_number,
                    answer=lease.attempt.answer,
                    latestAnswer=context.latest_answer,
                    coachingHistory=list(context.coaching_history),
                    coachingCount=context.coaching_count,
                    result=result,
                    createdAt=created_at,
                    **score_values(
                        lease.attempt.answer,
                        result.conclusion_score,
                        result.specificity_score,
                        result.reasoning_score,
                    ),
                )
            else:
                feedback = Feedback(
                    **result.wire(),
                    attemptId=lease.attempt.id,
                    sessionId=lease.attempt.session_id,
                    question=lease.attempt.question,
                    questionNumber=lease.attempt.question_number,
                    answer=lease.attempt.answer,
                    createdAt=created_at,
                )
        except TimeoutError:
            reason = "PROVIDER_TIMEOUT"
        except ValidationError, InvalidCoachingResult:
            reason = "INVALID_RESULT"
        except Exception as error:
            from interview_backend.evaluation.openai_provider import ProviderFailure

            if isinstance(error, ProviderFailure):
                logging.getLogger(__name__).warning("provider_failure=%s", error.kind)
                reason = (
                    "OUTCOME_UNKNOWN"
                    if error.uncertain
                    else "PROVIDER_TIMEOUT"
                    if error.kind == "TIMEOUT"
                    else "INVALID_RESULT"
                    if error.kind in {"INVALID_JSON", "INVALID_SCHEMA"}
                    else "PROVIDER_FAILED"
                )
            else:
                reason = "PROVIDER_FAILED"
        result = self.repository.finish(lease, feedback, reason)
        return result.status in {"applied", "already_terminal"}
