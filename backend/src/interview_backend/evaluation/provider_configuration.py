"""Pure validation of the AI portion of a runtime environment."""

from collections.abc import Mapping

from interview_backend.evaluation.openai_provider import ProviderFailure

AI_PREFIXES = (
    "INTERVIEW_AI_",
    "INTERVIEW_BEDROCK_",
    "INTERVIEW_ANTHROPIC_",
    "INTERVIEW_OPENAI_",
    "INTERVIEW_WIF_",
    "INTERVIEW_FAKE_",
    "INTERVIEW_VALIDATION_",
)
BEDROCK_KEYS = frozenset(
    {
        "INTERVIEW_AI_PROVIDER",
        "INTERVIEW_BEDROCK_ENABLED",
        "INTERVIEW_BEDROCK_PROFILE_ID",
        "INTERVIEW_BEDROCK_EFFORT",
        "INTERVIEW_BEDROCK_MAX_TOKENS",
        "INTERVIEW_BEDROCK_MONTHLY_USER_LIMIT",
        "INTERVIEW_BEDROCK_MONTHLY_GLOBAL_LIMIT",
    }
)
OPENAI_KEYS = frozenset(
    {
        "INTERVIEW_AI_PROVIDER",
        "INTERVIEW_OPENAI_ENABLED",
        "INTERVIEW_OPENAI_AUTH",
        "INTERVIEW_OPENAI_IDENTITY_PROVIDER_ID",
        "INTERVIEW_OPENAI_SERVICE_ACCOUNT_ID",
        "INTERVIEW_OPENAI_SECRET_ARN",
        "INTERVIEW_OPENAI_EFFORT",
        "INTERVIEW_OPENAI_MAX_OUTPUT_TOKENS",
        "INTERVIEW_OPENAI_MONTHLY_USER_LIMIT",
        "INTERVIEW_OPENAI_MONTHLY_GLOBAL_LIMIT",
        "INTERVIEW_OPENAI_AWS_ISSUER",
    }
)
ANTHROPIC_KEYS = frozenset(
    {
        "INTERVIEW_AI_PROVIDER",
        "INTERVIEW_ANTHROPIC_ENABLED",
        "INTERVIEW_ANTHROPIC_AUTH",
        "INTERVIEW_ANTHROPIC_SECRET_ARN",
        "INTERVIEW_ANTHROPIC_WORKSPACE_ID",
        "INTERVIEW_ANTHROPIC_MODEL",
        "INTERVIEW_ANTHROPIC_API_VERSION",
        "INTERVIEW_ANTHROPIC_EFFORT",
        "INTERVIEW_ANTHROPIC_MAX_OUTPUT_TOKENS",
        "INTERVIEW_ANTHROPIC_MONTHLY_USER_LIMIT",
        "INTERVIEW_ANTHROPIC_MONTHLY_GLOBAL_LIMIT",
    }
)
FAKE_KEYS = frozenset(
    {
        "INTERVIEW_AI_PROVIDER",
        "INTERVIEW_FAKE_SCENARIO",
        "INTERVIEW_VALIDATION_ONLY",
        "INTERVIEW_VALIDATION_OWNER_HASHES",
        "INTERVIEW_WIF_SMOKE_ENABLED",
        "INTERVIEW_WIF_SMOKE_RUN_ID",
        "INTERVIEW_OPENAI_AWS_ISSUER",
        "INTERVIEW_OPENAI_AUTH",
        "INTERVIEW_OPENAI_ENABLED",
        "INTERVIEW_OPENAI_IDENTITY_PROVIDER_ID",
        "INTERVIEW_OPENAI_SERVICE_ACCOUNT_ID",
    }
)
WORKER_AI_KEYS = BEDROCK_KEYS | OPENAI_KEYS | ANTHROPIC_KEYS | FAKE_KEYS


def provider_values(environment):
    """Ignore ordinary runtime keys, reject every unknown or mixed AI key by presence."""
    if not isinstance(environment, Mapping) or any(type(k) is not str for k in environment):
        raise ProviderFailure("CONFIGURATION")
    values = {k: v for k, v in environment.items() if k.startswith(AI_PREFIXES)}
    if any(type(v) is not str for v in values.values()):
        raise ProviderFailure("CONFIGURATION")
    provider = values.get("INTERVIEW_AI_PROVIDER", "fake")
    allowed = {"bedrock": BEDROCK_KEYS, "openai": OPENAI_KEYS, "anthropic": ANTHROPIC_KEYS, "fake": FAKE_KEYS}.get(provider)
    if allowed is None or set(values) - allowed:
        raise ProviderFailure("CONFIGURATION")
    return values
