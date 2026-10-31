mock_provider "aws" {}

variables {
  account_id        = "123456789012"
  region            = "ap-northeast-1"
  oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
  oidc_subjects = {
    artifact = "repo:yonegen0/ai_interview:environment:dev"
    plan     = "repo:yonegen0/ai_interview:environment:dev"
    deploy   = "repo:yonegen0/ai_interview:environment:dev"
    test     = "repo:yonegen0/ai_interview:environment:dev"
  }
  ses_identity_type = "domain"
  ses_domain        = "example.invalid"
  ses_from_email    = "sender@example.invalid"
}

run "anthropic_boundary_disabled_by_default" {
  command = plan
  assert {
    condition     = length(local.worker_anthropic_boundary_statements) == 0 && length(jsondecode(aws_iam_policy.runtime_boundary.policy).Statement) == 5
    error_message = "Default boundary must not contain Secrets Manager grants."
  }
}

run "anthropic_boundary_scopes_exact_dev_worker_and_secret" {
  command = plan
  variables {
    worker_anthropic_secret_arn = "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:anthropic-offline-Aa1234"
  }
  assert {
    condition = (
      length(local.worker_anthropic_boundary_statements) == 1 &&
      local.worker_anthropic_boundary_statements[0].Action == ["secretsmanager:GetSecretValue"] &&
      local.worker_anthropic_boundary_statements[0].Condition.ArnEquals["aws:PrincipalArn"] == "arn:aws:iam::123456789012:role/ai-interview-dev-worker-runtime" &&
      local.worker_anthropic_boundary_statements[0].Resource[0] == var.worker_anthropic_secret_arn &&
      length(jsondecode(aws_iam_policy.runtime_boundary.policy).Statement) == 6
    )
    error_message = "The secret grant must require explicit opt-in and exact Worker/ARN."
  }
}

run "anthropic_boundary_cross_account_rejected" {
  command = plan
  variables {
    worker_anthropic_secret_arn = "arn:aws:secretsmanager:ap-northeast-1:000000000000:secret:wrong"
  }
  expect_failures = [var.worker_anthropic_secret_arn]
}
