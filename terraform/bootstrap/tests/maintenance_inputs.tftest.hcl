mock_provider "aws" {}

variables {
  account_id         = "123456789012"
  region             = "ap-northeast-1"
  oidc_provider_arn  = ""
  worker_wif_enabled = false
  oidc_subjects = {
    artifact = "repo:yonegen0/ai_interview:environment:dev"
    plan     = "repo:yonegen0/ai_interview:environment:dev"
    deploy   = "repo:yonegen0/ai_interview:environment:dev"
    test     = "repo:yonegen0/ai_interview:environment:dev"
  }
  ses_identity_type = "email"
  ses_domain        = ""
  ses_from_email    = "synthetic@example.invalid"
}

run "maintenance_preserves_state_owned_provider_and_no_wif" {
  command = apply
  assert {
    condition     = length(aws_iam_openid_connect_provider.github) == 1 && length(aws_iam_role.ci) == 4
    error_message = "Maintenance must preserve the owned provider and four existing roles."
  }
  assert {
    condition     = length(aws_ses_email_identity.sender) == 1 && length(aws_ses_domain_identity.sender) == 0
    error_message = "The canonical email identity must not be replaced with a domain identity."
  }
  assert {
    condition     = length(jsondecode(aws_iam_policy.runtime_boundary.policy).Statement) == 5
    error_message = "Maintenance must not add a WIF boundary statement."
  }
  assert {
    condition = alltrue([for role in ["plan", "deploy"] :
      jsondecode(aws_iam_role_policy.state[role].policy).Statement[5].Action == ["s3:GetObjectVersion"] &&
      jsondecode(aws_iam_role_policy.state[role].policy).Statement[5].Resource == ["${aws_s3_bucket.storage["state"].arn}/dev/terraform.tfstate"]
    ])
    error_message = "Only exact dev versioned State read may be added."
  }
}
