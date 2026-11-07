"""Offline Quick Start, session restore and progress tests without real AI or AWS."""

from itertools import count

import pytest
from conftest import uid

from interview_backend.application.service import Application
from interview_backend.assets import load_questions
from interview_backend.models.internal import BusinessError
from interview_backend.models.public import ActiveAttempt
from interview_backend.repositories.memory import MemoryRepository
from interview_backend.repositories.practice_progress import completed_question_ids
from interview_backend.star_assist.models import AnswerContext, AnswerDraft
from interview_backend.star_assist.repository import digest
from test_practice_progress import attempt, evaluation

NOW = 1780000000000
OWNER = "quick-user"


def setup():
    sequence = count(400)
    repo = MemoryRepository(clock=lambda: NOW)
    app = Application(repo, load_questions(), lambda: uid(next(sequence)))
    return app, repo


def test_sparse_progress_is_computed_by_bank_id_order():
    app, repo = setup()
    questions = app.questions
    a = [attempt(i, questions[i].id) for i in [0, 2, 4]]
    e = [evaluation(i, f"a{i}") for i in [0, 2, 4]]
    completed = completed_question_ids(OWNER, {q.id for q in questions}, a, e)
    assert completed == {q.id for q in [questions[0], questions[2], questions[4]]}
    # Progress and next ID must come from the same successful-initial set.
    repo._state.attempts.update({record.id: record for record in a})
    repo._state.evaluations.update({record.id: record for record in e})
    result = app.practice_progress(OWNER).body
    assert result["totalQuestions"] == 15
    assert result["completedQuestions"] == 3
    assert result["nextIncompleteQuestionId"] == questions[1].id


def test_quick_session_single_question_replay_owner_and_bank_version():
    app, repo = setup()
    q = app.questions[3]
    payload = {"mode": "quick", "questionId": q.id, "bankVersion": 0, "difficulty": "standard"}
    created = app.create(OWNER, uid(100), payload)
    assert app.create(OWNER, uid(100), payload) == created
    body = app.question(OWNER, created.body["sessionId"]).body
    assert body["mode"] == "quick"
    assert body["question"] == q.wire()
    assert body["totalQuestions"] == body["questionNumber"] == 1
    assert body["hasNext"] is False
    assert len(repo.snapshot().sessions) == 1
    assert sum(v.count for v in repo.snapshot().session_creation_budgets.values()) == 1
    with pytest.raises(BusinessError) as denied:
        app.question("another-user", created.body["sessionId"])
    assert denied.value.status == 404

    with pytest.raises(BusinessError) as changed:
        app.create(OWNER, uid(101), {**payload, "bankVersion": 9})
    assert (changed.value.status, changed.value.code) == (409, "QUESTION_BANK_CONFLICT")
    with pytest.raises(BusinessError) as unknown:
        app.create(OWNER, uid(102), {**payload, "questionId": uid(999)})
    assert (unknown.value.status, unknown.value.code) == (409, "QUESTION_UNAVAILABLE")
    assert len(repo.snapshot().sessions) == 1


@pytest.mark.parametrize(
    "extra",
    [
        {"category": "career"},
        {"bankVersion": None},
        {"difficulty": "hard"},
        {"questionId": "not-a-uuid"},
    ],
)
def test_quick_invalid_payload_rejected_before_creation(extra):
    app, repo = setup()
    request = {
        "mode": "quick",
        "questionId": app.questions[0].id,
        "bankVersion": 0,
        "difficulty": "standard",
        **extra,
    }
    with pytest.raises(BusinessError) as invalid:
        app.create(OWNER, uid(104), request)
    assert invalid.value.status == 400
    assert not repo.snapshot().sessions


def make_session(app, key=200, question=None):
    q = question or app.questions[0]
    payload = {"mode": "quick", "questionId": q.id, "bankVersion": 0, "difficulty": "standard"}
    return app.create(OWNER, uid(key), payload).body["sessionId"]


def add_draft(repo, session_id, question, index=300, expiry=600, updated=None):
    context_id, draft_id = uid(index), uid(index + 1)
    context = AnswerContext(
        owner=OWNER,
        id=context_id,
        session_id=session_id,
        question_number=1,
        question_id=question.id,
        question_hash=digest(question.wire()),
        question=question.question,
        operation_kind="initial_answer",
        answer_draft_id=draft_id,
    )
    draft = AnswerDraft(
        owner=OWNER,
        id=draft_id,
        context_id=context_id,
        answer="保存済みです。",
        version=1,
        updated_at=NOW if updated is None else updated,
        expires_at=NOW // 1000 + expiry,
    )
    repo._state.star_records[("AnswerContext", OWNER, context_id)] = context
    repo._state.star_records[("AnswerDraft", OWNER, draft_id)] = draft
    return context, draft


def test_resume_is_owner_scoped_and_restores_original_session():
    app, repo = setup()
    first = make_session(app)
    second = make_session(app, key=201)
    add_draft(repo, first, app.questions[0], index=301, updated=NOW - 100)
    add_draft(repo, second, app.questions[0], index=303, updated=NOW)
    result = app.practice_resume(OWNER, app.questions[0].id)
    assert result.body == {"status": "resume", "reason": "draft", "sessionId": second}
    assert app.practice_resume("another-user", app.questions[0].id, first).body == {
        "status": "none"
    }


def test_processing_and_local_pending_precede_other_drafts():
    app, repo = setup()
    original = make_session(app)
    with_draft = make_session(app, key=201)
    add_draft(repo, with_draft, app.questions[0])
    repo._state.sessions[original].active = ActiveAttempt(
        attemptId=uid(410), evaluationId=uid(411), status="processing"
    )
    assert app.practice_resume(OWNER, app.questions[0].id, with_draft, True).body == {
        "status": "resume", "reason": "processing", "sessionId": original
    }
    repo._state.sessions[original].active = None
    assert app.practice_resume(OWNER, app.questions[0].id, original, True).body == {
        "status": "resume", "reason": "local", "sessionId": original, "questionNumber": 1
    }


def test_expired_draft_and_changed_question_fail_closed_without_data_loss():
    app, repo = setup()
    sid = make_session(app)
    context, draft = add_draft(repo, sid, app.questions[0])
    draft.expires_at = NOW // 1000 - 1
    assert app.practice_resume(OWNER, app.questions[0].id).body == {"status": "none"}
    draft.expires_at = NOW // 1000 + 600
    old = repo._state.sessions[sid]
    old.questions = (old.question.model_copy(update={"question": "古い質問本文"}),)
    assert app.practice_resume(OWNER, app.questions[0].id).body == {"status": "changed"}
    assert context.answer_draft_id == draft.id
    assert draft.answer == "保存済みです。"


def test_local_session_reference_requires_original_question():
    app, repo = setup()
    sid = make_session(app, question=app.questions[1])
    assert app.practice_resume(OWNER, app.questions[0].id, sid).body == {"status": "none"}
    own = make_session(app, key=209)
    assert app.practice_resume(OWNER, app.questions[0].id, own).body == {
        "status": "resume", "reason": "local", "sessionId": own, "questionNumber": 1
    }
