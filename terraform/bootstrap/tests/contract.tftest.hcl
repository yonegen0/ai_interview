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

run "bootstrap_policy_contract" {
  command = apply
  assert {
    condition = alltrue([for role in ["plan", "deploy", "test"] : sum([
      length(aws_iam_role_policy.state[role].policy),
      length(aws_iam_role_policy.read[role].policy),
      length(aws_iam_role_policy.identity_read[role].policy),
      try(length(aws_iam_role_policy.deploy[role].policy), 0),
      try(length(aws_iam_role_policy.identity_deploy[role].policy), 0),
      role == "test" ? length(aws_iam_role_policy.tests.policy) : 0
    ]) <= 10240])
    error_message = "Combined inline policy size exceeds the role quota."
  }
  assert {
    condition     = alltrue([for role in values(aws_iam_role.ci) : role.max_session_duration == 7200])
    error_message = "Explicit short-session limit required."
  }
  assert {
    condition     = alltrue([for v in values(aws_s3_bucket_versioning.storage) : v.versioning_configuration[0].status == "Enabled"])
    error_message = "State and artifact buckets must be versioned."
  }
}
