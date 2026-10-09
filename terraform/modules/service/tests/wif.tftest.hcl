mock_provider "aws" {
  mock_resource "aws_cognito_user_pool" {
    defaults = {
      id  = "ap-northeast-1_synthetic"
      arn = "arn:aws:cognito-idp:ap-northeast-1:123456789012:userpool/ap-northeast-1_synthetic"
    }
  }
  mock_resource "aws_sns_topic" {
    defaults = { arn = "arn:aws:sns:ap-northeast-1:123456789012:ai-interview-dev-alarms" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/synthetic-runtime" }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:ap-northeast-1:123456789012:log-group:/aws/lambda/synthetic" }
  }
  mock_resource "aws_lambda_function" {
    defaults = { arn = "arn:aws:lambda:ap-northeast-1:123456789012:function:synthetic", version = "1" }
  }
  mock_resource "aws_lambda_alias" {
    defaults = { arn = "arn:aws:lambda:ap-northeast-1:123456789012:function:synthetic:live" }
  }
  mock_resource "aws_dynamodb_table" {
    defaults = { arn = "arn:aws:dynamodb:ap-northeast-1:123456789012:table/synthetic", stream_arn = "arn:aws:dynamodb:ap-northeast-1:123456789012:table/synthetic/stream/2026-10-08T00:00:00.000" }
  }
  mock_resource "aws_sqs_queue" {
    defaults = { arn = "arn:aws:sqs:ap-northeast-1:123456789012:synthetic" }
  }
  mock_resource "aws_apigatewayv2_api" {
    defaults = { execution_arn = "arn:aws:execute-api:ap-northeast-1:123456789012:synthetic" }
  }
}
variables {
  log_usage              = "developer"
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
run "default_wif_has_no_grant" {
  command = plan
  assert {
    condition     = length(local.worker_wif_statements) == 0
    error_message = "Default must preserve baseline IAM."
  }
}
run "worker_wif_exact_conditions" {
  command = apply
  variables { worker_wif_enabled = true }
  assert {
    condition     = jsondecode(aws_iam_role_policy.runtime["worker"].policy).Statement[length(jsondecode(aws_iam_role_policy.runtime["worker"].policy).Statement) - 1].Action == ["sts:GetWebIdentityToken"]
    error_message = "Worker grant must be exact."
  }
  assert {
    condition     = alltrue([for role in ["api", "admin", "dispatcher"] : alltrue([for s in jsondecode(aws_iam_role_policy.runtime[role].policy).Statement : !contains(s.Action, "sts:GetWebIdentityToken")])])
    error_message = "Other roles must receive no grant."
  }
  assert {
    condition     = local.worker_wif_statements[0].Condition.NumericLessThanEquals["sts:DurationSeconds"] == 300 && local.worker_wif_statements[0].Condition.StringEquals["sts:SigningAlgorithm"] == "ES384" && !aws_lambda_event_source_mapping.worker.enabled
    error_message = "Audience/TTL/algorithm grant must not activate Worker."
  }
}
run "test_worker_wif_forbidden" {
  command = plan
  variables {
    worker_wif_enabled = true
    run_id             = "wif-test"
  }
  expect_failures = [var.worker_wif_enabled]
}
