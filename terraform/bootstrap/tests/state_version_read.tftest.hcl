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
run "exact_dev_version_read_only" {
  command = apply
  assert {
    condition = alltrue([for role in ["plan", "deploy"] :
      jsondecode(aws_iam_role_policy.state[role].policy).Statement[5] == {
        Sid      = "DevVersionedStateRead"
        Effect   = "Allow"
        Action   = ["s3:GetObjectVersion"]
        Resource = ["${aws_s3_bucket.storage["state"].arn}/dev/terraform.tfstate"]
      }
    ])
    error_message = "Only the canonical dev State may gain versioned read access."
  }
  assert {
    condition = length(jsondecode(aws_iam_role_policy.state["test"].policy).Statement) == 5 && alltrue([
      for role in ["plan", "deploy", "test"] :
      keys(jsondecode(aws_iam_role_policy.state[role].policy).Statement[0].Condition.StringLike) == ["s3:prefix"]
    ])
    error_message = "Test permissions and prefix-bound ListBucket must remain unchanged."
  }
  assert {
    condition = jsondecode(aws_iam_role_policy.state["plan"].policy).Statement[2].Action == ["s3:GetObject"] && alltrue([
      for role in ["plan", "deploy"] : jsondecode(aws_iam_role_policy.state[role].policy).Statement[3].Action == ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    ])
    error_message = "Plan State writes must stay forbidden; normal exact lockfile lifecycle remains."
  }
}
