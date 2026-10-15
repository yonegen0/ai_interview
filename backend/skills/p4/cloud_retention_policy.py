"""Immutable exact five-resource Plan-only exception, generated from pinned State."""

POLICY = {
    "revision": 1,
    "baseline_state_sha256": "490df5dae032fadbce564fa3998a86d9d06c383d71975f670493a969bca9570d",
    "required_updates": 5,
    "targets": [
        {
            "address": "module.service.aws_cloudwatch_log_group.api",
            "name": "/aws/apigateway/ai-interview-dev",
            "arn": (
                "arn:aws:logs:ap-northeast-1:835384817629"
                ":log-group:/aws/apigateway/ai-interview-dev"
            ),
            "before_attributes_sha256": (
                "7493e9c68935d03abdec7cc1a9756f1cef5f6b617f1e9c1a0b70ad7408e97fde"
            ),
            "before_days": 7,
            "after_days": 14,
        },
        {
            "address": 'module.service.aws_cloudwatch_log_group.lambda["admin"]',
            "name": "/aws/lambda/ai-interview-dev-admin",
            "arn": (
                "arn:aws:logs:ap-northeast-1:835384817629"
                ":log-group:/aws/lambda/ai-interview-dev-admin"
            ),
            "before_attributes_sha256": (
                "9d8c7e42b04891a4af804d627ba414afbca9db1a1b5271e229ef4b8caf1bd526"
            ),
            "before_days": 7,
            "after_days": 14,
        },
        {
            "address": 'module.service.aws_cloudwatch_log_group.lambda["api"]',
            "name": "/aws/lambda/ai-interview-dev-api",
            "arn": (
                "arn:aws:logs:ap-northeast-1:835384817629"
                ":log-group:/aws/lambda/ai-interview-dev-api"
            ),
            "before_attributes_sha256": (
                "a65bd4bd73c49b445e76e9ddadcc2cf73d98ae715eaf7cc1f7feab38805f5123"
            ),
            "before_days": 7,
            "after_days": 14,
        },
        {
            "address": 'module.service.aws_cloudwatch_log_group.lambda["dispatcher"]',
            "name": "/aws/lambda/ai-interview-dev-dispatcher",
            "arn": (
                "arn:aws:logs:ap-northeast-1:835384817629"
                ":log-group:/aws/lambda/ai-interview-dev-dispatcher"
            ),
            "before_attributes_sha256": (
                "6c0703b52f1ecb1dea0b2faa32712c74eee971ac872ee79bd7e6c40880daa135"
            ),
            "before_days": 7,
            "after_days": 14,
        },
        {
            "address": 'module.service.aws_cloudwatch_log_group.lambda["worker"]',
            "name": "/aws/lambda/ai-interview-dev-worker",
            "arn": (
                "arn:aws:logs:ap-northeast-1:835384817629"
                ":log-group:/aws/lambda/ai-interview-dev-worker"
            ),
            "before_attributes_sha256": (
                "d12b69718f1618bec8959032d3f1b95860aaef13b73e511713121c43fe453c5b"
            ),
            "before_days": 7,
            "after_days": 14,
        },
    ],
    "only_field": "retention_in_days",
    "actions": ["update"],
    "apply_authorized": False,
}
