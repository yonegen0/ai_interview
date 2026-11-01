mock_provider "aws" {
  override_during = plan
  mock_resource "aws_secretsmanager_secret" {
    defaults = { arn = "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:ai-interview-invite-g1-claude-Abc123" }
  }
  mock_resource "aws_iam_policy" {
    defaults = { arn = "arn:aws:iam::123456789012:policy/ai-interview-invite-g1-runtime-boundary" }
  }
}
variables {
  account_id             = "123456789012"
  deployment_role_arn    = "arn:aws:iam::123456789012:role/approved-deployer"
  anthropic_workspace_id = "wrkspc_InviteSynthetic"
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
run "closed_generation" {
  command = plan
  assert {
    condition = (
      output.manifest.environment == "invite-g1" &&
      output.manifest.table_name == "ai-interview-invite-g1-main" &&
      !output.manifest.configuration.api_enabled && !output.manifest.configuration.worker_enabled &&
      !output.manifest.configuration.streams_enabled && !output.manifest.configuration.scheduler_enabled &&
      !output.frontend.enabled && length(aws_iam_role_policy.legacy_quarantine) == 0
    )
    error_message = "New generation must be independent and closed without touching legacy by default."
  }
  assert {
    condition = (
      jsondecode(aws_secretsmanager_secret_policy.claude.policy).Statement[0].Effect == "Deny" &&
      jsondecode(aws_secretsmanager_secret_policy.claude.policy).Statement[0].Condition.ArnNotEquals["aws:PrincipalArn"] == [local.worker_role] &&
      output.manifest.worker_ai_environment["INTERVIEW_ANTHROPIC_MONTHLY_USER_LIMIT"] == "20" &&
      output.manifest.worker_ai_environment["INTERVIEW_ANTHROPIC_MONTHLY_GLOBAL_LIMIT"] == "600"
    )
    error_message = "Only the generation Worker can read the new secret, with bounded shared quota."
  }
  assert {
    condition = alltrue([for s in jsondecode(aws_iam_policy.runtime_boundary.policy).Statement :
      alltrue([for r in s.Resource : r == "*" || strcontains(r, "ai-interview-invite-g1")])
    ])
    error_message = "The new runtime boundary cannot authorize legacy data or AI providers."
  }
}
run "legacy_runtime_cannot_administer_isolation" {
  command = plan
  variables { deployment_role_arn = "arn:aws:iam::123456789012:role/ai-interview-dev-worker-runtime" }
  expect_failures = [var.deployment_role_arn]
}
run "http_origin_rejected" {
  command = plan
  variables { cors_origins = ["http://localhost:3000"] }
  expect_failures = [var.cors_origins]
}
run "enable_without_quarantine_rejected" {
  command = plan
  variables { api_enabled = true }
  expect_failures = [var.legacy_quarantine_enabled]
}
run "quarantine_has_no_legacy_data_mutation" {
  command = plan
  variables { legacy_quarantine_enabled = true }
  assert {
    condition = length(aws_iam_role_policy.legacy_quarantine) == 5 && alltrue([
      for p in aws_iam_role_policy.legacy_quarantine :
      jsondecode(p.policy).Statement[0].Effect == "Deny" &&
      contains(jsondecode(p.policy).Statement[0].Action, "bedrock:*") &&
      contains(jsondecode(p.policy).Statement[0].Action, "sts:AssumeRole")
    ])
    error_message = "Quarantine must deny legacy side effects and credential acquisition for all five roles."
  }
}
