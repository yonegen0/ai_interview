# A separate Bootstrap Apply is required before enabling the service Worker grant.
# Only the named dev Worker may cross the permissions boundary.
variable "worker_bedrock_enabled" {
  type    = bool
  default = false
}
locals {
  bedrock_profile_arn = "arn:aws:bedrock:ap-northeast-1:${var.account_id}:inference-profile/jp.anthropic.claude-haiku-5-5"
  bedrock_model_arns = [
    "arn:aws:bedrock:ap-northeast-1::foundation-model/anthropic.claude-haiku-5-5",
    "arn:aws:bedrock:ap-northeast-3::foundation-model/anthropic.claude-haiku-5-5",
  ]
  bedrock_dev_worker = "arn:aws:iam::${var.account_id}:role/ai-interview-dev-worker-runtime"
  worker_bedrock_boundary_statements = var.worker_bedrock_enabled ? [
    {
      Sid = "WorkerHaiku55Profile", Effect = "Allow", Action = ["bedrock:InvokeModel"],
      Resource = [local.bedrock_profile_arn],
      Condition = { ArnEquals = { "aws:PrincipalArn" = local.bedrock_dev_worker } }
    },
    {
      Sid = "WorkerHaiku55Models", Effect = "Allow", Action = ["bedrock:InvokeModel"],
      Resource = local.bedrock_model_arns,
      Condition = {
        ArnEquals = { "aws:PrincipalArn" = local.bedrock_dev_worker }
        StringEquals = { "bedrock:InferenceProfileArn" = local.bedrock_profile_arn }
      }
    }
  ] : []
}
