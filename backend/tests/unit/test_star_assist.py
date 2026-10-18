"""STAR T01-T24 server acceptance tests, fixed clocks and offline transactions."""

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from itertools import count
from pathlib import Path
from uuid import uuid4

import pytest

from interview_backend.bootstrap import build_runtime
from interview_backend.models.internal import StorageUnavailable
from interview_backend.repositories.codec import decode, encode, from_wire, to_wire
from interview_backend.star_assist.models import DAY, GlobalStarQuota, StarQuota
from interview_backend.star_assist.repository import month_for, quota_id, ref


def test_T01_shared_fixture_matches_python():
    from interview_backend.star_assist.models import CATEGORIES, StarInput, StarResult
    from interview_backend.star_assist.provider import FakeStarProvider
    from interview_backend.star_assist.repository import digest

    fixture = json.loads(
        (Path(__file__).resolve().parents[3] / "contracts/star-v14-fixtures.json").read_text(
            encoding="utf-8"
        )
    )
    assert CATEGORIES == fixture["categories"]
    value = StarInput.model_validate(fixture["input"])
    result = StarResult.model_validate(fixture["result"])
    assert FakeStarProvider().generate("経験を教えてください。", value) == result
    assert digest(fixture["canonical"]["payload"]) == fixture["canonical"]["sha256"]


@pytest.fixture
def star():
    now = [int(datetime(2026, 10, 10, tzinfo=UTC).timestamp() * 1000)]
    runtime = build_runtime(clock=lambda: datetime.fromtimestamp(now[0] / 1000, UTC))
    numbers = count(1)

    def request(method, path, body=None, *, owner="owner", key=None, application=None):
        key = key or str(uuid4())
        event = {
            "requestContext": {
                "authorizer": {"jwt": {"claims": {"sub": owner}}},
                "http": {"method": method},
            },
            "rawPath": path,
            "headers": {"Idempotency-Key": key},
            "body": json.dumps(body),
        }
        if application:
            event["headers"]["X-Star-Application-Id"] = application
        response = runtime.handler(event)
        return response["statusCode"], json.loads(response["body"])

    sid = runtime.application.create(
        "owner", str(uuid4()), {"category": "job_change", "difficulty": "standard"}
    ).body["sessionId"]
    qid = runtime.application.question("owner", sid).body["question"]["id"]
    status, context = request(
        "POST",
        f"/sessions/{sid}/answer-contexts",
        {"operationKind": "initial_answer", "questionId": qid},
    )
    assert status == 200
    context_id = context["contextId"]
    value = {
        "notes": {
            "S": "顧客に課題があった。",
            "T": "改善を担当した。",
            "A": "本人が課題を整理した。",
            "R": "課題を共有した。",
        },
        "targetCategory": "corporate_sales",
        "industry": "",
        "company": "",
        "candidates": [],
        "selectedCandidateId": None,
        "generationId": None,
    }
    _, answer = request(
        "POST",
        f"/answer-contexts/{context_id}/answer-drafts",
        {"answer": "", "applicationId": None},
    )
    _, draft = request("POST", f"/answer-contexts/{context_id}/star-drafts", value)
    return runtime, now, request, sid, qid, context_id, value, answer, draft, numbers


def generated(star):
    runtime, _, request, _, _, _, _, _, draft, _ = star
    status, accepted = request(
        "POST",
        "/star-assist/generations",
        {"starDraftId": draft["id"], "expectedVersion": draft["version"]},
    )
    assert status == 202, accepted
    runtime.worker.run("owner", accepted["generationId"])
    status, result = request("GET", "/star-assist/generations/" + accepted["generationId"])
    assert status == 200 and result["status"] == "SUCCEEDED"
    return accepted, result


def test_T01_T02_contract_owner_no_evaluation(star):
    runtime, _, request, _, _, cid, _, answer, draft, _ = star
    assert request("GET", "/answer-contexts/" + cid + "/drafts", owner="other")[0] == 404
    assert (
        request(
            "PUT",
            "/answer-drafts/" + answer["id"],
            {"answer": "改ざん", "expectedVersion": 1},
            owner="other",
        )[0]
        == 404
    )
    assert (
        request(
            "POST",
            "/star-assist/generations",
            {"starDraftId": draft["id"], "expectedVersion": 1, "owner": "other"},
        )[0]
        == 400
    )
    state = runtime.repository.snapshot()
    assert not state.evaluations and not state.attempts and not state.dispatches
    for reference, row in state.star_records.items():
        item = encode(reference[0], row, 1)
        assert decode(from_wire(to_wire(item)))[0] == row
        assert "work_pk" not in item
        if hasattr(row, "expires_at"):
            assert type(item["expiresAt"]) is int


@pytest.mark.parametrize("kind,days", [("answer", 14), ("star", 7)])
def test_T03_T08_expiry_and_deleted_update_never_upserts(star, kind, days):
    runtime, now, request, _, _, cid, value, answer, draft, _ = star
    row = answer if kind == "answer" else draft
    now[0] = row["expiresAt"] * 1000 - 1
    assert request("GET", f"/answer-contexts/{cid}/drafts")[1][kind + "Draft"] is not None
    now[0] += 1
    assert request("GET", f"/answer-contexts/{cid}/drafts")[1][kind + "Draft"] is None
    payload = {"answer": "新しい"} if kind == "answer" else value
    assert (
        request("PUT", f"/{kind}-drafts/{row['id']}", {**payload, "expectedVersion": 1})[0] == 409
    )
    record_kind = "AnswerDraft" if kind == "answer" else "StarDraft"
    runtime.repository._state.star_records.pop(ref(record_kind, "owner", row["id"]))
    assert (
        request("PUT", f"/{kind}-drafts/{row['id']}", {**payload, "expectedVersion": 1})[0] == 404
    )
    assert days * DAY == row["expiresAt"] - int(datetime(2026, 10, 10, tzinfo=UTC).timestamp())


def test_T04_preference_incarnation_and_separate_expiry(star):
    _, now, request, *_ = star
    payload = {
        "category": {"expectedVersion": 0, "expectedGeneration": None, "targetCategory": "other"}
    }
    status, receipt = request("PUT", "/star-assist/preferences", payload)
    assert status == 200
    previous = request("GET", "/star-assist/preferences")[1]["category"]
    now[0] += DAY * 1000
    request(
        "PUT",
        "/star-assist/preferences",
        {
            "details": {
                "expectedVersion": 0,
                "expectedGeneration": None,
                "company": "任意",
                "industry": "任意",
            }
        },
    )
    assert (
        request("GET", "/star-assist/preferences")[1]["category"]["expiresAt"]
        == previous["expiresAt"]
    )
    now[0] = previous["expiresAt"] * 1000
    assert request("PUT", "/star-assist/preferences", payload)[0] == 200
    stale = {
        "category": {
            "expectedVersion": 1,
            "expectedGeneration": receipt["category"]["id"],
            "targetCategory": "it_engineering",
        }
    }
    assert request("PUT", "/star-assist/preferences", stale)[0] == 409


def test_T05_T06_T07_saved_receipt_after_competing_update(star):
    runtime, _, request, _, _, _, _, answer, *_ = star
    path = "/answer-drafts/" + answer["id"]
    key = str(uuid4())
    first = {"answer": "第一保存", "expectedVersion": 1}
    assert request("PUT", path, first, key=key)[0] == 200
    assert request("PUT", path, {"answer": "別タブ", "expectedVersion": 2})[0] == 200
    assert request("GET", "/star-assist/requests/" + key)[1]["receipt"]["version"] == 2
    assert request("PUT", path, first, key=key)[1]["version"] == 2
    assert request("PUT", path, {"answer": "違う", "expectedVersion": 1}, key=key)[0] == 409
    assert request("GET", "/star-assist/requests/" + key, owner="other")[0] == 404
    assert all(
        "第一保存" not in json.dumps(row.receipt, ensure_ascii=False)
        for row in runtime.repository.snapshot().star_records.values()
        if type(row).__name__ == "StarRequest"
    )


def test_T05_parallel_save_one_winner(star):
    _, _, request, _, _, _, _, answer, *_ = star
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda v: request(
                    "PUT", "/answer-drafts/" + answer["id"], {"answer": v, "expectedVersion": 1}
                )[0],
                ["タブA", "タブB"],
            )
        )
    assert sorted(results) == [200, 409]


def test_T08_T09_formal_accept_cancels_before_start_and_closes_drafts(star):
    runtime, _, request, sid, qid, _, _, answer, draft, _ = star
    _, accepted = request(
        "POST", "/star-assist/generations", {"starDraftId": draft["id"], "expectedVersion": 1}
    )
    status, formal = request(
        "POST",
        f"/sessions/{sid}/answers",
        {"kind": "initial_answer", "questionId": qid, "answer": "最終正式回答"},
    )
    assert status == 202, formal
    assert (
        request(
            "PUT", "/answer-drafts/" + answer["id"], {"expectedVersion": 1, "answer": "遅延保存"}
        )[0]
        == 409
    )
    assert (
        request("GET", "/star-assist/generations/" + accepted["generationId"])[1]["status"]
        == "CANCELLED"
    )
    assert not runtime.worker.run("owner", accepted["generationId"])
    assert runtime.worker.star_worker.provider.calls == 0
    assert request("GET", "/star-assist/quota")[1]["user"] == {
        "reserved": 0,
        "consumed": 0,
        "remaining": 20,
    }


def test_T10_T11_started_call_never_refunded_or_recalled(star):
    runtime, now, request, sid, qid, _, _, _, draft, _ = star
    _, accepted = request(
        "POST", "/star-assist/generations", {"starDraftId": draft["id"], "expectedVersion": 1}
    )
    identifier = accepted["generationId"]
    lease = runtime.repository.star_claim("owner", identifier, 1, str(uuid4()))
    assert runtime.repository.star_start(lease)
    request(
        "POST",
        f"/sessions/{sid}/answers",
        {"kind": "initial_answer", "questionId": qid, "answer": "正式"},
    )
    now[0] += 60001
    runtime.repository.recover("owner", identifier)
    runtime.repository.recover("owner", identifier)
    assert (
        request("GET", "/star-assist/generations/" + identifier)[1]["status"] == "OUTCOME_UNKNOWN"
    )
    assert not runtime.worker.run("owner", identifier)
    assert request("GET", "/star-assist/quota")[1]["user"]["consumed"] == 1


def test_T12_same_key_parallel_one_reservation(star):
    runtime, _, request, _, _, _, _, _, draft, _ = star
    key = str(uuid4())
    payload = {"starDraftId": draft["id"], "expectedVersion": 1}
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(
            pool.map(
                lambda _: request("POST", "/star-assist/generations", payload, key=key), range(4)
            )
        )
    assert all(v == values[0] for v in values)
    assert request("POST", "/star-assist/generations", payload)[0] == 409
    assert request("GET", "/star-assist/quota")[1]["user"]["reserved"] == 1
    runtime.worker.run("owner", values[0][1]["generationId"])
    runtime.worker.run("owner", values[0][1]["generationId"])
    assert runtime.worker.star_worker.provider.calls == 1


def test_T12_user_twenty_and_global_six_hundred(star):
    runtime, _, request, _, _, _, _, _, draft, _ = star
    payload = {"starDraftId": draft["id"], "expectedVersion": 1}
    for _ in range(20):
        status, accepted = request("POST", "/star-assist/generations", payload)
        assert status == 202
        runtime.worker.run("owner", accepted["generationId"])
    assert request("POST", "/star-assist/generations", payload)[0] == 429
    month = month_for(runtime.repository.clock())
    global_row = GlobalStarQuota("@star-service", quota_id(month), month, consumed=600)
    runtime.repository._state.star_records[ref("GlobalStarQuota", "@star-service", month)] = (
        global_row
    )
    # New JST month resets both independent buckets.
    star[1][0] = int(datetime(2026, 10, 31, 15, tzinfo=UTC).timestamp() * 1000)
    assert request("GET", "/star-assist/quota")[1]["month"] == "2026-11"


def test_T12_global_boundary_atomic_rejection(star):
    runtime, _, request, _, _, _, _, _, draft, _ = star
    month = month_for(runtime.repository.clock())
    runtime.repository._state.star_records[ref("GlobalStarQuota", "@star-service", month)] = (
        GlobalStarQuota("@star-service", quota_id(month), month, consumed=599)
    )
    payload = {"starDraftId": draft["id"], "expectedVersion": 1}
    accepted = request("POST", "/star-assist/generations", payload)
    assert accepted[0] == 202
    runtime.worker.run("owner", accepted[1]["generationId"])
    before = runtime.repository.snapshot()
    assert request("POST", "/star-assist/generations", payload)[0] == 429
    assert runtime.repository.snapshot() == before
    assert request("GET", "/star-assist/quota")[1]["global"]["remaining"] == 0


def test_T12_two_owners_race_for_last_global_slot(star):
    runtime, _, request, _, _, _, value, _, first, _ = star
    owner = "second-owner"
    sid = runtime.application.create(
        owner, str(uuid4()), {"category": "job_change", "difficulty": "standard"}
    ).body["sessionId"]
    qid = runtime.application.question(owner, sid).body["question"]["id"]
    context = request(
        "POST",
        f"/sessions/{sid}/answer-contexts",
        {"operationKind": "initial_answer", "questionId": qid},
        owner=owner,
    )[1]
    second = request(
        "POST", f"/answer-contexts/{context['contextId']}/star-drafts", value, owner=owner
    )[1]
    month = month_for(runtime.repository.clock())
    runtime.repository._state.star_records[ref("GlobalStarQuota", "@star-service", month)] = (
        GlobalStarQuota("@star-service", quota_id(month), month, consumed=599)
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda pair: request(
                    "POST",
                    "/star-assist/generations",
                    {"starDraftId": pair[1]["id"], "expectedVersion": 1},
                    owner=pair[0],
                ),
                [("owner", first), (owner, second)],
            )
        )
    assert sorted(result[0] for result in results) == [202, 429]
    quota = request("GET", "/star-assist/quota")[1]["global"]
    assert quota == {"reserved": 1, "consumed": 599, "remaining": 0}
    assert len(runtime.repository.snapshot().dispatches) == 1


@pytest.mark.parametrize("method", ["star_start", "star_finish"])
def test_T11_committed_storage_response_lost_calls_once(star, monkeypatch, method):
    runtime, _, request, _, _, _, _, _, draft, _ = star
    accepted = request(
        "POST", "/star-assist/generations", {"starDraftId": draft["id"], "expectedVersion": 1}
    )[1]
    original = getattr(runtime.repository, method)
    attempts = []

    def losing(*args, **kwargs):
        result = original(*args, **kwargs)
        attempts.append(result)
        if len(attempts) == 1:
            raise StorageUnavailable("synthetic")
        return result

    monkeypatch.setattr(runtime.repository, method, losing)
    assert runtime.worker.run("owner", accepted["generationId"])
    assert len(attempts) == 2
    assert runtime.worker.star_worker.provider.calls == 1
    assert not runtime.worker.run("owner", accepted["generationId"])
    assert request("GET", "/star-assist/quota")[1]["user"] == {
        "reserved": 0,
        "consumed": 1,
        "remaining": 19,
    }


def test_T11_unknown_start_never_calls_or_refunds(star, monkeypatch):
    runtime, now, request, _, _, _, _, _, draft, _ = star
    accepted = request(
        "POST", "/star-assist/generations", {"starDraftId": draft["id"], "expectedVersion": 1}
    )[1]
    original = runtime.repository.star_start

    def losing(*args):
        original(*args)
        raise StorageUnavailable("synthetic")

    monkeypatch.setattr(runtime.repository, "star_start", losing)
    assert not runtime.worker.run("owner", accepted["generationId"])
    assert runtime.worker.star_worker.provider.calls == 0
    now[0] += 60001
    runtime.repository.recover("owner", accepted["generationId"])
    assert (
        request("GET", "/star-assist/generations/" + accepted["generationId"])[1]["status"]
        == "OUTCOME_UNKNOWN"
    )
    assert request("GET", "/star-assist/quota")[1]["user"]["consumed"] == 1


def test_T13_old_month_refund_exactly_once(star):
    runtime, now, request, sid, qid, _, _, _, draft, _ = star
    now[0] = int(datetime(2026, 10, 31, 14, 59, 59, tzinfo=UTC).timestamp() * 1000)
    # Renew expired draft using a new ID; PUT may never recreate it.
    context_id = star[5]
    _, draft = request("POST", f"/answer-contexts/{context_id}/star-drafts", star[6])
    accepted = request(
        "POST", "/star-assist/generations", {"starDraftId": draft["id"], "expectedVersion": 1}
    )[1]
    now[0] += 2000
    assert (
        request(
            "POST",
            f"/sessions/{sid}/answers",
            {"kind": "initial_answer", "questionId": qid, "answer": "正式"},
        )[0]
        == 202
    )
    runtime.repository.recover("owner", accepted["generationId"])
    runtime.repository.recover("owner", accepted["generationId"])
    quota = runtime.repository._read(ref("StarQuota", "owner", "2026-10"))
    assert isinstance(quota, StarQuota) and quota.reserved == quota.consumed == 0
    assert request("GET", "/star-assist/quota")[1]["month"] == "2026-11"


def test_T10_result_after_submit_never_revives_draft(star):
    runtime, _, request, sid, qid, cid, _, _, draft, _ = star
    accepted = request(
        "POST", "/star-assist/generations", {"starDraftId": draft["id"], "expectedVersion": 1}
    )[1]
    lease = runtime.repository.star_claim("owner", accepted["generationId"], 1, str(uuid4()))
    assert runtime.repository.star_start(lease)
    result = runtime.worker.star_worker.provider.generate(lease.question, lease.input)
    assert (
        request(
            "POST",
            f"/sessions/{sid}/answers",
            {"kind": "initial_answer", "questionId": qid, "answer": "表示された正式本文"},
        )[0]
        == 202
    )
    assert runtime.repository.star_finish(lease, "SUCCEEDED", result)
    row = runtime.repository._read(ref("StarDraft", "owner", draft["id"]))
    assert row.status == "COMPLETED" and not row.value.candidates
    assert request("GET", f"/answer-contexts/{cid}/drafts")[0] == 409


def test_T24_errors_and_logs_never_include_inputs(star, capsys):
    _, _, request, _, _, _, _, answer, _, _ = star
    secret = "本文SECRET-JWT-AUDIT"
    result = request(
        "PUT", "/answer-drafts/" + answer["id"], {"expectedVersion": 99, "answer": secret}
    )
    assert result[0] == 409 and secret not in json.dumps(result)
    assert secret not in capsys.readouterr().out


def test_T17_star_event_union_and_stream_filters(star):
    from interview_backend.evaluation.events import InternalHandlers

    runtime, _, request, _, _, _, _, answer, draft, _ = star
    accepted = request(
        "POST", "/star-assist/generations", {"starDraftId": draft["id"], "expectedVersion": 1}
    )[1]
    event = runtime.repository.dispatch_event("owner", accepted["generationId"])
    handler = InternalHandlers(
        runtime.worker,
        runtime.dispatcher,
        runtime.recovery,
        queue_arn="queue",
        stream_arn="stream",
        scheduler_arn="schedule",
    )

    class Context:
        def get_remaining_time_in_millis(self):
            return 60000

    def queue(value):
        return {
            "Records": [
                {
                    "eventSource": "aws:sqs",
                    "eventSourceARN": "queue",
                    "messageId": "m",
                    "body": json.dumps(value),
                }
            ]
        }

    wrong = {**event, "type": "EvaluationRequested", "evaluationId": event["generationId"]}
    wrong.pop("generationId")
    assert handler.sqs(queue(wrong), Context())["batchItemFailures"]
    assert runtime.provider.calls == runtime.worker.star_worker.provider.calls == 0
    row = runtime.repository._read(ref("AnswerDraft", "owner", answer["id"]))
    record = {
        "eventSource": "aws:dynamodb",
        "eventSourceARN": "stream",
        "eventName": "INSERT",
        "dynamodb": {"SequenceNumber": "1", "NewImage": to_wire(encode("AnswerDraft", row, 1))},
    }
    assert not handler.streams({"Records": [record]}, Context())["batchItemFailures"]
    record["eventName"] = "REMOVE"
    record["dynamodb"].pop("NewImage")
    assert not handler.streams({"Records": [record]}, Context())["batchItemFailures"]
    assert not runtime.publisher.events
    assert not handler.sqs(queue(event), Context())["batchItemFailures"]
    assert not handler.sqs(queue(event), Context())["batchItemFailures"]
    assert runtime.worker.star_worker.provider.calls == 1 and runtime.provider.calls == 0


def test_T17_stream_kind_must_match_durable_dispatch(star):
    from interview_backend.evaluation.events import InternalHandlers

    runtime, _, request, _, _, _, _, _, draft, _ = star
    accepted = request(
        "POST", "/star-assist/generations", {"starDraftId": draft["id"], "expectedVersion": 1}
    )[1]
    identifier = accepted["generationId"]
    image = to_wire(
        encode("Dispatch", runtime.repository._read(ref("Dispatch", "owner", identifier)), 1)
    )
    runtime.repository._state.dispatches[identifier].job_kind = None
    handler = InternalHandlers(
        runtime.worker,
        runtime.dispatcher,
        runtime.recovery,
        queue_arn="queue",
        stream_arn="stream",
        scheduler_arn="schedule",
    )

    class Context:
        def get_remaining_time_in_millis(self):
            return 60000

    event = {
        "Records": [
            {
                "eventSource": "aws:dynamodb",
                "eventSourceARN": "stream",
                "eventName": "INSERT",
                "dynamodb": {"SequenceNumber": "mismatch", "NewImage": image},
            }
        ]
    }
    assert handler.streams(event, Context()) == {
        "batchItemFailures": [{"itemIdentifier": "mismatch"}]
    }
    assert (
        not runtime.publisher.events
        and runtime.provider.calls == runtime.worker.star_worker.provider.calls == 0
    )


def test_T18_backlog_star_fairness_and_rotation(star, monkeypatch):
    from interview_backend.repositories.codec import PARTITIONS

    runtime, now, request, _, _, _, _, _, draft, _ = star
    accepted = request(
        "POST", "/star-assist/generations", {"starDraftId": draft["id"], "expectedVersion": 1}
    )[1]
    lease = runtime.repository.star_claim("owner", accepted["generationId"], 1, str(uuid4()))
    assert runtime.repository.star_start(lease)
    for number in range(150):
        owner = f"backlog-{number}"
        sid = runtime.application.create(
            owner, str(uuid4()), {"category": "job_change", "difficulty": "standard"}
        ).body["sessionId"]
        qid = runtime.application.question(owner, sid).body["question"]["id"]
        runtime.application.submit(
            owner,
            str(uuid4()),
            sid,
            {"kind": "initial_answer", "questionId": qid, "answer": "正式"},
        )
    now[0] += 60001
    visited = []
    original = runtime.repository.due_candidates

    def pages(partition, *args):
        visited.append(partition)
        return original(partition, *args)

    monkeypatch.setattr(runtime.repository, "due_candidates", pages)
    runtime.recovery.tick(remaining_ms=lambda: 6000 if len(visited) < 5 else 4000)
    assert visited[:4] == list(PARTITIONS)
    assert (
        request("GET", "/star-assist/generations/" + accepted["generationId"])[1]["status"]
        == "OUTCOME_UNKNOWN"
    )
    visited.clear()
    runtime.recovery.tick(remaining_ms=lambda: 6000 if len(visited) < 1 else 4000)
    assert visited[0] == PARTITIONS[1]


def test_T01_fake_invented_fact_is_rejected_after_single_call(star, monkeypatch):
    runtime, _, request, _, _, _, _, _, draft, _ = star
    accepted = request(
        "POST", "/star-assist/generations", {"starDraftId": draft["id"], "expectedVersion": 1}
    )[1]
    original = runtime.worker.star_worker.provider.generate

    def invented(*args):
        result = original(*args)
        result.candidates[0].text = "未入力の売上100万円"
        return result

    monkeypatch.setattr(runtime.worker.star_worker.provider, "generate", invented)
    runtime.worker.run("owner", accepted["generationId"])
    assert (
        request("GET", "/star-assist/generations/" + accepted["generationId"])[1]["status"]
        == "FAILED_AFTER_START"
    )
    assert runtime.worker.star_worker.provider.calls == 1
    assert request("GET", "/star-assist/quota")[1]["user"]["consumed"] == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("quota_state", "released"),
        ("call_started", True),
        ("provider_id", "real"),
        ("star_draft_id", "invalid"),
    ],
)
def test_T01_codec_rejects_inconsistent_generation(star, field, value):
    from dataclasses import replace

    from interview_backend.models.internal import StorageError

    runtime, _, request, _, _, _, _, _, draft, _ = star
    accepted = request(
        "POST", "/star-assist/generations", {"starDraftId": draft["id"], "expectedVersion": 1}
    )[1]
    row = runtime.repository._read(ref("StarGeneration", "owner", accepted["generationId"]))
    with pytest.raises(StorageError):
        encode("StarGeneration", replace(row, **{field: value}), 1)


@pytest.mark.parametrize(
    "at,month",
    [
        ("2026-10-31T14:59:59+00:00", "2026-10"),
        ("2026-10-31T15:00:00+00:00", "2026-11"),
        ("2026-12-31T15:00:00+00:00", "2027-01"),
    ],
)
def test_T13_JST_month(at, month):
    assert month_for(int(datetime.fromisoformat(at).timestamp() * 1000)) == month


def test_T15_T16_apply_edit_accept_and_replay_after_expiry(star):
    runtime, now, request, sid, qid, cid, value, answer, draft, _ = star
    accepted, result = generated(star)
    value = {
        **value,
        "generationId": accepted["generationId"],
        "candidates": result["result"]["candidates"],
        "selectedCandidateId": "B",
        "expectedVersion": 1,
    }
    value["candidates"][0]["text"] = "選択前に編集したA"
    assert request("PUT", "/star-drafts/" + draft["id"], value)[0] == 200
    status, application = request(
        "POST",
        f"/star-drafts/{draft['id']}/applications",
        {
            "expectedVersion": 2,
            "candidateId": "B",
            "answerDraftId": answer["id"],
            "expectedAnswerVersion": 1,
        },
    )
    assert status == 200, application
    now[0] += 8 * DAY * 1000
    key = str(uuid4())
    final = {
        "kind": "initial_answer",
        "questionId": qid,
        "answer": "反映後に本人が編集した正式回答",
    }
    status, formal = request(
        "POST", f"/sessions/{sid}/answers", final, key=key, application=application["applicationId"]
    )
    assert status == 202, formal
    assist = runtime.repository._read(ref("AnswerAssist", "owner", formal["evaluationId"]))
    assert assist.edited and assist.generation_id == accepted["generationId"]
    now[0] += 30 * DAY * 1000
    assert (
        request(
            "POST",
            f"/sessions/{sid}/answers",
            final,
            key=key,
            application=application["applicationId"],
        )[1]
        == formal
    )


@pytest.mark.parametrize("mutation", ["empty", "category", "owner"])
def test_T01_generation_invalid_inputs_have_no_quota(star, mutation):
    runtime, _, request, _, _, _, value, _, draft, _ = star
    if mutation == "empty":
        value["notes"] = {k: " " for k in "STAR"}
    elif mutation == "category":
        value["targetCategory"] = None
    else:
        assert (
            request(
                "POST",
                "/star-assist/generations",
                {"starDraftId": draft["id"], "expectedVersion": 1},
                owner="other",
            )[0]
            == 404
        )
        return
    request("PUT", "/star-drafts/" + draft["id"], {**value, "expectedVersion": 1})
    assert (
        request(
            "POST", "/star-assist/generations", {"starDraftId": draft["id"], "expectedVersion": 2}
        )[0]
        == 400
    )
    assert not runtime.repository.snapshot().dispatches


def test_T21_unicode_no_truncation_and_oversized_draft(star):
    _, _, request, _, _, _, value, answer, draft, _ = star
    assert (
        request(
            "PUT", "/answer-drafts/" + answer["id"], {"answer": "😀" * 401, "expectedVersion": 1}
        )[0]
        == 200
    )
    accepted, result = generated(star)
    candidates = deepcopy(result["result"]["candidates"])
    candidates[0]["text"] = "😀" * 400
    body = {
        **value,
        "candidates": candidates,
        "generationId": accepted["generationId"],
        "expectedVersion": 1,
    }
    assert request("PUT", "/star-drafts/" + draft["id"], body)[0] == 200
    candidates[0]["text"] += "x"
    body["expectedVersion"] = 2
    assert request("PUT", "/star-drafts/" + draft["id"], body)[0] == 400


def test_audit_apply_cannot_commit_after_star_expiry(star, monkeypatch):
    from interview_backend.repositories.memory import MemoryUnit

    runtime, now, request, _, _, cid, value, answer, draft, _ = star
    accepted, result = generated(star)
    body = {
        **value,
        "generationId": accepted["generationId"],
        "candidates": result["result"]["candidates"],
        "selectedCandidateId": "A",
        "expectedVersion": 1,
    }
    saved = request("PUT", "/star-drafts/" + draft["id"], body)[1]
    now[0] = saved["expiresAt"] * 1000 - 1
    original = MemoryUnit.put

    def put(unit, reference, record):
        if reference[0] == "StarApplication":
            now[0] += 1
        return original(unit, reference, record)

    monkeypatch.setattr(MemoryUnit, "put", put)
    assert (
        request(
            "POST",
            f"/star-drafts/{draft['id']}/applications",
            {
                "expectedVersion": saved["version"],
                "candidateId": "A",
                "answerDraftId": answer["id"],
                "expectedAnswerVersion": 1,
            },
        )[0]
        == 409
    )
    assert request("GET", f"/answer-contexts/{cid}/drafts")[1]["answerDraft"]["answer"] == ""
    assert not any(r[0] == "StarApplication" for r in runtime.repository.snapshot().star_records)


def test_audit_preference_cas_cannot_extend_expired_generation(star, monkeypatch):
    from interview_backend.repositories.memory import MemoryUnit

    _, now, request, *_ = star
    initial = {
        "category": {"expectedVersion": 0, "expectedGeneration": None, "targetCategory": "other"}
    }
    saved = request("PUT", "/star-assist/preferences", initial)[1]["category"]
    now[0] = saved["expiresAt"] * 1000 - 1
    original = MemoryUnit.put

    def put(unit, reference, record):
        if reference[0] == "TargetCategoryPreference":
            now[0] += 1
        return original(unit, reference, record)

    monkeypatch.setattr(MemoryUnit, "put", put)
    assert (
        request(
            "PUT",
            "/star-assist/preferences",
            {
                "category": {
                    "expectedVersion": saved["version"],
                    "expectedGeneration": saved["id"],
                    "targetCategory": "it_engineering",
                }
            },
        )[0]
        == 409
    )
    assert request("GET", "/star-assist/preferences")[1]["category"] is None


def test_audit_formal_application_expiry_is_checked_at_commit(star, monkeypatch):
    from interview_backend.repositories.memory import MemoryUnit

    runtime, now, request, sid, qid, _, value, answer, draft, _ = star
    accepted, result = generated(star)
    assert (
        request(
            "PUT",
            "/star-drafts/" + draft["id"],
            {
                **value,
                "generationId": accepted["generationId"],
                "candidates": result["result"]["candidates"],
                "selectedCandidateId": "A",
                "expectedVersion": 1,
            },
        )[0]
        == 200
    )
    application = request(
        "POST",
        f"/star-drafts/{draft['id']}/applications",
        {
            "expectedVersion": 2,
            "candidateId": "A",
            "answerDraftId": answer["id"],
            "expectedAnswerVersion": 1,
        },
    )[1]
    now[0] = application["expiresAt"] * 1000 - 1
    original = MemoryUnit.put

    def put(unit, reference, record):
        if reference[0] == "AnswerAssist":
            now[0] += 1
        return original(unit, reference, record)

    monkeypatch.setattr(MemoryUnit, "put", put)
    assert (
        request(
            "POST",
            f"/sessions/{sid}/answers",
            {
                "kind": "initial_answer",
                "questionId": qid,
                "answer": "正式な本文",
            },
            application=application["applicationId"],
        )[0]
        == 404
    )
    assert not runtime.repository.snapshot().evaluations


@pytest.mark.parametrize("kind", ["answer", "star"])
def test_audit_inflight_save_arriving_after_formal_accept_is_rejected(star, monkeypatch, kind):
    from threading import Event

    runtime, _, request, sid, qid, _, value, answer, draft, _ = star
    row = answer if kind == "answer" else draft
    path = f"/{kind}-drafts/{row['id']}"
    body = {"answer": "遅延した通常本文"} if kind == "answer" else value
    entered, release = Event(), Event()
    original = runtime.repository.star_post

    def delayed(owner, key, fingerprint, method, target, operation):
        if target == path:
            entered.set()
            assert release.wait(5)
        return original(owner, key, fingerprint, method, target, operation)

    monkeypatch.setattr(runtime.repository, "star_post", delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(request, "PUT", path, {**body, "expectedVersion": 1})
        try:
            assert entered.wait(5)
            status, formal = request(
                "POST",
                f"/sessions/{sid}/answers",
                {
                    "kind": "initial_answer",
                    "questionId": qid,
                    "answer": "最終正式本文",
                },
            )
            assert status == 202
        finally:
            release.set()
        assert pending.result(timeout=5)[0] == 409
    state = runtime.repository.snapshot()
    assert len(state.evaluations) == len(state.attempts) == 1
    assert next(iter(state.attempts.values())).answer == "最終正式本文"
    record = runtime.repository._read(
        ref("AnswerDraft" if kind == "answer" else "StarDraft", "owner", row["id"])
    )
    assert record.status == "COMPLETED"
    assert (
        record.answer if kind == "answer" else any(record.value.notes.model_dump().values())
    ) == ("" if kind == "answer" else False)


def test_audit_other_owner_cannot_read_generation_update_star_or_mutate_quota(star):
    runtime, _, request, _, _, _, value, _, draft, _ = star
    accepted, _ = generated(star)
    before = runtime.repository.snapshot()
    assert (
        request("GET", "/star-assist/generations/" + accepted["generationId"], owner="other")[0]
        == 404
    )
    assert (
        request(
            "PUT", "/star-drafts/" + draft["id"], {**value, "expectedVersion": 1}, owner="other"
        )[0]
        == 404
    )
    assert request("PUT", "/star-assist/quota", {"consumed": 0}, owner="other")[0] == 405
    assert (
        request(
            "PUT",
            "/star-assist/preferences",
            {
                "owner": "owner",
                "category": {
                    "expectedVersion": 0,
                    "expectedGeneration": None,
                    "targetCategory": "other",
                },
            },
            owner="other",
        )[0]
        == 400
    )
    assert runtime.repository.snapshot() == before


@pytest.mark.parametrize("mutation", ["extra", "too_long", "missing", "wrong_style"])
def test_audit_invalid_provider_output_fails_once_without_refunding(star, monkeypatch, mutation):
    runtime, _, request, _, _, _, _, _, draft, _ = star
    original = runtime.worker.star_worker.provider.generate

    def invalid(*args):
        result = original(*args).model_dump()
        if mutation == "extra":
            result["secret"] = "not-allowed"
        elif mutation == "too_long":
            result["candidates"][0]["text"] = "😀" * 401
        elif mutation == "missing":
            del result["status"]
        else:
            result["candidates"][0]["style"] = "action"
        return result

    monkeypatch.setattr(runtime.worker.star_worker.provider, "generate", invalid)
    accepted = request(
        "POST", "/star-assist/generations", {"starDraftId": draft["id"], "expectedVersion": 1}
    )[1]
    runtime.worker.run("owner", accepted["generationId"])
    assert not runtime.worker.run("owner", accepted["generationId"])
    assert (
        request("GET", "/star-assist/generations/" + accepted["generationId"])[1]["status"]
        == "FAILED_AFTER_START"
    )
    assert runtime.worker.star_worker.provider.calls == 1
    assert request("GET", "/star-assist/quota")[1]["user"] == {
        "reserved": 0,
        "consumed": 1,
        "remaining": 19,
    }


def test_audit_star_recovery_emits_existing_outcome_alarm_once(star):
    from interview_backend.observability import Metrics, ObservedRepository

    runtime, now, request, _, _, _, _, _, draft, _ = star
    accepted = request(
        "POST",
        "/star-assist/generations",
        {
            "starDraftId": draft["id"],
            "expectedVersion": 1,
        },
    )[1]
    identifier = accepted["generationId"]
    lease = runtime.repository.star_claim("owner", identifier, 1, str(uuid4()))
    assert runtime.repository.star_start(lease)
    now[0] += 60001
    output = []
    observed = ObservedRepository(runtime.repository, Metrics("dispatcher", sink=output.append))
    observed.recover("owner", identifier)
    observed.recover("owner", identifier)
    items = [json.loads(row) for row in output]
    assert sum(row.get("OutcomeUnknown", 0) for row in items) == 1
    assert not any("EvaluationFailed" in row for row in items)
    assert all(row["Component"] == "dispatcher" for row in items)


def test_audit_star_worker_timeout_emits_existing_outcome_alarm_once(star):
    from interview_backend.evaluation.worker import Worker
    from interview_backend.observability import Metrics
    from interview_backend.star_assist.worker import StarWorker

    runtime, _, request, _, _, _, _, _, draft, _ = star
    accepted = request(
        "POST",
        "/star-assist/generations",
        {
            "starDraftId": draft["id"],
            "expectedVersion": 1,
        },
    )[1]
    output = []
    metrics = Metrics("worker", sink=output.append)
    # Production composition must pass the existing classification callback through.
    worker = Worker(runtime.repository, runtime.provider, metric=metrics.classification).star_worker
    clock = iter([0, 40])
    worker.monotonic = lambda: next(clock)
    assert worker.run("owner", accepted["generationId"])
    assert not worker.run("owner", accepted["generationId"])
    assert isinstance(worker, StarWorker)
    assert sum(json.loads(row).get("OutcomeUnknown", 0) for row in output) == 1


def test_audit_star_backlog_uses_existing_age_and_deadline_metrics(star):
    runtime, now, request, _, _, _, _, _, draft, _ = star
    accepted = request(
        "POST",
        "/star-assist/generations",
        {
            "starDraftId": draft["id"],
            "expectedVersion": 1,
        },
    )[1]
    now[0] += 10000
    assert runtime.repository.work_observation("owner", accepted["generationId"]) == (
        ("PendingAge", 10),
    )
    lease = runtime.repository.star_claim("owner", accepted["generationId"], 1, str(uuid4()))
    assert runtime.repository.star_start(lease)
    now[0] = lease.deadline_at
    assert runtime.repository.work_observation("owner", accepted["generationId"]) == (
        ("ExpiredLease", 1),
        ("DeadlineOverdue", 1),
    )


@pytest.mark.parametrize("uncertain", [False, True])
def test_live_worker_pins_provider_once_isolates_quota_and_never_replays(star, uncertain):
    from botocore.exceptions import ReadTimeoutError

    from interview_backend.evaluation.bedrock_provider import BedrockProvider
    from interview_backend.repositories.codec import decode, encode
    from interview_backend.star_assist.live_provider import LiveStarProvider
    from interview_backend.star_assist.worker import StarWorker

    class Client:
        calls = 0

        def converse(self, **kwargs):
            self.calls += 1
            if uncertain:
                raise ReadTimeoutError(endpoint_url="https://synthetic")
            body = {
                "status": "ready",
                "candidates": [
                    {"id": i, "style": s, "fields": fields}
                    for i, s, fields in (
                        ("A", "conclusion", ["R", "S", "T", "A"]),
                        ("B", "action", ["A", "S", "T", "R"]),
                        ("C", "conversational", ["S", "T", "A", "R"]),
                    )
                ],
                "missingInformation": [],
            }
            return {
                "stopReason": "end_turn",
                "output": {
                    "message": {"role": "assistant", "content": [{"text": json.dumps(body)}]}
                },
            }

    runtime, _, request, _, _, _, _, _, draft, _ = star
    from uuid import NAMESPACE_URL, uuid5

    from interview_backend.models.internal import ProviderUsage

    budget_id = str(uuid5(NAMESPACE_URL, "interview-provider-usage:2026-10"))

    def saturate(tx):
        for owner, limit in (("owner", 100), ("@ai-global-budget", 3000)):
            tx.new(
                ("ProviderUsage", owner, budget_id),
                ProviderUsage(owner, budget_id, "2026-10", limit),
            )

    runtime.repository._atomic(saturate)
    normal_before = runtime.repository.snapshot().provider_usage
    client = Client()
    provider = LiveStarProvider(BedrockProvider(client_factory=lambda *a, **k: client))
    worker = StarWorker(runtime.repository, provider)
    accepted = request(
        "POST", "/star-assist/generations", {"starDraftId": draft["id"], "expectedVersion": 1}
    )[1]
    identifier = accepted["generationId"]
    from interview_backend.models.internal import IntegrityError

    with pytest.raises(IntegrityError):
        worker.run("other", identifier)
    assert worker.run("owner", identifier)
    assert not worker.run("owner", identifier)
    result = request("GET", "/star-assist/generations/" + identifier)[1]
    assert result["status"] == ("OUTCOME_UNKNOWN" if uncertain else "SUCCEEDED")
    job = runtime.repository._read(ref("StarGeneration", "owner", identifier))
    assert job.provider_id == provider.provider_id and job.call_started
    assert decode(encode("StarGeneration", job, 1))[0].provider_id == provider.provider_id
    assert runtime.repository.star_quota("owner").body["user"]["consumed"] == 1
    assert runtime.repository.snapshot().provider_usage == normal_before
    runtime.repository.star_recover("owner", identifier)
    assert client.calls == 1


def test_live_started_recovery_after_provider_switch_never_reinfers(star):
    from dataclasses import replace

    from interview_backend.evaluation.bedrock_provider import BedrockProvider
    from interview_backend.star_assist.live_provider import LiveStarProvider
    from interview_backend.star_assist.worker import StarWorker

    runtime, now, request, _, _, _, _, _, draft, _ = star

    def forbidden(*args, **kwargs):
        raise AssertionError("Recovery must not construct a client")

    provider = LiveStarProvider(BedrockProvider(client_factory=forbidden))
    accepted = request(
        "POST", "/star-assist/generations", {"starDraftId": draft["id"], "expectedVersion": 1}
    )[1]
    identifier = accepted["generationId"]
    lease = runtime.repository.star_claim(
        "owner", identifier, 1, str(uuid4()), provider.provider_id
    )
    assert not runtime.repository.star_start(replace(lease, provider_id="fake"))
    assert runtime.repository.star_start(lease)
    now[0] += 60001
    runtime.repository.star_recover("owner", identifier)
    assert not StarWorker(runtime.repository, provider).run("owner", identifier)
    assert not runtime.worker.star_worker.run("owner", identifier)
    assert (
        request("GET", "/star-assist/generations/" + identifier)[1]["status"] == "OUTCOME_UNKNOWN"
    )
    assert runtime.repository.star_quota("owner").body["user"]["consumed"] == 1
