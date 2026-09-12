"""Private storage records. Public API never exposes worker state or owner."""

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


@dataclass
class IdempotentReply:
    fingerprint: str
    reply: Reply


@dataclass
class State:
    sessions: dict[str, Session] = field(default_factory=dict)
    attempts: dict[str, Attempt] = field(default_factory=dict)
    evaluations: dict[str, Evaluation] = field(default_factory=dict)
    requests: dict[tuple[str, str], IdempotentReply] = field(default_factory=dict)
