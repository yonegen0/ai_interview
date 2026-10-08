"""Worker-only explicit selection. Fake default does not import an external transport."""

from interview_backend.evaluation.provider import FakeProvider

WORKER_AI_KEYS = frozenset(
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
        "INTERVIEW_FAKE_SCENARIO",
        "INTERVIEW_VALIDATION_ONLY",
        "INTERVIEW_VALIDATION_OWNER_HASHES",
    }
)


def checked_provider_environment(values, account, region):
    """Validate manifest/approval settings without constructing clients or obtaining tokens."""
    import re

    if (
        not isinstance(values, dict)
        or set(values) - WORKER_AI_KEYS
        or any(type(v) is not str for v in values.values())
    ):
        raise ValueError("InvalidProviderEnvironment")
    if not values:
        return {}
    provider = values.get("INTERVIEW_AI_PROVIDER")
    if provider not in {"fake", "openai"}:
        raise ValueError("InvalidProviderEnvironment")
    if region != "ap-northeast-1":
        raise ValueError("InvalidProviderEnvironment")
    if provider == "fake":
        if set(values) - {
            "INTERVIEW_AI_PROVIDER",
            "INTERVIEW_FAKE_SCENARIO",
            "INTERVIEW_VALIDATION_ONLY",
            "INTERVIEW_VALIDATION_OWNER_HASHES",
        }:
            raise ValueError("InvalidProviderEnvironment")
        if "INTERVIEW_FAKE_SCENARIO" in values:
            from interview_backend.evaluation.validation_scenarios import ValidationScenario

            if values.get("INTERVIEW_VALIDATION_ONLY") != "true":
                raise ValueError("InvalidProviderEnvironment")
            ValidationScenario(
                values["INTERVIEW_FAKE_SCENARIO"],
                values.get("INTERVIEW_VALIDATION_OWNER_HASHES", "").split(","),
            )
    if provider == "openai":
        if values.get("INTERVIEW_OPENAI_ENABLED") != "true":
            raise ValueError("InvalidProviderEnvironment")
        mode = values.get("INTERVIEW_OPENAI_AUTH", "wif")
        if mode == "wif":
            if not all(
                re.fullmatch(r"[A-Za-z0-9_-]{1,128}", values.get(k, ""))
                for k in (
                    "INTERVIEW_OPENAI_IDENTITY_PROVIDER_ID",
                    "INTERVIEW_OPENAI_SERVICE_ACCOUNT_ID",
                )
            ):
                raise ValueError("InvalidProviderEnvironment")
        elif mode == "secret":
            if not re.fullmatch(
                re.escape(f"arn:aws:secretsmanager:{region}:{account}:secret:")
                + r"[A-Za-z0-9/_+=.@-]+",
                values.get("INTERVIEW_OPENAI_SECRET_ARN", ""),
            ):
                raise ValueError("InvalidProviderEnvironment")
        else:
            raise ValueError("InvalidProviderEnvironment")
        from interview_backend.evaluation.openai_provider import OpenAISettings

        OpenAISettings(
            effort=values.get("INTERVIEW_OPENAI_EFFORT", "low"),
            max_output_tokens=int(values.get("INTERVIEW_OPENAI_MAX_OUTPUT_TOKENS", "4096")),
            monthly_user_limit=int(values.get("INTERVIEW_OPENAI_MONTHLY_USER_LIMIT", "100")),
            monthly_global_limit=int(values.get("INTERVIEW_OPENAI_MONTHLY_GLOBAL_LIMIT", "3000")),
        )
    return dict(values)


def select_provider(environment):
    selection = environment.get("INTERVIEW_AI_PROVIDER", "fake")
    if selection == "fake":
        if "INTERVIEW_FAKE_SCENARIO" in environment:
            if environment.get("INTERVIEW_VALIDATION_ONLY") != "true":
                raise ValueError("ValidationEnablementRequired")
            from interview_backend.evaluation.validation_scenarios import ValidationScenario

            return ValidationScenario(
                environment["INTERVIEW_FAKE_SCENARIO"],
                environment.get("INTERVIEW_VALIDATION_OWNER_HASHES", "").split(","),
            )
        return FakeProvider()
    from interview_backend.evaluation.openai_auth import AWSFederation, SecretAuthentication
    from interview_backend.evaluation.openai_provider import (
        OpenAIProvider,
        OpenAISettings,
        ProviderFailure,
    )

    if selection != "openai" or environment.get("INTERVIEW_OPENAI_ENABLED") != "true":
        raise ProviderFailure("CONFIGURATION")
    region = environment.get("INTERVIEW_REGION")
    mode = environment.get("INTERVIEW_OPENAI_AUTH", "wif")
    if mode == "wif":
        authentication = AWSFederation(
            region,
            environment.get("INTERVIEW_OPENAI_IDENTITY_PROVIDER_ID", ""),
            environment.get("INTERVIEW_OPENAI_SERVICE_ACCOUNT_ID", ""),
        )
    elif mode == "secret":
        arn = environment.get("INTERVIEW_OPENAI_SECRET_ARN", "")
        if not arn.startswith(
            f"arn:aws:secretsmanager:{region}:{environment.get('INTERVIEW_ACCOUNT_ID')}:secret:"
        ):
            raise ProviderFailure("CONFIGURATION")
        authentication = SecretAuthentication(region, arn)
    else:
        raise ProviderFailure("CONFIGURATION")
    try:
        settings = OpenAISettings(
            effort=environment.get("INTERVIEW_OPENAI_EFFORT", "low"),
            max_output_tokens=int(environment.get("INTERVIEW_OPENAI_MAX_OUTPUT_TOKENS", "4096")),
            monthly_user_limit=int(environment.get("INTERVIEW_OPENAI_MONTHLY_USER_LIMIT", "100")),
            monthly_global_limit=int(
                environment.get("INTERVIEW_OPENAI_MONTHLY_GLOBAL_LIMIT", "3000")
            ),
        )
    except TypeError, ValueError:
        raise ProviderFailure("CONFIGURATION") from None
    return OpenAIProvider(authentication, settings=settings)
