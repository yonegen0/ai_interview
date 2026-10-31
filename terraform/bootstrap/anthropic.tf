# Bootstrap owns the shared runtime permissions boundary.
# Leave disabled until the exact Claude secret ARN and bootstrap Apply are approved.
variable "worker_anthropic_secret_arn" {
  type    = string
  default = ""
  validation {
    condition = var.worker_anthropic_secret_arn == "" || can(regex(
      "^arn:aws:secretsmanager:${var.region}:${var.account_id}:secret:[A-Za-z0-9/_+=.@-]+$",
      var.worker_anthropic_secret_arn
    ))
    error_message = "The Anthropic secret ARN must belong to the approved account and region."
  }
}
locals {
  worker_anthropic_boundary_statements = var.worker_anthropic_secret_arn == "" ? [] : [
    {
      Sid      = "WorkerAnthropicSecret"
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [var.worker_anthropic_secret_arn]
      Condition = {
        ArnEquals = {
          "aws:PrincipalArn" = "arn:aws:iam::${var.account_id}:role/ai-interview-dev-worker-runtime"
        }
      }
    }
  ]
}
