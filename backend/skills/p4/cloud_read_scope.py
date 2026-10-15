"""Service/operation/resource-pair bound read scope; no SDK or credentials."""

from collections import defaultdict

from cloud_controller_core import ACCOUNT, MAIN, REGION, canonical, require


class Scope:
    def __init__(self, approval, journal):
        self.a, self.j = approval, journal
        self.count = 0
        self.identity_calls = 0
        self.run_id = None
        self.ids = defaultdict(set)
        self.pairs = defaultdict(set)
        self.policy_versions = defaultdict(set)
        self.state_bucket = f"ai-interview-state-{ACCOUNT}-{REGION}"
        self.artifact_bucket = f"ai-interview-artifacts-{ACCOUNT}-{REGION}"
        self.state_versions = {
            ("bootstrap/terraform.tfstate", approval.x["bootstrap_state_identity"]["version_id"]),
            ("dev/terraform.tfstate", approval.x["dev_state_identity"]["version_id"]),
        }
        self.artifact_versions = set()
        self.budget_notifications = defaultdict(set)

    def add(self, service, field, *values):
        self.ids[(service, field)].update(v for v in values if isinstance(v, str) and v)

    def bind(self, state):
        require(
            isinstance(state, dict) and isinstance(state.get("resources"), list),
            "VerifiedStateRequiredForScope",
        )
        for resource in state["resources"]:
            if resource.get("mode") != "managed":
                continue
            t = resource["type"]
            for instance in resource["instances"]:
                a = instance["attributes"]
                mappings = {
                    "aws_iam_role": ("iam", "RoleName", ("name",)),
                    "aws_iam_policy": ("iam", "PolicyArn", ("arn",)),
                    "aws_iam_openid_connect_provider": (
                        "iam",
                        "OpenIDConnectProviderArn",
                        ("arn",),
                    ),
                    "aws_lambda_function": ("lambda", "FunctionName", ("function_name", "arn")),
                    "aws_lambda_event_source_mapping": ("lambda", "UUID", ("uuid", "id")),
                    "aws_apigatewayv2_api": ("apigatewayv2", "ApiId", ("id",)),
                    "aws_dynamodb_table": ("dynamodb", "TableName", ("name",)),
                    "aws_sqs_queue": ("sqs", "QueueUrl", ("url", "id")),
                    "aws_sns_topic": ("sns", "TopicArn", ("arn",)),
                    "aws_sns_topic_subscription": ("sns", "SubscriptionArn", ("arn",)),
                    "aws_cognito_user_pool": ("cognito-idp", "UserPoolId", ("id",)),
                    "aws_scheduler_schedule_group": ("scheduler", "Name", ("name",)),
                    "aws_cloudwatch_log_group": ("logs", "logGroupNamePrefix", ("name",)),
                    "aws_budgets_budget": ("budgets", "BudgetName", ("name",)),
                    "aws_ses_email_identity": ("ses", "Identity", ("email",)),
                    "aws_ses_domain_identity": ("ses", "Identity", ("domain",)),
                }
                if t in mappings:
                    s, f, keys = mappings[t]
                    self.add(s, f, *(a.get(k) for k in keys))
                if t == "aws_lambda_event_source_mapping":
                    self.add("lambda", "EventSourceArn", a.get("event_source_arn"))
                if t == "aws_iam_role_policy":
                    self.pairs["iam-role-policy"].add((a["role"], a["name"]))
                    self.add("iam", "RoleName", a["role"])
                if t == "aws_iam_role_policy_attachment":
                    self.add("iam", "RoleName", a["role"])
                    self.add("iam", "PolicyArn", a["policy_arn"])
                if t == "aws_iam_role":
                    for b in (
                        a.get("permissions_boundary", [])
                        if isinstance(a.get("permissions_boundary"), list)
                        else [a.get("permissions_boundary")]
                    ):
                        self.add("iam", "PolicyArn", b)
                if t == "aws_lambda_alias":
                    self.add("lambda", "FunctionName", a["function_name"])
                    function = a["function_name"]
                    function_names = {function}
                    if function.startswith("arn:"):
                        function_names.add(function.split(":function:")[1])
                    else:
                        function_names.add(f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{function}")
                    self.add("lambda", "FunctionName", *function_names)
                    for name in function_names:
                        self.pairs["lambda-alias"].add((name, a["name"]))
                        self.pairs["lambda-qualifier"].add((name, a["function_version"]))
                if t == "aws_cognito_user_pool_client":
                    self.pairs["cognito-client"].add((a["user_pool_id"], a["id"]))
                    self.add("cognito-idp", "UserPoolId", a["user_pool_id"])
                if t == "aws_cognito_user_group":
                    self.pairs["cognito-group"].add((a["user_pool_id"], a["name"]))
                    self.add("cognito-idp", "UserPoolId", a["user_pool_id"])
                if t == "aws_apigatewayv2_stage":
                    self.pairs["api-stage"].add((a["api_id"], a["name"]))
                if t == "aws_scheduler_schedule":
                    self.pairs["scheduler-schedule"].add((a["group_name"], a["name"]))
        manifest = state.get("outputs", {}).get("manifest", {}).get("value")
        if manifest:
            artifact = manifest.get("artifact", {})
            if artifact:
                self.artifact_versions.add(
                    (artifact["bucket"], artifact["key"], artifact["version"])
                )

    def observe(self, service, operation, params, response):
        if service == "budgets" and operation == "describe_notifications_for_budget":
            for notification in response["Notifications"]:
                self.budget_notifications[params["BudgetName"]].add(canonical(notification))
        if service == "iam" and operation == "get_policy":
            policy = response["Policy"]
            require(policy["Arn"] == params["PolicyArn"], "PolicyReadbackScopeMismatch")
            self.policy_versions[policy["Arn"]].add(policy["DefaultVersionId"])
        if (
            service == "s3"
            and operation == "head_object"
            and self.run_id
            and params["Bucket"] == self.artifact_bucket
        ):
            key = params["Key"]
            version = response.get("VersionId")
            require(
                isinstance(version, str)
                and version not in {"", "null"}
                and response.get("ServerSideEncryption") == "AES256",
                "ArtifactHeadNotVersionedEncrypted",
            )
            self.artifact_versions.add((params["Bucket"], key, version))

    def check(self, service, operation, params):
        from cloud_aws_readonly import ALLOWED

        require(operation in ALLOWED.get(service, set()), "AwsOperationForbidden")
        cursor = {
            "Marker",
            "NextToken",
            "MaxItems",
            "MaxResults",
            "MaxRecords",
            "Limit",
            "PaginationConfig",
        }
        fields = {
            "s3": {
                "Bucket",
                "Key",
                "Prefix",
                "VersionId",
                "ExpectedBucketOwner",
                "MaxKeys",
                "KeyMarker",
                "VersionIdMarker",
                "ContinuationToken",
            },
            "iam": {"RoleName", "PolicyName", "PolicyArn", "VersionId", "OpenIDConnectProviderArn"},
            "lambda": {"FunctionName", "Name", "Qualifier", "UUID", "EventSourceArn"},
            "apigatewayv2": {"ApiId", "StageName"},
            "dynamodb": {"TableName", "ExclusiveStartTableName"},
            "sqs": {"QueueUrl", "QueueNamePrefix", "AttributeNames", "MaxResults", "NextToken"},
            "sns": {"TopicArn", "SubscriptionArn"},
            "cognito-idp": {"UserPoolId", "ClientId", "GroupName"},
            "scheduler": {"Name", "GroupName"},
            "logs": {"logGroupNamePrefix", "limit", "nextToken"},
            "cloudwatch": {"AlarmNamePrefix", "AlarmTypes"},
            "ses": {"Identities"},
            "budgets": {"AccountId", "BudgetName", "Notification"},
            "sts": set(),
        }
        require(set(params) <= fields[service] | cursor, "UnknownReadScopeParameter")
        if service == "s3":
            if operation == "get_object":
                require(
                    isinstance(params.get("VersionId"), str)
                    and params["VersionId"] not in {"", "null"},
                    "ExactS3VersionRequired",
                )
            if operation in {"list_objects_v2", "list_object_versions"}:
                require("Prefix" in params, "S3NamespacePrefixRequired")
            bucket = params.get("Bucket")
            require(params.get("ExpectedBucketOwner") == ACCOUNT, "S3OwnerMismatch")
            require(bucket in {self.state_bucket, self.artifact_bucket}, "S3BucketMismatch")
            statekeys = {"bootstrap/terraform.tfstate", "dev/terraform.tfstate"}
            runkeys = (
                (
                    {
                        f"plans/{self.run_id}/1/{n}"
                        for n in (
                            "dev.tfplan",
                            "plan.json",
                            "summary.json",
                            "review.private.json",
                            "envelope.json",
                        )
                    }
                    | {f"lambda/{MAIN}/{self.run_id}/1/app.zip"}
                )
                if self.run_id
                else set()
            )
            if "Key" in params:
                key = params["Key"]
                if bucket == self.state_bucket:
                    require(
                        key in statekeys | {k + ".tflock" for k in statekeys}, "StateKeyMismatch"
                    )
                    if "VersionId" in params:
                        require(
                            (key, params["VersionId"]) in self.state_versions,
                            "StateVersionOutsideApproval",
                        )
                else:
                    known = {(k, v) for b, k, v in self.artifact_versions if b == bucket}
                    require(key in {k for k, v in known} | runkeys, "ArtifactKeyMismatch")
                    if "VersionId" in params:
                        require(
                            (key, params["VersionId"]) in known, "ArtifactVersionOutsideBinding"
                        )
            if "Prefix" in params:
                allowed = (
                    statekeys | {k + ".tflock" for k in statekeys}
                    if bucket == self.state_bucket
                    else (
                        {f"plans/{self.run_id}/1/", f"lambda/{MAIN}/{self.run_id}/1/"}
                        if self.run_id
                        else set()
                    )
                )
                require(params["Prefix"] in allowed, "S3PrefixMismatch")
            if "VersionId" in params:
                require(
                    isinstance(params["VersionId"], str)
                    and params["VersionId"] not in {"", "null"},
                    "ExactS3VersionRequired",
                )
        else:
            required_namespace = {
                ("logs", "describe_log_groups"): "logGroupNamePrefix",
                ("cloudwatch", "describe_alarms"): "AlarmNamePrefix",
                ("sqs", "list_queues"): "QueueNamePrefix",
                ("scheduler", "list_schedules"): "GroupName",
            }
            if (service, operation) in required_namespace:
                require(
                    required_namespace[(service, operation)] in params, "ExplicitNamespaceRequired"
                )
            if "EventSourceArn" in params:
                require(
                    params["EventSourceArn"] in self.ids[("lambda", "EventSourceArn")],
                    "EventSourceOutsideBoundState",
                )
            if "AlarmTypes" in params:
                require(
                    isinstance(params["AlarmTypes"], list)
                    and len(params["AlarmTypes"]) == len(set(params["AlarmTypes"]))
                    and set(params["AlarmTypes"]) == {"MetricAlarm", "CompositeAlarm", "LogAlarm"},
                    "AllAlarmTypesRequired",
                )
            targetfields = {
                "RoleName",
                "PolicyArn",
                "OpenIDConnectProviderArn",
                "FunctionName",
                "UUID",
                "ApiId",
                "TableName",
                "QueueUrl",
                "TopicArn",
                "SubscriptionArn",
                "UserPoolId",
                "BudgetName",
            }
            for field in targetfields & set(params):
                require(params[field] in self.ids[(service, field)], "AwsResourceOutsideBoundState")
            if service == "iam" and "PolicyName" in params:
                require(
                    (params.get("RoleName"), params["PolicyName"]) in self.pairs["iam-role-policy"],
                    "InlinePolicyPairMismatch",
                )
            if service == "iam" and "VersionId" in params:
                require(
                    params["VersionId"] in self.policy_versions[params.get("PolicyArn")],
                    "IAMPolicyVersionNotReadBound",
                )
            if service == "lambda" and "Name" in params:
                require(
                    (params.get("FunctionName"), params["Name"]) in self.pairs["lambda-alias"],
                    "LambdaAliasPairMismatch",
                )
            if service == "lambda" and "Qualifier" in params:
                require(
                    (params.get("FunctionName"), params["Qualifier"])
                    in self.pairs["lambda-alias"] | self.pairs["lambda-qualifier"],
                    "LambdaVersionPairMismatch",
                )
            if service == "cognito-idp" and "ClientId" in params:
                require(
                    (params.get("UserPoolId"), params["ClientId"]) in self.pairs["cognito-client"],
                    "CognitoClientPairMismatch",
                )
            if service == "cognito-idp" and "GroupName" in params:
                require(
                    (params.get("UserPoolId"), params["GroupName"]) in self.pairs["cognito-group"],
                    "CognitoGroupPairMismatch",
                )
            if service == "apigatewayv2" and "StageName" in params:
                require(
                    (params.get("ApiId"), params["StageName"]) in self.pairs["api-stage"],
                    "ApiStagePairMismatch",
                )
            if service == "scheduler":
                if operation == "get_schedule":
                    require(
                        (params.get("GroupName"), params.get("Name"))
                        in self.pairs["scheduler-schedule"],
                        "SchedulePairMismatch",
                    )
                elif "Name" in params:
                    require(
                        params["Name"] in self.ids[("scheduler", "Name")], "ScheduleGroupMismatch"
                    )
                elif "GroupName" in params:
                    require(params["GroupName"] == "ai-interview-dev", "ScheduleNamespaceMismatch")
            if "AccountId" in params:
                require(params["AccountId"] == ACCOUNT, "AwsAccountMismatch")
            if service == "budgets":
                require(
                    params.get("AccountId") == ACCOUNT
                    and params.get("BudgetName") in self.ids[("budgets", "BudgetName")],
                    "BudgetScopeMismatch",
                )
                if "Notification" in params:
                    require(
                        canonical(params["Notification"])
                        in self.budget_notifications[params["BudgetName"]],
                        "BudgetNotificationNotBound",
                    )
            if "Identities" in params:
                require(
                    isinstance(params["Identities"], list)
                    and params["Identities"]
                    and all(v in self.ids[("ses", "Identity")] for v in params["Identities"]),
                    "SesIdentityOutsideState",
                )
            for field in ("AlarmNamePrefix", "QueueNamePrefix"):
                if field in params:
                    require(params[field] == "ai-interview-dev-", "NamespacePrefixMismatch")
            if "logGroupNamePrefix" in params:
                require(
                    params["logGroupNamePrefix"] == "/aws/lambda/ai-interview-dev-"
                    or params["logGroupNamePrefix"] in self.ids[("logs", "logGroupNamePrefix")],
                    "LogGroupScopeMismatch",
                )
        self.j.admit(25)
        require(self.count < 1500, "OperatorReadRequestLimitExceeded")
        if service == "sts":
            require(self.identity_calls < 2, "OperatorCallerIdentityLimitExceeded")
            self.identity_calls += 1
        self.count += 1
        self.j.record(
            "operator-read-request-started",
            service=service,
            operation=operation,
            count=self.count,
            arguments_sha256=canonical(params),
        )
