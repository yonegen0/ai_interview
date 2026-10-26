"""Atomic STAR transitions shared by Memory and DynamoDB; no external calls."""

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid4, uuid5

from interview_backend.models.internal import (
    BusinessError,
    DeliveryClaim,
    DeliveryResult,
    Dispatch,
    IntegrityError,
    MutationResult,
    Reply,
)
from interview_backend.repositories.budget import CommitWindow
from interview_backend.star_assist.models import (
    DAY,
    AnswerAssist,
    AnswerContext,
    AnswerDraft,
    ContextRequest,
    GlobalStarQuota,
    RecoveryRotation,
    StarApplication,
    StarDraft,
    StarGeneration,
    StarQuota,
    StarRecoveryResult,
    StarRequest,
    TargetCategoryPreference,
    TargetDetailsPreference,
)


def ref(kind, owner, identifier):
    return kind, owner, identifier


def digest(value):
    raw = value if isinstance(value, str) else json.dumps(value, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8", errors="surrogatepass")).hexdigest()


def month_for(now):
    return datetime.fromtimestamp(now / 1000, UTC).astimezone(timezone_jst()).strftime("%Y-%m")


def timezone_jst():
    from datetime import timezone

    return timezone(timedelta(hours=9))


def quota_id(month):
    return str(uuid5(NAMESPACE_URL, "ai-interview/star-quota/v1/" + month))


def live(record, now):
    return record is not None and type(record.expires_at) is int and record.expires_at > now // 1000


def receipt(record):
    return {
        "id": record.id,
        "version": record.version,
        "updatedAt": record.updated_at,
        "expiresAt": record.expires_at,
    }


def bound_expiry(tx, expires_at):
    """Keep every read dependency live until the storage commit begins."""
    previous = tx.window or CommitWindow()
    upper = expires_at * 1000
    tx.window = CommitWindow(
        lower=previous.lower,
        upper=min(previous.upper, upper) if previous.upper is not None else upper,
        remaining_ms=previous.remaining_ms,
    )


class StarRepositoryMixin:
    def star_post(self, owner, key, fingerprint, method, path, operation):
        generated = {}

        def identifier(name):
            return generated.setdefault(name, str(uuid4()))

        def run(tx):
            rr = ref("StarRequest", owner, key)
            cached = tx.get(rr)
            if cached:
                if cached.fingerprint != fingerprint:
                    raise BusinessError(409, "IDEMPOTENCY_CONFLICT")
                return Reply(cached.status, deepcopy(cached.receipt))
            if tx.exists(ref("IdempotencyRecord", owner, key)) or tx.exists(
                ref("QuestionBankChange", owner, key)
            ):
                raise BusinessError(409, "IDEMPOTENCY_CONFLICT")
            now = self.clock()
            try:
                reply = operation(tx, now, identifier)
            except BusinessError:
                cached = tx.refresh(rr)
                if cached is None:
                    raise
                if cached.fingerprint != fingerprint:
                    raise BusinessError(409, "IDEMPOTENCY_CONFLICT") from None
                return Reply(cached.status, deepcopy(cached.receipt))
            tx.new(
                rr,
                StarRequest(
                    owner, key, fingerprint, method, path, reply.status, deepcopy(reply.body), now
                ),
            )
            return reply

        return self._atomic(run, temporal=True)

    def star_request(self, owner, key):
        row = self._read(ref("StarRequest", owner, key))
        if row is None:
            raise BusinessError(404, "STAR_REQUEST_NOT_FOUND")
        return Reply(
            200,
            {
                "requestHash": row.fingerprint,
                "method": row.method,
                "path": row.path,
                "status": row.status,
                "receipt": row.receipt,
            },
        )

    def star_preferences(self, owner):
        def run(tx):
            now = self.clock()
            category = tx.get(ref("TargetCategoryPreference", owner, "CURRENT"))
            details = tx.get(ref("TargetDetailsPreference", owner, "CURRENT"))
            return Reply(
                200,
                {
                    "category": None
                    if not live(category, now)
                    else {
                        **receipt(category),
                        "generationId": category.id,
                        "targetCategory": category.target_category,
                    },
                    "details": None
                    if not live(details, now)
                    else {
                        **receipt(details),
                        "generationId": details.id,
                        "industry": details.industry,
                        "company": details.company,
                    },
                },
            )

        return self._atomic(run)

    def star_save_preferences(self, tx, owner, body, now, new):
        result = {}
        for kind, value in (
            ("TargetCategoryPreference", body.category),
            ("TargetDetailsPreference", body.details),
        ):
            if value is None:
                continue
            rr = ref(kind, owner, "CURRENT")
            previous = tx.get(rr)
            active = live(previous, now)
            if value.expectedGeneration != (previous.id if active else None) or (
                value.expectedVersion != (previous.version if active else 0)
            ):
                raise BusinessError(409, "DRAFT_VERSION_CONFLICT")
            if active:
                bound_expiry(tx, previous.expires_at)
            identifier = previous.id if active else new(kind)
            version = previous.version + 1 if active else 1
            expiry = now // 1000 + 14 * DAY
            if kind == "TargetCategoryPreference":
                row = TargetCategoryPreference(
                    owner, identifier, value.targetCategory, version, now, expiry
                )
            else:
                if active and (previous.industry, previous.company) == (
                    value.industry,
                    value.company,
                ):
                    result["details"] = receipt(previous)
                    continue
                row = TargetDetailsPreference(
                    owner, identifier, value.industry, value.company, version, now, expiry
                )
            tx.put(rr, row)
            result["category" if kind == "TargetCategoryPreference" else "details"] = receipt(row)
        return Reply(200, result)

    def _star_context_spec(self, tx, owner, session_id, request):
        session = tx.get(ref("Session", owner, session_id))
        if session is None:
            raise BusinessError(404, "SESSION_NOT_FOUND")
        _, attempt, coaching, evaluation = self._active_records(tx, owner, session)
        if session.question.id != request.questionId:
            raise BusinessError(409, "SESSION_STATE_CONFLICT")
        if request.operationKind == "initial_answer":
            if attempt and (
                attempt.coaching_contract_version == 2 or evaluation.status != "failed"
            ):
                raise BusinessError(409, "SESSION_STATE_CONFLICT")
        else:
            if request.fromAttemptId != (attempt.id if attempt else None) or (
                request.fromEvaluationId != (evaluation.id if evaluation else None)
            ):
                raise BusinessError(409, "SESSION_STATE_CONFLICT")
            if request.operationKind == "retry_attempt":
                if evaluation.status != "completed" or (coaching and coaching.stage != "completed"):
                    raise BusinessError(409, "SESSION_STATE_CONFLICT")
            elif not coaching or coaching.stage != "awaiting_answer":
                raise BusinessError(409, "SESSION_STATE_CONFLICT")
        question = (
            coaching.pending_question
            if request.operationKind == "coaching_answer"
            else session.question.question
        )
        spec = {
            "owner": owner,
            "session_id": session_id,
            "question_number": session.number,
            "question_id": session.question.id,
            "question_hash": digest(session.question.wire()),
            "question": question,
            "operation_kind": request.operationKind,
            "from_attempt_id": attempt.id if attempt else None,
            "from_evaluation_id": evaluation.id if evaluation else None,
        }
        return AnswerContext(
            owner=owner,
            id=str(uuid5(NAMESPACE_URL, "ai-interview/star-context/v1/" + digest(spec))),
            **{k: v for k, v in spec.items() if k != "owner"},
        )

    def star_create_context(self, tx, owner, session_id, body):
        row = self._star_context_spec(tx, owner, session_id, body)
        rr = ref("AnswerContext", owner, row.id)
        previous = tx.get(rr)
        if previous and previous.status != "ACTIVE":
            raise BusinessError(409, "DRAFT_CLOSED")
        if previous is None:
            tx.new(rr, row)
        return Reply(200, {"contextId": row.id, "operationKind": row.operation_kind})

    def _star_context(self, tx, owner, context_id):
        row = tx.get(ref("AnswerContext", owner, context_id))
        if row is None:
            raise BusinessError(404, "STAR_CONTEXT_NOT_FOUND")
        if row.status != "ACTIVE":
            raise BusinessError(409, "DRAFT_CLOSED")
        request = ContextRequest(
            operationKind=row.operation_kind,
            questionId=row.question_id,
            fromAttemptId=row.from_attempt_id if row.operation_kind != "initial_answer" else None,
            fromEvaluationId=row.from_evaluation_id
            if row.operation_kind != "initial_answer"
            else None,
        )
        current = self._star_context_spec(tx, owner, row.session_id, request)
        if current.id != row.id:
            raise BusinessError(409, "SESSION_STATE_CONFLICT")
        return row

    def star_drafts(self, owner, context_id):
        def run(tx):
            context = self._star_context(tx, owner, context_id)
            now = self.clock()
            result = {}
            for kind, identifier, label in (
                ("AnswerDraft", context.answer_draft_id, "answerDraft"),
                ("StarDraft", context.star_draft_id, "starDraft"),
            ):
                row = tx.get(ref(kind, owner, identifier)) if identifier else None
                if row is None or row.status != "ACTIVE" or not live(row, now):
                    result[label] = None
                elif kind == "AnswerDraft":
                    result[label] = {
                        **receipt(row),
                        "answer": row.answer,
                        "applicationId": row.application_id,
                    }
                else:
                    result[label] = {
                        **receipt(row),
                        **row.value.model_dump(),
                        "originalCandidates": [c.model_dump() for c in row.original_candidates],
                        "generationTargetCategory": row.generation_target_category,
                    }
            return Reply(200, result)

        return self._atomic(run)

    def _star_draft(self, tx, owner, kind, identifier, now):
        row = tx.get(ref(kind, owner, identifier))
        if row is None:
            raise BusinessError(404, "STAR_DRAFT_NOT_FOUND")
        context = self._star_context(tx, owner, row.context_id)
        current_id = context.answer_draft_id if kind == "AnswerDraft" else context.star_draft_id
        if row.status != "ACTIVE" or not live(row, now) or current_id != row.id:
            raise BusinessError(409, "DRAFT_CLOSED")
        bound_expiry(tx, row.expires_at)
        return row, context

    def star_create_draft(self, tx, owner, context_id, kind, body, now, new):
        context = self._star_context(tx, owner, context_id)
        attribute = "answer_draft_id" if kind == "AnswerDraft" else "star_draft_id"
        previous_id = getattr(context, attribute)
        previous = tx.get(ref(kind, owner, previous_id)) if previous_id else None
        if previous and previous.status == "ACTIVE" and live(previous, now):
            raise BusinessError(409, "DRAFT_VERSION_CONFLICT")
        if kind == "StarDraft":
            self._star_cancel(tx, context, now)
            if body.generationId is not None:
                raise BusinessError(400, "VALIDATION_ERROR")
            row = StarDraft(owner, new(kind), context.id, body, 1, now, now // 1000 + 7 * DAY)
        else:
            if body.applicationId is not None:
                raise BusinessError(400, "VALIDATION_ERROR")
            row = AnswerDraft(
                owner, new(kind), context.id, body.answer, 1, now, now // 1000 + 14 * DAY
            )
        setattr(context, attribute, row.id)
        tx.put(ref("AnswerContext", owner, context.id), context)
        tx.new(ref(kind, owner, row.id), row)
        return Reply(201, receipt(row))

    def star_update_draft(self, tx, owner, identifier, kind, body, now, *, discard=False):
        row, context = self._star_draft(tx, owner, kind, identifier, now)
        if row.version != body.expectedVersion:
            raise BusinessError(409, "DRAFT_VERSION_CONFLICT")
        if discard:
            row.status = "DISCARDED"
            self._star_scrub(row)
            if kind == "StarDraft":
                self._star_cancel(tx, context, now)
        elif kind == "AnswerDraft":
            if row.answer == body.answer and row.application_id == body.applicationId:
                return Reply(200, receipt(row))
            if body.applicationId:
                application = tx.get(ref("StarApplication", owner, body.applicationId))
                if (
                    not live(application, now)
                    or application.context_id != context.id
                    or application.answer_draft_id != row.id
                ):
                    raise BusinessError(404, "STAR_APPLICATION_NOT_FOUND")
                bound_expiry(tx, application.expires_at)
                application.updated_at, application.expires_at = now, now // 1000 + 14 * DAY
                tx.put(ref("StarApplication", owner, application.id), application)
            row.answer, row.application_id = body.answer, body.applicationId
            row.expires_at = now // 1000 + 14 * DAY
        else:
            value = body.model_dump(exclude={"expectedVersion"})
            from interview_backend.star_assist.models import StarInput

            proposed = StarInput.model_validate(value)
            if proposed.generationId:
                generation = tx.get(ref("StarGeneration", owner, proposed.generationId))
                if (
                    not live(generation, now)
                    or generation.context_id != context.id
                    or generation.star_draft_id != row.id
                    or (generation.result is None or generation.result.status != "ready")
                ):
                    # Existing adopted generation remains editable after its payload expires.
                    if proposed.generationId != row.value.generationId:
                        raise BusinessError(404, "STAR_GENERATION_NOT_FOUND")
                elif proposed.generationId != row.value.generationId:
                    bound_expiry(tx, generation.expires_at)
                    row.original_candidates = tuple(generation.result.candidates)
                    row.generation_target_category = generation.input.targetCategory
            if proposed == row.value:
                return Reply(200, receipt(row))
            row.value = proposed
            row.expires_at = now // 1000 + 7 * DAY
        row.version += 1
        row.updated_at = now
        tx.put(ref(kind, owner, row.id), row)
        return Reply(200, receipt(row))

    @staticmethod
    def _star_scrub(row):
        if isinstance(row, AnswerDraft):
            row.answer, row.application_id = "", None
        else:
            from interview_backend.star_assist.models import Notes, StarInput

            row.value = StarInput(
                notes=Notes(S="", T="", A="", R=""),
                targetCategory=None,
                industry="",
                company="",
                candidates=[],
                selectedCandidateId=None,
                generationId=None,
            )
            row.original_candidates, row.generation_target_category = (), None

    def star_apply(self, tx, owner, identifier, body, now, new):
        star, context = self._star_draft(tx, owner, "StarDraft", identifier, now)
        answer, answer_context = self._star_draft(tx, owner, "AnswerDraft", body.answerDraftId, now)
        if answer_context.id != context.id:
            raise BusinessError(404, "STAR_DRAFT_NOT_FOUND")
        if star.version != body.expectedVersion or answer.version != body.expectedAnswerVersion:
            raise BusinessError(409, "DRAFT_VERSION_CONFLICT")
        candidate = next((c for c in star.value.candidates if c.id == body.candidateId), None)
        if candidate is None or star.value.selectedCandidateId != body.candidateId:
            raise BusinessError(400, "VALIDATION_ERROR")
        application = StarApplication(
            owner,
            new("application"),
            context.id,
            answer.id,
            star.value.generationId,
            candidate.id,
            digest(candidate.text),
            now,
            now // 1000 + 14 * DAY,
        )
        answer.answer, answer.application_id = candidate.text, application.id
        answer.version, answer.updated_at, answer.expires_at = (
            answer.version + 1,
            now,
            application.expires_at,
        )
        tx.new(ref("StarApplication", owner, application.id), application)
        tx.put(ref("AnswerDraft", owner, answer.id), answer)
        return Reply(
            200,
            {
                **receipt(answer),
                "applicationId": application.id,
                "answerHash": application.applied_hash,
            },
        )

    def _star_quota_rows(self, tx, owner, month):
        identifier = quota_id(month)
        rows = []
        for kind, subject, limit in (
            ("StarQuota", owner, 20),
            ("GlobalStarQuota", "@star-service", 600),
        ):
            rr = ref(kind, subject, month)
            row = tx.get(rr) or (StarQuota if kind == "StarQuota" else GlobalStarQuota)(
                subject, identifier, month
            )
            if row.month != month:
                raise IntegrityError("star_quota_month")
            rows.append((rr, row, limit))
        return rows

    def star_quota(self, owner):
        def run(tx):
            month = month_for(self.clock())
            rows = self._star_quota_rows(tx, owner, month)
            return Reply(
                200,
                {
                    "month": month,
                    "user": {
                        "reserved": rows[0][1].reserved,
                        "consumed": rows[0][1].consumed,
                        "remaining": 20 - rows[0][1].reserved - rows[0][1].consumed,
                    },
                    "global": {
                        "reserved": rows[1][1].reserved,
                        "consumed": rows[1][1].consumed,
                        "remaining": 600 - rows[1][1].reserved - rows[1][1].consumed,
                    },
                },
            )

        return self._atomic(run)

    def star_generate(self, tx, owner, body, now, new):
        row, context = self._star_draft(tx, owner, "StarDraft", body.starDraftId, now)
        if context.active_generation_id:
            raise BusinessError(409, "STAR_GENERATION_IN_PROGRESS")
        if row.version != body.expectedVersion:
            raise BusinessError(409, "DRAFT_VERSION_CONFLICT")
        if row.value.targetCategory is None or not any(
            v.strip() for v in row.value.notes.model_dump().values()
        ):
            raise BusinessError(400, "VALIDATION_ERROR")
        month = month_for(now)
        end = datetime.strptime(month, "%Y-%m").replace(tzinfo=timezone_jst())
        end = (end.replace(day=28) + timedelta(days=4)).replace(day=1)
        tx.window = CommitWindow(upper=min(row.expires_at * 1000, int(end.timestamp() * 1000)))
        for rr, quota, limit in self._star_quota_rows(tx, owner, month):
            if quota.reserved + quota.consumed >= limit:
                raise BusinessError(429, "STAR_QUOTA_EXCEEDED")
            quota.reserved += 1
            tx.put(rr, quota)
        job = StarGeneration(
            owner,
            new("generation"),
            context.id,
            row.id,
            deepcopy(row.value),
            context.question,
            month,
            now,
            now + 900000,
        )
        dispatch = Dispatch(
            owner, job.id, job.deadline_at, created_at=now, next_at=now, job_kind="star"
        )
        context.active_generation_id = job.id
        tx.put(ref("AnswerContext", owner, context.id), context)
        tx.new(ref("StarGeneration", owner, job.id), job)
        tx.new(ref("Dispatch", owner, job.id), dispatch)
        return Reply(202, {"generationId": job.id, "status": "QUEUED"})

    def star_generation(self, owner, identifier):
        job = self._read(ref("StarGeneration", owner, identifier))
        if job is None or (job.expires_at is not None and not live(job, self.clock())):
            raise BusinessError(404, "STAR_GENERATION_NOT_FOUND")
        return Reply(
            200,
            {
                "generationId": job.id,
                "status": job.status,
                "generationTargetCategory": job.input.targetCategory,
                "result": job.result.model_dump() if job.result else None,
            },
        )

    def _star_finish(self, tx, job, dispatch, now, status, result=None):
        if job.worker_state == "terminal":
            return
        if job.quota_state == "reserved":
            for rr, quota, _ in self._star_quota_rows(tx, job.owner, job.month):
                if quota.reserved < 1:
                    raise IntegrityError("star_quota_underflow")
                quota.reserved -= 1
                tx.put(rr, quota)
            job.quota_state = "released"
        job.status, job.worker_state, job.result = status, "terminal", result
        job.finished_at, job.expires_at = now, now // 1000 + 7 * DAY
        job.lock_owner = job.lock_expires_at = None
        dispatch.status = "DONE"
        dispatch.send_owner = dispatch.send_expires_at = dispatch.claim_due_at = None
        context = tx.get(ref("AnswerContext", job.owner, job.context_id))
        if context and context.active_generation_id == job.id:
            context.active_generation_id = None
            tx.put(ref("AnswerContext", job.owner, context.id), context)
        tx.put(ref("StarGeneration", job.owner, job.id), job)
        tx.put(ref("Dispatch", job.owner, job.id), dispatch)

    def _star_cancel(self, tx, context, now):
        if context.active_generation_id:
            job, dispatch = self._star_related(tx, context.owner, context.active_generation_id)
            if not job.call_started:
                self._star_finish(tx, job, dispatch, now, "CANCELLED")
                context.active_generation_id = None

    def star_complete_answer(
        self, tx, session, request, evaluation_id, answer, application_id, now
    ):
        kind = getattr(request, "kind", "initial_answer")
        if kind == "retry_evaluation":
            return
        values = {"operationKind": kind, "questionId": session.question.id}
        if kind != "initial_answer":
            values.update(
                fromAttemptId=getattr(
                    request, "attemptId", getattr(request, "fromAttemptId", None)
                ),
                fromEvaluationId=request.fromEvaluationId,
            )
        try:
            context = self._star_context_spec(
                tx, session.owner, session.id, ContextRequest(**values)
            )
        except BusinessError:
            if application_id:
                raise
            return  # Legacy repeated V1 submit has no new STAR context.
        stored = tx.get(ref("AnswerContext", session.owner, context.id))
        if application_id:
            from interview_backend.models.public import validate_id

            validate_id(application_id)
            application = tx.get(ref("StarApplication", session.owner, application_id))
            # Formal acceptance time is retained across CAS retries; expiry uses the live clock.
            if not live(application, self.clock()) or application.context_id != context.id:
                raise BusinessError(404, "STAR_APPLICATION_NOT_FOUND")
            bound_expiry(tx, application.expires_at)
            assist = AnswerAssist(
                session.owner,
                evaluation_id,
                context.id,
                application.id,
                application.generation_id,
                application.candidate_id,
                digest(answer),
                digest(answer) != application.applied_hash,
            )
            tx.new(ref("AnswerAssist", session.owner, evaluation_id), assist)
        if stored:
            stored.status = "COMPLETED"
            for kind, identifier in (
                ("AnswerDraft", stored.answer_draft_id),
                ("StarDraft", stored.star_draft_id),
            ):
                row = tx.get(ref(kind, session.owner, identifier)) if identifier else None
                if row:
                    row.status, row.version = "COMPLETED", row.version + 1
                    self._star_scrub(row)
                    tx.put(ref(kind, session.owner, row.id), row)
            self._star_cancel(tx, stored, now)
            tx.put(ref("AnswerContext", session.owner, stored.id), stored)

    def job_kind(self, owner, identifier):
        dispatch = self._read(ref("Dispatch", owner, identifier))
        return dispatch.job_kind if dispatch else None

    def _star_related(self, tx, owner, identifier):
        job, dispatch = tx.many(
            (ref("StarGeneration", owner, identifier), ref("Dispatch", owner, identifier))
        )
        if (
            not job
            or not dispatch
            or dispatch.job_kind != "star"
            or job.owner != owner
            or job.id != identifier
        ):
            raise IntegrityError("star_dispatch_relation")
        return job, dispatch

    def star_acquire_delivery(self, owner, identifier, generation, token):
        def run(tx):
            now = self.clock()
            job, dispatch = self._star_related(tx, owner, identifier)
            if (
                job.worker_state != "pending"
                or dispatch.status != "PENDING"
                or dispatch.generation != generation
            ):
                return DeliveryResult("obsolete")
            if now >= job.deadline_at:
                return DeliveryResult("deadline_due")
            if now < dispatch.next_at:
                return DeliveryResult("not_due")
            if (
                dispatch.send_expires_at
                and now < dispatch.send_expires_at
                and dispatch.send_owner != token
            ):
                return DeliveryResult("busy")
            if dispatch.send_owner != token:
                dispatch.send_owner, dispatch.send_expires_at = token, now + 45000
                dispatch.delivery_attempts += 1
                dispatch.generation_attempts += 1
                tx.put(ref("Dispatch", owner, identifier), dispatch)
            tx.window = CommitWindow(upper=min(dispatch.send_expires_at, job.deadline_at))
            return DeliveryResult(
                "acquired",
                DeliveryClaim(
                    owner,
                    identifier,
                    generation,
                    token,
                    dispatch.send_expires_at,
                    job.deadline_at,
                    "star",
                ),
            )

        return self._atomic(run, temporal=True)

    def star_delivery_result(self, delivery, next_at):
        def run(tx):
            now = self.clock()
            job, dispatch = self._star_related(tx, delivery.owner, delivery.evaluation_id)
            if (
                job.worker_state != "pending"
                or dispatch.status != "PENDING"
                or (
                    dispatch.generation != delivery.generation
                    or dispatch.send_owner != delivery.token
                    or not dispatch.send_expires_at
                    or now >= min(dispatch.send_expires_at, job.deadline_at)
                )
            ):
                return MutationResult("obsolete")
            tx.window = CommitWindow(upper=min(dispatch.send_expires_at, job.deadline_at))
            dispatch.send_owner = dispatch.send_expires_at = None
            if next_at is None:
                dispatch.status, dispatch.queued_at, dispatch.claim_due_at = (
                    "QUEUED",
                    now,
                    now + 120000,
                )
            else:
                dispatch.next_at = next_at
            tx.put(ref("Dispatch", job.owner, job.id), dispatch)
            return MutationResult("applied")

        return self._atomic(run, temporal=True)

    def star_claim(self, owner, identifier, generation, token, provider_id="fake"):
        from interview_backend.star_assist.live_provider import PROVIDER_IDS

        if provider_id not in PROVIDER_IDS | {"fake"}:
            raise ValueError("StarProviderConfiguration")

        def run(tx):
            now = self.clock()
            job, dispatch = self._star_related(tx, owner, identifier)
            if job.worker_state != "pending" or dispatch.generation != generation:
                return None
            context = tx.get(ref("AnswerContext", owner, job.context_id))
            draft = tx.get(ref("StarDraft", owner, job.star_draft_id))
            try:
                self._star_context(tx, owner, job.context_id)
                valid = (
                    context.active_generation_id == job.id
                    and live(draft, now)
                    and draft.status == "ACTIVE"
                )
            except BusinessError:
                valid = False
            if not valid or now >= job.deadline_at:
                self._star_finish(
                    tx, job, dispatch, now, "CANCELLED" if not valid else "FAILED_BEFORE_START"
                )
                return None
            job.worker_state, job.status, job.lock_owner, job.lock_expires_at = (
                "running",
                "PREPARED",
                token,
                now + 60000,
            )
            job.provider_id = provider_id  # Pin before durable started; never reselect after it.
            dispatch.status, dispatch.claim_due_at = "CLAIMED", None
            dispatch.send_owner = dispatch.send_expires_at = None
            tx.window = CommitWindow(upper=min(job.deadline_at, draft.expires_at * 1000))
            tx.put(ref("StarGeneration", owner, identifier), job)
            tx.put(ref("Dispatch", owner, identifier), dispatch)
            return job

        return self._atomic(run, temporal=True)

    def star_start(self, lease):
        def run(tx):
            now = self.clock()
            job, dispatch = self._star_related(tx, lease.owner, lease.id)
            if (
                job.worker_state != "running"
                or job.lock_owner != lease.lock_owner
                or job.provider_id != lease.provider_id
                or (now >= min(job.lock_expires_at or 0, job.deadline_at))
            ):
                return False
            if job.call_started:
                return True  # Storage confirmation for this same fenced execution only.
            try:
                context = self._star_context(tx, job.owner, job.context_id)
                draft = tx.get(ref("StarDraft", job.owner, job.star_draft_id))
                valid = (
                    context.active_generation_id == job.id
                    and live(draft, now)
                    and draft.status == "ACTIVE"
                )
            except BusinessError:
                valid = False
            if not valid:
                self._star_finish(tx, job, dispatch, now, "CANCELLED")
                return False
            for rr, quota, _ in self._star_quota_rows(tx, job.owner, job.month):
                if quota.reserved < 1:
                    raise IntegrityError("star_quota_underflow")
                quota.reserved -= 1
                quota.consumed += 1
                tx.put(rr, quota)
            job.call_started, job.quota_state, job.status = True, "consumed", "STARTED"
            tx.window = CommitWindow(
                upper=min(job.lock_expires_at, job.deadline_at, draft.expires_at * 1000)
            )
            tx.put(ref("StarGeneration", job.owner, job.id), job)
            return True

        return self._atomic(run, temporal=True)

    def star_finish(self, lease, status, result=None):
        def run(tx):
            now = self.clock()
            job, dispatch = self._star_related(tx, lease.owner, lease.id)
            if job.worker_state == "terminal":
                return True
            if job.lock_owner != lease.lock_owner or now >= min(
                job.lock_expires_at or 0, job.deadline_at
            ):
                return False
            if result is not None and not job.call_started:
                raise IntegrityError("star_result_without_start")
            tx.window = CommitWindow(upper=min(job.lock_expires_at, job.deadline_at))
            self._star_finish(tx, job, dispatch, now, status, result)
            return True

        return self._atomic(run, temporal=True)

    def star_recover(self, owner, identifier):
        def run(tx):
            now = self.clock()
            job, dispatch = self._star_related(tx, owner, identifier)
            if job.worker_state == "terminal":
                return StarRecoveryResult("unchanged")
            context = tx.get(ref("AnswerContext", owner, job.context_id))
            draft = tx.get(ref("StarDraft", owner, job.star_draft_id))
            try:
                self._star_context(tx, owner, job.context_id)
                closed = (
                    not live(draft, now)
                    or draft.status != "ACTIVE"
                    or context.active_generation_id != job.id
                )
            except BusinessError:
                closed = True
            changed = False
            if closed and not job.call_started:
                self._star_finish(tx, job, dispatch, now, "CANCELLED")
                changed = True
            elif now >= job.deadline_at or (
                job.worker_state == "running" and now >= job.lock_expires_at
            ):
                if job.call_started:
                    self._star_finish(tx, job, dispatch, now, "OUTCOME_UNKNOWN")
                elif now >= job.deadline_at:
                    self._star_finish(tx, job, dispatch, now, "FAILED_BEFORE_START")
                else:
                    job.worker_state, job.status, job.lock_owner, job.lock_expires_at = (
                        "pending",
                        "QUEUED",
                        None,
                        None,
                    )
                    self._star_requeue(tx, job, dispatch, now)
                changed = True
            elif dispatch.status == "QUEUED" and now >= dispatch.claim_due_at:
                self._star_requeue(tx, job, dispatch, now)
                changed = True
            return StarRecoveryResult(
                "applied" if changed else "unchanged",
                changed and job.status == "OUTCOME_UNKNOWN",
            )

        return self._atomic(run, temporal=True)

    def star_work_observation(self, owner, identifier):
        def run(tx):
            job, dispatch = self._star_related(tx, owner, identifier)
            if job.worker_state == "terminal":
                return ()
            now, values = self.clock(), []
            if dispatch.status == "PENDING":
                values.append(("PendingAge", max(0, now - dispatch.created_at) / 1000))
            elif dispatch.status == "QUEUED":
                values.append(("QueuedAge", max(0, now - dispatch.queued_at) / 1000))
            if job.worker_state == "running" and now >= job.lock_expires_at:
                values.append(("ExpiredLease", 1))
            if now >= job.deadline_at:
                values.append(("DeadlineOverdue", 1))
            return tuple(values)

        return self._atomic(run)

    @staticmethod
    def _star_requeue(tx, job, dispatch, now):
        dispatch.generation += 1
        dispatch.status, dispatch.next_at, dispatch.generation_attempts = "PENDING", now, 0
        dispatch.send_owner = dispatch.send_expires_at = dispatch.queued_at = (
            dispatch.claim_due_at
        ) = None
        tx.put(ref("StarGeneration", job.owner, job.id), job)
        tx.put(ref("Dispatch", job.owner, job.id), dispatch)

    def recovery_rotation(self):
        identifier = str(uuid5(NAMESPACE_URL, "ai-interview/recovery-rotation/v1"))

        def run(tx):
            rr = ref("RecoveryRotation", "@system", identifier)
            row = tx.get(rr) or RecoveryRotation("@system", identifier)
            position = row.position
            row.position = (position + 1) % 4
            tx.put(rr, row)
            return position

        return self._atomic(run)
