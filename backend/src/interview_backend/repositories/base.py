"""Atomic operation contract for memory now and a persistent adapter in P3."""

from collections.abc import Callable
from typing import Protocol

from interview_backend.models.internal import (
    CandidatePage,
    ClaimResult,
    CursorSnapshot,
    DeliveryClaim,
    DeliveryResult,
    ExecutionConfig,
    LeaseClaim,
    MutationResult,
    RecoveryCursor,
    Reply,
)
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
    def claim(
        self,
        owner: str,
        evaluation_id: str,
        generation: int,
        execution_id: str,
        execution_config: ExecutionConfig,
        now: int | None = None,
    ) -> ClaimResult: ...
    def mark_call_started(self, lease: LeaseClaim, now: int | None = None) -> MutationResult: ...
    def finish(
        self,
        lease: LeaseClaim,
        feedback: Feedback | None = None,
        reason: str = "PROVIDER_FAILED",
        now: int | None = None,
    ) -> MutationResult: ...
    def acquire_delivery(
        self,
        owner: str,
        evaluation_id: str,
        generation: int,
        sender_id: str,
        now: int | None = None,
    ) -> DeliveryResult: ...
    def confirm_delivery(
        self, delivery: DeliveryClaim, now: int | None = None
    ) -> MutationResult: ...
    def fail_delivery(
        self, delivery: DeliveryClaim, next_at: int, now: int | None = None
    ) -> MutationResult: ...
    def recover(self, owner: str, evaluation_id: str, now: int | None = None) -> MutationResult: ...
    def due_candidates(
        self, partition: str, cutoff: int, cursor: dict | None = None, limit: int = 100
    ) -> CandidatePage: ...
    def get_cursor(self, partition: str) -> CursorSnapshot: ...
    def save_cursor(self, snapshot: CursorSnapshot, cursor: RecoveryCursor) -> bool: ...
    def dispatch_event(self, owner: str, evaluation_id: str) -> dict | None: ...
    def delivery_attempts(self, owner: str, evaluation_id: str) -> int: ...
    def work_observation(self, owner: str, evaluation_id: str) -> tuple[tuple[str, float], ...]: ...
