"""Atomic operation contract for memory now and a persistent adapter in P3."""

from collections.abc import Callable
from typing import Protocol

from interview_backend.models.internal import Attempt, Reply
from interview_backend.models.public import Feedback, Question


class Repository(Protocol):
    """Future adapters must preserve each operation's atomicity and replay ordering."""

    def create_once(
        self,
        owner: str,
        key: str,
        fingerprint: str,
        questions: tuple[Question, ...],
        new_id: Callable[[], str],
    ) -> Reply: ...
    def accept_once(
        self,
        owner: str,
        key: str,
        fingerprint: str,
        session_id: str,
        question_id: str,
        answer: str,
        new_id: Callable[[], str],
    ) -> Reply: ...
    def next_once(
        self, owner: str, key: str, fingerprint: str, session_id: str, attempt_id: str
    ) -> Reply: ...
    def get_session(self, owner: str, resource_id: str) -> Reply: ...
    def get_evaluation(self, owner: str, resource_id: str) -> Reply: ...
    def get_feedback(self, owner: str, resource_id: str) -> Reply: ...
    def claim(self, evaluation_id: str) -> Attempt | None: ...
    def finish(self, evaluation_id: str, feedback: Feedback | None, version: str) -> None: ...
