variable "isolation_operator_arn" {
  description = "Exact approved deployment role allowed to manage invite resource policies."
  type        = string
  default     = ""
  validation {
    condition = var.deployment_generation == "" ? var.isolation_operator_arn == "" : (
      can(regex("^arn:aws:iam::${var.account_id}:role/[A-Za-z0-9/+=,.@_-]+$", var.isolation_operator_arn)) &&
      !strcontains(var.isolation_operator_arn, "ai-interview-dev-") && !endswith(var.isolation_operator_arn, "-runtime")
    )
    error_message = "Invite isolation requires a same-account operator role, never a legacy runtime."
  }
}
locals {
  isolation_enabled = var.deployment_generation != ""
  # Exceptions to Deny do not grant data access. Identity IAM and boundary still apply.
  isolation_runtime_roles = [for role in keys(local.function_arns) : "arn:aws:iam::${var.account_id}:role/${local.prefix}-${role}-runtime"]
  isolation_trusted_roles = concat(local.isolation_runtime_roles, [var.isolation_operator_arn])
}
resource "aws_dynamodb_resource_policy" "isolation_table" {
  count        = local.isolation_enabled ? 1 : 0
  resource_arn = aws_dynamodb_table.main.arn
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Sid       = "RejectOtherGenerations", Effect = "Deny", Principal = "*", Action = "dynamodb:*",
    Resource  = [local.table_arn, "${local.table_arn}/index/*"],
    Condition = { ArnNotEquals = { "aws:PrincipalArn" = local.isolation_trusted_roles } }
  }] })
}
resource "aws_dynamodb_resource_policy" "isolation_stream" {
  count        = local.isolation_enabled ? 1 : 0
  resource_arn = aws_dynamodb_table.main.stream_arn
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Sid       = "RejectOtherGenerations", Effect = "Deny", Principal = "*", Action = "dynamodb:*",
    Resource  = aws_dynamodb_table.main.stream_arn,
    Condition = { ArnNotEquals = { "aws:PrincipalArn" = ["arn:aws:iam::${var.account_id}:role/${local.prefix}-dispatcher-runtime", var.isolation_operator_arn] } }
  }] })
}
resource "aws_sqs_queue_policy" "isolation" {
  for_each  = local.isolation_enabled ? { main = aws_sqs_queue.main, worker_dlq = aws_sqs_queue.worker_dlq, stream_failure = aws_sqs_queue.stream_failure } : {}
  queue_url = each.value.url
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Sid = "RejectOtherGenerations", Effect = "Deny", Principal = "*", Action = "sqs:*", Resource = each.value.arn,
    # AWS service delivery/redrive remains governed by identity/source/redrive policies.
    Condition = { ArnNotEquals = { "aws:PrincipalArn" = local.isolation_trusted_roles }, Bool = { "aws:PrincipalIsAWSService" = "false" } }
  }] })
}
