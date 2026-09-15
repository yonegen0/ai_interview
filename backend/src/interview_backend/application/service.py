"""Six application operations; fingerprint only validated request properties."""

import json
from collections.abc import Callable
from hashlib import sha256

from pydantic import BaseModel, ValidationError

from interview_backend.models.internal import BusinessError, Reply
from interview_backend.models.public import (
    CreateRequest,
    InvalidIdentifier,
    NextRequest,
    Question,
    SubmitRequest,
    validate_id,
)
from interview_backend.repositories.base import Repository


def request_model[T: BaseModel](model: type[T], payload: dict) -> T:
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise BusinessError(400, "VALIDATION_ERROR") from exc


class Application:
    def __init__(
        self, repository: Repository, questions: tuple[Question, ...], new_id: Callable[[], str]
    ):
        self.repository = repository
        self.questions = tuple(question.model_copy(deep=True) for question in questions)
        self.new_id = new_id

    def _new_id(self) -> str:
        try:
            return validate_id(self.new_id())
        except InvalidIdentifier as exc:
            # An injected/generated invalid ID is an internal failure, not a bad request.
            raise RuntimeError("Invalid generated identifier") from exc

    @staticmethod
    def _owner(owner: str) -> None:
        if not isinstance(owner, str) or not owner.strip():
            raise BusinessError(401, "UNAUTHORIZED")

    @staticmethod
    def _fingerprint(path: str, payload: dict) -> str:
        canonical = json.dumps(
            ["POST", path, payload], sort_keys=True, ensure_ascii=True, separators=(",", ":")
        )
        return sha256(canonical.encode("ascii")).hexdigest()

    def create(self, owner: str, key: str, payload: dict) -> Reply:
        self._owner(owner)
        request = request_model(CreateRequest, payload)
        validate_id(key)
        questions = tuple(q for q in self.questions if q.category == request.category)
        return self.repository.create_once(
            owner, key, self._fingerprint("/sessions", request.wire()), questions, self._new_id
        )

    def question(self, owner: str, session_id: str) -> Reply:
        self._owner(owner)
        validate_id(session_id)
        return self.repository.get_session(owner, session_id)

    def submit(self, owner: str, key: str, session_id: str, payload: dict) -> Reply:
        self._owner(owner)
        validate_id(session_id)
        validate_id(key)
        request = request_model(SubmitRequest, payload)
        return self.repository.accept_once(
            owner,
            key,
            self._fingerprint(f"/sessions/{session_id}/answers", request.wire()),
            session_id,
            request.questionId,
            request.answer,
            self._new_id,
        )

    def evaluation(self, owner: str, evaluation_id: str) -> Reply:
        self._owner(owner)
        validate_id(evaluation_id)
        return self.repository.get_evaluation(owner, evaluation_id)

    def feedback(self, owner: str, attempt_id: str) -> Reply:
        self._owner(owner)
        validate_id(attempt_id)
        return self.repository.get_feedback(owner, attempt_id)

    def next_question(self, owner: str, key: str, session_id: str, payload: dict) -> Reply:
        self._owner(owner)
        validate_id(session_id)
        validate_id(key)
        request = request_model(NextRequest, payload)
        return self.repository.next_once(
            owner,
            key,
            self._fingerprint(f"/sessions/{session_id}/questions/next", request.wire()),
            session_id,
            request.fromAttemptId,
        )
