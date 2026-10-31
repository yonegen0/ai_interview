# Explicit Claude direct API secret grant, Worker only. No secret value in Terraform.
locals {
  anthropic_worker_statements = lookup(var.worker_ai_environment, "INTERVIEW_AI_PROVIDER", "") == "anthropic" ? [
    {
      Sid      = "WorkerAnthropicSecret"
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [var.worker_ai_environment["INTERVIEW_ANTHROPIC_SECRET_ARN"]]
    }
  ] : []
}
