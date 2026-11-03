"""Shared paid-provider monthly request ceilings."""

MONTHLY_USER_MAX = 100
MONTHLY_GLOBAL_MAX = 2000


def validate_limits(
    user_limit, global_limit, *, user_max=MONTHLY_USER_MAX, global_max=MONTHLY_GLOBAL_MAX
):
    if (
        type(user_limit) is not int
        or not 1 <= user_limit <= user_max
        or type(global_limit) is not int
        or not 1 <= global_limit <= global_max
    ):
        raise ValueError("provider_usage_limit")
