# Explicit, separately approved opt-in. Default false preserves closed Stage2 baseline.
variable "worker_bedrock_enabled" {
  type    = bool
  default = false
  validation {
    condition     = !var.worker_bedrock_enabled || (var.run_id == "" && var.region == "ap-northeast-1")
    error_message = "Bedrock grant is restricted to the dev Worker in Tokyo."
  }
}

locals {
  bedrock_model_id   = "anthropic.claude-haiku-5-5"
  bedrock_profile_id = "jp.anthropic.claude-haiku-5-5"
  bedrock_profile_arn = "arn:aws:bedrock:ap-northeast-1:${var.account_id}:inference-profile/${local.bedrock_profile_id}"
  bedrock_model_arns = [
    "arn:aws:bedrock:ap-northeast-1::foundation-model/${local.bedrock_model_id}",
    "arn:aws:bedrock:ap-northeast-3::foundation-model/${local.bedrock_model_id}",
  ]
  worker_bedrock_statements = var.worker_bedrock_enabled ? [
    {
      Sid = "InvokeJapanHaiku55Profile", Effect = "Allow",
      Action = ["bedrock:InvokeModel"], Resource = [local.bedrock_profile_arn]
    },
    {
      Sid = "InvokeJapanHaiku55Models", Effect = "Allow",
      Action = ["bedrock:InvokeModel"], Resource = local.bedrock_model_arns,
      Condition = { StringEquals = { "bedrock:InferenceProfileArn" = local.bedrock_profile_arn } }
    }
  ] : []
}
