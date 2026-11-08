"""ADMIN-only Cognito nickname and owner history API tests (no AWS calls)."""

import json
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

from interview_backend.api.admin import AdminHandler
from interview_backend.api.admin_users import CognitoUsers, normalize_nickname
from interview_backend.assets import load_questions
from interview_backend.models.internal import Attempt, BusinessError
from interview_backend.models.public import Question
from interview_backend.repositories.history import build_history, parse_history_query

OWNER = "10000000-0000-4000-8000-000000000001"
OTHER = "10000000-0000-4000-8000-000000000002"


class FakeUsers:
    def __init__(self):
        self.calls = []
        self.nickname = None

    def list_users(self, limit, cursor):
        self.calls.append((limit, cursor))
        return {
            "users": [
                {
                    "userId": OWNER,
                    "nickname": self.nickname,
                    "email": "sample@example.invalid",
                    "enabled": True,
                }
            ],
            "nextCursor": "next" if cursor is None else None,
        }

    def update_nickname(self, user_id, value):
        self.calls.append((user_id, value))
        self.nickname = value or None
        return {"userId": user_id, "nickname": self.nickname}


def invoke(repo, users, method, path, *, groups="ADMIN", sub=OWNER, query=None, body=None):
    event = {
        "rawPath": path,
        "requestContext": {
            "authorizer": {"jwt": {"claims": {"sub": sub, "cognito:groups": groups}}},
            "http": {"method": method},
        },
    }
    if query is not None:
        event["queryStringParameters"] = query
    if body is not None:
        event["body"] = json.dumps(body)
    result = AdminHandler(repo, load_questions(), users)(event)
    return result["statusCode"], json.loads(result["body"]), result["headers"]


def test_admin_permission_and_no_store(runtime):
    users = FakeUsers()
    url = "/admin/users"
    assert invoke(runtime.repository, users, "GET", url, sub="")[0] == 401
    assert invoke(runtime.repository, users, "GET", url, groups="USER")[0] == 403
    status, body, headers = invoke(runtime.repository, users, "GET", url)
    assert status == 200 and headers["Cache-Control"] == "no-store"
    assert body["users"][0]["userId"] == OWNER and body["nextCursor"] == "next"
    assert users.calls == [(60, None)]
    assert (
        invoke(runtime.repository, users, "GET", url, query={"limit": "3", "cursor": "next"})[0]
        == 200
    )
    assert users.calls[-1] == (3, "next")
    for query in [{"limit": "61"}, {"limit": "0"}, {"limit": "1x"}, {"cursor": "\n"}]:
        assert invoke(runtime.repository, users, "GET", url, query=query)[0] == 400
    assert invoke(runtime.repository, users, "POST", url)[0] == 405


def test_history_owner_not_admin_and_feedback_not_found(runtime):
    users = FakeUsers()
    path = f"/admin/users/{OTHER}/history"
    status, result, _ = invoke(
        runtime.repository, users, "GET", path, query={"mode": "all", "period": "all"}
    )
    assert status == 200
    assert result["items"] == []
    assert result["usage"]["practiceAttempts"] == 0
    status, _, _ = invoke(
        runtime.repository,
        users,
        "GET",
        f"/admin/users/{OTHER}/attempts/{OWNER}/feedback",
        query={"includeFollowUpReviews": "1"},
    )
    assert status == 404
    assert (
        invoke(runtime.repository, users, "GET", f"/admin/users/{OTHER}/history", groups="USER")[0]
        == 403
    )
    assert (
        invoke(
            runtime.repository,
            users,
            "GET",
            f"/admin/users/{OTHER}/attempts/{OWNER}/feedback",
            query={"evaluationId": "invalid"},
        )[0]
        == 400
    )
    assert (
        invoke(
            runtime.repository,
            users,
            "GET",
            f"/admin/users/{OTHER}/attempts/{OWNER}/feedback",
            query={"includeFollowUpReviews": "0"},
        )[0]
        == 400
    )


def test_cursor_bound_to_target_owner(runtime):
    now = 1789084800000
    question = Question(id=OTHER, category="strengths", difficulty="standard", question="質問")
    attempt = Attempt(OWNER, OWNER, OTHER, OTHER, question, 1, "回答", now - 10)
    evaluation = SimpleNamespace(
        id=OTHER,
        owner=OWNER,
        attempt_id=OWNER,
        status="processing",
        coaching_contract_version=None,
        feedback=None,
    )
    second = Attempt(OWNER, OTHER, OTHER, OWNER, question, 1, "回答", now - 20)
    second_evaluation = SimpleNamespace(**{**vars(evaluation), "id": OWNER, "attempt_id": OTHER})
    page = build_history(
        OWNER, {"limit": "1"}, now, [attempt, second],
        [evaluation, second_evaluation], [], [], [],
    ).body
    cursor = page["nextCursor"]
    assert cursor is not None
    with pytest.raises(BusinessError) as error:
        parse_history_query(OTHER, {"limit": "1", "cursor": cursor}, now)
    assert error.value.status == 400


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ""),
        ("  かずき  ", "かずき"),
        ("e\u0301", "é"),
        ("👩‍💻", "👩‍💻"),
        ("あ" * 24, "あ" * 24),
    ],
)
def test_normalize_nickname(raw, expected):
    assert normalize_nickname(raw) == expected


@pytest.mark.parametrize("invalid", [None, 123, "a" * 25, "a\nb", "\x00"])
def test_invalid_nickname(invalid):
    with pytest.raises(BusinessError):
        normalize_nickname(invalid)


def test_nickname_set_and_delete(runtime):
    users = FakeUsers()
    path = f"/admin/users/{OWNER}/nickname"
    assert invoke(runtime.repository, users, "PUT", path, body={"nickname": " かずき "})[:2] == (
        200, {"userId": OWNER, "nickname": "かずき"}
    )
    assert (
        invoke(runtime.repository, users, "PUT", path, body={"nickname": ""})[1]["nickname"]
        is None
    )
    assert (
        invoke(runtime.repository, users, "PUT", path, body={"nickname": "a", "email": "other"})[0]
        == 400
    )
    assert (
        invoke(runtime.repository, users, "PUT", path, groups="USER", body={"nickname": "a"})[0]
        == 403
    )
    assert invoke(runtime.repository, users, "GET", path)[0] == 405


class FakeCognitoClient:
    def __init__(self):
        self.requests = []

    def list_users(self, **kwargs):
        self.requests.append(kwargs)
        return {
            "Users": [{
                "Attributes": [
                    {"Name": "sub", "Value": OWNER},
                    {"Name": "email", "Value": "sample@example.invalid"},
                ],
                "Enabled": True,
            }],
            "PaginationToken": "next",
        }
    def admin_update_user_attributes(self, **kwargs):
        self.requests.append(kwargs)
        if kwargs["Username"] == OTHER:
            raise ClientError(
                {"Error": {"Code": "UserNotFoundException", "Message": "private"}},
                "AdminUpdateUserAttributes",
            )


def test_cognito_sdk_shape_and_missing_user():
    fake = FakeCognitoClient()
    identity = CognitoUsers("ap-northeast-1", "ap-northeast-1_pool", client=fake)
    page = identity.list_users(60, "older")
    assert page["users"][0]["nickname"] is None
    assert page["nextCursor"] == "next"
    assert fake.requests[0]["PaginationToken"] == "older"
    assert identity.update_nickname(OWNER, "")["nickname"] is None
    assert fake.requests[-1]["UserAttributes"] == [{"Name": "nickname", "Value": ""}]
    with pytest.raises(BusinessError) as error:
        identity.update_nickname(OTHER, "test")
    assert error.value.status == 404
