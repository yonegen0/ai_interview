resource "aws_cloudwatch_log_group" "lambda" {
  for_each          = local.function_arns
  name              = "/aws/lambda/${local.prefix}-${each.key}"
  retention_in_days = 30
  tags              = local.tags
}
resource "aws_iam_role" "lambda" {
  for_each             = local.function_arns
  name                 = "${local.prefix}-${each.key}-runtime"
  permissions_boundary = var.boundary_arn
  assume_role_policy   = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "lambda.amazonaws.com" } }] })
  tags                 = local.tags
}
locals {
  common_env = {
    INTERVIEW_ACCOUNT_ID = var.account_id
    INTERVIEW_REGION     = var.region
    INTERVIEW_TABLE_NAME = aws_dynamodb_table.main.name
  }
  role_env = {
    api = {
      INTERVIEW_CLIENT_ID    = aws_cognito_user_pool_client.web.id
      INTERVIEW_USER_POOL_ID = aws_cognito_user_pool.main.id
      INTERVIEW_API_ID       = aws_apigatewayv2_api.main.id
      INTERVIEW_STAGE        = "dev"
    }
    worker = { INTERVIEW_QUEUE_ARN = aws_sqs_queue.main.arn }
    dispatcher = {
      INTERVIEW_QUEUE_ARN    = aws_sqs_queue.main.arn
      INTERVIEW_QUEUE_URL    = aws_sqs_queue.main.url
      INTERVIEW_STREAM_ARN   = aws_dynamodb_table.main.stream_arn
      INTERVIEW_SCHEDULE_ARN = local.schedule_arn
    }
  }
  aliases = { api = { role = "api", alias = "live" }, worker = { role = "worker", alias = "live" }, streams = { role = "dispatcher", alias = "streams" }, recovery = { role = "dispatcher", alias = "recovery" } }
}
resource "aws_lambda_function" "main" {
  for_each                       = local.function_arns
  function_name                  = "${local.prefix}-${each.key}"
  role                           = aws_iam_role.lambda[each.key].arn
  runtime                        = "python3.14"
  architectures                  = ["x86_64"]
  handler                        = "interview_backend.aws_runtime.${each.key}_handler"
  memory_size                    = 512
  timeout                        = each.key == "worker" ? 60 : each.key == "dispatcher" ? 30 : 15
  reserved_concurrent_executions = each.key == "worker" ? 2 : -1
  s3_bucket                      = var.artifact_bucket
  s3_key                         = var.artifact_key
  s3_object_version              = var.artifact_version
  source_code_hash               = var.artifact_sha256_base64
  publish                        = true
  environment {
    variables = merge(local.common_env, local.role_env[each.key], { INTERVIEW_COMPONENT = each.key, INTERVIEW_FUNCTION_NAME = "${local.prefix}-${each.key}" })
  }
  depends_on = [aws_cloudwatch_log_group.lambda, aws_iam_role_policy.runtime]
  tags       = local.tags
}
resource "aws_lambda_alias" "entry" {
  for_each         = local.aliases
  name             = each.value.alias
  function_name    = aws_lambda_function.main[each.value.role].function_name
  function_version = aws_lambda_function.main[each.value.role].version
}
resource "aws_lambda_event_source_mapping" "worker" {
  event_source_arn                   = aws_sqs_queue.main.arn
  function_name                      = aws_lambda_alias.entry["worker"].arn
  enabled                            = var.worker_enabled
  batch_size                         = 1
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
  scaling_config { maximum_concurrency = 2 }
}
resource "aws_lambda_event_source_mapping" "streams" {
  event_source_arn                   = aws_dynamodb_table.main.stream_arn
  function_name                      = aws_lambda_alias.entry["streams"].arn
  enabled                            = var.streams_enabled
  starting_position                  = "TRIM_HORIZON"
  batch_size                         = 100
  maximum_batching_window_in_seconds = 0
  maximum_retry_attempts             = 3
  maximum_record_age_in_seconds      = 3600
  bisect_batch_on_function_error     = true
  function_response_types            = ["ReportBatchItemFailures"]
  filter_criteria {
    filter { pattern = jsonencode({ dynamodb = { NewImage = { kind = { S = ["Dispatch"] } } } }) }
  }
  destination_config {
    on_failure { destination_arn = aws_sqs_queue.stream_failure.arn }
  }
}
resource "aws_scheduler_schedule_group" "recovery" {
  name = local.prefix
  tags = local.tags
}
resource "aws_iam_role" "scheduler" {
  name                 = "${local.prefix}-scheduler-runtime"
  permissions_boundary = var.boundary_arn
  assume_role_policy   = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "scheduler.amazonaws.com" }, Condition = { StringEquals = { "aws:SourceAccount" = var.account_id }, ArnEquals = { "aws:SourceArn" = aws_scheduler_schedule_group.recovery.arn } } }] })
  tags                 = local.tags
}
resource "aws_iam_role_policy" "scheduler" {
  role   = aws_iam_role.scheduler.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = ["${local.function_arns.dispatcher}:recovery"] }] })
}
resource "aws_scheduler_schedule" "recovery" {
  name                = "recovery"
  group_name          = aws_scheduler_schedule_group.recovery.name
  schedule_expression = "rate(1 minute)"
  state               = var.scheduler_enabled ? "ENABLED" : "DISABLED"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_lambda_alias.entry["recovery"].arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ eventVersion = 1, type = "RecoveryTick" })
    retry_policy {
      maximum_retry_attempts       = 3
      maximum_event_age_in_seconds = 60
    }
  }
  depends_on = [aws_iam_role_policy.scheduler]
}
