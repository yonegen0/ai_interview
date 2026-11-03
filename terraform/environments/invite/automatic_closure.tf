# Dedicated close-only principal. No business data, secret, IAM write or enable path.
locals {
  closure_target = merge(module.service.closure_target, {
    distribution_id = module.frontend.distribution_id
    expires_at      = local.release_end_epoch
  })
  closure_arn = "arn:aws:lambda:${local.region}:${var.account_id}:function:${local.prefix}-close"
  closure_policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["apigateway:GET", "apigateway:PATCH"], Resource = ["arn:aws:apigateway:${local.region}::/apis/${module.service.closure_target.api_id}"] },
    { Effect = "Allow", Action = ["lambda:GetEventSourceMapping", "lambda:UpdateEventSourceMapping"], Resource = [for id in module.service.closure_target.mappings : "arn:aws:lambda:${local.region}:${var.account_id}:event-source-mapping:${id}"] },
    { Effect = "Allow", Action = ["scheduler:GetSchedule", "scheduler:UpdateSchedule"], Resource = ["arn:aws:scheduler:${local.region}:${var.account_id}:schedule/${local.prefix}/recovery"] },
    { Effect = "Allow", Action = ["iam:PassRole"], Resource = [module.service.closure_target.scheduler_role_arn], Condition = { StringEquals = { "iam:PassedToService" = "scheduler.amazonaws.com" } } },
    { Effect = "Allow", Action = ["cloudfront:GetDistributionConfig", "cloudfront:GetDistribution", "cloudfront:UpdateDistribution"], Resource = ["arn:aws:cloudfront::${var.account_id}:distribution/${module.frontend.distribution_id}"] },
    { Effect = "Allow", Action = ["cloudwatch:DescribeAlarms", "cloudwatch:DeleteAlarms"], Resource = [for name in module.service.closure_target.alarms : "arn:aws:cloudwatch:${local.region}:${var.account_id}:alarm:${name}"] },
    { Effect = "Allow", Action = ["sns:Publish"], Resource = [module.service.closure_target.topic] },
    { Effect = "Allow", Action = ["sqs:SendMessage"], Resource = [module.service.closure_target.failure_queue_arn] },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = ["arn:aws:logs:${local.region}:${var.account_id}:log-group:/aws/lambda/${local.prefix}-close:*"] },
    { Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = [local.closure_arn] }
  ] })
}
resource "aws_iam_policy" "closure_boundary" {
  name   = "${local.prefix}-closure-boundary"
  policy = local.closure_policy
}
resource "aws_iam_role" "closure" {
  name                 = "${local.prefix}-close-runtime"
  permissions_boundary = aws_iam_policy.closure_boundary.arn
  assume_role_policy   = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "lambda.amazonaws.com" } }] })
}
resource "aws_iam_role_policy" "closure" {
  name   = "close-only"
  role   = aws_iam_role.closure.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [for s in jsondecode(local.closure_policy).Statement : s if !contains(s.Action, "lambda:InvokeFunction")] })
}
resource "aws_cloudwatch_log_group" "closure" {
  name              = "/aws/lambda/${local.prefix}-close"
  retention_in_days = 3
}
resource "aws_lambda_function" "closure" {
  function_name     = "${local.prefix}-close"
  role              = aws_iam_role.closure.arn
  runtime           = "python3.14"
  architectures     = ["x86_64"]
  handler           = "interview_backend.release_closure.handler"
  memory_size       = 128
  timeout           = 900
  s3_bucket         = var.artifact_bucket
  s3_key            = var.artifact_key
  s3_object_version = var.artifact_version
  source_code_hash  = var.artifact_sha256_base64
  environment {
    variables = { INTERVIEW_CLOSURE_TARGET = jsonencode(local.closure_target) }
  }
  depends_on = [aws_iam_role_policy.closure, aws_cloudwatch_log_group.closure]
}
resource "aws_lambda_function_event_invoke_config" "closure" {
  function_name                = aws_lambda_function.closure.function_name
  maximum_event_age_in_seconds = 3600
  maximum_retry_attempts       = 2
  destination_config {
    on_failure { destination = module.service.closure_target.failure_queue_arn }
  }
}
resource "aws_iam_role" "closure_trigger" {
  name                 = "${local.prefix}-close-trigger"
  permissions_boundary = aws_iam_policy.closure_boundary.arn
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "scheduler.amazonaws.com" }, Condition = {
    StringEquals = { "aws:SourceAccount" = var.account_id }, ArnEquals = { "aws:SourceArn" = "arn:aws:scheduler:${local.region}:${var.account_id}:schedule-group/${local.prefix}" }
  } }] })
}
resource "aws_iam_role_policy" "closure_trigger" {
  name = "invoke-close-only"
  role = aws_iam_role.closure_trigger.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = [local.closure_arn] },
    { Effect = "Allow", Action = ["sqs:SendMessage"], Resource = [module.service.closure_target.failure_queue_arn] }
  ] })
}
resource "aws_scheduler_schedule" "closure" {
  name                         = "month-end-close"
  group_name                   = local.prefix
  schedule_expression          = "at(${formatdate("YYYY-MM-DD'T'hh:mm:ss", local.release_end)})"
  schedule_expression_timezone = "UTC"
  state                        = "ENABLED"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_lambda_function.closure.arn
    role_arn = aws_iam_role.closure_trigger.arn
    input    = "{}"
    retry_policy {
      maximum_event_age_in_seconds = 60
      maximum_retry_attempts       = 0
    }
    dead_letter_config { arn = module.service.closure_target.failure_queue_arn }
  }
  depends_on = [aws_iam_role_policy.closure_trigger, aws_lambda_function_event_invoke_config.closure]
}
