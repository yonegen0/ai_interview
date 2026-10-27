"""No-network checks for the explicitly limited Python orchestration meter."""

from types import SimpleNamespace

import pytest
from botocore.client import BaseClient
from botocore.httpsession import URLLib3Session

from interview_backend.deployment import DeploymentError


@pytest.fixture
def harness(monkeypatch):
    import stage_request_budget as budget

    calls, records = [], []
    client = SimpleNamespace(meta=SimpleNamespace(service_model=SimpleNamespace(service_name="s3")))
    transport = object()

    def send(_transport, _request):
        calls.append("http")
        return "response"

    def invoke(_client, operation, params):
        result = URLLib3Session.send(transport, object())
        if params.get("retry"):
            URLLib3Session.send(transport, object())
        return result

    monkeypatch.setattr(BaseClient, "_make_api_call", invoke)
    monkeypatch.setattr(URLLib3Session, "send", send)
    meter = budget.install(lambda stage, **fields: records.append((stage, fields)))
    try:
        yield meter, client, calls, records, invoke, send
    finally:
        meter.close()


def test_sdk_and_physical_counts_without_parameters_in_journal(harness):
    meter, client, calls, records, _, _ = harness
    assert BaseClient._make_api_call(client, "GetObject", {"Secret": "never-record"}) == "response"
    assert (meter.sdk, meter.http, calls) == (1, 1, ["http"])
    assert "never-record" not in repr(records)


def test_retry_is_refused_before_second_physical_send(harness):
    meter, client, calls, _, _, _ = harness
    with pytest.raises(DeploymentError):
        BaseClient._make_api_call(client, "GetObject", {"retry": True})
    assert (meter.sdk, meter.http, calls) == (1, 1, ["http"])


@pytest.mark.parametrize("counter", ["sdk", "http"])
def test_budget_exhaustion_sends_nothing(harness, counter):
    import stage_request_budget as budget

    meter, client, calls, _, _, _ = harness
    setattr(meter, counter, budget.LIMIT)
    with pytest.raises(DeploymentError):
        BaseClient._make_api_call(client, "GetObject", {})
    assert not calls


def test_unscoped_send_is_refused(harness):
    _, _, calls, _, _, _ = harness
    with pytest.raises(DeploymentError):
        URLLib3Session.send(object(), object())
    assert not calls


def test_close_restores_functions_before_journal_and_is_idempotent(harness):
    meter, _, _, records, invoke, send = harness
    meter.close()
    assert BaseClient._make_api_call is invoke
    assert URLLib3Session.send is send
    completed = len(records)
    meter.close()
    assert len(records) == completed
    assert records[-1][1]["scope"] == "python-orchestration-only;terraform-go-unmetered"
