"""Copy-on-write memory transactions. Not a distributed lock or persistence layer."""

from collections.abc import Callable
from copy import deepcopy
from threading import RLock

from interview_backend.models.internal import (
    Attempt,
    BusinessError,
    Evaluation,
    IdempotentReply,
    Reply,
    Session,
    State,
)
from interview_backend.models.public import ActiveAttempt, Feedback, Question, SessionResponse


def session_body(session: Session) -> dict:
    return SessionResponse(
        sessionId=session.id,
        question=session.question,
        questionNumber=session.number,
        activeAttempt=session.active,
    ).wire()


def owned(records: dict, resource_id: str, owner: str, code: str):
    record = records.get(resource_id)
    if record is None or record.owner != owner:
        raise BusinessError(404, code)
    return record


class MemoryRepository:
    def __init__(self):
        self._state = State()
        self._lock = RLock()

    def snapshot(self) -> State:
        """Detached diagnostic snapshot for tests; never a writable live reference."""
        with self._lock:
            return deepcopy(self._state)

    def _commit(self, candidate: State) -> None:
        # All potentially failing preparation/copying happens before this assignment.
        self._state = candidate

    def _once(
        self, owner: str, key: str, fingerprint: str, operation: Callable[[State], Reply]
    ) -> Reply:
        with self._lock:
            cached = self._state.requests.get((owner, key))
            if cached is not None:
                if cached.fingerprint != fingerprint:
                    raise BusinessError(409, "IDEMPOTENCY_CONFLICT")
                return deepcopy(cached.reply)
            candidate = deepcopy(self._state)
            reply = operation(candidate)
            candidate.requests[(owner, key)] = IdempotentReply(fingerprint, deepcopy(reply))
            detached = deepcopy(reply)
            self._commit(candidate)
            return detached

    def create_once(
        self,
        owner: str,
        key: str,
        fingerprint: str,
        questions: tuple[Question, ...],
        new_id: Callable[[], str],
    ) -> Reply:
        def operation(state: State) -> Reply:
            session_id = new_id()
            if session_id in state.sessions:
                raise RuntimeError("ID collision")
            state.sessions[session_id] = Session(owner, session_id, deepcopy(questions))
            return Reply(201, {"sessionId": session_id})

        return self._once(owner, key, fingerprint, operation)

    def accept_once(
        self,
        owner: str,
        key: str,
        fingerprint: str,
        session_id: str,
        question_id: str,
        answer: str,
        new_id: Callable[[], str],
    ) -> Reply:
        def operation(state: State) -> Reply:
            session = owned(state.sessions, session_id, owner, "SESSION_NOT_FOUND")
            if session.question.id != question_id or (
                session.active and session.active.status == "processing"
            ):
                raise BusinessError(409, "SESSION_STATE_CONFLICT")
            attempt_id, evaluation_id = new_id(), new_id()
            if attempt_id in state.attempts or evaluation_id in state.evaluations:
                raise RuntimeError("ID collision")
            state.attempts[attempt_id] = Attempt(
                owner,
                attempt_id,
                session_id,
                evaluation_id,
                deepcopy(session.question),
                session.number,
                answer,
            )
            state.evaluations[evaluation_id] = Evaluation(owner, evaluation_id, attempt_id)
            session.active = ActiveAttempt(
                attemptId=attempt_id, evaluationId=evaluation_id, status="processing"
            )
            return Reply(202, session.active.wire())

        return self._once(owner, key, fingerprint, operation)

    def next_once(
        self, owner: str, key: str, fingerprint: str, session_id: str, attempt_id: str
    ) -> Reply:
        def operation(state: State) -> Reply:
            session = owned(state.sessions, session_id, owner, "SESSION_NOT_FOUND")
            if (
                not session.active
                or session.active.attemptId != attempt_id
                or (session.active.status != "completed")
            ):
                raise BusinessError(409, "SESSION_STATE_CONFLICT")
            session.number += 1
            session.active = None
            return Reply(200, session_body(session))

        return self._once(owner, key, fingerprint, operation)

    def get_session(self, owner: str, resource_id: str) -> Reply:
        with self._lock:
            session = owned(self._state.sessions, resource_id, owner, "SESSION_NOT_FOUND")
            return Reply(200, session_body(session))

    def get_evaluation(self, owner: str, resource_id: str) -> Reply:
        with self._lock:
            evaluation = owned(self._state.evaluations, resource_id, owner, "ATTEMPT_NOT_FOUND")
            body = {
                "evaluationId": evaluation.id,
                "attemptId": evaluation.attempt_id,
                "status": evaluation.status,
            }
            if evaluation.error is not None:
                body["error"] = deepcopy(evaluation.error)
            return Reply(200, body)

    def get_feedback(self, owner: str, resource_id: str) -> Reply:
        with self._lock:
            attempt = owned(self._state.attempts, resource_id, owner, "ATTEMPT_NOT_FOUND")
            evaluation = self._state.evaluations[attempt.evaluation_id]
            if evaluation.status != "completed" or evaluation.feedback is None:
                raise BusinessError(409, "EVALUATION_NOT_COMPLETED")
            return Reply(200, evaluation.feedback.wire())

    def claim(self, evaluation_id: str) -> Attempt | None:
        with self._lock:
            evaluation = self._state.evaluations.get(evaluation_id)
            if evaluation is None or evaluation.worker_state != "pending":
                return None
            candidate = deepcopy(self._state)
            candidate.evaluations[evaluation_id].worker_state = "running"
            attempt = deepcopy(candidate.attempts[evaluation.attempt_id])
            self._commit(candidate)
            return attempt

    def finish(self, evaluation_id: str, feedback: Feedback | None, version: str) -> None:
        with self._lock:
            evaluation = self._state.evaluations.get(evaluation_id)
            if evaluation is None or evaluation.worker_state != "running":
                return
            candidate = deepcopy(self._state)
            result = candidate.evaluations[evaluation_id]
            result.worker_state = "terminal"
            result.status = "completed" if feedback is not None else "failed"
            result.feedback = deepcopy(feedback)
            result.prompt_version = version
            result.error = (
                None
                if feedback is not None
                else {"code": "EVALUATION_FAILED", "message": "Evaluation could not be completed."}
            )
            attempt = candidate.attempts[result.attempt_id]
            session = candidate.sessions[attempt.session_id]
            if (
                session.active
                and session.active.attemptId == result.attempt_id
                and (session.active.evaluationId == evaluation_id)
            ):
                session.active = session.active.model_copy(update={"status": result.status})
            self._commit(candidate)
