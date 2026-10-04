"""Event model checks against independent hand-calculated examples."""

import pytest
from test_p4_tools import tool


@pytest.mark.parametrize("route,expected", [("feedback", 0.072393), ("next_question", 0.082393)])
def test_result_and_next_question_sdk_round_trips(route, expected):
    m = tool("performance_model")
    result = m.simulate(plain_requests=[(0, route)], assumptions=m.Assumptions(warm=True))
    assert result["api_p95_seconds"] == pytest.approx(expected)


def test_bucket_refills_and_caps():
    b = tool("performance_model").Bucket(2, 2)
    assert b.available(0)
    b.take()
    b.take()
    assert not b.available(0.49)
    assert b.available(0.5)
    b.take()
    assert b.available(10)
    assert b.tokens == 2


def test_cold_only_once_and_reuses_completed_slot():
    p = tool("performance_model").LambdaPool(1)
    assert p.invoke(0, 0.1, 0.5) == 0.6
    assert p.invoke(0.2, 0.1, 0.5) is None
    assert abs(p.invoke(0.6, 0.1, 0.5) - 0.7) < 1e-9
    assert p.cold == 1


def test_worker_two_lanes_and_immediate_then_polling():
    m = tool("performance_model")
    a = m.Assumptions(warm=True, sdk_seconds=0, network_seconds=0, delivery_seconds=0)
    result = m.simulate([0] * 30, assumptions=a)
    assert result["results_received"] == 30
    assert result["route_requests"]["evaluation"] == 60
    assert 2 < result["all_results_seconds"] < 2.1
    assert result["retry_count"] == 0


def test_rejections_are_not_hidden_by_p95():
    m = tool("performance_model")
    result = m.simulate([0] * 31, assumptions=m.Assumptions(warm=True))
    assert result["rejections"]["route_429"] == 1
    assert result["verdict"] == "MODEL_FAIL"
    assert result["results_received"] == 30


def test_route_defaults_are_independent_account_bucket_shared():
    m = tool("performance_model")
    requests = [(0, "session")] * 30 + [(0, "evaluation")] * 30
    assert m.simulate(plain_requests=requests)["rejections"]["route_429"] == 0
    r = m.simulate(plain_requests=requests, assumptions=m.Assumptions(account_burst=40))
    assert r["rejections"]["account_429"] == 20
