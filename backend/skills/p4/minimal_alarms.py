"""Invite minimal monitoring readback: five alarms and six metric references."""


def expected_minimal_alarms(manifest, prefix):
    config = manifest["configuration"]
    if not any(
        config[key]
        for key in ("api_enabled", "worker_enabled", "streams_enabled", "scheduler_enabled")
    ):
        return {}
    topic = manifest["alarm_topic_arn"]
    common = {
        "ComparisonOperator": "GreaterThanOrEqualToThreshold",
        "Threshold": 1,
        "EvaluationPeriods": 1,
        "Period": 60,
        "Statistic": "Sum",
        "TreatMissingData": "notBreaching",
        "AlarmActions": [topic],
        "OKActions": [],
        "InsufficientDataActions": [],
        "ActionsEnabled": True,
    }
    alarms = {}
    for name in ("CriticalFailure", "RecoveryHeartbeat"):
        alarms[prefix + "-" + name] = common | {
            "Namespace": "AIInterview",
            "MetricName": name,
            "Dimensions": [
                {"Name": "Project", "Value": "ai-interview"},
                {"Name": "Environment", "Value": manifest["environment"]},
            ],
        }
    alarms[prefix + "-RecoveryHeartbeat"].update(
        ComparisonOperator="LessThanThreshold",
        EvaluationPeriods=3,
        TreatMissingData="breaching",
        ActionsEnabled=config["scheduler_enabled"],
    )
    alarms[prefix + "-api-5xx"] = common | {
        "Namespace": "AWS/ApiGateway",
        "MetricName": "5xx",
        "Dimensions": [{"Name": "ApiId", "Value": manifest["api_id"]}],
    }
    alarms[prefix + "-worker-Errors"] = common | {
        "Namespace": "AWS/Lambda",
        "MetricName": "Errors",
        "Period": 300,
        "Dimensions": [{"Name": "FunctionName", "Value": prefix + "-worker"}],
    }
    dlq = {k: v for k, v in common.items() if k not in {"Period", "Statistic"}}
    dlq["Metrics"] = [{"Id": "total", "Expression": "SUM([worker,stream])", "ReturnData": True}]
    for name, suffix in (("worker", "worker-dlq"), ("stream", "stream-failure")):
        dlq["Metrics"].append(
            {
                "Id": name,
                "ReturnData": False,
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/SQS",
                        "MetricName": "ApproximateNumberOfMessagesVisible",
                        "Dimensions": [{"Name": "QueueName", "Value": prefix + "-" + suffix}],
                    },
                    "Period": 60,
                    "Stat": "Maximum",
                },
            }
        )
    alarms[prefix + "-dlq"] = dlq
    return alarms
