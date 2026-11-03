mock_provider "aws" {}
variables {
  account_id             = "123456789012"
  region                 = "ap-northeast-1"
  deployment_generation  = "g1"
  isolation_operator_arn = "arn:aws:iam::123456789012:role/approved-deployer"
  boundary_arn           = "arn:aws:iam::123456789012:policy/invite-boundary"
  artifact_bucket        = "synthetic-artifacts"
  artifact_key           = "lambda/invite/app.zip"
  artifact_version       = "synthetic-version"
  artifact_sha256_base64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
  ses_email              = "sender@example.invalid"
  ses_identity_arn       = "arn:aws:ses:ap-northeast-1:123456789012:identity/sender@example.invalid"
  alarm_email            = "alarm@example.invalid"
  cors_origins           = ["https://invite.example.invalid"]
  monthly_budget_usd     = 10
}
run "isolation_policies" {
  command = plan
  assert {
    condition = (
      aws_dynamodb_table.main.name == "ai-interview-invite-g1-main" &&
      aws_dynamodb_table.main.deletion_protection_enabled &&
      aws_dynamodb_table.main.point_in_time_recovery[0].enabled &&
      length(aws_dynamodb_resource_policy.isolation_table) == 1 &&
      length(aws_dynamodb_resource_policy.isolation_stream) == 1 &&
      length(aws_sqs_queue_policy.isolation) == 3
    )
    error_message = "Each invite generation requires protected data and policies on table, stream and all queues."
  }
  assert {
    condition = (
      jsondecode(aws_dynamodb_resource_policy.isolation_table[0].policy).Statement[0].Effect == "Deny" &&
      jsondecode(aws_dynamodb_resource_policy.isolation_table[0].policy).Statement[0].Condition.ArnNotEquals["aws:PrincipalArn"] == local.isolation_trusted_roles &&
      !contains(local.isolation_trusted_roles, "arn:aws:iam::123456789012:role/ai-interview-dev-worker-runtime") &&
      !contains(local.isolation_trusted_roles, "arn:aws:iam::123456789012:role/ai-interview-invite-g2-worker-runtime")
    )
    error_message = "Explicit Deny must exclude old and other generation roles even with broad identity IAM."
  }
}
run "enabled_monitoring_is_generation_scoped" {
  command = plan
  variables { api_enabled = true }
  assert {
    condition = (
      length(aws_cloudwatch_metric_alarm.emf) == 9 &&
      length(aws_cloudwatch_metric_alarm.api_5xx) == 1 &&
      length(aws_cloudwatch_metric_alarm.evaluation_failed) == 1 &&
      aws_cloudwatch_metric_alarm.emf["worker-IntegrityError"].dimensions.Environment == "invite-g1" &&
      length(aws_cloudwatch_metric_alarm.lambda) == 8 &&
      length(aws_cloudwatch_metric_alarm.dlq) == 2 &&
      !aws_lambda_event_source_mapping.worker.enabled
    )
    error_message = "Invite monitoring must retain all 21 customer alarms without mixing legacy EMF."
  }
}
run "invalid_generation_rejected" {
  command = plan
  variables { deployment_generation = "g1/legacy" }
  expect_failures = [var.deployment_generation]
}
run "minimal_monitoring_and_closure_isolation" {
  command = plan
  variables {
    monitoring_profile        = "minimal"
    automatic_closure_enabled = true
    api_enabled               = true
    log_usage                 = "customer"
    release_expires_at_epoch  = 1796050800
  }
  assert {
    condition = (
      length(aws_cloudwatch_metric_alarm.emf) == 0 &&
      length(aws_cloudwatch_metric_alarm.dlq) == 0 &&
      length(aws_cloudwatch_metric_alarm.lambda) == 1 &&
      length(aws_cloudwatch_metric_alarm.minimal) == 2 &&
      length(aws_cloudwatch_metric_alarm.minimal_dlq) == 1 &&
      length(aws_cloudwatch_metric_alarm.api_5xx) == 1 &&
      length(aws_cloudwatch_metric_alarm.evaluation_failed) == 0 &&
      length(aws_cloudwatch_metric_alarm.minimal["CriticalFailure"].dimensions) == 2 &&
      aws_cloudwatch_metric_alarm.minimal["RecoveryHeartbeat"].treat_missing_data == "breaching" &&
      aws_cloudwatch_log_group.lambda["worker"].retention_in_days == 3
    )
    error_message = "Minimal invite monitoring must keep five alarms, two bounded custom series and short logs."
  }
  assert {
    condition = (
      strcontains(aws_sqs_queue_policy.isolation["stream_failure"].policy, "close-runtime") &&
      !strcontains(aws_sqs_queue_policy.isolation["main"].policy, "close-runtime") &&
      !strcontains(aws_dynamodb_resource_policy.isolation_table[0].policy, "close-runtime") &&
      aws_lambda_function.main["api"].environment[0].variables.INTERVIEW_RELEASE_EXPIRES_AT == "1796050800"
    )
    error_message = "Closure roles may deliver failure notices, without entering business data or bypassing API expiry."
  }
}
run "test_and_invite_cannot_share_generation" {
  command = plan
  variables { run_id = "synthetic" }
  expect_failures = [var.deployment_generation]
}
