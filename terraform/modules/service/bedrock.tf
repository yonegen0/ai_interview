# Candidate JP Geo profile permissions. Verify all ARNs via GetInferenceProfile before Apply.
locals {
  bedrock_profile_arn = "arn:aws:bedrock:${var.region}:${var.account_id}:inference-profile/jp.anthropic.claude-haiku-5-5"
  bedrock_model_arns = [
    "arn:aws:bedrock:ap-northeast-1::foundation-model/anthropic.claude-haiku-5-5",
    "arn:aws:bedrock:ap-northeast-3::foundation-model/anthropic.claude-haiku-5-5"
  ]
  bedrock_worker_statements = [for statement in [
    {
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel"]
      Resource = [local.bedrock_profile_arn]
    },
    {
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel"]
      Resource = local.bedrock_model_arns
      Condition = {
        StringEquals = { "bedrock:InferenceProfileArn" = local.bedrock_profile_arn }
      }
    }
  ] : statement if lookup(var.worker_ai_environment, "INTERVIEW_AI_PROVIDER", "") == "bedrock"]
}
