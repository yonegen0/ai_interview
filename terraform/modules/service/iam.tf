locals {
  bank_keys = { "ForAllValues:StringEquals" = { "dynamodb:LeadingKeys" = ["SYSTEM#QUESTION_BANK"] }, Null = { "dynamodb:LeadingKeys" = "false" } }
  user_keys = { "ForAllValues:StringLike" = { "dynamodb:LeadingKeys" = ["USER#*"] }, Null = { "dynamodb:LeadingKeys" = "false" } }
  user_key_attributes = merge(local.user_keys, {
    "ForAllValues:StringEquals" = { "dynamodb:Attributes" = ["PK", "SK"] }
    Null                        = { "dynamodb:LeadingKeys" = "false", "dynamodb:Attributes" = "false" }
  })
  admin_statements = [
    { Effect = "Allow", Action = ["dynamodb:GetItem"], Resource = [local.table_arn], Condition = local.bank_keys },
    { Effect = "Allow", Action = ["dynamodb:PutItem", "dynamodb:ConditionCheckItem"], Resource = [local.table_arn], Condition = merge(local.bank_keys, { StringEquals = { "dynamodb:EnclosingOperation" = "TransactWriteItems" } }) },
    # Only PK/SK presence is needed to share the existing user's idempotency namespace.
    { Effect = "Allow", Action = ["dynamodb:GetItem"], Resource = [local.table_arn], Condition = merge(local.user_key_attributes, { StringEqualsIfExists = { "dynamodb:Select" = "SPECIFIC_ATTRIBUTES" } }) },
    { Effect = "Allow", Action = ["dynamodb:ConditionCheckItem"], Resource = [local.table_arn], Condition = merge(local.user_key_attributes, { StringEquals = { "dynamodb:EnclosingOperation" = "TransactWriteItems" }, StringEqualsIfExists = { "dynamodb:ReturnValues" = "NONE" } }) }
  ]
  base_statements = { for role in keys(local.function_arns) : role => concat([
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = ["${aws_cloudwatch_log_group.lambda[role].arn}:*"] }
    ], [for s in local.admin_statements : s if role == "admin"], [for s in [
      { Effect = "Allow", Action = ["dynamodb:GetItem"], Resource = [local.table_arn] },
      { Effect = "Allow", Action = role == "api" ? ["dynamodb:PutItem"] : ["dynamodb:PutItem", "dynamodb:ConditionCheckItem"], Resource = [local.table_arn], Condition = merge({ StringEquals = { "dynamodb:EnclosingOperation" = "TransactWriteItems" } }, { for k, v in local.user_keys : k => v if role == "api" }) }
      ] : s if role != "admin"], [for s in [
      { Effect = "Allow", Action = ["dynamodb:ConditionCheckItem"], Resource = [local.table_arn], Condition = merge(local.bank_keys, { StringEquals = { "dynamodb:EnclosingOperation" = "TransactWriteItems" } }) }
  ] : s if role == "api"]) }
  worker_statements = [{ Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = [aws_sqs_queue.main.arn] }]
  dispatcher_statements = [
    { Effect = "Allow", Action = ["dynamodb:Query"], Resource = ["${local.table_arn}/index/WorkIndex"] },
    { Effect = "Allow", Action = ["dynamodb:DescribeStream", "dynamodb:GetRecords", "dynamodb:GetShardIterator"], Resource = [aws_dynamodb_table.main.stream_arn] },
    { Effect = "Allow", Action = ["dynamodb:ListStreams"], Resource = ["*"] },
    { Effect = "Allow", Action = ["sqs:SendMessage"], Resource = [aws_sqs_queue.main.arn, aws_sqs_queue.stream_failure.arn] },
    { Effect = "Allow", Action = ["dynamodb:PutItem"], Resource = [local.table_arn], Condition = { "ForAllValues:StringEquals" = { "dynamodb:LeadingKeys" = ["SYSTEM#RECOVERY"] }, Null = { "dynamodb:EnclosingOperation" = "true", "dynamodb:LeadingKeys" = "false" } } }
  ]
}
resource "aws_iam_role_policy" "runtime" {
  for_each = local.function_arns
  name     = "business"
  role     = aws_iam_role.lambda[each.key].id
  policy   = jsonencode({ Version = "2012-10-17", Statement = concat(local.base_statements[each.key], [for s in local.worker_statements : s if each.key == "worker"], [for s in local.worker_wif_statements : s if each.key == "worker"], [for s in local.dispatcher_statements : s if each.key == "dispatcher"]) })
}
