"""Validation automation exercised through the actual local API/domain; no live IAM claims."""

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from interview_backend.api.admin import AdminHandler
from interview_backend.assets import load_questions
from interview_backend.bootstrap import build_runtime
from interview_backend.evaluation.openai_provider import Deadline, HTTPTransport, ProviderFailure
from interview_backend.evaluation.selection import select_provider
from interview_backend.evaluation.validation_scenarios import ValidationScenario
from interview_backend.repositories.codec import decode, encode

OTHER_SECRET = "arn:aws:secretsmanager:ap-northeast-1:222222222222:secret:other"


def tool(name):
    path = Path(__file__).parents[2] / "skills/p4" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LocalApi:
    def __init__(self, runtime, owner, admin=False):
        self.runtime, self.owner, self.admin = runtime, owner, admin

    def call(self, method, path, payload=None, key=None, headers=None):
        parts = urlsplit(path)
        event = {
            "rawPath": parts.path,
            "body": json.dumps(payload),
            "headers": {"Idempotency-Key": key, **(headers or {})},
            "queryStringParameters": {k: v[0] for k, v in parse_qs(parts.query).items()},
            "requestContext": {
                "http": {"method": method},
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": self.owner,
                            "cognito:groups": ["ADMIN" if self.admin else "USER"],
                        }
                    }
                },
            },
        }
        handler = (
            AdminHandler(self.runtime.repository, load_questions())
            if parts.path.startswith("/admin/")
            else self.runtime.handler
        )
        reply = handler(event)
        return reply["statusCode"], json.loads(reply["body"]), reply["headers"]


@pytest.mark.parametrize("rounds", [0, 3])
def test_live_flow_preparation_all_rounds_offline(rounds):
    live = tool("coaching_live")
    hashes = [hashlib.sha256(b"user-a").hexdigest()]
    runtime = build_runtime(
        provider=ValidationScenario("coaching_three", hashes) if rounds else None
    )
    a, b = LocalApi(runtime, "user-a"), LocalApi(runtime, "user-b")

    def wait(api, eid):
        runtime.worker.run("user-a", eid)
        return api.call("GET", f"/evaluations/{eid}")[1]

    run = live.Run("offline-" + str(rounds))
    live.coaching_flow(a, b, run, expected_rounds=rounds, wait=wait)
    assert all(r["status"] == "passed" for r in run.rows)
    assert any(r["check"] == "other-owner-feedback" for r in run.rows)
    assert any(r["check"] == "retry-attempt-feedback" for r in run.rows)
    assert all(e.status == "completed" for e in runtime.repository.snapshot().evaluations.values())


@pytest.mark.parametrize("status", ["failed", "processing"])
def test_coaching_flow_does_not_pass_an_unfinished_or_failed_retry(status):
    live = tool("coaching_live")
    runtime = build_runtime()
    a, b = LocalApi(runtime, "user-a"), LocalApi(runtime, "user-b")
    waited = []

    def wait(api, eid):
        waited.append(eid)
        if len(waited) == 2:
            return {"status": status}
        runtime.worker.run("user-a", eid)
        return api.call("GET", f"/evaluations/{eid}")[1]

    run = live.Run("retry-terminal")
    with pytest.raises(AssertionError, match="LiveValidationAssertionFailed"):
        live.coaching_flow(a, b, run, wait=wait)
    assert len(waited) == 2 and waited[0] != waited[1]
    assert run.rows[-1]["check"] == "retry-attempt-completed"
    assert run.rows[-1]["status"] == "failed"
    assert len(runtime.repository.snapshot().evaluations) == 2


def test_admin_operations_restore_original_and_conflicts_offline():
    live = tool("coaching_live")
    runtime = build_runtime()
    user, admin = LocalApi(runtime, "user"), LocalApi(runtime, "admin", True)
    original = admin.call("GET", "/admin/question-bank")[1]["questions"]
    run = live.Run("offline-admin")
    live.admin_flow(user, admin, run, writes=True)
    assert admin.call("GET", "/admin/question-bank")[1]["questions"] == original
    assert all(r["status"] == "passed" for r in run.rows)


@pytest.mark.parametrize("status", ["processing", "unknown"])
def test_coaching_flow_rejects_nonterminal_result_before_reading_feedback(status):
    live = tool("coaching_live")
    runtime = build_runtime()
    a, b = LocalApi(runtime, "user-a"), LocalApi(runtime, "user-b")

    def wait(api, eid):
        runtime.worker.run("user-a", eid)
        return {"status": status}

    run = live.Run("initial-terminal")
    with pytest.raises(AssertionError, match="LiveValidationAssertionFailed"):
        live.coaching_flow(a, b, run, wait=wait)
    assert run.rows[-1]["check"] == "evaluation-completed"
    assert len(runtime.repository.snapshot().evaluations) == 1


@pytest.mark.parametrize("read", [2, 3, 4, 5])
@pytest.mark.parametrize("field", ["questions", "version", "status"])
def test_admin_flow_rejects_corrupted_mutation_readback_and_restores_owned_state(read, field):
    live = tool("coaching_live")
    runtime = build_runtime()
    user = LocalApi(runtime, "user")

    class CorruptRead(LocalApi):
        reads = 0

        def call(self, method, path, *args, **kwargs):
            status, body, headers = super().call(method, path, *args, **kwargs)
            if method == "GET" and path == "/admin/question-bank":
                self.reads += 1
                if self.reads == read:
                    body = deepcopy(body)
                    if field == "questions":
                        body["questions"][0]["question"] = "破損した読戻し"
                    elif field == "version":
                        body["version"] += 1
                    else:
                        status = 503
            return status, body, headers

    admin = CorruptRead(runtime, "admin", True)
    original = LocalApi(runtime, "admin", True).call("GET", "/admin/question-bank")[1]
    run = live.Run("admin-corrupt")
    with pytest.raises(AssertionError, match="LiveValidationAssertionFailed"):
        live.admin_flow(user, admin, run, writes=True)
    assert any(r["check"].endswith("-readback") and r["status"] == "failed" for r in run.rows)
    assert admin.call("GET", "/admin/question-bank")[1]["questions"] == original["questions"]


@pytest.mark.parametrize("field", ["questions", "version", "status"])
def test_admin_restore_requires_exact_readback_and_never_repeats_restore(field):
    live = tool("coaching_live")
    runtime = build_runtime()
    user = LocalApi(runtime, "user")
    run = live.Run("admin-restore-proof")

    class CorruptRestore(LocalApi):
        reads = 0
        restores = 0

        def call(self, method, path, payload=None, key=None, **kwargs):
            status, body, headers = super().call(method, path, payload, key, **kwargs)
            if method == "POST" and key == run.key("restore-bank"):
                self.restores += 1
            if method == "GET" and path == "/admin/question-bank":
                self.reads += 1
                if self.reads == 2 or self.restores:
                    body = deepcopy(body)
                    if self.reads == 2 or field == "questions":
                        body["questions"][0]["question"] = "破損した読戻し"
                    elif field == "version":
                        body["version"] += 1
                    else:
                        status = 503
            return status, body, headers

    admin = CorruptRestore(runtime, "admin", True)
    with pytest.raises(AssertionError, match="LiveValidationAssertionFailed"):
        live.admin_flow(user, admin, run, writes=True)
    assert admin.restores == 1
    assert run.rows[-1]["check"] == "admin-restore-readback"
    assert run.rows[-1]["status"] == "failed"


def test_star_business_flow_preserves_assist_and_no_early_evaluation():
    live = tool("coaching_live")
    runtime = build_runtime()
    a, b = LocalApi(runtime, "star-a"), LocalApi(runtime, "star-b")

    def wait(api, gid):
        assert not runtime.repository.snapshot().evaluations
        runtime.worker.run("star-a", gid)
        return api.call("GET", f"/star-assist/generations/{gid}")[1]

    def evaluate(api, eid):
        state = runtime.repository.snapshot()
        assert len(state.evaluations) == 1 and len(state.attempts) == 1
        runtime.worker.run("star-a", eid)
        return api.call("GET", f"/evaluations/{eid}")[1]

    run = live.Run("star-functional")
    result = live.star_flow(a, b, run, wait=wait, evaluate=evaluate)
    from interview_backend.star_assist.repository import ref

    assist = runtime.repository._read(ref("AnswerAssist", "star-a", result["evaluationId"]))
    # This edit precedes Apply; `edited` compares the formal answer with applied text.
    assert assist and not assist.edited and assist.candidate_id == "A"
    assert runtime.worker.star_worker.provider.calls == 1
    assert a.call("GET", "/star-assist/quota")[1]["user"]["consumed"] == 1
    assert all(r["status"] == "passed" for r in run.rows)
    # Only safe identifiers/statuses are journaled, never generated content or notes.
    assert "検証用編集" not in json.dumps(run.rows, ensure_ascii=False)


@pytest.mark.parametrize(
    ("field", "read"),
    [
        ("notes", 1),
        ("targetCategory", 1),
        ("industry", 1),
        ("company", 1),
        ("candidates", 2),
        ("generationId", 2),
        ("candidates", 3),
        ("company", 3),
        ("selectedCandidateId", 3),
    ],
)
def test_star_flow_rejects_corrupted_restored_input_or_generated_candidates(field, read):
    live = tool("coaching_live")
    runtime = build_runtime()

    class CorruptRead(LocalApi):
        reads = 0
        writes = 0

        def call(self, method, path, *args, **kwargs):
            if method == "PUT":
                self.writes += 1
            status, value, headers = super().call(method, path, *args, **kwargs)
            if method == "GET" and path.endswith("/drafts"):
                self.reads += 1
                if self.reads == read:
                    value = deepcopy(value)
                    draft = value["starDraft"]
                    if field == "candidates":
                        draft[field][1]["text"] = "出典と異なる回答です。"
                    elif field == "notes":
                        draft[field]["R"] = "元の成果と異なります。"
                    elif field == "generationId":
                        draft[field] = "10000000-0000-4000-8000-000000000099"
                    elif field == "selectedCandidateId":
                        draft[field] = "B"
                    else:
                        draft[field] = None if field == "targetCategory" else "復元不整合"
            return status, value, headers

    a, b = CorruptRead(runtime, "star-a"), LocalApi(runtime, "star-b")

    def wait(api, gid):
        runtime.worker.run("star-a", gid)
        return api.call("GET", f"/star-assist/generations/{gid}")[1]

    def evaluate(api, eid):
        runtime.worker.run("star-a", eid)
        return api.call("GET", f"/evaluations/{eid}")[1]

    run = live.Run("star-restoration")
    with pytest.raises(AssertionError, match="LiveValidationAssertionFailed"):
        live.star_flow(a, b, run, wait=wait, evaluate=evaluate)
    assert not runtime.repository.snapshot().evaluations
    assert a.writes == read - 1
    assert run.rows[-1]["status"] == "failed"


@pytest.mark.parametrize("failure", ["NEEDS_INFORMATION", "OUTCOME_UNKNOWN", "FAILED_AFTER_START"])
def test_star_flow_stops_without_formal_submission_on_nonready_result(failure):
    live = tool("coaching_live")
    runtime = build_runtime()
    a, b = LocalApi(runtime, "star-a"), LocalApi(runtime, "star-b")
    run = live.Run("star-stop")
    with pytest.raises(AssertionError):
        live.star_flow(a, b, run, wait=lambda *_: {"status": failure, "result": None})
    assert not runtime.repository.snapshot().evaluations
    assert run.rows[-1] == {"run_id": "star-stop", "check": "star-ready", "status": "failed"}


def test_star_poll_handles_all_inflight_states_and_does_not_retry_unknown():
    live = tool("coaching_live")

    class Api:
        states = iter(["QUEUED", "PREPARED", "STARTED", "OUTCOME_UNKNOWN"])
        calls = 0

        def call(self, method, path):
            assert method == "GET"
            self.calls += 1
            return 200, {"status": next(self.states)}, {}

    api = Api()
    assert live.poll_star(api, "synthetic", clock=lambda: 0, sleep=lambda _: None) == {
        "status": "OUTCOME_UNKNOWN"
    }
    assert api.calls == 4


def test_star_flow_does_not_resend_a_write_with_unknown_result():
    live = tool("coaching_live")

    class Api:
        calls = 0

        def call(self, *args, **kwargs):
            self.calls += 1
            raise TimeoutError("synthetic-unknown-write")

    api = Api()
    with pytest.raises(TimeoutError):
        live.star_flow(api, api, live.Run("star-no-replay"))
    assert api.calls == 1


def test_star_corpus_is_valid_and_uses_locked_converse_shape_without_network(monkeypatch):
    import socket

    import botocore
    from botocore.loaders import Loader
    from botocore.model import ServiceModel
    from botocore.validate import validate_parameters

    from interview_backend.evaluation.bedrock_provider import BedrockProvider
    from interview_backend.star_assist.live_provider import LiveStarProvider
    from interview_backend.star_assist.models import StarInput

    def forbidden(*args, **kwargs):
        raise AssertionError("NetworkNotAllowed")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    # Service model lookup only: no client/credential/config discovery.
    loader = Loader(
        extra_search_paths=[str(Path(botocore.__file__).parent / "data")],
        include_default_search_paths=False,
    )
    sdk = ServiceModel(loader.load_service_model("bedrock-runtime", "service-2"))
    shape = sdk.operation_model("Converse").input_shape
    corpus = tool("coaching_live").star_corpus()
    assert corpus["synthetic_only"] and corpus["live_result"] is None
    assert len({case["id"] for case in corpus["cases"]}) == 12
    for case in corpus["cases"]:

        class Client:
            def __init__(self):
                self.requests = []

            def converse(self, **request):
                validate_parameters(request, shape)
                assert request["modelId"] == "jp.anthropic.claude-haiku-5-5"
                assert request["inferenceConfig"] == {"maxTokens": 2048}
                assert len(json.dumps(request, ensure_ascii=True).encode()) <= 24000
                self.requests.append(request)
                # Safe synthetic clarification validates corpus request feasibility only.
                return {
                    "stopReason": "end_turn",
                    "output": {
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "text": json.dumps(
                                        {
                                            "status": "needs_information",
                                            "candidates": [],
                                            "missingInformation": [
                                                "本人の行動を確認してください。"
                                            ],
                                        }
                                    )
                                }
                            ],
                        }
                    },
                }

        client = Client()
        provider = LiveStarProvider(
            BedrockProvider(client_factory=lambda *a, client=client, **k: client)
        )
        result = provider.generate("工夫した経験は？", StarInput.model_validate(case["input"]))
        assert result.status == "needs_information"
        assert len(client.requests) <= 1
        assert len(client.requests) == (0 if case["id"] in {"contradiction", "boundary-401"} else 1)


def test_offline_sdk_cannot_read_host_config_or_credentials(monkeypatch):
    import os

    import botocore.configloader
    import botocore.session

    original = botocore.configloader.raw_config_parse
    paths = []

    def isolated(path, *args, **kwargs):
        # Check before opening, so a regression cannot read the host's files.
        assert path == os.devnull
        paths.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(botocore.configloader, "raw_config_parse", isolated)
    assert botocore.session.Session().full_config == {"profiles": {}}
    assert paths and set(paths) == {os.devnull}


def test_failed_validation_always_invokes_closure_callback():
    live = tool("coaching_live")
    calls = []
    run = live.Run("offline-failure")

    def failed():
        raise AssertionError("synthetic")

    def closed():
        calls.append("closed")
        return {
            "status": "CLOSED_READBACK_VERIFIED",
            "api_disabled": True,
            "worker_disabled": True,
            "streams_disabled": True,
            "scheduler_disabled": True,
            "validation_alarm_count": 0,
            "active_lock": False,
            "state_outside_dev_resources": 0,
        }

    with pytest.raises(AssertionError):
        live.run_with_closure(failed, closed, run)
    assert calls == ["closed"]
    assert run.rows[-1]["check"] == "closed-readback"


def test_closure_callback_return_without_readback_never_passes():
    live = tool("coaching_live")
    run = live.Run("offline-no-proof")
    with pytest.raises(ValueError, match="VerifiedClosureReadbackRequired"):
        live.run_with_closure(lambda: None, lambda: None, run)
    assert run.rows[-1]["status"] == "failed"


def test_fake_scenario_requires_operator_settings_and_owner_allowlist():
    with pytest.raises(ValueError, match="ValidationEnablementRequired"):
        select_provider({"INTERVIEW_FAKE_SCENARIO": "coaching_three"})
    scenario = ValidationScenario("coaching_three", [hashlib.sha256(b"test-owner").hexdigest()])
    with pytest.raises(ValueError, match="ValidationOwnerNotAllowed"):
        scenario.authorize_owner("real-user")
    with pytest.raises(ValueError, match="ValidationOwnerRequired"):
        scenario.evaluate(None)


def test_eval_corpus_and_partial_annotation_denominators():
    evaluation = tool("provider_eval")
    cases = evaluation.corpus()
    assert len(cases) == 19 and len({r[0]["name"] for r in cases}) == 19
    assert any(p.context.coaching_count == 3 for _, p in cases)
    assert evaluation.cost(
        {"input_tokens": 2000, "output_tokens": 1200, "reasoning_tokens": 800, "cached_tokens": 0}
    ) == pytest.approx(0.0008)
    summary = evaluation.aggregate(
        [
            {
                "latency_ms": 10,
                "score_within_one": True,
                "status_matches": True,
                "cost_usd": None,
                "usage": None,
            }
        ]
    )
    assert summary["semantic_duplicate_rate"] is None
    assert summary["semantic_duplicate_coverage"] == 0
    assert summary["usage_coverage"] == 0


def test_unknown_outcome_transport_has_exactly_one_send(monkeypatch):
    import http.client

    calls = []

    class Connection:
        def __init__(self, *args, **kwargs):
            self.sock = self

        def connect(self):
            calls.append("connect")

        def settimeout(self, value):
            assert value > 0

        def request(self, *args, **kwargs):
            calls.append("send")
            raise TimeoutError

        def close(self):
            calls.append("close")

    monkeypatch.setattr(http.client, "HTTPSConnection", Connection)
    with pytest.raises(ProviderFailure) as error:
        HTTPTransport().post("api.openai.com", "/v1/responses", {}, {}, Deadline(40, lambda: 0))
    assert error.value.kind == "TIMEOUT" and error.value.uncertain
    assert calls == ["connect", "send", "close"]


def test_connection_close_body_uses_remaining_deadline(monkeypatch):
    import http.client

    now, timeouts = [0], []

    class Socket:
        def settimeout(self, seconds):
            timeouts.append(seconds)

    class Response:
        status = 200
        calls = 0

        def read1(self, size):
            self.calls += 1
            now[0] += 10
            return b"x"

        def isclosed(self):
            return self.calls == 2

    class Connection:
        def __init__(self, *args, **kwargs):
            self.sock = Socket()

        def connect(self):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            self.sock = None
            now[0] += 10
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(http.client, "HTTPSConnection", Connection)
    assert HTTPTransport().post(
        "api.openai.com", "/v1/responses", {}, {}, Deadline(40, lambda: now[0])
    ) == (200, b"xx")
    assert timeouts == [40, 40, 30, 20]


def test_usage_record_roundtrip_and_old_evaluation_unchanged(runtime):
    from test_openai_provider import Authentication, Transport, start

    from interview_backend.evaluation.openai_provider import OpenAIProvider
    from interview_backend.evaluation.worker import Worker

    eid = start(runtime)
    before = runtime.repository.snapshot().evaluations[eid]
    assert "provider_usage_month" not in json.loads(encode("Evaluation", before, 0)["data"])
    worker = Worker(
        runtime.repository,
        OpenAIProvider(Authentication(), transport=Transport()),
        runtime.worker.clock,
    )
    assert worker.run("owner", eid)
    usage = next(iter(runtime.repository.snapshot().provider_usage.values()))
    assert decode(encode("ProviderUsage", usage, 0))[0] == usage


def test_dynamodb_usage_reservation_ack_loss_is_not_repeated():
    from botocore.exceptions import EndpointConnectionError
    from conftest import uid
    from test_dynamodb import CONFIG, OWNER, SnapshotClient, db, prepared, snapshot

    from interview_backend.repositories.codec import to_wire
    from interview_backend.repositories.domain import ref

    memory, _, _, _, reply, _ = prepared()
    eid = reply.body["evaluationId"]
    lease = memory.claim(OWNER, eid, 1, uid(800), CONFIG).lease
    client = SnapshotClient(snapshot(memory))
    assert memory.reserve_provider_call(lease, 1).status == "reserved"
    current = snapshot(memory)
    usage = next(iter(memory.snapshot().provider_usage.values()))
    item = encode("ProviderUsage", usage, memory._revisions[ref("ProviderUsage", OWNER, usage.id)])
    current[(item["PK"], item["SK"])] = to_wire(item)

    def lost(request):
        client.items = current
        raise EndpointConnectionError(endpoint_url="https://offline.invalid")

    client.on_write = lost
    assert db(client).reserve_provider_call(lease, 1).status == "already_reserved"
    assert len(client.writes) == 1
    writes = client.writes[0]["TransactItems"]
    assert any("Put" in w and "PROVIDER_USAGE#" in str(w["Put"]["Item"]) for w in writes)


def test_global_cap_shared_across_owners(runtime):
    from test_openai_provider import Authentication, Transport, start

    from interview_backend.evaluation.openai_provider import OpenAIProvider, OpenAISettings
    from interview_backend.evaluation.worker import Worker

    transport = Transport()
    worker = Worker(
        runtime.repository,
        OpenAIProvider(
            Authentication(), transport=transport, settings=OpenAISettings(monthly_global_limit=1)
        ),
        runtime.worker.clock,
    )
    assert worker.run("one", start(runtime, owner="one", number=1))
    eid = start(runtime, owner="two", number=2)
    assert worker.run("two", eid)
    assert len(transport.requests) == 1
    assert runtime.repository.snapshot().evaluations[eid].provider_usage_month is None


def test_manifest_provider_environment_rejects_keys_and_cross_account_secret():
    from interview_backend.evaluation.selection import checked_provider_environment

    assert checked_provider_environment({}, "123456789012", "ap-northeast-1") == {}
    for values in (
        {"OPENAI_API_KEY": "forbidden-placeholder"},
        {"INTERVIEW_AI_PROVIDER": "openai"},
        {
            "INTERVIEW_AI_PROVIDER": "openai",
            "INTERVIEW_OPENAI_ENABLED": "true",
            "INTERVIEW_OPENAI_AUTH": "secret",
            "INTERVIEW_OPENAI_SECRET_ARN": OTHER_SECRET,
        },
        {"INTERVIEW_AI_PROVIDER": "fake", "INTERVIEW_FAKE_SCENARIO": "coaching_three"},
    ):
        with pytest.raises(ValueError):
            checked_provider_environment(values, "123456789012", "ap-northeast-1")
