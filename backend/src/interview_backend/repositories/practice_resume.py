"""Bounded, owner-only discovery of a resumable question; no draft text in the reply."""

from interview_backend.models.internal import BusinessError, IntegrityError, Reply
from interview_backend.star_assist.repository import digest

RESUME_MAX_RECORDS = 2000
RESUME_PAGE_SIZE = 100


def practice_resume(repo, owner, question_id, defaults, local_session_id=None, local_pending=False):
    bank = repo.get_question_bank(defaults)
    question = next((q for q in bank["questions"] if q["id"] == question_id), None)
    if question is None:
        raise BusinessError(409, "QUESTION_BANK_CONFLICT")
    sessions = repo._owner_records("Session", owner, RESUME_MAX_RECORDS)
    by_id = {row.id: row for row in sessions}
    if len(by_id) != len(sessions):
        raise IntegrityError("resume_duplicate_session")
    now = repo.clock()
    pending = []
    draft_candidates = []
    changed = False

    def compatible(session):
        return session.question.wire() == question

    for session in sessions:
        if session.owner != owner:
            raise IntegrityError("resume_session_owner")
        if session.question.id != question_id:
            continue
        if session.active and session.active.status == "processing":
            if compatible(session):
                pending.append(session)
            else:
                changed = True

    if pending:
        session = max(pending, key=lambda row: (row.updated_at, row.id))
        return Reply(200, {"status": "resume", "reason": "processing", "sessionId": session.id})

    local = by_id.get(local_session_id) if local_session_id else None
    if local_pending and local is not None and local.question.id == question_id:
        if compatible(local) and (local.active is None or local.active.status != "completed"):
            return Reply(
                200,
                {
                    "status": "resume",
                    "reason": "local",
                    "sessionId": local.id,
                    "questionNumber": local.number,
                },
            )
        changed = True

    contexts = repo._owner_records("AnswerContext", owner, RESUME_MAX_RECORDS)
    for context in contexts:
        if context.owner != owner:
            raise IntegrityError("resume_context_owner")
        if (
            context.question_id != question_id
            or context.status != "ACTIVE"
            or context.operation_kind != "initial_answer"
        ):
            continue
        session = by_id.get(context.session_id)
        if session is None:
            # A cross-owner or deleted session may never be used as a restore target.
            continue
        if (
            session.question.id != question_id
            or session.number != context.question_number
            or context.question_hash != digest(session.question.wire())
            or context.question != session.question.question
            or (session.active and session.active.status == "completed")
        ):
            continue
        if session.active and session.active.status == "failed":
            # V2 retry-attempt is a separate operation, not an initial-answer draft.
            continue
        recent = None
        for kind, identifier in (
            ("AnswerDraft", context.answer_draft_id),
            ("StarDraft", context.star_draft_id),
        ):
            if not identifier:
                continue
            row = repo._read((kind, owner, identifier))
            if row is None:
                raise IntegrityError("resume_missing_draft")
            if row.owner != owner or row.context_id != context.id:
                raise IntegrityError("resume_draft_relation")
            if row.status == "ACTIVE" and row.expires_at > now // 1000:
                recent = max(recent or 0, row.updated_at)
        if recent is None:
            continue
        if compatible(session):
            draft_candidates.append((recent, session.updated_at, session.id))
        else:
            changed = True
    if draft_candidates:
        _, _, session_id = max(draft_candidates)
        return Reply(200, {"status": "resume", "reason": "draft", "sessionId": session_id})
    if local is not None and local.question.id == question_id:
        if compatible(local) and (local.active is None or local.active.status != "completed"):
            return Reply(
                200,
                {
                    "status": "resume",
                    "reason": "local",
                    "sessionId": local.id,
                    "questionNumber": local.number,
                },
            )
        changed = True
    return Reply(200, {"status": "changed" if changed else "none"})
