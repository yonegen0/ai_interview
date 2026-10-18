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

run "bedrock_disabled_by_default" {
  command = plan
  assert {
    condition     = length(jsondecode(aws_iam_policy.runtime_boundary.policy).Statement) == 5
    error_message = "Default boundary must match the pre-Bedrock policy."
  }
}

run "bedrock_opt_in_is_worker_only" {
  command = plan
  variables { worker_bedrock_enabled = true }
  assert {
    condition = (
      length(jsondecode(aws_iam_policy.runtime_boundary.policy).Statement) == 7 &&
      jsondecode(aws_iam_policy.runtime_boundary.policy).Statement[5].Condition.ArnLike["aws:PrincipalArn"] == "arn:aws:iam::123456789012:role/ai-interview-*-worker-runtime" &&
      jsondecode(aws_iam_policy.runtime_boundary.policy).Statement[6].Condition.StringEquals["bedrock:InferenceProfileArn"] == "arn:aws:bedrock:ap-northeast-1:123456789012:inference-profile/jp.anthropic.claude-haiku-5-5"
    )
    error_message = "Bedrock opt-in must add only the JP Worker profile and conditioned FM."
  }
}

run "wif_and_bedrock_keep_independent_conditions" {
  command = plan
  variables {
    worker_wif_enabled     = true
    worker_bedrock_enabled = true
  }
  assert {
    condition = (
      length(jsondecode(aws_iam_policy.runtime_boundary.policy).Statement) == 8 &&
      jsondecode(aws_iam_policy.runtime_boundary.policy).Statement[5].Condition.ArnEquals["aws:PrincipalArn"] == "arn:aws:iam::123456789012:role/ai-interview-dev-worker-runtime" &&
      jsondecode(aws_iam_policy.runtime_boundary.policy).Statement[7].Condition.StringEquals["bedrock:InferenceProfileArn"] == "arn:aws:bedrock:ap-northeast-1:123456789012:inference-profile/jp.anthropic.claude-haiku-5-5"
    )
    error_message = "The WIF and Bedrock grants must stay independent."
  }
}
