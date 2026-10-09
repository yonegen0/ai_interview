"""Fixed P4 alarm contracts; notifications remain independently unverified."""

from manifest_checks import expect, pages


def expected_alarms(manifest, prefix):
    if manifest["schema_version"] == 4:
        from cost_controls import validate_configuration

        validate_configuration(manifest)
        if (
            manifest["environment"] == "test"
            and not manifest["configuration"]["test_monitoring_enabled"]
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
    modern = manifest.get("monitoring_contract_version") == 2

    def sparse_sum(metric, expression_id, inputs, **kwargs):
        value = {k: v for k, v in common.items() if k not in {"Period", "Statistic"}}
        value.update(EvaluationPeriods=5, DatapointsToAlarm=1, **kwargs)
        value["Metrics"] = [
            {
                "Id": expression_id,
                "Expression": "SUM([" + ",".join(key for key, _ in inputs) + "])",
                "ReturnData": True,
            }
        ]
        for key, role in inputs:
            value["Metrics"].append(
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
                        "Period": 60,
                        "Stat": "Sum",
                    },
                }
            )
        return value

    roles = (
        ("api", "worker", "dispatcher", "admin")
        if manifest["schema_version"] >= 3
        else ("api", "worker", "dispatcher")
    )

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
    for role in roles:
        for metric in (
            "DBError",
            "IntegrityError",
            "InvalidEvent",
            "InvalidConfiguration",
            "InternalInvocationFailed",
        ):
            emf(role + "-" + metric, role, metric, Period=300)
    emf("OutcomeUnknown")
    if modern:
        alarms[prefix + "-OutcomeUnknown"] = sparse_sum(
            "OutcomeUnknown",
            "unknown",
            (("wo", "worker"), ("do", "dispatcher")),
            OKActions=[topic],
        )
    for key, suffix in (("worker", "worker-dlq"), ("stream", "stream-failure")):
        alarms[f"{prefix}-dlq-{key}"] = common | {
            "Namespace": "AWS/SQS",
            "MetricName": "ApproximateNumberOfMessagesVisible",
            "Dimensions": [{"Name": "QueueName", "Value": f"{prefix}-{suffix}"}],
            "Statistic": "Maximum",
        }
    for role in roles:
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
    if modern:
        rate.update(EvaluationPeriods=3, DatapointsToAlarm=1)
        rate["Metrics"][0]["Expression"] = (
            "IF(SUM([wc,wf,dc,df])>=10,100*SUM([wf,df])/SUM([wc,wf,dc,df]),0)"
        )
    if manifest["environment"] == "dev":
        configuration = manifest["configuration"]
        if not any(
            configuration[key]
            for key in ("api_enabled", "worker_enabled", "streams_enabled", "scheduler_enabled")
        ):
            return {}
        names = {
            "RecoveryHeartbeat",
            "RecoverySweepLag",
            "OutcomeUnknown",
            "dlq-worker",
            "dlq-stream",
        } | {
            f"{role}-{metric}"
            for role in roles
            for metric in ("Errors", "Throttles", "IntegrityError")
        }
        if manifest["schema_version"] == 4 and configuration["log_usage"] == "customer":
            names |= {"PendingAge", "QueuedAge"}
        alarms = {
            name: value
            for name, value in alarms.items()
            if name.removeprefix(prefix + "-") in names
        }
        alarms[prefix + "-RecoverySweepLag"]["ActionsEnabled"] = configuration["scheduler_enabled"]
    if (
        manifest["environment"] == "dev"
        and manifest["schema_version"] == 4
        and manifest["configuration"]["log_usage"] == "customer"
    ):
        alarms[prefix + "-api-5xx"] = common | {
            "Namespace": "AWS/ApiGateway",
            "MetricName": "5xx",
            "Dimensions": [{"Name": "ApiId", "Value": manifest["api_id"]}],
        }
        failed = {k: v for k, v in common.items() if k not in {"Period", "Statistic"}}
        failed["Metrics"] = [
            {"Id": "failed", "Expression": "FILL(wf,0)+FILL(df,0)", "ReturnData": True}
        ]
        for key, role in (("wf", "worker"), ("df", "dispatcher")):
            failed["Metrics"].append(
                {
                    "Id": key,
                    "ReturnData": False,
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AIInterview",
                            "MetricName": "EvaluationFailed",
                            "Dimensions": [
                                {"Name": "Project", "Value": "ai-interview"},
                                {"Name": "Environment", "Value": "dev"},
                                {"Name": "Component", "Value": role},
                            ],
                        },
                        "Period": 60,
                        "Stat": "Sum",
                    },
                }
            )
        alarms[prefix + "-evaluation-failed"] = (
            sparse_sum("EvaluationFailed", "failed", (("wf", "worker"), ("df", "dispatcher")))
            if modern
            else failed
        )
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
