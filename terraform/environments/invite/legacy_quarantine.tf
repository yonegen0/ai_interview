# Opt-in only after preserving pending work and approving the exact saved plan.
# Stops known legacy writers and model/credential acquisition. It does not revoke a
# cached third-party key: freeze the four Lambdas and revoke that key before enablement.
variable "legacy_quarantine_enabled" {
  type    = bool
  default = false
  validation {
    condition     = var.legacy_quarantine_enabled || !anytrue([var.api_enabled, var.worker_enabled, var.streams_enabled, var.scheduler_enabled, var.frontend_enabled])
    error_message = "Invite entry points require legacy quarantine; evidence/readback is also required operationally."
  }
  validation {
    condition     = !var.legacy_quarantine_enabled || var.legacy_preservation_enabled
    error_message = "Prepare and independently verify native async preservation before quarantine."
  }
}
resource "aws_iam_role_policy" "legacy_quarantine" {
  for_each = var.legacy_quarantine_enabled ? toset(["api", "admin", "worker", "dispatcher", "scheduler"]) : toset([])
  name     = "invite-g1-legacy-quarantine"
  role     = "ai-interview-dev-${each.key}-runtime"
  lifecycle { prevent_destroy = true }
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Sid    = "FreezeLegacySideEffects", Effect = "Deny", Resource = "*",
    Action = ["dynamodb:*", "lambda:InvokeFunction", "bedrock:*", "secretsmanager:GetSecretValue", "secretsmanager:BatchGetSecretValue", "sts:GetWebIdentityToken", "sts:AssumeRole"]
    }, {
    Sid = "BlockWorkQueues", Effect = "Deny", Action = "sqs:*", NotResource = local.legacy_archive_arn
    }, {
    Sid = "ArchiveIsSendOnly", Effect = "Deny", NotAction = "sqs:SendMessage", Resource = local.legacy_archive_arn
  }] })
  depends_on = [aws_iam_role_policy.legacy_preservation_delivery, aws_lambda_function_event_invoke_config.legacy_preservation]
}
