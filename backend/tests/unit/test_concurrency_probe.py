import pytest
from test_p4_tools import tool


def test_fake_campaign_respects_two_lanes_and_http_contract():
    result = tool("concurrency_probe").offline(
        participants=6, provider_delay=0.005, poll_seconds=0.01
    )
    assert result["accepted"] == result["completed"] == result["feedback_ok"] == 6
    assert result["provider_calls"] == 6
    assert result["peak_provider_concurrency"] == 2
    assert result["failed"] == result["unobserved"] == result["paid_ai_calls"] == 0


def test_thirty_people_service_time_lower_bound_does_not_hide_queue():
    rows = {
        row["worker_seconds_assumed"]: row for row in tool("concurrency_probe").wave_sensitivity()
    }
    assert rows[20]["last_terminal_lower_bound_seconds"] == 300
    assert rows[2]["completion_30s_possible_before_overheads"] is False
    assert rows[0.5]["sustainable_evaluations_per_minute_upper_bound"] == 240


def test_campaign_rejects_unsafe_size_before_clients_or_side_effects():
    with pytest.raises(ValueError, match="InvalidCampaignBounds"):
        tool("concurrency_probe").campaign([object()] * 31)
