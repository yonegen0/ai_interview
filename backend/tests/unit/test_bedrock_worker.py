"""Offline Bedrock Worker execution and durable replay contracts."""

import json

from botocore.exceptions import ReadTimeoutError
from test_bedrock_provider import StubClient
from test_openai_provider import result, start

from interview_backend.evaluation.bedrock_provider import BedrockProvider
from interview_backend.evaluation.worker import Worker


def _provider(client):
    return BedrockProvider(client_factory=lambda *args, **kwargs: client)


def test_bedrock_worker_completes_once_and_replay_does_not_infer(runtime):
    client = StubClient(
        body={
            "stopReason": "end_turn",
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": json.dumps(result())}],
                }
            },
            "usage": {"inputTokens": 12, "outputTokens": 3},
        }
    )
    worker = Worker(runtime.repository, _provider(client), runtime.worker.clock)
    evaluation_id = start(runtime)
    assert worker.run("owner", evaluation_id)
    assert worker.run("owner", evaluation_id) is False
    assert client.calls == 1
    snapshot = runtime.repository.snapshot()
    assert snapshot.evaluations[evaluation_id].status == "completed"
    assert len([item for item in snapshot.provider_usage.values() if item.owner == "owner"]) == 1


def test_bedrock_worker_ambiguous_delivery_never_infers_twice(runtime):
    client = StubClient(
        error=ReadTimeoutError(endpoint_url="https://bedrock-runtime.ap-northeast-1.amazonaws.com")
    )
    worker = Worker(runtime.repository, _provider(client), runtime.worker.clock)
    evaluation_id = start(runtime)
    assert worker.run("owner", evaluation_id)
    assert (
        runtime.repository.snapshot().evaluations[evaluation_id].failure_reason == "OUTCOME_UNKNOWN"
    )
    assert worker.run("owner", evaluation_id) is False
    assert client.calls == 1
