variable "worker_wif_enabled" {
  type    = bool
  default = false
  validation {
    condition     = !var.worker_wif_enabled || (var.run_id == "" && var.region == "ap-northeast-1")
    error_message = "Federation grant is limited to the dev Worker in Tokyo."
  }
}
locals {
  worker_wif_statements = var.worker_wif_enabled ? [{
    Sid = "WorkerOpenAIWIF", Effect = "Allow", Action = ["sts:GetWebIdentityToken"], Resource = ["*"],
    Condition = {
      "ForAllValues:StringEquals" = { "sts:IdentityTokenAudience" = ["https://api.openai.com/v1"] }
      NumericLessThanEquals       = { "sts:DurationSeconds" = 300 }
      StringEquals                = { "sts:SigningAlgorithm" = "ES384" }
      Null                        = { "sts:IdentityTokenAudience" = "false", "sts:DurationSeconds" = "false", "sts:SigningAlgorithm" = "false" }
    }
  }] : []
}
