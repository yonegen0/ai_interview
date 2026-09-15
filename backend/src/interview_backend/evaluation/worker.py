"""Lease-fenced single Provider call; only storage may be retried after starting."""

from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from pydantic import ValidationError

from interview_backend.evaluation.provider import PROMPT_VERSION, build_prompt
from interview_backend.models.internal import ExecutionConfig
from interview_backend.models.public import EvaluationResult, Feedback
from interview_backend.repositories.budget import invocation_budget
from interview_backend.repositories.domain import utc_ms


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
        self.config = config or ExecutionConfig(prompt_version=PROMPT_VERSION)
        self.metric = metric

    @invocation_budget(60000)
    def run(self, owner, evaluation_id, generation=1, remaining_ms=None):
        entered = False
        started = self.monotonic()
        remaining = remaining_ms or (
            lambda: max(0, 60000 - int((self.monotonic() - started) * 1000))
        )
        claim = self.repository.claim(
            owner, evaluation_id, generation, self.new_execution_id(), self.config
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
                lease.execution_config != self.config
                or self.config.prompt_version != PROMPT_VERSION
                or self.config.provider_id != "fake"
                or self.config.model_id != "fake"
            ):
                raise ValueError("execution_config")
            prompt = build_prompt(lease.attempt.question, lease.attempt.answer)
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
            raw = self.provider.evaluate(prompt)
            if (self.monotonic() - called_at) * 1000 >= self.config.provider_timeout_ms:
                raise TimeoutError
            result = EvaluationResult.model_validate(raw)
            feedback = Feedback(
                **result.wire(),
                attemptId=lease.attempt.id,
                sessionId=lease.attempt.session_id,
                question=lease.attempt.question,
                questionNumber=lease.attempt.question_number,
                answer=lease.attempt.answer,
                createdAt=datetime.fromtimestamp(self.clock() / 1000, UTC)
                .isoformat()
                .replace("+00:00", "Z"),
            )
        except TimeoutError:
            reason = "PROVIDER_TIMEOUT"
        except ValidationError:
            reason = "INVALID_RESULT"
        except Exception:
            reason = "PROVIDER_FAILED"
        result = self.repository.finish(lease, feedback, reason)
        return result.status in {"applied", "already_terminal"}
