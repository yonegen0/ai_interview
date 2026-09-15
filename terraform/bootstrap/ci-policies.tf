locals {
  state_arn     = aws_s3_bucket.storage["state"].arn
  artifact_arn  = aws_s3_bucket.storage["artifacts"].arn
  ci_prefix     = { plan = "ai-interview-dev", deploy = "ai-interview-dev", test = "ai-interview-test-*" }
  state_keys    = { plan = "dev/*", deploy = "dev/*", test = "runs/*" }
  read_actions  = ["dynamodb:DescribeTable", "dynamodb:DescribeContinuousBackups", "dynamodb:DescribeTimeToLive", "dynamodb:ListTagsOfResource", "sqs:GetQueueAttributes", "sqs:ListQueueTags", "lambda:GetFunction", "lambda:GetFunctionConfiguration", "lambda:GetFunctionConcurrency", "lambda:GetPolicy", "lambda:GetAlias", "lambda:ListVersionsByFunction", "lambda:ListAliases", "lambda:ListTags", "lambda:GetFunctionCodeSigningConfig", "scheduler:GetSchedule", "scheduler:GetScheduleGroup", "scheduler:ListTagsForResource", "logs:ListTagsForResource", "sns:GetTopicAttributes", "sns:ListTagsForResource", "sns:GetSubscriptionAttributes", "cognito-idp:DescribeUserPool", "cognito-idp:DescribeUserPoolClient", "cognito-idp:GetGroup", "cognito-idp:ListTagsForResource", "iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:GetPolicy", "iam:GetPolicyVersion", "ses:GetIdentityVerificationAttributes", "ses:GetIdentityDkimAttributes", "ses:GetIdentityMailFromDomainAttributes", "ses:GetIdentityNotificationAttributes"]
  write_actions = ["dynamodb:CreateTable", "dynamodb:UpdateTable", "dynamodb:DeleteTable", "dynamodb:UpdateContinuousBackups", "dynamodb:TagResource", "dynamodb:UntagResource", "sqs:CreateQueue", "sqs:DeleteQueue", "sqs:SetQueueAttributes", "sqs:TagQueue", "sqs:UntagQueue", "lambda:CreateFunction", "lambda:DeleteFunction", "lambda:UpdateFunctionCode", "lambda:UpdateFunctionConfiguration", "lambda:PutFunctionConcurrency", "lambda:DeleteFunctionConcurrency", "lambda:PublishVersion", "lambda:CreateAlias", "lambda:UpdateAlias", "lambda:DeleteAlias", "lambda:AddPermission", "lambda:RemovePermission", "lambda:TagResource", "lambda:UntagResource", "scheduler:CreateSchedule", "scheduler:UpdateSchedule", "scheduler:DeleteSchedule", "scheduler:CreateScheduleGroup", "scheduler:DeleteScheduleGroup", "scheduler:TagResource", "scheduler:UntagResource", "logs:CreateLogGroup", "logs:DeleteLogGroup", "logs:PutRetentionPolicy", "logs:DeleteRetentionPolicy", "logs:TagResource", "logs:UntagResource", "sns:CreateTopic", "sns:DeleteTopic", "sns:SetTopicAttributes", "sns:Subscribe", "sns:Unsubscribe", "sns:TagResource", "sns:UntagResource"]
  managed_arns = { for role, prefix in local.ci_prefix : role => [
    "arn:aws:dynamodb:${var.region}:${var.account_id}:table/${prefix}*",
    "arn:aws:sqs:${var.region}:${var.account_id}:${prefix}*",
    "arn:aws:lambda:${var.region}:${var.account_id}:function:${prefix}*",
    "arn:aws:scheduler:${var.region}:${var.account_id}:schedule-group/${prefix}",
    "arn:aws:scheduler:${var.region}:${var.account_id}:schedule/${prefix}/*",
    "arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/lambda/${prefix}*",
    "arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/apigateway/${prefix}*",
    "arn:aws:sns:${var.region}:${var.account_id}:${prefix}*"
  ] }
}
resource "aws_iam_role_policy" "state" {
  for_each = { for name, role in aws_iam_role.ci : name => role if name != "artifact" }
  role     = each.value.id
  name     = "state-and-artifacts"
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = [local.state_arn], Condition = { StringLike = { "s3:prefix" = [local.state_keys[each.key]] } } },
    { Effect = "Allow", Action = ["s3:GetBucketLocation"], Resource = [local.state_arn, local.artifact_arn] },
    { Effect = "Allow", Action = each.key == "plan" ? ["s3:GetObject"] : ["s3:GetObject", "s3:PutObject"], Resource = ["${local.state_arn}/${local.state_keys[each.key]}"] },
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], Resource = ["${local.state_arn}/${local.state_keys[each.key]}.tflock"] },
    { Effect = "Allow", Action = ["s3:GetObject", "s3:GetObjectVersion"], Resource = ["${local.artifact_arn}/lambda/*", "${local.artifact_arn}/plans/*"] }
  ] })
}
resource "aws_iam_role_policy" "read" {
  for_each = { for name, role in aws_iam_role.ci : name => role if name != "artifact" }
  role     = each.value.id
  name     = "read-project"
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = local.read_actions, Resource = concat(local.managed_arns[each.key], ["arn:aws:iam::${var.account_id}:role/${local.ci_prefix[each.key]}*-runtime", aws_iam_policy.runtime_boundary.arn]) },
    { Effect = "Allow", Action = ["sts:GetCallerIdentity", "logs:DescribeLogGroups", "cloudwatch:DescribeAlarms", "cloudwatch:ListTagsForResource", "lambda:ListEventSourceMappings", "lambda:GetEventSourceMapping", "sns:ListSubscriptionsByTopic", "ses:GetSendQuota", "ses:GetIdentityVerificationAttributes", "ses:GetIdentityDkimAttributes", "ses:GetIdentityMailFromDomainAttributes", "ses:GetIdentityNotificationAttributes", "lambda:GetAccountSettings"], Resource = ["*"] }
  ] })
}
resource "aws_iam_role_policy" "deploy" {
  for_each = { for name, role in aws_iam_role.ci : name => role if contains(["deploy", "test"], name) }
  role     = each.value.id
  name     = "deploy-project"
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = local.write_actions, Resource = local.managed_arns[each.key] },
    { Effect = "Allow", Action = ["iam:CreateRole", "iam:PutRolePermissionsBoundary"], Resource = ["arn:aws:iam::${var.account_id}:role/${local.ci_prefix[each.key]}*-runtime"], Condition = { ArnEquals = { "iam:PermissionsBoundary" = aws_iam_policy.runtime_boundary.arn } } },
    { Effect = "Allow", Action = ["iam:DeleteRole", "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:UpdateAssumeRolePolicy", "iam:TagRole", "iam:UntagRole"], Resource = ["arn:aws:iam::${var.account_id}:role/${local.ci_prefix[each.key]}*-runtime"] },
    { Effect = "Allow", Action = ["iam:PassRole"], Resource = ["arn:aws:iam::${var.account_id}:role/${local.ci_prefix[each.key]}*-runtime"], Condition = { StringEquals = { "iam:PassedToService" = ["lambda.amazonaws.com", "scheduler.amazonaws.com"] } } },
    { Effect = "Allow", Action = ["cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms", "cloudwatch:TagResource", "cloudwatch:UntagResource"], Resource = ["arn:aws:cloudwatch:${var.region}:${var.account_id}:alarm:${local.ci_prefix[each.key]}-*"] },
    { Effect = "Allow", Action = ["lambda:CreateEventSourceMapping", "lambda:UpdateEventSourceMapping", "lambda:DeleteEventSourceMapping"], Resource = ["*"], Condition = { ArnLike = { "lambda:FunctionArn" = "arn:aws:lambda:${var.region}:${var.account_id}:function:${local.ci_prefix[each.key]}-*" } } }
  ] })
}

resource "aws_iam_role_policy" "artifact" {
  role = aws_iam_role.ci["artifact"].id
  name = "versioned-artifact-only"
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:GetBucketLocation"], Resource = [local.artifact_arn] },
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = [local.artifact_arn], Condition = { StringLike = { "s3:prefix" = ["plans/*"] } } },
    { Effect = "Allow", Action = ["s3:PutObject", "s3:GetObject", "s3:GetObjectVersion"], Resource = ["${local.artifact_arn}/lambda/*", "${local.artifact_arn}/plans/*"] }
  ] })
}
resource "aws_iam_role_policy" "tests" {
  role = aws_iam_role.ci["test"].id
  name = "synthetic-tests"
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["dynamodb:CreateTable", "dynamodb:DeleteTable", "dynamodb:DescribeTable", "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:ConditionCheckItem", "dynamodb:Query"], Resource = ["arn:aws:dynamodb:${var.region}:${var.account_id}:table/interview-p3-test-*", "arn:aws:dynamodb:${var.region}:${var.account_id}:table/ai-interview-test-*"] },
    { Effect = "Allow", Action = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = ["arn:aws:sqs:${var.region}:${var.account_id}:ai-interview-test-*"] },
    { Effect = "Allow", Action = ["logs:FilterLogEvents", "logs:GetLogEvents", "logs:DescribeLogStreams"], Resource = ["arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/lambda/ai-interview-test-*"] },
    { Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = ["arn:aws:lambda:${var.region}:${var.account_id}:function:ai-interview-test-*"] }
  ] })
}
