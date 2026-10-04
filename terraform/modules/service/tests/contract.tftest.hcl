mock_provider "aws" {}

variables {
  account_id             = "123456789012"
  region                 = "ap-northeast-1"
  boundary_arn           = "arn:aws:iam::123456789012:policy/ai-interview-runtime-boundary"
  artifact_bucket        = "ai-interview-artifacts-123456789012-ap-northeast-1"
  artifact_key           = "lambda/deploy/synthetic/app.zip"
  artifact_version       = "synthetic-version"
  artifact_sha256_base64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
  ses_email              = "sender@example.invalid"
  ses_identity_arn       = "arn:aws:ses:ap-northeast-1:123456789012:identity/sender@example.invalid"
  alarm_email            = "alarm@example.invalid"
  cors_origins           = ["http://localhost:3000"]
  monthly_budget_usd     = 10
}

run "p2_fixed_configuration" {
  command = plan
  assert {
    condition = (
      aws_dynamodb_table.main.hash_key == "PK" && aws_dynamodb_table.main.range_key == "SK" &&
      aws_dynamodb_table.main.billing_mode == "PAY_PER_REQUEST" && aws_dynamodb_table.main.stream_enabled &&
      toset([for a in aws_dynamodb_table.main.attribute : "${a.name}:${a.type}"]) == toset(["PK:S", "SK:S", "work_pk:S", "work_sk:S"]) &&
      one(aws_dynamodb_table.main.global_secondary_index).name == "WorkIndex" &&
      length(one(aws_dynamodb_table.main.global_secondary_index).key_schema) == 2 &&
      toset([for k in one(aws_dynamodb_table.main.global_secondary_index).key_schema : "${k.attribute_name}:${k.key_type}"]) == toset(["work_pk:HASH", "work_sk:RANGE"])
    )
    error_message = "Table keys, string attributes and WorkIndex key schema must retain the P2 contract."
  }
  assert {
    condition     = aws_dynamodb_table.main.stream_view_type == "NEW_AND_OLD_IMAGES" && length(aws_dynamodb_table.main.global_secondary_index) == 1
    error_message = "One WorkIndex and both stream images are required."
  }
  assert {
    condition     = one(aws_dynamodb_table.main.global_secondary_index).projection_type == "KEYS_ONLY" && length(aws_dynamodb_table.main.ttl) == 0
    error_message = "No TTL or additional GSI projection."
  }
  assert {
    condition     = aws_lambda_function.main["worker"].timeout == 60 && alltrue([for f in aws_lambda_function.main : f.reserved_concurrent_executions == -1]) && aws_sqs_queue.main.visibility_timeout_seconds == 360 && aws_lambda_event_source_mapping.worker.scaling_config[0].maximum_concurrency == 2
    error_message = "Keep execution budgets and SQS maximum concurrency 2 without reserving account capacity."
  }
  assert {
    condition     = aws_apigatewayv2_stage.dev.default_route_settings[0].throttling_rate_limit == 20 && aws_apigatewayv2_stage.dev.default_route_settings[0].throttling_burst_limit == 30
    error_message = "Allow 30-user polling and short bursts without removing the API rate limit."
  }
  assert {
    condition     = aws_lambda_event_source_mapping.worker.batch_size == 1 && !aws_lambda_event_source_mapping.worker.enabled && !aws_lambda_event_source_mapping.streams.enabled && aws_scheduler_schedule.recovery.state == "DISABLED"
    error_message = "First deployment must not start asynchronous work."
  }
  assert {
    condition     = aws_apigatewayv2_api.main.disable_execute_api_endpoint && alltrue([for r in aws_apigatewayv2_route.business : r.authorization_type == "JWT"])
    error_message = "First deployment is closed and business routes require JWT."
  }
  assert {
    condition     = aws_cognito_user_pool_client.web.access_token_validity == 5 && !aws_cognito_user_pool_client.web.generate_secret && aws_cognito_user_pool.main.user_pool_tier == "ESSENTIALS"
    error_message = "Passwordless public client and five-minute tokens are required."
  }
  assert {
    condition     = alltrue([for f in aws_lambda_function.main : f.runtime == "python3.14" && f.memory_size == 512 && f.s3_object_version == "synthetic-version"])
    error_message = "All entrypoints must deploy the same versioned artifact."
  }
}

run "reject_wildcard_origin" {
  command = plan
  variables { cors_origins = ["*"] }
  expect_failures = [var.cors_origins]
}

run "reject_missing_account" {
  command = plan
  variables { account_id = "" }
  expect_failures = [var.account_id]
}

run "budget_notifications" {
  command = plan
  assert {
    condition     = toset([for n in aws_budgets_budget.dev[0].notification : "${n.notification_type}:${n.threshold}"]) == toset(["ACTUAL:80", "ACTUAL:100", "FORECASTED:100"])
    error_message = "Both actual thresholds and the forecast notification are mandatory."
  }
}

run "reject_foreign_sender" {
  command = plan
  variables { ses_identity_arn = "arn:aws:ses:us-east-1:999999999999:identity/sender@example.invalid" }
  expect_failures = [var.ses_identity_arn]
}
