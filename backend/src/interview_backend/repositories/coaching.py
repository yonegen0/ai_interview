"""V2 aggregate transitions using the existing transactional repository unit."""

from copy import deepcopy

from interview_backend.evaluation.coaching import unavailable
from interview_backend.models.internal import (
    Attempt,
    AttemptCoaching,
    BusinessError,
    CoachingTurn,
    Dispatch,
    Evaluation,
    IntegrityError,
    Reply,
    StorageUnavailable,
)
from interview_backend.models.public import (
    ActiveAttempt,
    ActiveCoaching,
    CoachingHistoryItem,
    CoachingInput,
)


def reference(kind, owner, identifier):
    return kind, owner, identifier


def context_for(attempt, coaching):
    history = tuple(
        CoachingHistoryItem(question=h.question, answer=h.answer) for h in coaching.history
    )
    return CoachingInput(
        question=deepcopy(attempt.question),
        initial_answer=attempt.answer,
        coaching_history=history,
        latest_answer=history[-1].answer if history else attempt.answer,
        coaching_count=coaching.coaching_count,
        can_ask_follow_up=coaching.coaching_count < 3,
        unavailable_questions=coaching.unavailable_questions,
    )


def progress_for(attempt, coaching):
    context = context_for(attempt, coaching)
    return ActiveCoaching(
        attemptId=attempt.id,
        evaluationId=coaching.current_evaluation_id,
        stage=coaching.stage,
        initialAnswer=attempt.answer,
        latestAnswer=context.latest_answer,
        coachingHistory=list(context.coaching_history),
        coachingCount=coaching.coaching_count,
        followUpQuestion=coaching.pending_question,
        lastSuccessfulEvaluationId=coaching.last_successful_evaluation_id,
    ).wire()


def validate_progress(attempt, coaching, evaluation):
    if (
        coaching is None
        or evaluation is None
        or coaching.owner != attempt.owner
        or coaching.id != attempt.id
        or coaching.session_id != attempt.session_id
        or coaching.current_evaluation_id != evaluation.id
        or evaluation.attempt_id != attempt.id
        or evaluation.owner != attempt.owner
        or evaluation.coaching_contract_version != 2
        or evaluation.coaching_input != context_for(attempt, coaching)
    ):
        raise IntegrityError("coaching_relation")
    expected = {
        "evaluating": "processing",
        "awaiting_answer": "completed",
        "completed": "completed",
        "failed": "failed",
    }
    if evaluation.status != expected[coaching.stage]:
        raise IntegrityError("coaching_state")
    if coaching.stage in {"awaiting_answer", "completed"}:
        result = evaluation.feedback.result
        if (result.status == "coaching") != (coaching.stage == "awaiting_answer"):
            raise IntegrityError("coaching_result_state")
        if result.follow_up_question != coaching.pending_question:
            raise IntegrityError("coaching_question")
    last = (
        evaluation.id
        if evaluation.status == "completed"
        else (coaching.history[-1].source_evaluation_id if coaching.history else None)
    )
    if coaching.last_successful_evaluation_id != last:
        raise IntegrityError("last_successful_evaluation")


class CoachingRepositoryMixin:
    @staticmethod
    def _validate_history_sources(tx, attempt, coaching):
        for index, turn in enumerate(coaching.history):
            er = reference("Evaluation", attempt.owner, turn.source_evaluation_id)
            source = tx.get(er)
            if (
                source is None
                or source.owner != attempt.owner
                or source.attempt_id != attempt.id
                or source.coaching_contract_version != 2
                or source.status != "completed"
                or source.feedback.result.status != "coaching"
                or source.feedback.result.follow_up_question != turn.question
                or source.coaching_input
                != context_for(
                    attempt,
                    AttemptCoaching(
                        attempt.owner,
                        attempt.id,
                        attempt.session_id,
                        source.id,
                        history=coaching.history[:index],
                        coaching_count=index,
                        unavailable_questions=tuple(
                            q
                            for q in coaching.unavailable_questions
                            if q in {h.question for h in coaching.history[:index]}
                        ),
                    ),
                )
                or turn.accepted_at < source.created_at
            ):
                raise IntegrityError("history_source_relation")
            tx.ignore_dependency(er)  # Successful source evaluations are immutable.

    @staticmethod
    def _active_is_v2(tx, owner, session):
        if not session.active:
            return False
        attempt = tx.get(reference("Attempt", owner, session.active.attemptId))
        if attempt is None:
            raise IntegrityError("missing_attempt")
        return attempt.coaching_contract_version == 2

    def _active_records(self, tx, owner, session):
        if not session.active:
            return session, None, None, None
        aid, eid = session.active.attemptId, session.active.evaluationId
        ar = reference("Attempt", owner, aid)
        attempt = tx.get(ar)
        if attempt is None:
            raise IntegrityError("missing_attempt")
        cr = reference("AttemptCoaching", owner, aid)
        er = reference("Evaluation", owner, eid)
        refs = (reference("Session", owner, session.id), ar, er)
        if attempt.coaching_contract_version == 2:
            refs += (cr,)
        records = tx.many(refs)
        current, attempt, evaluation = records[:3]
        if current.active != session.active:
            raise StorageUnavailable("snapshot_changed")
        if (
            attempt is None
            or evaluation is None
            or attempt.owner != owner
            or evaluation.owner != owner
            or attempt.session_id != current.id
            or evaluation.attempt_id != aid
            or current.number != attempt.question_number
            or current.question != attempt.question
            or current.active.status != evaluation.status
        ):
            raise IntegrityError("active_relation")
        coaching = records[3] if len(records) == 4 else None
        if attempt.coaching_contract_version == 2:
            validate_progress(attempt, coaching, evaluation)
            self._validate_history_sources(tx, attempt, coaching)
        elif (
            evaluation.coaching_contract_version is not None
            or attempt.evaluation_id != eid
            or attempt.created_at != evaluation.created_at
        ):
            raise IntegrityError("legacy_relation")
        return current, attempt, coaching, evaluation

    def _accept_v2(self, owner, key, fingerprint, session_id, request, new_id):
        generated = []
        accepted_time = []

        def run(tx, now):
            sr = reference("Session", owner, session_id)
            session = tx.get(sr)
            if session is None:
                raise BusinessError(404, "SESSION_NOT_FOUND")
            # Resolve caller IDs with the owner key before checking current pointers.
            target = getattr(request, "attemptId", getattr(request, "fromAttemptId", None))
            if target is not None and tx.get(reference("Attempt", owner, target)) is None:
                if session.active and target == session.active.attemptId:
                    raise IntegrityError("missing_attempt")
                raise BusinessError(404, "ATTEMPT_NOT_FOUND")
            source_id = getattr(request, "fromEvaluationId", None)
            if source_id is not None and tx.get(reference("Evaluation", owner, source_id)) is None:
                if session.active and source_id == session.active.evaluationId:
                    raise IntegrityError("missing_evaluation")
                raise BusinessError(404, "ATTEMPT_NOT_FOUND")
            session, previous, coaching, evaluation = self._active_records(tx, owner, session)
            kind = request.kind
            if hasattr(request, "questionId") and request.questionId != session.question.id:
                raise BusinessError(409, "SESSION_STATE_CONFLICT")
            if kind == "initial_answer":
                if previous and (
                    previous.coaching_contract_version == 2 or evaluation.status != "failed"
                ):
                    raise BusinessError(409, "SESSION_STATE_CONFLICT")
            else:
                if previous is None or target != previous.id or source_id != evaluation.id:
                    raise BusinessError(409, "SESSION_STATE_CONFLICT")
                if kind == "retry_attempt":
                    if evaluation.status != "completed" or (
                        coaching and coaching.stage != "completed"
                    ):
                        raise BusinessError(409, "SESSION_STATE_CONFLICT")
                elif coaching is None or coaching.stage != (
                    "awaiting_answer" if kind == "coaching_answer" else "failed"
                ):
                    raise BusinessError(409, "SESSION_STATE_CONFLICT")
            if evaluation:
                # Terminal evaluations are immutable; mutable dependencies use Put CAS.
                tx.ignore_dependency(reference("Evaluation", owner, evaluation.id))
            if not accepted_time:
                accepted_time.append(
                    max(
                        now,
                        session.updated_at,
                        previous.created_at if previous else 0,
                        evaluation.created_at if evaluation else 0,
                        coaching.updated_at if coaching else 0,
                    )
                )
            now = accepted_time[0]
            fresh = kind in {"initial_answer", "retry_attempt"}
            if not generated:
                generated.extend((new_id(), new_id()) if fresh else (new_id(),))
            if fresh:
                aid, eid = generated
                attempt = Attempt(
                    owner,
                    aid,
                    session_id,
                    eid,
                    deepcopy(session.question),
                    session.number,
                    request.answer,
                    now,
                    2,
                )
                head = AttemptCoaching(owner, aid, session_id, eid, created_at=now, updated_at=now)
                context = context_for(attempt, head)
                if coaching:
                    coaching.updated_at = max(now, coaching.updated_at)
                    tx.put(reference("AttemptCoaching", owner, coaching.id), coaching)
                tx.new(reference("Attempt", owner, aid), attempt)
            else:
                attempt, head, eid = previous, coaching, generated[0]
                if kind == "coaching_answer":
                    question = head.pending_question
                    head.history += (CoachingTurn(question, request.answer, evaluation.id, now),)
                    head.coaching_count += 1
                    if unavailable(request.answer):
                        head.unavailable_questions += (question,)
                    context = context_for(attempt, head)
                else:
                    context = deepcopy(evaluation.coaching_input)
                head.current_evaluation_id, head.stage, head.pending_question = (
                    eid,
                    "evaluating",
                    None,
                )
                head.updated_at = max(now, head.updated_at)
            job = Evaluation(
                owner,
                eid,
                attempt.id,
                created_at=now,
                deadline_at=now + 900000,
                coaching_contract_version=2,
                coaching_input=context,
                round_index=context.coaching_count,
                retry_of_evaluation_id=evaluation.id if kind == "retry_evaluation" else None,
            )
            dispatch = Dispatch(owner, eid, job.deadline_at, created_at=now, next_at=now)
            session.active = ActiveAttempt(
                attemptId=attempt.id, evaluationId=eid, status="processing"
            )
            self._touch(session, now)
            tx.put(sr, session)
            method = tx.new if fresh else tx.put
            method(reference("AttemptCoaching", owner, attempt.id), head)
            tx.new(reference("Evaluation", owner, eid), job)
            tx.new(reference("Dispatch", owner, eid), dispatch)
            return Reply(202, session.active.wire())

        return self._post(owner, key, fingerprint, run)

    def accept_initial_coaching_once(self, *args):
        return self._accept_v2(*args)

    def accept_coaching_answer_once(self, *args):
        return self._accept_v2(*args)

    def retry_coaching_evaluation_once(self, *args):
        return self._accept_v2(*args)

    def retry_coaching_attempt_once(self, *args):
        return self._accept_v2(*args)

    def _coaching_terminal(self, tx, evaluation, feedback, now):
        if evaluation.coaching_contract_version != 2:
            return
        cr = reference("AttemptCoaching", evaluation.owner, evaluation.attempt_id)
        coaching = tx.get(cr)
        if coaching is None or coaching.current_evaluation_id != evaluation.id:
            raise IntegrityError("current_coaching_pointer")
        coaching.stage = (
            "failed"
            if feedback is None
            else ("awaiting_answer" if feedback.result.status == "coaching" else "completed")
        )
        coaching.pending_question = None if feedback is None else feedback.result.follow_up_question
        if feedback is not None:
            coaching.last_successful_evaluation_id = evaluation.id
        coaching.updated_at = max(now, coaching.updated_at)
        tx.put(cr, coaching)
