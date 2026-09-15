"""Shared domain transitions; storage adapters own snapshots and commit retries."""

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from interview_backend.models.internal import (
    Attempt,
    BusinessError,
    ClaimResult,
    CursorSnapshot,
    DeliveryClaim,
    DeliveryResult,
    Dispatch,
    Evaluation,
    IdempotentReply,
    IntegrityError,
    ItemTooLarge,
    LeaseClaim,
    MutationResult,
    RecoveryCursor,
    Reply,
    Session,
)
from interview_backend.models.public import ActiveAttempt, SessionResponse, validate_id
from interview_backend.repositories.budget import CommitWindow
from interview_backend.repositories.codec import FAILURE, PARTITIONS, encode, validate


def utc_ms():
    return int(datetime.now(UTC).timestamp() * 1000)


def validate_feedback(feedback, attempt):
    if feedback is None or (
        feedback.attemptId != attempt.id
        or feedback.sessionId != attempt.session_id
        or feedback.question != attempt.question
        or feedback.questionNumber != attempt.question_number
        or feedback.answer != attempt.answer
    ):
        raise IntegrityError("feedback_snapshot")


def ref(kind, owner, identifier):
    return kind, owner, identifier


def execution_identity(owner, evaluation_id, generation, token):
    if type(owner) is not str or not owner.strip() or type(generation) is not int or generation < 1:
        raise ValueError("execution_identity")
    validate_id(evaluation_id)
    validate_id(token)


def session_body(session):
    return SessionResponse(
        sessionId=session.id,
        question=session.question,
        questionNumber=session.number,
        activeAttempt=session.active,
    ).wire()


class DomainRepository:
    def __init__(self, clock=utc_ms):
        self.clock = clock

    def _atomic(self, operation, *, temporal=False, conflict_once=False):
        raise NotImplementedError

    def _read(self, reference):
        return self._atomic(lambda tx: tx.get(reference))

    def _post(self, owner, key, fingerprint, operation):
        reference = ref("IdempotencyRecord", owner, key)
        now = self.clock()

        def run(tx):
            cached = tx.get(reference)
            if cached is not None:
                if cached.fingerprint != fingerprint:
                    raise BusinessError(409, "IDEMPOTENCY_CONFLICT")
                return cached.reply
            try:
                reply = operation(tx, now)
            except BusinessError:
                # A competing same-key request may commit between the first I read and S read.
                cached = tx.refresh(reference)
                if cached is None:
                    raise
                if cached.fingerprint != fingerprint:
                    raise BusinessError(409, "IDEMPOTENCY_CONFLICT") from None
                return cached.reply
            tx.put(reference, IdempotentReply(fingerprint, reply, now, 1, owner, key))
            return reply

        return self._atomic(run)

    def create_once(self, owner, key, fingerprint, questions, new_id):
        generated = []

        def run(tx, now):
            if not generated:
                generated.append(new_id())
            session = Session(
                owner, generated[0], deepcopy(questions), created_at=now, updated_at=now
            )
            tx.new(ref("Session", owner, session.id), session)
            return Reply(201, {"sessionId": session.id})

        return self._post(owner, key, fingerprint, run)

    def accept_once(self, owner, key, fingerprint, session_id, question_id, answer, new_id):
        generated = []

        def run(tx, now):
            sr = ref("Session", owner, session_id)
            session = tx.get(sr)
            if session is None:
                raise BusinessError(404, "SESSION_NOT_FOUND")
            if session.question.id != question_id or (
                session.active and session.active.status == "processing"
            ):
                raise BusinessError(409, "SESSION_STATE_CONFLICT")
            if not generated:
                generated.extend((new_id(), new_id()))
            aid, eid = generated
            attempt = Attempt(
                owner, aid, session_id, eid, deepcopy(session.question), session.number, answer, now
            )
            evaluation = Evaluation(owner, eid, aid, created_at=now, deadline_at=now + 900000)
            dispatch = Dispatch(owner, eid, evaluation.deadline_at, created_at=now, next_at=now)
            session.active = ActiveAttempt(attemptId=aid, evaluationId=eid, status="processing")
            self._touch(session, now)
            tx.put(sr, session)
            for kind, record in (
                ("Attempt", attempt),
                ("Evaluation", evaluation),
                ("Dispatch", dispatch),
            ):
                tx.new(ref(kind, owner, record.id), record)
            return Reply(202, session.active.wire())

        return self._post(owner, key, fingerprint, run)

    def next_once(self, owner, key, fingerprint, session_id, attempt_id):
        def run(tx, now):
            sr = ref("Session", owner, session_id)
            session = tx.get(sr)
            if session is None:
                raise BusinessError(404, "SESSION_NOT_FOUND")
            if (
                session.active is None
                or session.active.attemptId != attempt_id
                or session.active.status != "completed"
            ):
                raise BusinessError(409, "SESSION_STATE_CONFLICT")
            session.number += 1
            session.active = None
            self._touch(session, now)
            tx.put(sr, session)
            return Reply(200, session_body(session))

        return self._post(owner, key, fingerprint, run)

    def get_session(self, owner, resource_id):
        session = self._read(ref("Session", owner, resource_id))
        if session is None:
            raise BusinessError(404, "SESSION_NOT_FOUND")
        return Reply(200, session_body(session))

    def get_evaluation(self, owner, resource_id):
        evaluation = self._read(ref("Evaluation", owner, resource_id))
        if evaluation is None:
            raise BusinessError(404, "ATTEMPT_NOT_FOUND")
        body = {
            "evaluationId": evaluation.id,
            "attemptId": evaluation.attempt_id,
            "status": evaluation.status,
        }
        if evaluation.error is not None:
            body["error"] = evaluation.error
        return Reply(200, body)

    def get_feedback(self, owner, resource_id):
        attempt = self._read(ref("Attempt", owner, resource_id))
        if attempt is None:
            raise BusinessError(404, "ATTEMPT_NOT_FOUND")
        evaluation = self._read(ref("Evaluation", owner, attempt.evaluation_id))
        if evaluation is None or evaluation.attempt_id != attempt.id:
            raise IntegrityError("feedback_relation")
        if evaluation.status != "completed":
            raise BusinessError(409, "EVALUATION_NOT_COMPLETED")
        validate_feedback(evaluation.feedback, attempt)
        return Reply(200, evaluation.feedback.wire())

    @staticmethod
    def _touch(session, now):
        session.version += 1
        session.updated_at = max(session.updated_at, now)

    def _related(self, tx, owner, eid, full=False):
        er, dr = ref("Evaluation", owner, eid), ref("Dispatch", owner, eid)
        evaluation, dispatch = tx.many((er, dr))
        if evaluation is None and dispatch is None:
            return None
        if evaluation is None or dispatch is None:
            raise IntegrityError("missing_relation")
        attempt = session = None
        if full:
            ar = ref("Attempt", owner, evaluation.attempt_id)
            attempt = tx.get(ar)
            if attempt is None:
                raise IntegrityError("missing_attempt")
            sr = ref("Session", owner, attempt.session_id)
            evaluation, dispatch, attempt, session = tx.many((er, dr, ar, sr))
            if any(r is None for r in (evaluation, dispatch, attempt, session)):
                raise IntegrityError("missing_relation")
            if (
                attempt.evaluation_id != eid
                or evaluation.attempt_id != attempt.id
                or attempt.session_id != session.id
                or attempt.created_at != evaluation.created_at
                or attempt.question
                != session.questions[(attempt.question_number - 1) % len(session.questions)]
            ):
                raise IntegrityError("reverse_reference")
            if session.active and (
                session.active.evaluationId == eid or session.active.attemptId == attempt.id
            ):
                if (
                    session.active.evaluationId != eid
                    or session.active.attemptId != attempt.id
                    or session.active.status != evaluation.status
                    or session.number != attempt.question_number
                ):
                    raise IntegrityError("active_relation")
        records = (evaluation, dispatch, attempt, session) if full else (evaluation, dispatch)
        if any(record.owner != owner for record in records):
            raise IntegrityError("owner_relation")
        if (
            evaluation.id != eid
            or dispatch.id != eid
            or evaluation.deadline_at != dispatch.deadline_at
            or evaluation.created_at != dispatch.created_at
        ):
            raise IntegrityError("evaluation_dispatch_relation")
        expected = {"pending": {"PENDING", "QUEUED"}, "running": {"CLAIMED"}, "terminal": {"DONE"}}
        if dispatch.status not in expected[evaluation.worker_state]:
            raise IntegrityError("cross_state")
        return evaluation, dispatch, attempt, session

    @staticmethod
    def _save(tx, *records):
        for record in records:
            tx.put(ref(type(record).__name__, record.owner, record.id), record)

    def claim(self, owner, evaluation_id, generation, execution_id, execution_config, now=None):
        execution_identity(owner, evaluation_id, generation, execution_id)
        validate(execution_config)

        def run(tx):
            at = self.clock() if now is None else max(now, self.clock())
            related = self._related(tx, owner, evaluation_id, full=True)
            if related is None:
                return ClaimResult("missing")
            e, d, a, _ = related
            if e.worker_state == "terminal":
                return ClaimResult("terminal")
            if generation != d.generation:
                return ClaimResult("stale")
            if at >= e.deadline_at:
                return ClaimResult("deadline_due")
            if (
                e.worker_state == "running"
                and e.lock_owner == execution_id
                and e.call_phase == "not_started"
                and at < e.lock_expires_at
            ):
                return ClaimResult(
                    "acquired",
                    LeaseClaim(
                        owner,
                        e.id,
                        a,
                        execution_id,
                        e.lease_version,
                        e.lock_expires_at,
                        e.deadline_at,
                        d.generation,
                        e.execution_config,
                    ),
                )
            if e.worker_state != "pending":
                return ClaimResult("busy")
            tx.window = CommitWindow(upper=e.deadline_at)
            e.worker_state = "running"
            e.lease_version += 1
            e.lock_owner, e.lock_expires_at = execution_id, at + 90000
            e.execution_config = execution_config
            d.status = "CLAIMED"
            d.send_owner = d.send_expires_at = d.claim_due_at = None
            self._save(tx, e, d)
            return ClaimResult(
                "acquired",
                LeaseClaim(
                    owner,
                    e.id,
                    a,
                    execution_id,
                    e.lease_version,
                    e.lock_expires_at,
                    e.deadline_at,
                    d.generation,
                    execution_config,
                ),
            )

        return self._atomic(run, temporal=True)

    @staticmethod
    def _has_lease(e, d, lease, now):
        return (
            e.worker_state == "running"
            and d.status == "CLAIMED"
            and d.generation == lease.generation
            and e.lock_owner == lease.execution_id
            and e.lease_version == lease.lease_version
            and now < min(e.lock_expires_at, e.deadline_at)
        )

    def mark_call_started(self, lease, now=None):
        def run(tx):
            at = self.clock() if now is None else max(now, self.clock())
            related = self._related(tx, lease.owner, lease.evaluation_id)
            if related is None or not self._has_lease(*related[:2], lease, at):
                return MutationResult("lost_lease")
            e, _ = related[:2]
            if e.call_phase == "started":
                return MutationResult("confirmed_same_execution")
            if min(e.lock_expires_at, e.deadline_at) - at < 50000:
                return MutationResult("lost_lease")
            tx.window = CommitWindow(
                upper=min(e.lock_expires_at, e.deadline_at) - 50000 + 1,
                remaining_ms=50000,
            )
            if not tx.window.valid(at):
                return MutationResult("lost_lease")
            e.call_phase, e.call_started_at = "started", at
            self._save(tx, e)
            return MutationResult("applied")

        return self._atomic(run, temporal=True)

    def _terminal(self, tx, e, d, session, feedback, reason, now):
        e.worker_state, e.finished_at = "terminal", now
        e.status = "completed" if feedback is not None else "failed"
        e.feedback = deepcopy(feedback)
        e.error = None if feedback is not None else dict(FAILURE)
        e.failure_reason = None if feedback is not None else reason
        e.prompt_version = e.execution_config.prompt_version if e.execution_config else None
        d.status = "DONE"
        d.send_owner = d.send_expires_at = d.claim_due_at = None
        if session.active and (session.active.attemptId, session.active.evaluationId) == (
            e.attempt_id,
            e.id,
        ):
            session.active = session.active.model_copy(update={"status": e.status})
            self._touch(session, now)
            self._save(tx, session)
        self._save(tx, e, d)

    def finish(self, lease, feedback=None, reason="PROVIDER_FAILED", now=None):
        def run(tx):
            at = self.clock() if now is None else max(now, self.clock())
            related = self._related(tx, lease.owner, lease.evaluation_id, full=True)
            if related is None:
                return MutationResult("lost_lease")
            e, d, a, s = related
            if e.worker_state == "terminal":
                return MutationResult("already_terminal", e)
            if not self._has_lease(e, d, lease, at):
                return MutationResult("lost_lease")
            tx.window = CommitWindow(upper=min(e.lock_expires_at, e.deadline_at))
            result, failure = feedback, reason
            if result is not None:
                if e.call_phase != "started":
                    raise IntegrityError("result_without_start")
                validate_feedback(result, a)
                try:
                    candidate = replace(
                        e,
                        feedback=result,
                        status="completed",
                        worker_state="terminal",
                        finished_at=at,
                    )
                    encode("Evaluation", candidate, 0)
                except ItemTooLarge:
                    result, failure = None, "RESULT_TOO_LARGE"
            self._terminal(tx, e, d, s, result, failure, at)
            return MutationResult("applied", e)

        return self._atomic(run, temporal=True)

    def acquire_delivery(self, owner, evaluation_id, generation, sender_id, now=None):
        execution_identity(owner, evaluation_id, generation, sender_id)

        def run(tx):
            at = self.clock() if now is None else max(now, self.clock())
            related = self._related(tx, owner, evaluation_id)
            if related is None:
                return DeliveryResult("obsolete")
            e, d = related[:2]
            if e.worker_state != "pending" or d.generation != generation or d.status != "PENDING":
                return DeliveryResult("obsolete")
            if at >= e.deadline_at:
                return DeliveryResult("deadline_due")
            if at < d.next_at:
                return DeliveryResult("not_due")
            if (
                d.send_owner == sender_id
                and d.send_expires_at is not None
                and at < d.send_expires_at
            ):
                return DeliveryResult(
                    "acquired",
                    DeliveryClaim(
                        owner,
                        evaluation_id,
                        generation,
                        sender_id,
                        d.send_expires_at,
                        d.deadline_at,
                    ),
                )
            if d.send_expires_at is not None and at < d.send_expires_at:
                return DeliveryResult("busy")
            tx.window = CommitWindow(
                lower=max(d.next_at, d.send_expires_at or 0), upper=d.deadline_at
            )
            d.send_owner, d.send_expires_at = sender_id, at + 45000
            d.delivery_attempts += 1
            d.generation_attempts += 1
            self._save(tx, d)
            return DeliveryResult(
                "acquired",
                DeliveryClaim(
                    owner, evaluation_id, generation, sender_id, d.send_expires_at, d.deadline_at
                ),
            )

        return self._atomic(run, temporal=True)

    def _delivery_result(self, delivery, next_at, now):
        def run(tx):
            at = self.clock() if now is None else max(now, self.clock())
            related = self._related(tx, delivery.owner, delivery.evaluation_id)
            if related is None:
                return MutationResult("obsolete")
            e, d = related[:2]
            if (
                e.worker_state != "pending"
                or d.status != "PENDING"
                or d.generation != delivery.generation
                or d.send_owner != delivery.token
                or d.send_expires_at is None
                or at >= min(d.send_expires_at, d.deadline_at)
            ):
                return MutationResult("obsolete")
            tx.window = CommitWindow(upper=min(d.send_expires_at, d.deadline_at))
            d.send_owner = d.send_expires_at = None
            if next_at is None:
                d.status, d.queued_at, d.claim_due_at = "QUEUED", at, at + 120000
            else:
                d.next_at = next_at
            self._save(tx, d)
            return MutationResult("applied")

        return self._atomic(run, temporal=True)

    def confirm_delivery(self, delivery, now=None):
        return self._delivery_result(delivery, None, now)

    def fail_delivery(self, delivery, next_at, now=None):
        return self._delivery_result(delivery, next_at, now)

    def delivery_attempts(self, owner, evaluation_id):
        d = self._read(ref("Dispatch", owner, evaluation_id))
        return d.generation_attempts if d else 1

    def recover(self, owner, evaluation_id, now=None):
        def run(tx):
            at = self.clock() if now is None else max(now, self.clock())
            related = self._related(tx, owner, evaluation_id, full=True)
            if related is None:
                return MutationResult("unchanged")
            e, d, _, s = related
            if e.worker_state == "terminal":
                return MutationResult("unchanged", e)
            reason = None
            if at >= e.deadline_at:
                reason = "DEADLINE_EXCEEDED"
                tx.window = CommitWindow(lower=e.deadline_at)
            elif e.worker_state == "running" and at >= e.lock_expires_at:
                tx.window = CommitWindow(lower=e.lock_expires_at, upper=e.deadline_at)
                if e.call_phase == "started":
                    reason = "OUTCOME_UNKNOWN"
                else:
                    e.worker_state = "pending"
                    e.lock_owner = e.lock_expires_at = e.execution_config = None
                    self._save(tx, e)
            elif not (d.status == "QUEUED" and at >= d.claim_due_at):
                return MutationResult("unchanged", e)
            else:
                # T10 only fences E/D; Session was checked for integrity but is not mutable input.
                tx.window = CommitWindow(lower=d.claim_due_at, upper=e.deadline_at)
                tx.ignore_dependency(ref("Session", owner, s.id))
            if reason:
                self._terminal(tx, e, d, s, None, reason, at)
                return MutationResult("failed", e)
            d.generation += 1
            d.status, d.next_at, d.generation_attempts = "PENDING", at, 0
            d.send_owner = d.send_expires_at = d.queued_at = d.claim_due_at = None
            self._save(tx, d)
            return MutationResult("requeued", e)

        return self._atomic(run, temporal=True)

    def dispatch_event(self, owner, evaluation_id):
        """Resolve current generation for Recovery; this grants no rights."""
        d = self._read(ref("Dispatch", owner, evaluation_id))
        if d is None:
            return None
        return DeliveryClaim(owner, evaluation_id, d.generation, str(uuid4()), 0).event()

    def work_observation(self, owner, evaluation_id):
        """Recovery-only read: consistent E/D classification, no business mutation."""

        def run(tx):
            related = self._related(tx, owner, evaluation_id)
            if related is None:
                return ()
            e, d, _, _ = related
            if e.worker_state == "terminal":
                return ()
            now, values = self.clock(), []
            if d.status == "PENDING":
                values.append(("PendingAge", max(0, now - d.created_at) / 1000))
            elif d.status == "QUEUED":
                values.append(("QueuedAge", max(0, now - d.queued_at) / 1000))
            if e.worker_state == "running" and now >= e.lock_expires_at:
                values.append(("ExpiredLease", 1))
            if now >= e.deadline_at:
                values.append(("DeadlineOverdue", 1))
            return tuple(values)

        return self._atomic(run)

    def get_cursor(self, partition):
        if partition not in PARTITIONS:
            raise ValueError("partition")
        reference = ref("RecoveryCursor", "", partition.removeprefix("WORK#"))

        def run(tx):
            cursor = tx.get(reference)
            now = self.clock()
            return CursorSnapshot(
                cursor or RecoveryCursor(partition, now, None, now, now), tx.revision(reference)
            )

        return self._atomic(run)

    def save_cursor(self, snapshot, cursor):
        reference = ref("RecoveryCursor", "", cursor.partition.removeprefix("WORK#"))

        def run(tx):
            tx.get(reference)
            if tx.revision(reference) != snapshot.revision:
                return False
            tx.put(reference, cursor)
            return True

        return self._atomic(run, conflict_once=True)
