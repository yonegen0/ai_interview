"""Strict schema-4 cost settings; legacy receipts keep their original contracts."""

FLAGS = ("api_enabled", "worker_enabled", "streams_enabled", "scheduler_enabled")


def validate_configuration(manifest):
    configuration = manifest["configuration"]
    usage = configuration.get("log_usage")
    days = configuration.get("log_retention_days")
    if usage not in ("developer", "customer") or type(days) is not int:
        raise ValueError("ExplicitLogUsageRequired")
    if days != (14 if usage == "customer" else 3):
        raise ValueError("LogRetentionUsageMismatch")
    for key in (*FLAGS, "test_monitoring_enabled", "test_closure_confirmed"):
        if type(configuration.get(key)) is not bool:
            raise ValueError("ExplicitCostControlFlagsRequired")
    active = any(configuration[key] for key in FLAGS)
    test = manifest["environment"] == "test"
    if configuration["test_closure_confirmed"] and (not test or active):
        raise ValueError("ClosedTestConfirmationRequired")
    if not configuration["test_monitoring_enabled"] and (
        not test or active or not configuration["test_closure_confirmed"]
    ):
        raise ValueError("VerifiedTestClosureRequired")
