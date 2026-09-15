"""Deployment readback against fixed service contracts and approved configuration."""

import json


def expect(actual, expected):
    """Mandatory fields; do not silently default missing AWS response attributes."""
    for key, value in expected.items():
        if key not in actual or actual[key] != value:
            raise ValueError("DeploymentAttributeMismatch")


def pages(call, field, *, token="NextToken", **kwargs):
    result, seen = [], set()
    while True:
        response = call(**kwargs)
        result.extend(response[field])
        cursor = response.get(token)
        if not cursor:
            return result
        if not isinstance(cursor, str) or cursor in seen:
            raise ValueError("InvalidPagination")
        seen.add(cursor)
        kwargs[token] = cursor


def key_schema(value):
    return sorted(value, key=lambda item: item["KeyType"])


def verify_configuration(session, manifest, config):
    m, c = manifest, manifest["configuration"]
    account, region = m["account_id"], m["region"]
    prefix = "ai-interview-dev" if not m["run_id"] else "ai-interview-test-" + m["run_id"]

    def client(name):
        return session.client(name, region_name=region, config=config)

    db = client("dynamodb")
    table = db.describe_table(TableName=m["table_name"])["Table"]
    expect(table, {"TableStatus": "ACTIVE"})
    if sorted(table["AttributeDefinitions"], key=lambda v: v["AttributeName"]) != [
        {"AttributeName": name, "AttributeType": "S"} for name in ("PK", "SK", "work_pk", "work_sk")
    ]:
        raise ValueError("TableAttributesMismatch")
    expect(table["BillingModeSummary"], {"BillingMode": "PAY_PER_REQUEST"})
    if key_schema(table["KeySchema"]) != key_schema(
        [{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}]
    ):
        raise ValueError("TableKeyMismatch")
    index = table["GlobalSecondaryIndexes"][0]
    expect(index, {"IndexStatus": "ACTIVE", "Projection": {"ProjectionType": "KEYS_ONLY"}})
    if key_schema(index["KeySchema"]) != key_schema(
        [
            {"AttributeName": "work_pk", "KeyType": "HASH"},
            {"AttributeName": "work_sk", "KeyType": "RANGE"},
        ]
    ):
        raise ValueError("IndexKeyMismatch")
    expect(
        db.describe_time_to_live(TableName=m["table_name"])["TimeToLiveDescription"],
        {"TimeToLiveStatus": "DISABLED"},
    )

    sqs = client("sqs")
    queue_arns = {}
    for key, suffix, retention, visibility in (
        ("queue_url", "main", "345600", "360"),
        ("worker_dlq_url", "worker-dlq", "1209600", "30"),
        ("stream_failure_url", "stream-failure", "1209600", "30"),
    ):
        attrs = sqs.get_queue_attributes(QueueUrl=m[key], AttributeNames=["All"])["Attributes"]
        arn = f"arn:aws:sqs:{region}:{account}:{prefix}-{suffix}"
        queue_arns[key] = arn
        expect(
            attrs,
            {
                "QueueArn": arn,
                "MessageRetentionPeriod": retention,
                "VisibilityTimeout": visibility,
                "SqsManagedSseEnabled": "true",
            },
        )
        if attrs.get("FifoQueue", "false") != "false" or attrs.get("KmsMasterKeyId"):
            raise ValueError("QueueTypeMismatch")
        if key == "queue_url":
            if json.loads(attrs["RedrivePolicy"]) != {
                "deadLetterTargetArn": f"arn:aws:sqs:{region}:{account}:{prefix}-worker-dlq",
                "maxReceiveCount": 5,
            }:
                raise ValueError("RedriveMismatch")
        elif attrs.get("RedrivePolicy"):
            raise ValueError("UnexpectedRedrive")
        if key == "worker_dlq_url" and json.loads(attrs["RedriveAllowPolicy"]) != {
            "redrivePermission": "byQueue",
            "sourceQueueArns": [m["queue_arn"]],
        }:
            raise ValueError("RedriveAllowMismatch")

    lambdas = client("lambda")
    common = {
        "INTERVIEW_ACCOUNT_ID": account,
        "INTERVIEW_REGION": region,
        "INTERVIEW_TABLE_NAME": m["table_name"],
    }
    role_env = {
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
    }
    iam = client("iam")
    for role in ("api", "worker", "dispatcher"):
        name = f"{prefix}-{role}"
        deployed = lambdas.get_function_configuration(
            FunctionName=name, Qualifier=str(m["versions"][role])
        )
        expect(
            deployed,
            {
                "Handler": f"interview_backend.aws_runtime.{role}_handler",
                "Role": f"arn:aws:iam::{account}:role/{name}-runtime",
                "State": "Active",
            },
        )
        expect(
            deployed["Environment"],
            {
                "Variables": common
                | role_env[role]
                | {"INTERVIEW_COMPONENT": role, "INTERVIEW_FUNCTION_NAME": name}
            },
        )
        concurrency = lambdas.get_function_concurrency(FunctionName=name)
        # AWS omits ReservedConcurrentExecutions when no reservation exists.
        if concurrency.get("ReservedConcurrentExecutions", -1) != (2 if role == "worker" else -1):
            raise ValueError("ConcurrencyMismatch")
        observed_role = iam.get_role(RoleName=name + "-runtime")["Role"]
        expect(
            observed_role["PermissionsBoundary"],
            {"PermissionsBoundaryArn": c["boundary_arn"], "PermissionsBoundaryType": "Policy"},
        )
    for name in ("worker", "streams"):
        mapping = lambdas.get_event_source_mapping(UUID=m["mappings"][name])
        expect(
            mapping,
            {
                "UUID": m["mappings"][name],
                "EventSourceArn": m["queue_arn"] if name == "worker" else m["stream_arn"],
                "FunctionArn": m["aliases"][name],
                "State": "Enabled" if c[name + "_enabled"] else "Disabled",
                "BatchSize": 1 if name == "worker" else 100,
                "MaximumBatchingWindowInSeconds": 0,
                "FunctionResponseTypes": ["ReportBatchItemFailures"],
            },
        )
        if name == "worker":
            expect(mapping["ScalingConfig"], {"MaximumConcurrency": 2})
        else:
            expect(
                mapping,
                {
                    "MaximumRetryAttempts": 3,
                    "MaximumRecordAgeInSeconds": 3600,
                    "BisectBatchOnFunctionError": True,
                    "ParallelizationFactor": 1,
                    "DestinationConfig": {
                        "OnFailure": {"Destination": queue_arns["stream_failure_url"]}
                    },
                },
            )
            filters = mapping["FilterCriteria"]["Filters"]
            if len(filters) != 1 or json.loads(filters[0]["Pattern"]) != {
                "dynamodb": {"NewImage": {"kind": {"S": ["Dispatch"]}}}
            }:
                raise ValueError("StreamFilterMismatch")

    scheduler = client("scheduler")
    schedule = scheduler.get_schedule(Name="recovery", GroupName=prefix)
    expect(
        schedule,
        {
            "Arn": m["schedule_arn"],
            "Name": "recovery",
            "GroupName": prefix,
            "ScheduleExpression": "rate(1 minute)",
            "State": "ENABLED" if c["scheduler_enabled"] else "DISABLED",
            "FlexibleTimeWindow": {"Mode": "OFF"},
        },
    )
    expect(
        schedule["Target"],
        {
            "Arn": m["aliases"]["recovery"],
            "RoleArn": f"arn:aws:iam::{account}:role/{prefix}-scheduler-runtime",
            "RetryPolicy": {"MaximumRetryAttempts": 3, "MaximumEventAgeInSeconds": 60},
        },
    )
    if json.loads(schedule["Target"]["Input"]) != {"eventVersion": 1, "type": "RecoveryTick"}:
        raise ValueError("ScheduleInputMismatch")
    expect(scheduler.get_schedule_group(Name=prefix), {"Name": prefix, "State": "ACTIVE"})
    verify_api(client("apigatewayv2"), m, prefix)
    verify_cognito(client("cognito-idp"), m)
    logs = client("logs")
    for name in [f"/aws/lambda/{prefix}-{role}" for role in ("api", "worker", "dispatcher")] + [
        f"/aws/apigateway/{prefix}"
    ]:
        found = [
            g
            for g in pages(
                logs.describe_log_groups, "logGroups", token="nextToken", logGroupNamePrefix=name
            )
            if g["logGroupName"] == name
        ]
        if len(found) != 1:
            raise ValueError("LogGroupMissing")
        expect(found[0], {"retentionInDays": 30})
    verify_notifications(client, m, prefix)
    from manifest_alarms import verify_alarms

    verify_alarms(client("cloudwatch"), m, prefix)


def verify_api(api, m, prefix):
    c = m["configuration"]
    observed = api.get_api(ApiId=m["api_id"])
    expect(observed, {"ProtocolType": "HTTP", "DisableExecuteApiEndpoint": not c["api_enabled"]})
    cors = observed["CorsConfiguration"]
    for key, values in {
        "AllowOrigins": c["cors_origins"],
        "AllowMethods": ["GET", "POST", "OPTIONS"],
        "AllowHeaders": ["authorization", "content-type", "idempotency-key"],
        "ExposeHeaders": ["allow"],
    }.items():
        if sorted(
            v.lower() if key in {"AllowHeaders", "ExposeHeaders"} else v for v in cors[key]
        ) != sorted(values):
            raise ValueError("CorsMismatch")
    expect(cors, {"AllowCredentials": False, "MaxAge": 300})
    stage = api.get_stage(ApiId=m["api_id"], StageName="dev")
    expect(stage, {"StageName": "dev", "AutoDeploy": True})
    expect(stage["DefaultRouteSettings"], {"ThrottlingBurstLimit": 10, "ThrottlingRateLimit": 5.0})
    expected_log = (
        f"arn:aws:logs:{m['region']}:{m['account_id']}:log-group:/aws/apigateway/{prefix}"
    )
    expect(stage["AccessLogSettings"], {"DestinationArn": expected_log})
    if json.loads(stage["AccessLogSettings"]["Format"]) != {
        "requestId": "$context.requestId",
        "routeKey": "$context.routeKey",
        "status": "$context.status",
        "responseLength": "$context.responseLength",
    }:
        raise ValueError("AccessLogFormatMismatch")
    authorizers = pages(api.get_authorizers, "Items", ApiId=m["api_id"])
    integrations = pages(api.get_integrations, "Items", ApiId=m["api_id"])
    if len(authorizers) != 1 or len(integrations) != 1:
        raise ValueError("ApiComponentsMismatch")
    auth, integration = authorizers[0], integrations[0]
    expect(
        auth,
        {
            "AuthorizerType": "JWT",
            "IdentitySource": ["$request.header.Authorization"],
            "JwtConfiguration": {
                "Audience": [m["client_id"]],
                "Issuer": f"https://cognito-idp.{m['region']}.amazonaws.com/{m['user_pool_id']}",
            },
        },
    )
    expect(
        integration,
        {
            "IntegrationType": "AWS_PROXY",
            "PayloadFormatVersion": "2.0",
            "TimeoutInMillis": 15000,
            "IntegrationUri": (
                f"arn:aws:apigateway:{m['region']}:lambda:path/2015-03-31/"
                f"functions/{m['aliases']['api']}/invocations"
            ),
        },
    )
    routes = pages(api.get_routes, "Items", ApiId=m["api_id"])
    business = {
        "POST /sessions",
        "GET /sessions/{sessionId}/question",
        "POST /sessions/{sessionId}/answers",
        "GET /evaluations/{evaluationId}",
        "GET /attempts/{attemptId}/feedback",
        "POST /sessions/{sessionId}/questions/next",
        "$default",
    }
    if len(routes) != 9 or {r["RouteKey"] for r in routes} != business | {
        "OPTIONS /{proxy+}",
        "OPTIONS /",
    }:
        raise ValueError("ApiRoutesMismatch")
    for route in routes:
        expect(
            route,
            {
                "Target": "integrations/" + integration["IntegrationId"],
                "AuthorizationType": "JWT" if route["RouteKey"] in business else "NONE",
            },
        )
        if route["RouteKey"] in business:
            expect(route, {"AuthorizerId": auth["AuthorizerId"]})


def verify_cognito(cognito, m):
    c = m["configuration"]
    pool = cognito.describe_user_pool(UserPoolId=m["user_pool_id"])["UserPool"]
    expect(
        pool,
        {
            "UserPoolTier": "ESSENTIALS",
            "UsernameAttributes": ["email"],
            "AutoVerifiedAttributes": ["email"],
            "MfaConfiguration": "OFF",
        },
    )
    expect(pool["AdminCreateUserConfig"], {"AllowAdminCreateUserOnly": True})
    expect(pool["Policies"]["SignInPolicy"], {"AllowedFirstAuthFactors": ["EMAIL_OTP"]})
    expect(
        pool["EmailConfiguration"],
        {
            "EmailSendingAccount": "DEVELOPER",
            "SourceArn": c["ses_identity_arn"],
            "From": c["ses_email"],
        },
    )
    observed = cognito.describe_user_pool_client(
        UserPoolId=m["user_pool_id"], ClientId=m["client_id"]
    )["UserPoolClient"]
    expect(
        observed,
        {
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
        },
    )
    if set(observed["ExplicitAuthFlows"]) != {
        "ALLOW_USER_AUTH",
        "ALLOW_REFRESH_TOKEN_AUTH",
    } or observed.get("ClientSecret"):
        raise ValueError("ClientAuthenticationMismatch")
    for name in ("USER", "ADMIN"):
        expect(
            cognito.get_group(UserPoolId=m["user_pool_id"], GroupName=name)["Group"],
            {"GroupName": name, "UserPoolId": m["user_pool_id"]},
        )


def verify_notifications(client, m, prefix):
    from decimal import Decimal

    sns = client("sns")
    topic = f"arn:aws:sns:{m['region']}:{m['account_id']}:{prefix}-alarms"
    if m["alarm_topic_arn"] != topic:
        raise ValueError("AlarmTopicMismatch")
    attributes = sns.get_topic_attributes(TopicArn=topic)["Attributes"]
    expect(attributes, {"TopicArn": topic, "Owner": m["account_id"]})
    from bootstrap_contract import canonical_policy

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "cloudwatch.amazonaws.com"},
                "Action": "sns:Publish",
                "Resource": topic,
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": m["account_id"]},
                    "ArnLike": {
                        "aws:SourceArn": (
                            f"arn:aws:cloudwatch:{m['region']}:{m['account_id']}:alarm:{prefix}-*"
                        )
                    },
                },
            }
        ],
    }
    if canonical_policy(attributes["Policy"]) != canonical_policy(policy):
        raise ValueError("TopicPolicyMismatch")
    subscriptions = pages(sns.list_subscriptions_by_topic, "Subscriptions", TopicArn=topic)
    matching = [
        s
        for s in subscriptions
        if s["Protocol"] == "email" and s["Endpoint"] == m["configuration"]["alarm_email"]
    ]
    if len(matching) != 1 or len(subscriptions) != 1:
        raise ValueError("AlarmSubscriptionMissing")
    # PendingConfirmation is an external prerequisite, never a delivery receipt.
    if not m["run_id"]:
        budgets = client("budgets")
        args = {"AccountId": m["account_id"], "BudgetName": prefix + "-monthly"}
        budget = budgets.describe_budget(**args)["Budget"]
        expect(
            budget, {"BudgetName": args["BudgetName"], "BudgetType": "COST", "TimeUnit": "MONTHLY"}
        )
        if (
            Decimal(budget["BudgetLimit"]["Amount"])
            != Decimal(m["configuration"]["monthly_budget_usd"])
            or budget["BudgetLimit"]["Unit"] != "USD"
            or budget.get("CostFilters")
        ):
            raise ValueError("BudgetMismatch")
        notifications = pages(budgets.describe_notifications_for_budget, "Notifications", **args)
        if len(notifications) != 3 or {n["Threshold"] for n in notifications} != {50, 80, 100}:
            raise ValueError("BudgetNotificationMismatch")
        for notification in notifications:
            expect(
                notification,
                {
                    "ComparisonOperator": "GREATER_THAN",
                    "ThresholdType": "PERCENTAGE",
                    "NotificationType": "ACTUAL",
                },
            )
            subscribers = pages(
                budgets.describe_subscribers_for_notification,
                "Subscribers",
                Notification=notification,
                **args,
            )
            if subscribers != [
                {"SubscriptionType": "EMAIL", "Address": m["configuration"]["alarm_email"]}
            ]:
                raise ValueError("BudgetSubscriberMismatch")
