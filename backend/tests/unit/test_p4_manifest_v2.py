"""Full synthetic closed deployment and rejection of missing readback fields."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_p4_tools import manifest, tool


@pytest.fixture
def deployment(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "skills/p4"))
    m = manifest()
    a, r, p = m["account_id"], m["region"], "ai-interview-dev"
    m.update(
        stream_arn=f"arn:aws:dynamodb:{r}:{a}:table/{p}-main/stream/synthetic",
        schedule_arn=f"arn:aws:scheduler:{r}:{a}:schedule/{p}/recovery",
        mappings={"worker": "worker-id", "streams": "streams-id"},
        alarm_topic_arn=f"arn:aws:sns:{r}:{a}:{p}-alarms",
    )
    c = m["configuration"]
    data = {}

    def add(service, operation, value, key=""):
        data[service, operation, key] = value

    add("sts", "get_caller_identity", {"Account": a})
    table = {
        "TableArn": f"arn:aws:dynamodb:{r}:{a}:table/{p}-main",
        "LatestStreamArn": m["stream_arn"],
        "TableStatus": "ACTIVE",
        "AttributeDefinitions": [
            {"AttributeName": name, "AttributeType": "S"}
            for name in ("PK", "SK", "work_pk", "work_sk")
        ],
        "BillingModeSummary": {"BillingMode": "PAY_PER_REQUEST"},
        "KeySchema": [
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        "StreamSpecification": {"StreamEnabled": True, "StreamViewType": "NEW_AND_OLD_IMAGES"},
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "WorkIndex",
                "IndexStatus": "ACTIVE",
                "Projection": {"ProjectionType": "KEYS_ONLY"},
                "KeySchema": [
                    {"AttributeName": "work_pk", "KeyType": "HASH"},
                    {"AttributeName": "work_sk", "KeyType": "RANGE"},
                ],
            }
        ],
    }
    add("dynamodb", "describe_table", {"Table": table})
    add(
        "dynamodb",
        "describe_time_to_live",
        {"TimeToLiveDescription": {"TimeToLiveStatus": "DISABLED"}},
    )
    for key, suffix, retention, visibility in (
        ("queue_url", "main", "345600", "360"),
        ("worker_dlq_url", "worker-dlq", "1209600", "30"),
        ("stream_failure_url", "stream-failure", "1209600", "30"),
    ):
        attrs = {
            "QueueArn": f"arn:aws:sqs:{r}:{a}:{p}-{suffix}",
            "MessageRetentionPeriod": retention,
            "VisibilityTimeout": visibility,
            "SqsManagedSseEnabled": "true",
        }
        if key == "queue_url":
            attrs["RedrivePolicy"] = json.dumps(
                {"deadLetterTargetArn": f"arn:aws:sqs:{r}:{a}:{p}-worker-dlq", "maxReceiveCount": 5}
            )
        if key == "worker_dlq_url":
            attrs["RedriveAllowPolicy"] = json.dumps(
                {"redrivePermission": "byQueue", "sourceQueueArns": [m["queue_arn"]]}
            )
        add("sqs", "get_queue_attributes", {"Attributes": attrs}, m[key])
    for alias, arn in m["aliases"].items():
        role = "dispatcher" if alias in {"streams", "recovery"} else alias
        add("lambda", "get_alias", {"AliasArn": arn, "FunctionVersion": m["versions"][role]}, arn)
    for role in ("api", "worker", "dispatcher"):
        name = p + "-" + role
        env = {
            "INTERVIEW_ACCOUNT_ID": a,
            "INTERVIEW_REGION": r,
            "INTERVIEW_TABLE_NAME": m["table_name"],
            "INTERVIEW_COMPONENT": role,
            "INTERVIEW_FUNCTION_NAME": name,
        }
        env.update(
            {
                "api": {
                    "INTERVIEW_CLIENT_ID": m["client_id"],
                    "INTERVIEW_USER_POOL_ID": m["user_pool_id"],
                    "INTERVIEW_API_ID": m["api_id"],
                    "INTERVIEW_STAGE": "dev",
                },
                "worker": {"INTERVIEW_QUEUE_ARN": m["queue_arn"]},
                "dispatcher": {
                    "INTERVIEW_QUEUE_ARN": m["queue_arn"],
                    "INTERVIEW_QUEUE_URL": m["queue_url"],
                    "INTERVIEW_STREAM_ARN": m["stream_arn"],
                    "INTERVIEW_SCHEDULE_ARN": m["schedule_arn"],
                },
            }[role]
        )
        add(
            "lambda",
            "get_function_configuration",
            {
                "CodeSha256": m["artifact"]["sha256_base64"],
                "Version": str(m["versions"][role]),
                "Runtime": "python3.14",
                "Architectures": ["x86_64"],
                "MemorySize": 512,
                "Timeout": {"api": 15, "worker": 60, "dispatcher": 30}[role],
                "Handler": f"interview_backend.aws_runtime.{role}_handler",
                "Role": f"arn:aws:iam::{a}:role/{name}-runtime",
                "State": "Active",
                "Environment": {"Variables": env},
            },
            name,
        )
        add(
            "lambda",
            "get_function_concurrency",
            {"ReservedConcurrentExecutions": 2} if role == "worker" else {},
            name,
        )
        add(
            "iam",
            "get_role",
            {
                "Role": {
                    "PermissionsBoundary": {
                        "PermissionsBoundaryArn": c["boundary_arn"],
                        "PermissionsBoundaryType": "Policy",
                    }
                }
            },
            name + "-runtime",
        )
    for role in ("worker", "streams"):
        value = {
            "UUID": role + "-id",
            "EventSourceArn": m["queue_arn"] if role == "worker" else m["stream_arn"],
            "FunctionArn": m["aliases"][role],
            "State": "Disabled",
            "BatchSize": 1 if role == "worker" else 100,
            "MaximumBatchingWindowInSeconds": 0,
            "FunctionResponseTypes": ["ReportBatchItemFailures"],
        }
        if role == "worker":
            value["ScalingConfig"] = {"MaximumConcurrency": 2}
        else:
            value.update(
                MaximumRetryAttempts=3,
                MaximumRecordAgeInSeconds=3600,
                BisectBatchOnFunctionError=True,
                ParallelizationFactor=1,
                DestinationConfig={
                    "OnFailure": {"Destination": f"arn:aws:sqs:{r}:{a}:{p}-stream-failure"}
                },
                FilterCriteria={
                    "Filters": [
                        {
                            "Pattern": json.dumps(
                                {"dynamodb": {"NewImage": {"kind": {"S": ["Dispatch"]}}}}
                            )
                        }
                    ]
                },
            )
        add("lambda", "get_event_source_mapping", value, role + "-id")
    add(
        "scheduler",
        "get_schedule",
        {
            "Arn": m["schedule_arn"],
            "Name": "recovery",
            "GroupName": p,
            "ScheduleExpression": "rate(1 minute)",
            "State": "DISABLED",
            "FlexibleTimeWindow": {"Mode": "OFF"},
            "Target": {
                "Arn": m["aliases"]["recovery"],
                "RoleArn": f"arn:aws:iam::{a}:role/{p}-scheduler-runtime",
                "RetryPolicy": {"MaximumRetryAttempts": 3, "MaximumEventAgeInSeconds": 60},
                "Input": '{"eventVersion":1,"type":"RecoveryTick"}',
            },
        },
    )
    add("scheduler", "get_schedule_group", {"Name": p, "State": "ACTIVE"})
    add(
        "apigatewayv2",
        "get_api",
        {
            "ApiEndpoint": m["api_endpoint"].removesuffix("/dev"),
            "ProtocolType": "HTTP",
            "DisableExecuteApiEndpoint": True,
            "CorsConfiguration": {
                "AllowOrigins": c["cors_origins"],
                "AllowMethods": ["GET", "POST", "OPTIONS"],
                "AllowHeaders": ["Authorization", "Content-Type", "Idempotency-Key"],
                "ExposeHeaders": ["Allow"],
                "AllowCredentials": False,
                "MaxAge": 300,
            },
        },
    )
    add(
        "apigatewayv2",
        "get_stage",
        {
            "StageName": "dev",
            "AutoDeploy": True,
            "DefaultRouteSettings": {"ThrottlingBurstLimit": 10, "ThrottlingRateLimit": 5.0},
            "AccessLogSettings": {
                "DestinationArn": f"arn:aws:logs:{r}:{a}:log-group:/aws/apigateway/{p}",
                "Format": json.dumps(
                    {
                        "requestId": "$context.requestId",
                        "routeKey": "$context.routeKey",
                        "status": "$context.status",
                        "responseLength": "$context.responseLength",
                    }
                ),
            },
        },
    )
    add(
        "apigatewayv2",
        "get_authorizers",
        {
            "Items": [
                {
                    "AuthorizerId": "auth",
                    "AuthorizerType": "JWT",
                    "IdentitySource": ["$request.header.Authorization"],
                    "JwtConfiguration": {
                        "Audience": [m["client_id"]],
                        "Issuer": f"https://cognito-idp.{r}.amazonaws.com/{m['user_pool_id']}",
                    },
                }
            ]
        },
    )
    add(
        "apigatewayv2",
        "get_integrations",
        {
            "Items": [
                {
                    "IntegrationId": "integration",
                    "IntegrationType": "AWS_PROXY",
                    "PayloadFormatVersion": "2.0",
                    "TimeoutInMillis": 15000,
                    "IntegrationUri": (
                        f"arn:aws:apigateway:{r}:lambda:path/2015-03-31/"
                        f"functions/{m['aliases']['api']}/invocations"
                    ),
                }
            ]
        },
    )
    routes = [
        "POST /sessions",
        "GET /sessions/{sessionId}/question",
        "POST /sessions/{sessionId}/answers",
        "GET /evaluations/{evaluationId}",
        "GET /attempts/{attemptId}/feedback",
        "POST /sessions/{sessionId}/questions/next",
        "$default",
        "OPTIONS /{proxy+}",
        "OPTIONS /",
    ]
    add(
        "apigatewayv2",
        "get_routes",
        {
            "Items": [
                {
                    "RouteKey": route,
                    "Target": "integrations/integration",
                    "AuthorizationType": "NONE" if route.startswith("OPTIONS") else "JWT",
                    "AuthorizerId": "auth",
                }
                for route in routes
            ]
        },
    )
    add(
        "cognito-idp",
        "describe_user_pool",
        {
            "UserPool": {
                "Arn": f"arn:aws:cognito-idp:{r}:{a}:userpool/{m['user_pool_id']}",
                "UserPoolTier": "ESSENTIALS",
                "UsernameAttributes": ["email"],
                "AutoVerifiedAttributes": ["email"],
                "MfaConfiguration": "OFF",
                "AdminCreateUserConfig": {"AllowAdminCreateUserOnly": True},
                "Policies": {"SignInPolicy": {"AllowedFirstAuthFactors": ["EMAIL_OTP"]}},
                "EmailConfiguration": {
                    "EmailSendingAccount": "DEVELOPER",
                    "SourceArn": c["ses_identity_arn"],
                    "From": c["ses_email"],
                },
            }
        },
    )
    add(
        "cognito-idp",
        "describe_user_pool_client",
        {
            "UserPoolClient": {
                "ClientId": m["client_id"],
                "AccessTokenValidity": 5,
                "IdTokenValidity": 5,
                "RefreshTokenValidity": 1,
                "TokenValidityUnits": {
                    "AccessToken": "minutes",
                    "IdToken": "minutes",
                    "RefreshToken": "days",
                },
                "EnableTokenRevocation": True,
                "PreventUserExistenceErrors": "ENABLED",
                "ExplicitAuthFlows": ["ALLOW_USER_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
            }
        },
    )
    for name in ("USER", "ADMIN"):
        add(
            "cognito-idp",
            "get_group",
            {"Group": {"GroupName": name, "UserPoolId": m["user_pool_id"]}},
            name,
        )
    for name in [f"/aws/lambda/{p}-{role}" for role in ("api", "worker", "dispatcher")] + [
        f"/aws/apigateway/{p}"
    ]:
        add(
            "logs",
            "describe_log_groups",
            {"logGroups": [{"logGroupName": name, "retentionInDays": 30}]},
            name,
        )
    add(
        "sns",
        "get_topic_attributes",
        {
            "Attributes": {
                "TopicArn": m["alarm_topic_arn"],
                "Owner": a,
                "Policy": json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"Service": "cloudwatch.amazonaws.com"},
                                "Action": "sns:Publish",
                                "Resource": m["alarm_topic_arn"],
                                "Condition": {
                                    "StringEquals": {"aws:SourceAccount": a},
                                    "ArnLike": {
                                        "aws:SourceArn": f"arn:aws:cloudwatch:{r}:{a}:alarm:{p}-*"
                                    },
                                },
                            }
                        ],
                    }
                ),
            }
        },
    )
    add(
        "sns",
        "list_subscriptions_by_topic",
        {
            "Subscriptions": [
                {
                    "Protocol": "email",
                    "Endpoint": c["alarm_email"],
                    "SubscriptionArn": "PendingConfirmation",
                }
            ]
        },
    )
    add(
        "budgets",
        "describe_budget",
        {
            "Budget": {
                "BudgetName": p + "-monthly",
                "BudgetType": "COST",
                "TimeUnit": "MONTHLY",
                "BudgetLimit": {"Amount": "20.0", "Unit": "USD"},
            }
        },
    )
    add(
        "budgets",
        "describe_notifications_for_budget",
        {
            "Notifications": [
                {
                    "Threshold": n,
                    "ComparisonOperator": "GREATER_THAN",
                    "ThresholdType": "PERCENTAGE",
                    "NotificationType": "ACTUAL",
                }
                for n in (50, 80, 100)
            ]
        },
    )
    add(
        "budgets",
        "describe_subscribers_for_notification",
        {"Subscribers": [{"SubscriptionType": "EMAIL", "Address": c["alarm_email"]}]},
    )
    alarms = tool("manifest_alarms").expected_alarms(m, p)
    add(
        "cloudwatch",
        "describe_alarms",
        {"MetricAlarms": [value | {"AlarmName": key} for key, value in alarms.items()]},
    )

    def call(service, operation, **kw):
        key = next(
            (
                kw[k]
                for k in ("QueueUrl", "UUID", "RoleName", "GroupName", "logGroupNamePrefix")
                if k in kw
            ),
            "",
        )
        if service == "scheduler":
            key = ""
        if operation == "get_alias":
            key = kw["FunctionName"] + ":" + kw["Name"]
        elif "FunctionName" in kw:
            key = kw["FunctionName"].split(":")[-1]
        return copy.deepcopy(data[service, operation, key])

    class Client:
        def __init__(self, service):
            self.service = service

        def __getattr__(self, operation):
            return lambda **kw: call(self.service, operation, **kw)

    return m, data, SimpleNamespace(client=lambda service, **kw: Client(service))


def test_complete_closed_deployment(deployment):
    m, _, session = deployment
    tool("manifest").verify_live_manifest(
        session, m, require_api_enabled=False, approved_inputs=m["configuration"]
    )


def test_every_alarm_condition_is_checked(deployment):
    m, data, session = deployment
    alarms = data["cloudwatch", "describe_alarms", ""]["MetricAlarms"]
    for alarm in alarms:
        original = alarm["Threshold"]
        alarm["Threshold"] = original + 1
        with pytest.raises(ValueError, match="DeploymentReadbackFailed"):
            tool("manifest").verify_live_manifest(session, m, require_api_enabled=False)
        alarm["Threshold"] = original


def test_each_required_response_leaf_is_checked(deployment):
    m, data, session = deployment

    def paths(value, prefix=()):
        if isinstance(value, dict):
            for key, item in value.items():
                yield from paths(item, (*prefix, key))
        elif isinstance(value, list) and value:
            for index, item in enumerate(value):
                yield from paths(item, (*prefix, index))
        else:
            yield prefix

    checked = 0
    for target, original in list(data.items()):
        for path in paths(original):
            # These are not delivery evidence, and OPTIONS has no authorizer.
            if path[-1] == "SubscriptionArn" or (
                target[1] == "get_routes" and path[-1] == "AuthorizerId" and path[1] in {7, 8}
            ):
                continue
            data[target] = copy.deepcopy(original)
            parent = data[target]
            for part in path[:-1]:
                parent = parent[part]
            del parent[path[-1]]
            with pytest.raises(ValueError, match="DeploymentReadbackFailed"):
                tool("manifest").verify_live_manifest(session, m, require_api_enabled=False)
            checked += 1
        data[target] = original
    assert checked > 300


@pytest.mark.parametrize(
    "target,field",
    [
        (("apigatewayv2", "get_api", ""), "DisableExecuteApiEndpoint"),
        (("scheduler", "get_schedule", ""), "State"),
        (("lambda", "get_event_source_mapping", "worker-id"), "State"),
        (("lambda", "get_event_source_mapping", "streams-id"), "MaximumRetryAttempts"),
        (("lambda", "get_function_configuration", "ai-interview-dev-api"), "Environment"),
        (("apigatewayv2", "get_authorizers", ""), "Items"),
        (("apigatewayv2", "get_routes", ""), "Items"),
        (("sns", "list_subscriptions_by_topic", ""), "Subscriptions"),
        (("budgets", "describe_notifications_for_budget", ""), "Notifications"),
        (("cloudwatch", "describe_alarms", ""), "MetricAlarms"),
    ],
)
def test_missing_required_readback_fails(deployment, target, field):
    m, data, session = deployment
    del data[target][field]
    with pytest.raises(ValueError, match="DeploymentReadbackFailed"):
        tool("manifest").verify_live_manifest(session, m, require_api_enabled=False)


def test_pagination_reads_all_and_rejects_cycles(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "skills/p4"))
    module = tool("manifest_checks")
    responses = iter([{"Items": [1], "NextToken": "next"}, {"Items": [2]}])
    assert module.pages(lambda **kw: next(responses), "Items") == [1, 2]
    with pytest.raises(ValueError, match="InvalidPagination"):
        module.pages(lambda **kw: {"Items": [], "NextToken": "repeat"}, "Items")


def test_readback_poll_deadline_is_monotonic(monkeypatch):
    module = tool("manifest")
    ticks = [0]

    def fail(*args, **kwargs):
        raise ValueError("DeploymentReadbackFailed")

    monkeypatch.setattr(module, "verify_live_manifest", fail)
    with pytest.raises(ValueError, match="DeploymentReadbackDeadlineExceeded"):
        module.wait_for_manifest(
            None,
            {},
            approved_inputs={},
            timeout=5,
            clock=lambda: ticks[0],
            sleep=lambda n: ticks.__setitem__(0, ticks[0] + n),
        )
    assert ticks == [5]
