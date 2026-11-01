"""Shared paid-provider monthly request ceilings."""

MONTHLY_USER_MAX = 20
MONTHLY_GLOBAL_MAX = 600


def validate_limits(user_limit, global_limit):
    if (
        type(user_limit) is not int
        or not 1 <= user_limit <= MONTHLY_USER_MAX
        or type(global_limit) is not int
        or not 1 <= global_limit <= MONTHLY_GLOBAL_MAX
    ):
        raise ValueError("provider_usage_limit")
