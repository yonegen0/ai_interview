mock_provider "aws" {}

variables {
  account_id             = "123456789012"
  region                 = "ap-northeast-1"
  boundary_arn           = "arn:aws:iam::123456789012:policy/ai-interview-runtime-boundary"
  artifact_bucket        = "ai-interview-artifacts-123456789012-ap-northeast-1"
  artifact_key           = "lambda/synthetic/app.zip"
  artifact_version       = "synthetic-version"
  artifact_sha256_base64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
  ses_email              = "sender@example.invalid"
  ses_identity_arn       = "arn:aws:ses:ap-northeast-1:123456789012:identity/sender@example.invalid"
  alarm_email            = "alarm@example.invalid"
  cors_origins           = ["http://localhost:3000"]
  monthly_budget_usd     = 10
}

run "closed_dev" {
  command = plan
  assert {
    condition     = aws_apigatewayv2_api.main.disable_execute_api_endpoint && !aws_lambda_event_source_mapping.worker.enabled && !aws_lambda_event_source_mapping.streams.enabled && aws_scheduler_schedule.recovery.state == "DISABLED"
    error_message = "Omitting activation inputs must keep the first deployment closed."
  }
  assert {
    condition     = length(aws_cloudwatch_metric_alarm.emf) + length(aws_cloudwatch_metric_alarm.lambda) + length(aws_cloudwatch_metric_alarm.dlq) + length(aws_cloudwatch_metric_alarm.iterator) + length(aws_cloudwatch_metric_alarm.failure_rate) == 0
    error_message = "Closed dev must have no billable alarms."
  }
  assert {
    condition     = aws_cloudwatch_log_group.api.retention_in_days == 7 && alltrue([for g in aws_cloudwatch_log_group.lambda : g.retention_in_days == 7])
    error_message = "Dev logs retain seven days."
  }
  assert {
    condition     = alltrue([for f in aws_lambda_function.main : f.tracing_config[0].mode == "PassThrough" && length(f.vpc_config) == 0 && f.memory_size == 512 && length(f.architectures) == 1 && contains(f.architectures, "x86_64") && f.reserved_concurrent_executions == -1])
    error_message = "Runtime must remain on demand, unreserved and outside a VPC."
  }
}

run "worker_only" {
  command = plan
  variables { worker_enabled = true }
  assert {
    condition     = toset(keys(aws_cloudwatch_metric_alarm.emf)) == toset(["api-IntegrityError", "worker-IntegrityError", "dispatcher-IntegrityError", "OutcomeUnknown", "RecoveryHeartbeat", "RecoverySweepLag"]) && length(aws_cloudwatch_metric_alarm.lambda) == 6 && length(aws_cloudwatch_metric_alarm.dlq) == 2 && length(aws_cloudwatch_metric_alarm.iterator) == 0 && length(aws_cloudwatch_metric_alarm.failure_rate) == 0
    error_message = "Any active dev component requires the fourteen attended-test alarms."
  }
  assert {
    condition     = !aws_cloudwatch_metric_alarm.emf["RecoveryHeartbeat"].actions_enabled && !aws_cloudwatch_metric_alarm.emf["RecoverySweepLag"].actions_enabled
    error_message = "A disabled scheduler must not alert on missing recovery."
  }
}

run "api_only" {
  command = plan
  variables { api_enabled = true }
  assert {
    condition     = length(aws_cloudwatch_metric_alarm.emf) == 6 && length(aws_cloudwatch_metric_alarm.lambda) == 6 && length(aws_cloudwatch_metric_alarm.dlq) == 2
    error_message = "API activation cannot bypass monitoring."
  }
}

run "streams_only" {
  command = plan
  variables { streams_enabled = true }
  assert {
    condition     = length(aws_cloudwatch_metric_alarm.emf) == 6 && length(aws_cloudwatch_metric_alarm.lambda) == 6 && length(aws_cloudwatch_metric_alarm.dlq) == 2
    error_message = "Streams activation cannot bypass monitoring."
  }
}

run "scheduler_only" {
  command = plan
  variables { scheduler_enabled = true }
  assert {
    condition     = length(aws_cloudwatch_metric_alarm.emf) == 6 && aws_cloudwatch_metric_alarm.emf["RecoveryHeartbeat"].actions_enabled && aws_cloudwatch_metric_alarm.emf["RecoverySweepLag"].actions_enabled
    error_message = "Enabled recovery requires heartbeat and sweep notifications."
  }
}

run "fully_active_dev" {
  command = plan
  variables {
    api_enabled       = true
    worker_enabled    = true
    streams_enabled   = true
    scheduler_enabled = true
  }
  assert {
    condition     = length(aws_cloudwatch_metric_alarm.emf) + length(aws_cloudwatch_metric_alarm.lambda) + length(aws_cloudwatch_metric_alarm.dlq) == 14 && alltrue([for a in aws_cloudwatch_metric_alarm.emf : a.actions_enabled])
    error_message = "Active dev has fourteen enabled alarms."
  }
  assert {
    condition     = !aws_apigatewayv2_api.main.disable_execute_api_endpoint && aws_lambda_event_source_mapping.worker.enabled && aws_lambda_event_source_mapping.streams.enabled && aws_scheduler_schedule.recovery.state == "ENABLED" && aws_scheduler_schedule.recovery.schedule_expression == "rate(1 minute)"
    error_message = "All four explicit activation inputs must enable the existing E2E path without changing its schedule."
  }
  assert {
    condition     = aws_lambda_event_source_mapping.worker.scaling_config[0].maximum_concurrency == 2 && alltrue([for f in aws_lambda_function.main : f.reserved_concurrent_executions == -1 && length(f.vpc_config) == 0 && f.runtime == "python3.14" && f.memory_size == 512 && toset(f.architectures) == toset(["x86_64"])])
    error_message = "Activation must retain the Worker limit, on-demand runtime and existing compute settings."
  }
  assert {
    condition     = alltrue([for r in aws_apigatewayv2_route.business : r.authorization_type == "JWT"]) && aws_apigatewayv2_authorizer.jwt.authorizer_type == "JWT" && toset(aws_cognito_user_pool.main.sign_in_policy[0].allowed_first_auth_factors) == toset(["PASSWORD", "EMAIL_OTP"]) && !aws_cognito_user_pool_client.web.generate_secret && toset(aws_cognito_user_pool_client.web.explicit_auth_flows) == toset(["ALLOW_USER_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"])
    error_message = "Opening the HTTP endpoint must preserve Cognito choice authentication and every business route's JWT requirement."
  }
  assert {
    condition     = alltrue([for f in aws_lambda_function.main : f.s3_bucket == var.artifact_bucket && f.s3_key == var.artifact_key && f.s3_object_version == var.artifact_version && f.source_code_hash == var.artifact_sha256_base64])
    error_message = "Activation must not change any function's versioned artifact binding."
  }
}

run "full_test_monitoring" {
  command = plan
  variables { run_id = "synthetic" }
  assert {
    condition     = length(aws_cloudwatch_metric_alarm.emf) == 22 && length(aws_cloudwatch_metric_alarm.lambda) == 6 && length(aws_cloudwatch_metric_alarm.dlq) == 2 && length(aws_cloudwatch_metric_alarm.iterator) == 1 && length(aws_cloudwatch_metric_alarm.failure_rate) == 1
    error_message = "Test keeps all thirty-two alarms."
  }
  assert {
    condition     = aws_cloudwatch_log_group.api.retention_in_days == 30 && alltrue([for g in aws_cloudwatch_log_group.lambda : g.retention_in_days == 30]) && aws_cloudwatch_metric_alarm.emf["RecoverySweepLag"].actions_enabled
    error_message = "Test log retention and sweep behavior remain unchanged."
  }
}
