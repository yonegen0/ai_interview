"""Question publication, immutable practice snapshots and ADMIN authorization."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from conftest import uid

from interview_backend.api.admin import AdminHandler
from interview_backend.assets import load_questions
from interview_backend.models.internal import BusinessError, IntegrityError, Session
from interview_backend.models.public import BankSaveRequest
from interview_backend.repositories.codec import decode, encode


def save(runtime, questions, version=0, key=800, owner="admin"):
    event = {
        "rawPath": "/admin/question-bank",
        "headers": {"Idempotency-Key": uid(key)},
        "requestContext": {
            "http": {"method": "POST"},
            "authorizer": {"jwt": {"claims": {"sub": owner, "cognito:groups": '["USER","ADMIN"]'}}},
        },
        "body": json.dumps({"expectedVersion": version, "questions": questions}),
    }
    response = AdminHandler(runtime.repository, load_questions())(event)
    return response["statusCode"], json.loads(response["body"])


def test_defaults_and_snapshot_publication(runtime):
    defaults = [q.wire() for q in load_questions()]
    assert len(defaults) == 15
    assert defaults[0]["id"] == "f1500000-0000-4000-8000-000000000001"
    assert defaults[-1]["id"] == "f1500000-0000-4000-8000-000000000015"
    assert "\nまた、その軸" in defaults[1]["question"]
    sid = runtime.application.create(
        "user", uid(801), {"mode": "full", "difficulty": "standard"}
    ).body["sessionId"]
    changed = [{**defaults[-1], "question": "新しい質問"}]
    status, receipt = save(runtime, changed)
    assert status == 200 and receipt["version"] == 1
    assert runtime.application.question("user", sid).body["question"] == defaults[0]
    sid2 = runtime.application.create(
        "user", uid(802), {"mode": "full", "difficulty": "standard"}
    ).body["sessionId"]
    assert runtime.application.question("user", sid2).body["question"] == changed[0]
    assert (
        runtime.application.create(
            "user", uid(801), {"mode": "full", "difficulty": "standard"}
        ).body["sessionId"]
        == sid
    )
    assert save(runtime, changed) == (status, receipt)
    assert save(runtime, changed, 0, 803)[0] == 409
    assert save(runtime, changed, 1, 804)[1] == receipt
    assert not runtime.repository.snapshot().dispatches
    for kind, records in (
        ("QuestionBank", runtime.repository.snapshot().question_banks),
        ("QuestionBankChange", runtime.repository.snapshot().question_bank_changes),
    ):
        for record in records.values():
            item = encode(kind, record, 0)
            assert item["PK"] == "SYSTEM#QUESTION_BANK" and "work_pk" not in item
            assert encode(kind, decode(item)[0], 0) == item


def test_removed_category_replay_and_one_question_completion(runtime):
    payload = {"category": "career", "difficulty": "standard"}
    created = runtime.application.create("user", uid(805), payload)
    sid = created.body["sessionId"]
    qid = runtime.application.question("user", sid).body["question"]["id"]
    accepted = runtime.application.submit(
        "user", uid(806), sid, {"questionId": qid, "answer": "回答"}
    ).body
    runtime.worker.run("user", accepted["evaluationId"])
    with pytest.raises(BusinessError, match="SESSION_COMPLETED"):
        runtime.application.next_question(
            "user", uid(807), sid, {"fromAttemptId": accepted["attemptId"]}
        )
    assert save(runtime, [load_questions()[0].wire()])[0] == 200
    assert runtime.application.create("user", uid(805), payload) == created
    with pytest.raises(BusinessError, match="CATEGORY_UNAVAILABLE"):
        runtime.application.create("user", uid(808), payload)
    retry = runtime.application.submit(
        "user", uid(809), sid, {"questionId": qid, "answer": "再挑戦"}
    )
    assert retry.status == 202


def test_legacy_snapshot_stays_cyclic(runtime):
    question = load_questions()[0]
    legacy = Session("user", uid(810), (question,), number=2)
    assert legacy.question == question
    assert "practice_mode" not in json.loads(encode("Session", legacy, 0)["data"])
    assert decode(encode("Session", legacy, 0))[0] == legacy
    with pytest.raises(IntegrityError):
        encode("Session", replace(legacy, practice_mode="full", question_bank_version=0), 0)


@pytest.mark.parametrize(
    "groups,status",
    [
        (None, 403),
        ("USER", 403),
        ("ADMIN_HELPER", 403),
        ("admin", 403),
        ("ADMIN", 200),
        (["ADMIN"], 200),
        ('["ADMIN"]', 200),
        ("USER,ADMIN", 200),
        ("[ADMIN]", 200),
        ("[USER ADMIN]", 200),
        ("[USER, ADMIN]", 200),
        (" [ USER ADMIN ] ", 200),
        ("[ADMIN_HELPER]", 403),
        ("[USER NOTADMIN]", 403),
        ("[USER admin]", 403),
        ("[[ADMIN]]", 403),
        ('["ADMIN", 1]', 403),
        ('["ADMIN"', 403),
        ("[ADMIN,]", 403),
    ],
)
def test_exact_admin_group(runtime, groups, status):
    event = {
        "rawPath": "/admin/question-bank",
        "requestContext": {
            "http": {"method": "GET"},
            "authorizer": {"jwt": {"claims": {"sub": "admin", "cognito:groups": groups}}},
        },
    }
    assert AdminHandler(runtime.repository, load_questions())(event)["statusCode"] == status


def test_two_admins_same_version_only_one_wins(runtime):
    barrier = Barrier(2)
    defaults = [q.wire() for q in load_questions()]

    def edit(i):
        barrier.wait()
        return save(
            runtime, [{**defaults[0], "question": f"質問{i}"}], key=820 + i, owner=f"admin{i}"
        )[0]

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(edit, (0, 1))) == [200, 409]


def test_aggregate_size_rejection_keeps_bank_and_ledger_unchanged(runtime):
    from interview_backend.models.internal import QuestionBank
    from interview_backend.models.public import Question

    question = load_questions()[0].wire()
    oversized = [{**question, "id": uid(2000 + i), "question": "あ" * 1000} for i in range(100)]
    runtime.repository._state.question_banks["CURRENT"] = QuestionBank(
        tuple(Question(**q) for q in oversized), 1, 1, "admin"
    )
    runtime.repository._revisions[("QuestionBank", "", "CURRENT")] = 0
    before = runtime.repository.snapshot()
    status, body = save(runtime, oversized, 1)
    assert status == 400 and body["code"] == "QUESTION_BANK_TOO_LARGE"
    state = runtime.repository.snapshot()
    assert state == before


def test_corrupt_stored_bank_is_not_a_default_fallback(runtime):
    from interview_backend.models.internal import QuestionBank

    runtime.repository._state.question_banks["CURRENT"] = QuestionBank((), 1, 1, "admin")
    event = {
        "rawPath": "/admin/question-bank",
        "requestContext": {
            "http": {"method": "GET"},
            "authorizer": {"jwt": {"claims": {"sub": "admin", "cognito:groups": "ADMIN"}}},
        },
    }
    response = AdminHandler(runtime.repository, load_questions())(event)
    assert response["statusCode"] == 500
    assert json.loads(response["body"])["code"] == "INTERNAL_SERVER_ERROR"


@pytest.mark.parametrize("count,valid", [(0, False), (1, True), (100, True), (101, False)])
def test_bank_count_boundary(count, valid):
    questions = [{**load_questions()[0].wire(), "id": uid(900 + i)} for i in range(count)]
    if valid:
        BankSaveRequest(expectedVersion=0, questions=questions)
    else:
        with pytest.raises(ValueError):
            BankSaveRequest(expectedVersion=0, questions=questions)


def test_text_uuid_and_unknown_field_validation(runtime):
    question = load_questions()[0].wire()
    for questions in (
        [{**question, "question": " "}],
        [{**question, "question": "🙂" * 501}],
        [question, {**question, "id": question["id"].upper()}],
        [{**question, "category": "difficulty"}],
        [{**question, "unknown": True}],
    ):
        assert save(runtime, questions)[0] == 400
    assert save(runtime, [{**question, "question": "🙂" * 200}])[0] == 200
    assert save(runtime, [{**question, "question": "🙂" * 201}], 1, key=999)[0] == 400


def test_admin_ack_loss_is_confirmed_by_durable_operation_record(runtime):
    from types import SimpleNamespace

    from botocore.exceptions import EndpointConnectionError
    from test_dynamodb import SnapshotClient, db, snapshot, written

    before = snapshot(runtime.repository)
    questions = [load_questions()[0].wire()]
    expected = save(runtime, questions)
    after = snapshot(runtime.repository)
    client = SnapshotClient(before)

    def lost(_request):
        client.items = after
        raise EndpointConnectionError(endpoint_url="http://synthetic")

    client.on_write = lost
    assert save(SimpleNamespace(repository=db(client)), questions) == expected
    assert len(client.writes) == 1
    assert set(written(client)) == {"QuestionBank", "QuestionBankChange"}


def test_session_creation_retries_against_latest_complete_bank(runtime):
    from botocore.exceptions import ClientError
    from test_dynamodb import SnapshotClient, db, snapshot, written

    from interview_backend.application.service import Application

    first = [load_questions()[0].wire()]
    assert save(runtime, first)[0] == 200
    before = snapshot(runtime.repository)
    second = [load_questions()[1].wire()]
    assert save(runtime, second, 1, 860)[0] == 200
    after = snapshot(runtime.repository)
    client = SnapshotClient(before)

    def conflict(_request):
        if len(client.writes) == 1:
            client.items = after
            raise ClientError(
                {
                    "Error": {"Code": "TransactionCanceledException"},
                    "CancellationReasons": [{"Code": "ConditionalCheckFailed"}],
                },
                "TransactWriteItems",
            )
        return {}

    client.on_write = conflict
    app = Application(db(client), load_questions(), lambda: uid(861))
    assert app.create("user", uid(862), {"mode": "full", "difficulty": "standard"}).status == 201
    assert len(client.writes) == 2
    session = written(client)["Session"]
    assert session.question_bank_version == 2 and session.questions[0].wire() == second[0]
    checks = [
        a["ConditionCheck"] for a in client.writes[-1]["TransactItems"] if "ConditionCheck" in a
    ]
    assert len(checks) == 2
    assert {a["Key"]["SK"]["S"] for a in checks} == {"CURRENT", f"OP#user#{uid(862)}"}
    assert all(a["Key"]["PK"] == {"S": "SYSTEM#QUESTION_BANK"} for a in checks)


@pytest.mark.parametrize("field", ["accountId", "apiId", "stage", "token_use", "client_id", "iss"])
def test_admin_runtime_rejects_wrong_gateway_identity(runtime, field):
    from test_p4_runtime import context, environment, event

    from interview_backend.aws_runtime import ApiEntry
    from interview_backend.aws_settings import AwsSettings

    request = event()
    request["rawPath"] = "/dev/admin/question-bank"
    request["requestContext"]["http"]["method"] = "GET"
    claims = request["requestContext"]["authorizer"]["jwt"]["claims"]
    claims["cognito:groups"] = "ADMIN"
    entry = ApiEntry(
        AwsSettings.load(environment("admin"), "admin"),
        AdminHandler(runtime.repository, load_questions()),
    )
    assert entry(request, context("admin"))["statusCode"] == 200
    if field in {"accountId", "apiId", "stage"}:
        request["requestContext"][field] = "wrong"
    else:
        claims[field] = "wrong"
    assert entry(request, context("admin"))["statusCode"] == 401
