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

run "test_drain_read_scope" {
  command = apply
  assert {
    condition = jsondecode(aws_iam_role_policy.tests.policy).Statement[0] == {
      Sid      = "TestDrainInventory", Effect = "Allow", Action = ["dynamodb:Scan"],
      Resource = ["arn:aws:dynamodb:ap-northeast-1:123456789012:table/ai-interview-test-*-main"]
    }
    error_message = "Base Scan must target synthetic test tables only, never dev, P3, or indexes."
  }
  assert {
    condition = toset(jsondecode(aws_iam_role_policy.tests.policy).Statement[1].Resource) == toset([
      "arn:aws:lambda:ap-northeast-1:123456789012:function:ai-interview-test-*-api:live",
      "arn:aws:lambda:ap-northeast-1:123456789012:function:ai-interview-test-*-admin:live",
      "arn:aws:lambda:ap-northeast-1:123456789012:function:ai-interview-test-*-worker:live",
      "arn:aws:lambda:ap-northeast-1:123456789012:function:ai-interview-test-*-dispatcher:streams",
      "arn:aws:lambda:ap-northeast-1:123456789012:function:ai-interview-test-*-dispatcher:recovery"
    ]) && jsondecode(aws_iam_role_policy.tests.policy).Statement[1].Action == ["lambda:GetFunctionEventInvokeConfig"]
    error_message = "Async read must cover exactly the five test aliases without invoke/write grants."
  }
  assert {
    condition = (jsondecode(aws_iam_role_policy.tests.policy).Statement[3].Resource == ["${aws_s3_bucket.storage["state"].arn}/test/*/terraform.tfstate"] &&
      toset(jsondecode(aws_iam_role_policy.tests.policy).Statement[3].Action) == toset(["s3:GetObject", "s3:GetObjectVersion"]) &&
      jsondecode(aws_iam_role_policy.tests.policy).Statement[4].Resource == ["${aws_s3_bucket.storage["state"].arn}/test/*/terraform.tfstate.tflock"] &&
    jsondecode(aws_iam_role_policy.tests.policy).Statement[4].Action == ["s3:GetObject"])
    error_message = "Read State at a fixed version and current lock only; never grant State writes."
  }
  assert {
    condition = (jsondecode(aws_iam_role_policy.tests.policy).Statement[2].Action == ["s3:ListBucket"] &&
      jsondecode(aws_iam_role_policy.tests.policy).Statement[2].Resource == [aws_s3_bucket.storage["state"].arn] &&
    alltrue([for role in ["plan", "deploy"] : !contains(flatten([for s in jsondecode(aws_iam_role_policy.read[role].policy).Statement : s.Action]), "dynamodb:Scan") && !contains(flatten([for s in jsondecode(aws_iam_role_policy.read[role].policy).Statement : s.Action]), "lambda:GetFunctionEventInvokeConfig")]))
    error_message = "Absent lock metadata needs the one bucket; other CI roles must not gain drain reads."
  }
  assert {
    condition = (alltrue([for role in values(aws_iam_role.ci) : jsondecode(role.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com" &&
      jsondecode(role.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:yonegen0/ai_interview:environment:dev"]) &&
    !contains(flatten([for s in jsondecode(aws_iam_policy.runtime_boundary.policy).Statement : s.Action]), "dynamodb:Scan"))
    error_message = "OIDC trust and runtime boundary must remain unchanged; runtime must not gain Scan."
  }
}
