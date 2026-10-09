mock_provider "aws" {}
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
run "default_fake_no_provider_environment" {
  command = plan
  assert {
    condition     = !contains(keys(aws_lambda_function.main["worker"].environment[0].variables), "INTERVIEW_AI_PROVIDER") && !aws_lambda_event_source_mapping.worker.enabled
    error_message = "Default provider remains Fake and the environment remains closed."
  }
}
run "reject_plaintext_credentials" {
  command = plan
  variables { worker_ai_environment = { OPENAI_API_KEY = "forbidden-placeholder" } }
  expect_failures = [var.worker_ai_environment]
}
run "openai_configuration_worker_only" {
  command = plan
  variables {
    worker_wif_enabled = true
    worker_ai_environment = {
      INTERVIEW_AI_PROVIDER                 = "openai"
      INTERVIEW_OPENAI_ENABLED              = "true"
      INTERVIEW_OPENAI_AUTH                 = "wif"
      INTERVIEW_OPENAI_IDENTITY_PROVIDER_ID = "idp-offline"
      INTERVIEW_OPENAI_SERVICE_ACCOUNT_ID   = "sa-offline"
    }
  }
  assert {
    condition     = aws_lambda_function.main["worker"].environment[0].variables["INTERVIEW_AI_PROVIDER"] == "openai" && !contains(keys(aws_lambda_function.main["api"].environment[0].variables), "INTERVIEW_AI_PROVIDER") && !aws_lambda_event_source_mapping.worker.enabled
    error_message = "Provider settings affect Worker only and do not enable the environment."
  }
}
