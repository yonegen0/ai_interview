"""Owner-scoped previous accepted answer lookup: offline regression tests."""

from itertools import count

import pytest

from conftest import uid
from interview_backend.application.service import Application
from interview_backend.assets import load_questions
from interview_backend.api.handler import Handler
from interview_backend.demo import demo_event
from interview_backend.models.internal import BusinessError, Attempt
from interview_backend.repositories.codec import encode, to_wire
from interview_backend.repositories.dynamodb import DynamoDBRepository
from interview_backend.repositories.memory import MemoryRepository


def make_app():
    time = [1789171200000]
    repository = MemoryRepository(lambda: time[0])
    ids = count(1)
    app = Application(repository, load_questions(), lambda: uid(next(ids)))
    return app, repository, time


def submit_in_new_session(app, owner, category, text, number):
    created = app.create(owner, uid(number), {"category": category, "difficulty": "standard"})
    session_id = created.body["sessionId"]
    question_id = app.question(owner, session_id).body["question"]["id"]
    app.submit(owner, uid(number + 1000), session_id, {"questionId": question_id, "answer": text})
    return question_id


def test_latest_answer_across_sessions_with_owner_isolation():
    app, repo, time = make_app()
    qid = submit_in_new_session(app, "user-a", "career", "first", 200)
    time[0] += 1000
    assert submit_in_new_session(app, "user-a", "career", "second", 201) == qid
    time[0] += 1000
    submit_in_new_session(app, "user-b", "career", "other-user", 202)
    time[0] += 1000
    submit_in_new_session(app, "user-a", "motivation", "other-question", 203)
    assert app.previous_answer("user-a", qid).body == {
        "questionId": qid, "answer": "second"
    }
    assert app.previous_answer("user-b", qid).body == {
        "questionId": qid, "answer": "other-user"
    }
    assert app.previous_answer("user-c", qid).body == {
        "questionId": qid, "answer": None
    }
    assert len(repo.snapshot().attempts) == 4


def test_unsubmitted_draft_is_not_an_attempt():
    app, _, _ = make_app()
    session_id = app.create("user-a", uid(210), {
        "category": "career", "difficulty": "standard"
    }).body["sessionId"]
    qid = app.question("user-a", session_id).body["question"]["id"]
    assert app.previous_answer("user-a", qid).body["answer"] is None


def test_http_auth_validation_and_no_owner_override():
    app, _, _ = make_app()
    qid = submit_in_new_session(app, "user-a", "career", "private-answer", 211)
    handler = Handler(app)
    path = f"/questions/{qid}/previous-answer"
    assert handler(demo_event("GET", path, owner="user-b"))["body"].find("private-answer") == -1
    assert '"answer": null' in handler(demo_event("GET", path, owner="user-b"))["body"]
    assert '"private-answer"' in handler(demo_event("GET", path, owner="user-a"))["body"]
    event = demo_event("GET", path)
    event["requestContext"]["authorizer"]["jwt"]["claims"].pop("sub")
    assert handler(event)["statusCode"] == 401
    assert handler(demo_event("GET", "/questions/invalid/previous-answer"))["statusCode"] == 400
    assert handler(demo_event("POST", path))["statusCode"] == 405


def test_memory_search_cap_fails_closed(monkeypatch):
    import interview_backend.repositories.memory as memory
    monkeypatch.setattr(memory, "PREVIOUS_ANSWER_MAX_ATTEMPTS", 1)
    app, _, _ = make_app()
    qid = submit_in_new_session(app, "user-a", "career", "old", 220)
    submit_in_new_session(app, "user-a", "career", "new", 221)
    with pytest.raises(BusinessError) as exc:
        app.previous_answer("user-a", qid)
    assert (exc.value.status, exc.value.code) == (503, "PREVIOUS_ANSWER_UNAVAILABLE")


def test_dynamo_query_paginated_by_owner_and_latest_timestamp():
    from interview_backend.repositories.dynamodb import PREVIOUS_ANSWER_PAGE_SIZE
    question = load_questions()[0]
    other = next(q for q in load_questions() if q.id != question.id)
    owner = "user-a"
    first = Attempt(owner, uid(1), uid(21), uid(31), question, 1, "older", 100)
    excluded = Attempt(owner, uid(2), uid(22), uid(32), other, 1, "different", 150)
    latest = Attempt(owner, uid(3), uid(23), uid(33), question, 1, "newer", 300)
    cursor = {"PK": "USER#user-a", "SK": "ATTEMPT#" + uid(2)}
    items = [to_wire(encode("Attempt", record, 0)) for record in (first, excluded, latest)]

    class QueryClient:
        def __init__(self):
            self.calls = []

        def query(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return {"Items": items[:2], "LastEvaluatedKey": to_wire(cursor)}
            assert kwargs["ExclusiveStartKey"] == to_wire(cursor)
            return {"Items": items[2:]}

        def scan(self, **kwargs):
            pytest.fail("Scan is forbidden")

    client = QueryClient()
    repository = DynamoDBRepository(client, "test-table", monotonic_clock=lambda: 0)
    result = repository.previous_answer(owner, question.id).body
    assert result == {"questionId": question.id, "answer": "newer"}
    assert len(client.calls) == 2
    assert all(call["Limit"] == PREVIOUS_ANSWER_PAGE_SIZE for call in client.calls)
    assert all(call["ConsistentRead"] is True for call in client.calls)
    assert all(\n        call["KeyConditionExpression"] == "PK = :owner AND begins_with(SK, :attempt)"\n        for call in client.calls\n    )


def test_dynamo_cap_and_repeated_cursor_never_claim_absence(monkeypatch):
    import interview_backend.repositories.dynamodb as dynamodb
    monkeypatch.setattr(dynamodb, "PREVIOUS_ANSWER_MAX_ATTEMPTS", 1)
    question = load_questions()[0]
    cursor = {"PK": "USER#user-a", "SK": "ATTEMPT#" + uid(2)}
    item = to_wire(encode(
        "Attempt", Attempt("user-a", uid(2), uid(22), uid(32), question, 1, "x", 100), 0
    ))

    class Forever:
        def query(self, **kwargs):
            return {"Items": [item], "LastEvaluatedKey": to_wire(cursor)}

    repository = DynamoDBRepository(Forever(), "test-table", monotonic_clock=lambda: 0)
    with pytest.raises(BusinessError) as exc:
        repository.previous_answer("user-a", question.id)
    assert exc.value.code == "PREVIOUS_ANSWER_UNAVAILABLE"
