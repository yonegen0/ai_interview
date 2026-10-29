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

run "retirement_without_replacement_refused" {
  command = plan
  variables { legacy_ci_retired = true }
  expect_failures = [var.legacy_ci_retired]
}

run "log_delivery_without_standard_roles_refused" {
  command = plan
  variables { standard_ci_stage_log_delivery_enabled = true }
  expect_failures = [var.standard_ci_stage_log_delivery_enabled]
}

run "additive_standard_roles" {
  command = apply
  variables { standard_ci_enabled = true }
  assert {
    condition     = length(aws_iam_role.standard_ci) == 4 && length(aws_iam_role.ci) == 4
    error_message = "Add roles without deleting the existing recovery path."
  }
  assert {
    condition = alltrue([for name, role in aws_iam_role.standard_ci :
      jsondecode(role.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:yonegen0@76547980/ai_interview@1361325921:environment:${local.standard_ci_environments[name]}" &&
      jsondecode(role.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    ])
    error_message = "Use exact immutable repository IDs and purpose-specific environments."
  }
  assert {
    condition     = alltrue([for p in values(aws_iam_role_policy.standard_ci) : length(p.policy) <= 10240])
    error_message = "Standard inline policies must fit the IAM role quota."
  }
  assert {
    condition     = !strcontains(jsonencode(local.standard_ci_policies), "logs:CreateLogDelivery") && !strcontains(jsonencode(local.standard_ci_policies), "logs:PutResourcePolicy")
    error_message = "Existing callers must not gain log delivery permissions by default."
  }
  assert {
    condition = !anytrue(flatten([for statement in local.standard_ci_policies.plan :
      [for action in statement.Action : contains(["iam:PassRole", "iam:CreateRole", "lambda:UpdateFunctionCode"], action)]
    ]))
    error_message = "Plan must not acquire deploy or IAM mutation privileges."
  }
  assert {
    condition     = !strcontains(jsonencode(local.standard_ci_policies.artifact-plan), "apply-started.json") && !strcontains(jsonencode(local.standard_ci_policies.artifact-apply), "app.zip")
    error_message = "Plan artifact writes and Apply journal writes must be separate."
  }
}

run "explicit_dev_stage_log_delivery" {
  command = apply
  variables {
    standard_ci_enabled                    = true
    standard_ci_stage_log_delivery_enabled = true
  }
  assert {
    condition = one([for statement in local.standard_ci_policies.deploy : statement if try(statement.Sid, "") == "DevStageLogDelivery"]) == {
      Sid       = "DevStageLogDelivery"
      Effect    = "Allow"
      Action    = ["logs:CreateLogDelivery", "logs:PutResourcePolicy", "logs:DescribeResourcePolicies", "logs:ListLogDeliveries", "logs:GetLogDelivery"]
      Resource  = ["*"]
      Condition = { StringEquals = { "aws:RequestedRegion" = "ap-northeast-1" } }
    }
    error_message = "Only the five evidenced access-log setup permissions in Tokyo are approved candidates."
  }
  assert {
    condition     = alltrue([for role, statements in local.standard_ci_policies : !strcontains(jsonencode(statements), "DevStageLogDelivery") if role != "deploy"]) && !strcontains(jsonencode([for policy in values(aws_iam_role_policy.deploy) : policy.policy]), "DevStageLogDelivery")
    error_message = "Plan, artifact, test and legacy deploy roles must not inherit the opt-in."
  }
  assert {
    condition     = alltrue([for p in values(aws_iam_role_policy.standard_ci) : length(p.policy) <= 10240]) && length(aws_iam_role.standard_ci) == 4
    error_message = "Keep the existing roles and inline policy size limits."
  }
}

run "retire_only_after_additive_migration" {
  command = plan
  variables {
    standard_ci_enabled = true
    legacy_ci_retired   = true
  }
  assert {
    condition     = alltrue([for role in values(aws_iam_role.ci) : jsondecode(role.assume_role_policy).Statement[0].Effect == "Deny"])
    error_message = "Retired legacy subjects must not retain credential issuance."
  }
}

