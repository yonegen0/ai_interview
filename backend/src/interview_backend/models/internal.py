"""Private storage records. Public API never exposes worker state or owner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from interview_backend.models.public import ActiveAttempt, Feedback, Question


class BusinessError(Exception):
    def __init__(self, status: int, code: str):
        self.status = status
        self.code = code
        super().__init__(code)


@dataclass
class Reply:
    status: int
    body: dict


@dataclass
class Session:
    owner: str
    id: str
    questions: tuple[Question, ...]
    number: int = 1
    active: ActiveAttempt | None = None
    version: int = 0
    created_at: int = 0
    updated_at: int = 0

    @property
    def question(self) -> Question:
        return self.questions[(self.number - 1) % len(self.questions)]


@dataclass
class Attempt:
    owner: str
    id: str
    session_id: str
    evaluation_id: str
    question: Question
    question_number: int
    answer: str
    created_at: int = 0


@dataclass
class Evaluation:
    owner: str
    id: str
    attempt_id: str
    worker_state: Literal["pending", "running", "terminal"] = "pending"
    status: Literal["processing", "completed", "failed"] = "processing"
    feedback: Feedback | None = None
    error: dict | None = None
    prompt_version: str | None = None
    created_at: int = 0
    deadline_at: int = 0
    call_phase: Literal["not_started", "started"] = "not_started"
    lease_version: int = 0
    lock_owner: str | None = None
    lock_expires_at: int | None = None
    failure_reason: str | None = None
    call_started_at: int | None = None
    execution_config: ExecutionConfig | None = None
    finished_at: int | None = None


@dataclass
class IdempotentReply:
    fingerprint: str
    reply: Reply
    created_at: int = 0
    fingerprint_version: int = 1
    owner: str = ""
    key: str = ""

    @property
    def request_hash(self) -> str:
        return self.fingerprint


@dataclass
class Dispatch:
    owner: str
    id: str
    deadline_at: int
    status: str = "PENDING"
    generation: int = 1
    next_at: int = 0
    send_owner: str | None = None
    send_expires_at: int | None = None
    queued_at: int | None = None
    created_at: int = 0
    delivery_attempts: int = 0
    generation_attempts: int = 0
    claim_due_at: int | None = None


@dataclass(frozen=True)
class ExecutionConfig:
    provider_id: str = "fake"
    model_id: str = "fake"
    prompt_version: str = ""
    result_schema_version: int = 1
    provider_timeout_ms: int = 40000


@dataclass(frozen=True)
class LeaseClaim:
    owner: str
    evaluation_id: str
    attempt: Attempt
    execution_id: str
    lease_version: int
    expires_at: int
    deadline_at: int
    generation: int
    execution_config: ExecutionConfig


@dataclass(frozen=True)
class ClaimResult:
    status: Literal["acquired", "busy", "terminal", "stale", "missing", "deadline_due"]
    lease: LeaseClaim | None = None


@dataclass(frozen=True)
class DeliveryClaim:
    owner: str
    evaluation_id: str
    generation: int
    token: str
    expires_at: int
    deadline_at: int = 9999999999999

    def event(self) -> dict:
        return {
            "eventVersion": 1,
            "type": "EvaluationRequested",
            "ownerSub": self.owner,
            "evaluationId": self.evaluation_id,
            "dispatchVersion": self.generation,
        }


@dataclass(frozen=True)
class DeliveryResult:
    status: Literal["acquired", "not_due", "busy", "obsolete", "deadline_due"]
    delivery: DeliveryClaim | None = None


@dataclass(frozen=True)
class MutationResult:
    status: Literal[
        "applied",
        "confirmed_same_execution",
        "lost_lease",
        "already_terminal",
        "obsolete",
        "requeued",
        "failed",
        "unchanged",
    ]
    evaluation: Evaluation | None = None


@dataclass
class RecoveryCursor:
    partition: str
    cutoff: int
    after: dict | None
    cycle_started_at: int
    updated_at: int


@dataclass(frozen=True)
class CursorSnapshot:
    cursor: RecoveryCursor
    revision: int | None


@dataclass(frozen=True)
class Candidate:
    owner: str
    evaluation_id: str
    key: dict


@dataclass(frozen=True)
class CorruptCandidate:
    key: dict | None
    classification: str = "IntegrityError"


@dataclass(frozen=True)
class CandidatePage:
    candidates: tuple[Candidate | CorruptCandidate, ...]
    continuation: dict | None
    continuation_valid: bool = True


class StorageError(Exception):
    """Safe classification only; never attach raw payloads or SDK exceptions."""


class StorageUnavailable(StorageError):
    pass


class RetryExhausted(StorageError):
    pass


class IntegrityError(StorageError):
    pass


class StorageFormatError(StorageError):
    pass


class ItemTooLarge(StorageError):
    pass


@dataclass
class State:
    sessions: dict[str, Session] = field(default_factory=dict)
    attempts: dict[str, Attempt] = field(default_factory=dict)
    evaluations: dict[str, Evaluation] = field(default_factory=dict)
    requests: dict[tuple[str, str], IdempotentReply] = field(default_factory=dict)
    dispatches: dict[str, Dispatch] = field(default_factory=dict)
    cursors: dict[str, RecoveryCursor] = field(default_factory=dict)
