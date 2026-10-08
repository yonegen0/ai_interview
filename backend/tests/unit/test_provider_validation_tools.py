"""Validation automation exercised through the actual local API/domain; no live IAM claims."""

import hashlib
import importlib.util
import json
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

    def call(self, method, path, payload=None, key=None):
        parts = urlsplit(path)
        event = {
            "rawPath": parts.path,
            "body": json.dumps(payload),
            "headers": {"Idempotency-Key": key},
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


def test_admin_operations_restore_original_and_conflicts_offline():
    live = tool("coaching_live")
    runtime = build_runtime()
    user, admin = LocalApi(runtime, "user"), LocalApi(runtime, "admin", True)
    original = admin.call("GET", "/admin/question-bank")[1]["questions"]
    run = live.Run("offline-admin")
    live.admin_flow(user, admin, run, writes=True)
    assert admin.call("GET", "/admin/question-bank")[1]["questions"] == original
    assert all(r["status"] == "passed" for r in run.rows)


def test_failed_validation_always_invokes_closure_callback():
    live = tool("coaching_live")
    calls = []
    run = live.Run("offline-failure")

    def failed():
        raise AssertionError("synthetic")

    with pytest.raises(AssertionError):
        live.run_with_closure(failed, lambda: calls.append("closed"), run)
    assert calls == ["closed"]
    assert run.rows[-1]["check"] == "closed-readback"


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
