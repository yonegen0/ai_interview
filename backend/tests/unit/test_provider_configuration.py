"""Reject AI key escapes before a paid provider or SDK client is constructed."""

import pytest

from interview_backend.evaluation.bedrock_provider import BedrockSettings
from interview_backend.evaluation.openai_provider import OpenAISettings, ProviderFailure
from interview_backend.evaluation.provider_configuration import provider_values
from interview_backend.evaluation.selection import checked_provider_environment, select_provider

BASE = {"INTERVIEW_AI_PROVIDER": "bedrock", "INTERVIEW_BEDROCK_ENABLED": "true"}


@pytest.mark.parametrize(
    "key,value",
    [
        ("INTERVIEW_VALIDATION_ONLY", "false"),
        ("INTERVIEW_VALIDATION_ONLY", ""),
        ("INTERVIEW_VALIDATION_OWNER_HASHES", "synthetic-owner"),
        ("INTERVIEW_VALIDATION_FUTURE", "false"),
        ("INTERVIEW_AI_FUTURE_OPTION", "false"),
        ("INTERVIEW_BEDROCK_FUTURE", "false"),
        ("INTERVIEW_OPENAI_ENABLED", "false"),
        ("INTERVIEW_WIF_SMOKE_ENABLED", "false"),
        ("INTERVIEW_FAKE_SCENARIO", "false"),
    ],
)
def test_bedrock_rejects_ai_key_by_presence_at_every_entry(key, value):
    environment = BASE | {key: value, "INTERVIEW_REGION": "ap-northeast-1"}
    for entry in (
        lambda: BedrockSettings.from_environment(environment),
        lambda: select_provider(environment),
        lambda: checked_provider_environment(
            {k: v for k, v in environment.items() if k != "INTERVIEW_REGION"},
            "123456789012",
            "ap-northeast-1",
        ),
    ):
        with pytest.raises((ProviderFailure, ValueError)):
            entry()


def test_common_runtime_keys_do_not_count_as_unknown_ai_settings():
    environment = BASE | {
        "INTERVIEW_REGION": "ap-northeast-1",
        "INTERVIEW_TABLE_NAME": "synthetic-table",
        "INTERVIEW_QUEUE_ARN": "synthetic-queue",
        "AWS_REGION": "ap-northeast-1",
    }
    assert provider_values(environment) == BASE
    assert BedrockSettings.from_environment(environment).max_tokens == 2048
    assert select_provider(environment).provider_id.startswith("bedrock:")


@pytest.mark.parametrize(
    "settings",
    [
        {"effort": "medium"},
        {"effort": "high"},
        {"max_tokens": 1024},
        {"monthly_user_limit": 101},
        {"monthly_global_limit": 3001},
        {"monthly_user_limit": True},
        {"monthly_global_limit": 1.5},
    ],
)
def test_bedrock_contract_is_low_2048_and_shared_ceiling(settings):
    with pytest.raises(ProviderFailure) as error:
        BedrockSettings(**settings)
    assert error.value.kind == "CONFIGURATION"


@pytest.mark.parametrize(
    "settings",
    [
        {"monthly_user_limit": 101},
        {"monthly_global_limit": 3001},
        {"monthly_user_limit": True},
        {"monthly_global_limit": 1.5},
    ],
)
def test_openai_uses_same_hard_ceiling(settings):
    with pytest.raises(ProviderFailure) as error:
        OpenAISettings(**settings)
    assert error.value.kind == "CONFIGURATION"


def test_lower_limits_remain_available_for_isolated_tests():
    assert BedrockSettings(monthly_user_limit=1, monthly_global_limit=2)
    assert OpenAISettings(monthly_user_limit=1, monthly_global_limit=2)
