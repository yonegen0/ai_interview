"""Fixed P4 alarm contracts; notifications remain independently unverified."""

from manifest_checks import expect, pages


def expected_alarms(manifest, prefix):
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

    def emf(name, component="dispatcher", metric=None, **kwargs):
        alarms[prefix + "-" + name] = (
            common
            | {
                "Namespace": "AIInterview",
                "MetricName": metric or name,
                "Dimensions": [
                    {"Name": "Project", "Value": "ai-interview"},
                    {"Name": "Environment", "Value": manifest["environment"]},
                    {"Name": "Component", "Value": component},
                ],
                "OKActions": [topic],
            }
            | kwargs
        )

    for name in ("PendingAge", "QueuedAge"):
        emf(name, Threshold=120, ComparisonOperator="GreaterThanThreshold", Statistic="Maximum")
    emf(
        "RecoveryHeartbeat",
        ComparisonOperator="LessThanThreshold",
        EvaluationPeriods=3,
        TreatMissingData="breaching",
        ActionsEnabled=manifest["configuration"]["scheduler_enabled"],
    )
    emf(
        "RecoverySweepLag",
        Threshold=180,
        ComparisonOperator="GreaterThanThreshold",
        Statistic="Maximum",
    )
    for name in ("ExpiredLease", "DeadlineOverdue"):
        emf(name, EvaluationPeriods=2)
    for role in ("api", "worker", "dispatcher"):
        for metric in (
            "DBError",
            "IntegrityError",
            "InvalidEvent",
            "InvalidConfiguration",
            "InternalInvocationFailed",
        ):
            emf(role + "-" + metric, role, metric, Period=300)
    emf("OutcomeUnknown")
    for key, suffix in (("worker", "worker-dlq"), ("stream", "stream-failure")):
        alarms[f"{prefix}-dlq-{key}"] = common | {
            "Namespace": "AWS/SQS",
            "MetricName": "ApproximateNumberOfMessagesVisible",
            "Dimensions": [{"Name": "QueueName", "Value": f"{prefix}-{suffix}"}],
            "Statistic": "Maximum",
        }
    for role in ("api", "worker", "dispatcher"):
        for metric in ("Errors", "Throttles"):
            alarms[f"{prefix}-{role}-{metric}"] = common | {
                "Namespace": "AWS/Lambda",
                "MetricName": metric,
                "Dimensions": [{"Name": "FunctionName", "Value": f"{prefix}-{role}"}],
                "Period": 300,
            }
    alarms[prefix + "-iterator-age"] = common | {
        "Namespace": "AWS/Lambda",
        "MetricName": "IteratorAge",
        "Dimensions": [{"Name": "FunctionName", "Value": prefix + "-dispatcher"}],
        "Period": 300,
        "Statistic": "Maximum",
        "ComparisonOperator": "GreaterThanThreshold",
        "Threshold": 120000,
        "ActionsEnabled": manifest["configuration"]["streams_enabled"],
    }
    rate = {key: val for key, val in common.items() if key not in {"Period", "Statistic"}}
    rate.update(
        ComparisonOperator="GreaterThanThreshold",
        Threshold=20,
        Metrics=[
            {
                "Id": "rate",
                "Expression": (
                    "IF((FILL(wc,0)+FILL(wf,0)+FILL(dc,0)+FILL(df,0))>=10,"
                    "100*(FILL(wf,0)+FILL(df,0))/(FILL(wc,0)+FILL(wf,0)+FILL(dc,0)+FILL(df,0)),0)"
                ),
                "ReturnData": True,
            }
        ],
    )
    for key, role, metric in (
        ("wc", "worker", "EvaluationCompleted"),
        ("wf", "worker", "EvaluationFailed"),
        ("dc", "dispatcher", "EvaluationCompleted"),
        ("df", "dispatcher", "EvaluationFailed"),
    ):
        rate["Metrics"].append(
            {
                "Id": key,
                "ReturnData": False,
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AIInterview",
                        "MetricName": metric,
                        "Dimensions": [
                            {"Name": "Project", "Value": "ai-interview"},
                            {"Name": "Environment", "Value": manifest["environment"]},
                            {"Name": "Component", "Value": role},
                        ],
                    },
                    "Period": 900,
                    "Stat": "Sum",
                },
            }
        )
    alarms[prefix + "-failure-rate"] = rate
    return alarms


def normalize(value):
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        import json

        return sorted(
            (normalize(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True)
        )
    return value


def verify_alarms(cloudwatch, manifest, prefix):
    expected = expected_alarms(manifest, prefix)
    observed = pages(cloudwatch.describe_alarms, "MetricAlarms", AlarmNamePrefix=prefix + "-")
    if len(observed) != len(expected) or {a["AlarmName"] for a in observed} != set(expected):
        raise ValueError("AlarmSetMismatch")
    for alarm in observed:
        expect(normalize(alarm), normalize(expected[alarm["AlarmName"]]))
