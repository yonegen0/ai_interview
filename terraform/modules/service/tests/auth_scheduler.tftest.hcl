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

run "cognito_first_auth_factors" {
  command = plan
  assert {
    condition     = toset(aws_cognito_user_pool.main.sign_in_policy[0].allowed_first_auth_factors) == toset(["PASSWORD", "EMAIL_OTP"])
    error_message = "Cognito requires PASSWORD while retaining EMAIL_OTP."
  }
  assert {
    condition     = aws_cognito_user_pool.main.user_pool_tier == "ESSENTIALS" && aws_cognito_user_pool.main.mfa_configuration == "OFF" && aws_cognito_user_pool.main.admin_create_user_config[0].allow_admin_create_user_only && toset(aws_cognito_user_pool.main.username_attributes) == toset(["email"]) && toset(aws_cognito_user_pool.main.auto_verified_attributes) == toset(["email"])
    error_message = "Keep the existing email OTP and administrator-created user requirements."
  }
  assert {
    condition     = toset(aws_cognito_user_pool_client.web.explicit_auth_flows) == toset(["ALLOW_USER_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]) && !aws_cognito_user_pool_client.web.generate_secret && aws_cognito_user_pool_client.web.access_token_validity == 5 && aws_cognito_user_pool_client.web.enable_token_revocation && aws_cognito_user_pool_client.web.prevent_user_existence_errors == "ENABLED"
    error_message = "Keep choice-based OTP authentication, public client, short tokens and revocation."
  }
}

run "empty_run_id_only_omitted_from_scheduler" {
  command = plan
  assert {
    condition     = aws_scheduler_schedule_group.recovery.tags == tomap({ Project = "ai-interview", Environment = "dev", ManagedBy = "Terraform" }) && !contains(keys(aws_scheduler_schedule_group.recovery.tags), "RunId")
    error_message = "Scheduler must omit an empty RunId and retain all other tags."
  }
  assert {
    condition     = local.tags.RunId == "" && aws_dynamodb_table.main.tags == tomap(local.tags) && aws_sqs_queue.main.tags == tomap(local.tags) && aws_apigatewayv2_api.main.tags == tomap(local.tags) && aws_iam_role.scheduler.tags == tomap(local.tags) && aws_cloudwatch_log_group.api.tags == tomap(local.tags) && aws_cognito_user_pool.main.tags == tomap(local.tags) && alltrue([for f in aws_lambda_function.main : f.tags == tomap(local.tags)])
    error_message = "The Scheduler exception must not change other resources' common tags."
  }
}

run "nonempty_run_id_preserved" {
  command = plan
  variables { run_id = "regression-01" }
  assert {
    condition     = aws_scheduler_schedule_group.recovery.tags == tomap(local.tags) && aws_scheduler_schedule_group.recovery.tags.RunId == "regression-01" && aws_scheduler_schedule_group.recovery.name == "ai-interview-test-regression-01" && local.tags.Environment == "test"
    error_message = "Test Scheduler must keep its RunId, namespace and all common tags."
  }
  assert {
    condition     = aws_dynamodb_table.main.tags == tomap(local.tags) && aws_sqs_queue.main.tags == tomap(local.tags) && aws_iam_role.scheduler.tags == tomap(local.tags) && alltrue([for f in aws_lambda_function.main : f.tags == tomap(local.tags)])
    error_message = "A nonempty RunId must remain unchanged on other resources too."
  }
}
