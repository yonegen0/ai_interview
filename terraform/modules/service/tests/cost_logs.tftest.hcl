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
run "safe_customer_default" {
  command = plan
  assert {
    condition     = aws_cloudwatch_log_group.api.retention_in_days == 14 && alltrue([for g in aws_cloudwatch_log_group.lambda : g.retention_in_days == 14])
    error_message = "Omitted module use must be safe for customer data: all five groups 14 days."
  }
  assert {
    condition     = length(aws_cloudwatch_metric_alarm.api_5xx) == 0 && length(aws_cloudwatch_metric_alarm.evaluation_failed) == 0
    error_message = "Closed customer dev must not retain new alarms."
  }
}
run "active_customer" {
  command = plan
  variables {
    api_enabled       = true
    worker_enabled    = true
    streams_enabled   = true
    scheduler_enabled = true
    log_usage         = "customer"
  }
  assert {
    condition     = length(aws_cloudwatch_metric_alarm.emf) == 9 && length(aws_cloudwatch_metric_alarm.lambda) == 8 && length(aws_cloudwatch_metric_alarm.dlq) == 2 && length(aws_cloudwatch_metric_alarm.api_5xx) == 1 && length(aws_cloudwatch_metric_alarm.evaluation_failed) == 1
    error_message = "Customer dev requires 21 alarms, retaining every existing 17."
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.api_5xx[0].metric_name == "5xx" && aws_cloudwatch_metric_alarm.api_5xx[0].namespace == "AWS/ApiGateway" && aws_cloudwatch_metric_alarm.api_5xx[0].period == 60 && aws_cloudwatch_metric_alarm.api_5xx[0].threshold == 1 && aws_cloudwatch_metric_alarm.api_5xx[0].treat_missing_data == "notBreaching"
    error_message = "Caught API failures require standard API-wide 5xx with explicit missing data."
  }
  assert {
    condition     = length([for q in aws_cloudwatch_metric_alarm.evaluation_failed[0].metric_query : q if length(q.metric) == 1]) == 2 && length([for q in aws_cloudwatch_metric_alarm.evaluation_failed[0].metric_query : q if q.expression == "FILL(wf,0)+FILL(df,0)"]) == 1 && aws_cloudwatch_metric_alarm.evaluation_failed[0].threshold == 1 && aws_cloudwatch_metric_alarm.evaluation_failed[0].treat_missing_data == "notBreaching"
    error_message = "Single business failure must alarm on two existing metric references, without a minimum sample gate."
  }
  assert {
    condition     = alltrue([for n in ["PendingAge", "QueuedAge"] : aws_cloudwatch_metric_alarm.emf[n].threshold == 120 && aws_cloudwatch_metric_alarm.emf[n].statistic == "Maximum" && aws_cloudwatch_metric_alarm.emf[n].period == 60 && aws_cloudwatch_metric_alarm.emf[n].treat_missing_data == "notBreaching"])
    error_message = "Keep individual-work backlog semantics; heartbeat cannot substitute for these metrics."
  }
}
run "invalid_use" {
  command = plan
  variables { log_usage = "production" }
  expect_failures = [var.log_usage]
}
run "unconfirmed_test_close" {
  command = plan
  variables {
    run_id                  = "cost-close"
    log_usage               = "developer"
    test_monitoring_enabled = false
  }
  expect_failures = [var.test_monitoring_enabled]
}
run "active_test_close_rejected" {
  command = plan
  variables {
    run_id                  = "cost-close"
    test_monitoring_enabled = false
    test_closure_confirmed  = true
    worker_enabled          = true
  }
  expect_failures = [var.test_monitoring_enabled]
}
run "confirmed_test_closed" {
  command = plan
  variables {
    run_id                  = "cost-close"
    log_usage               = "developer"
    test_monitoring_enabled = false
    test_closure_confirmed  = true
  }
  assert {
    condition     = length(aws_cloudwatch_metric_alarm.emf) + length(aws_cloudwatch_metric_alarm.lambda) + length(aws_cloudwatch_metric_alarm.dlq) + length(aws_cloudwatch_metric_alarm.iterator) + length(aws_cloudwatch_metric_alarm.failure_rate) == 0 && aws_cloudwatch_log_group.api.retention_in_days == 3 && alltrue([for g in aws_cloudwatch_log_group.lambda : g.retention_in_days == 3])
    error_message = "Verified closed test retains data and logs but no validation alarms."
  }
}
run "test_reopened" {
  command = plan
  variables {
    run_id                  = "cost-close"
    log_usage               = "developer"
    test_monitoring_enabled = true
    test_closure_confirmed  = false
    worker_enabled          = true
  }
  assert {
    condition     = length(aws_cloudwatch_metric_alarm.emf) + length(aws_cloudwatch_metric_alarm.lambda) + length(aws_cloudwatch_metric_alarm.dlq) + length(aws_cloudwatch_metric_alarm.iterator) + length(aws_cloudwatch_metric_alarm.failure_rate) == 39
    error_message = "Verification must keep all 39 test alarms when reopened."
  }
}
