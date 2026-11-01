# Prepare BEFORE concurrency=0/quarantine. No consumer, event source or redrive.
variable "legacy_preservation_enabled" {
  type    = bool
  default = false
}
locals {
  legacy_archive_arn = "arn:aws:sqs:${local.region}:${var.account_id}:ai-interview-legacy-archive-g1"
  legacy_roles       = [for role in ["api", "admin", "worker", "dispatcher"] : "arn:aws:iam::${var.account_id}:role/ai-interview-dev-${role}-runtime"]
}
resource "aws_sqs_queue" "legacy_archive" {
  count                     = var.legacy_preservation_enabled ? 1 : 0
  name                      = "ai-interview-legacy-archive-g1"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
  lifecycle { prevent_destroy = true }
  tags = { Project = "ai-interview", Environment = "legacy-preservation", ManagedBy = "Terraform" }
}
resource "aws_sqs_queue_policy" "legacy_archive" {
  count     = var.legacy_preservation_enabled ? 1 : 0
  queue_url = aws_sqs_queue.legacy_archive[0].url
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Sid       = "OnlyLegacyPreservationAndOperator", Effect = "Deny", Principal = "*", Action = "sqs:*", Resource = local.legacy_archive_arn,
    Condition = { ArnNotEquals = { "aws:PrincipalArn" = concat(local.legacy_roles, [var.deployment_role_arn]) }, Bool = { "aws:PrincipalIsAWSService" = "false" } }
  }] })
}
resource "aws_iam_role_policy" "legacy_preservation_delivery" {
  for_each = var.legacy_preservation_enabled ? toset(["api", "admin", "worker", "dispatcher"]) : toset([])
  name     = "invite-g1-legacy-preservation"
  role     = "ai-interview-dev-${each.key}-runtime"
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Sid = "PreserveNativeAsyncFailuresOnly", Effect = "Allow", Action = ["sqs:SendMessage"], Resource = local.legacy_archive_arn
  }] })
  depends_on = [aws_sqs_queue_policy.legacy_archive]
  lifecycle { prevent_destroy = true }
}
variable "legacy_async_targets" {
  description = "Only readback-confirmed missing async configs; never overwrite an existing destination."
  type = map(object({
    function_name = string
    qualifier     = string
  }))
  default = {}
  validation {
    condition = (var.legacy_preservation_enabled || length(var.legacy_async_targets) == 0) && length(distinct([
      for target in values(var.legacy_async_targets) : "${target.function_name}:${target.qualifier == "" ? "$LATEST" : target.qualifier}"
      ])) == length(var.legacy_async_targets) && alltrue([
      for target in values(var.legacy_async_targets) :
      can(regex("^ai-interview-dev-(api|admin|worker|dispatcher)$", target.function_name)) &&
      (contains(["", "$LATEST", "live", "streams", "recovery"], target.qualifier) || can(regex("^[1-9][0-9]*$", target.qualifier)))
    ])
    error_message = "Preservation targets must be confirmed legacy function/version/alias configurations."
  }
}
resource "aws_lambda_function_event_invoke_config" "legacy_preservation" {
  for_each                     = var.legacy_async_targets
  function_name                = each.value.function_name
  qualifier                    = each.value.qualifier == "" ? null : each.value.qualifier
  maximum_retry_attempts       = 0
  maximum_event_age_in_seconds = 21600
  destination_config {
    on_failure { destination = local.legacy_archive_arn }
  }
  depends_on = [aws_iam_role_policy.legacy_preservation_delivery]
  lifecycle { prevent_destroy = true }
}
