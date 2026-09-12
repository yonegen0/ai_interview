"""Explicit, single-attempt execution. Crash/lease recovery is intentionally P2+."""

from collections.abc import Callable
from datetime import UTC, datetime

from interview_backend.evaluation.provider import PROMPT_VERSION, Provider, build_prompt
from interview_backend.models.public import EvaluationResult, Feedback
from interview_backend.repositories.base import Repository


class Worker:
    def __init__(self, repository: Repository, provider: Provider, clock: Callable[[], datetime]):
        self.repository = repository
        self.provider = provider
        self.clock = clock

    def run(self, evaluation_id: str) -> bool:
        attempt = self.repository.claim(evaluation_id)
        if attempt is None:
            return False
        try:
            prompt = build_prompt(attempt.question, attempt.answer)
            result = EvaluationResult.model_validate(self.provider.evaluate(prompt))
            now = self.clock()
            if now.tzinfo is None:
                raise ValueError("Clock must be timezone aware")
            feedback = Feedback(
                **result.wire(),
                attemptId=attempt.id,
                sessionId=attempt.session_id,
                question=attempt.question,
                questionNumber=attempt.question_number,
                answer=attempt.answer,
                createdAt=now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            )
        except Exception:
            # No raw provider output/exception retained. No automatic retry in P1.
            feedback = None
        self.repository.finish(evaluation_id, feedback, PROMPT_VERSION)
        return True
