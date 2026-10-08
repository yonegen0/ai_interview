# Shared boundary stays owned by bootstrap. This never enables account federation.
variable "worker_wif_enabled" {
  type    = bool
  default = false
}
locals {
  worker_wif_boundary_statements = var.worker_wif_enabled ? [{
    Sid = "WorkerOpenAIWIF", Effect = "Allow", Action = ["sts:GetWebIdentityToken"], Resource = ["*"],
    Condition = {
      "ForAllValues:StringEquals" = { "sts:IdentityTokenAudience" = ["https://api.openai.com/v1"] }
      NumericLessThanEquals       = { "sts:DurationSeconds" = 300 }
      StringEquals                = { "sts:SigningAlgorithm" = "ES384" }
      Null                        = { "sts:IdentityTokenAudience" = "false", "sts:DurationSeconds" = "false", "sts:SigningAlgorithm" = "false" }
      ArnEquals                   = { "aws:PrincipalArn" = "arn:aws:iam::${var.account_id}:role/ai-interview-dev-worker-runtime" }
    }
  }] : []
}
