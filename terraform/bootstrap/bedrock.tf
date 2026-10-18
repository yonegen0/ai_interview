# The permissions boundary is shared: add Bedrock only with an explicit opt-in.
variable "worker_bedrock_enabled" {
  type    = bool
  default = false
}

locals {
  worker_bedrock_profile_arn = "arn:aws:bedrock:${var.region}:${var.account_id}:inference-profile/jp.anthropic.claude-haiku-5-5"
  worker_bedrock_model_arns = [
    "arn:aws:bedrock:ap-northeast-1::foundation-model/anthropic.claude-haiku-5-5",
    "arn:aws:bedrock:ap-northeast-3::foundation-model/anthropic.claude-haiku-5-5"
  ]
  worker_bedrock_principal = "arn:aws:iam::${var.account_id}:role/ai-interview-*-worker-runtime"
  worker_bedrock_boundary_statements = [for statement in [
    {
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel"]
      Resource = [local.worker_bedrock_profile_arn]
      Condition = {
        ArnLike = { "aws:PrincipalArn" = local.worker_bedrock_principal }
      }
    },
    {
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel"]
      Resource = local.worker_bedrock_model_arns
      Condition = {
        StringEquals = { "bedrock:InferenceProfileArn" = local.worker_bedrock_profile_arn }
        ArnLike      = { "aws:PrincipalArn" = local.worker_bedrock_principal }
      }
    }
  ] : statement if var.worker_bedrock_enabled]
}
