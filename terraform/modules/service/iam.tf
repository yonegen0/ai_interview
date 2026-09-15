locals {
  base_statements = { for role in keys(local.function_arns) : role => [
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = ["${aws_cloudwatch_log_group.lambda[role].arn}:*"] },
    { Effect = "Allow", Action = ["dynamodb:GetItem"], Resource = [local.table_arn] },
    { Effect = "Allow", Action = role == "api" ? ["dynamodb:PutItem"] : ["dynamodb:PutItem", "dynamodb:ConditionCheckItem"], Resource = [local.table_arn], Condition = { StringEquals = { "dynamodb:EnclosingOperation" = "TransactWriteItems" } } }
  ] }
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
  policy   = jsonencode({ Version = "2012-10-17", Statement = concat(local.base_statements[each.key], [for s in local.worker_statements : s if each.key == "worker"], [for s in local.dispatcher_statements : s if each.key == "dispatcher"]) })
}
