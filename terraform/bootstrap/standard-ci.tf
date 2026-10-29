# Additive migration. Existing roles remain usable until the separately approved
# retirement step; never use the old Apply002 or a dev service Plan for this root.
variable "standard_ci_enabled" {
  type    = bool
  default = false
}
variable "legacy_ci_retired" {
  type    = bool
  default = false
  validation {
    condition     = !var.legacy_ci_retired || var.standard_ci_enabled
    error_message = "Create and qualify the standard roles before retiring legacy trust."
  }
}
variable "standard_ci_stage_log_delivery_enabled" {
  type        = bool
  default     = false
  description = "Explicitly approved HTTP API access-log delivery permissions for the standard dev deploy role."
  validation {
    condition     = !var.standard_ci_stage_log_delivery_enabled || var.standard_ci_enabled
    error_message = "Stage log delivery requires the standard CI roles."
  }
}
locals {
  standard_ci_environments = {
    artifact-plan  = "dev-plan"
    artifact-apply = "dev-apply"
    plan           = "dev-plan"
    deploy         = "dev-apply"
  }
  standard_ci_roles = var.standard_ci_enabled ? local.standard_ci_environments : {}
  standard_ci_policies = merge({
    for role in ["plan", "deploy"] : role => concat(
      jsondecode(aws_iam_role_policy.state[role].policy).Statement,
      jsondecode(aws_iam_role_policy.read[role].policy).Statement,
      jsondecode(aws_iam_role_policy.identity_read[role].policy).Statement,
      [for statement in jsondecode(aws_iam_role_policy.deploy["deploy"].policy).Statement : statement if role == "deploy"],
      [for statement in jsondecode(aws_iam_role_policy.identity_deploy["deploy"].policy).Statement : statement if role == "deploy"],
      role == "deploy" && var.standard_ci_stage_log_delivery_enabled ? [{
        Sid       = "DevStageLogDelivery"
        Effect    = "Allow"
        Action    = ["logs:CreateLogDelivery", "logs:PutResourcePolicy", "logs:DescribeResourcePolicies", "logs:ListLogDeliveries", "logs:GetLogDelivery"]
        Resource  = ["*"]
        Condition = { StringEquals = { "aws:RequestedRegion" = var.region } }
      }] : []
    )
    }, {
    artifact-plan = [
      { Effect = "Allow", Action = ["s3:GetBucketLocation"], Resource = [local.artifact_arn] },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:GetObjectVersion"], Resource = ["${local.artifact_arn}/lambda/*", "${local.artifact_arn}/plans/*"] },
      { Effect = "Allow", Action = ["s3:PutObject"], Resource = ["${local.artifact_arn}/lambda/*/app.zip", "${local.artifact_arn}/plans/*/dev.tfplan", "${local.artifact_arn}/plans/*/plan.json", "${local.artifact_arn}/plans/*/summary.json", "${local.artifact_arn}/plans/*/review.private.json", "${local.artifact_arn}/plans/*/envelope.json"] }
    ]
    artifact-apply = [
      { Effect = "Allow", Action = ["s3:GetBucketLocation"], Resource = [local.artifact_arn] },
      { Effect = "Allow", Action = ["s3:ListBucket"], Resource = [local.artifact_arn], Condition = { StringLike = { "s3:prefix" = ["plans/*"] } } },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:GetObjectVersion"], Resource = ["${local.artifact_arn}/plans/*"] },
      { Effect = "Allow", Action = ["s3:PutObject"], Resource = ["${local.artifact_arn}/plans/*/apply-started.json", "${local.artifact_arn}/plans/*/apply-completed.json", "${local.artifact_arn}/plans/*/deployment.json"] }
    ]
  })
}
resource "aws_iam_role" "standard_ci" {
  for_each             = local.standard_ci_roles
  name                 = "ai-interview-standard-ci-${each.key}"
  max_session_duration = 3600
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Allow", Action = "sts:AssumeRoleWithWebIdentity",
    Principal = { Federated = var.oidc_provider_arn == "" ? aws_iam_openid_connect_provider.github[0].arn : var.oidc_provider_arn },
    Condition = { StringEquals = {
      "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub" = "repo:yonegen0@76547980/ai_interview@1361325921:environment:${each.value}"
    } }
  }] })
  tags = local.tags
  lifecycle { prevent_destroy = true }
}
resource "aws_iam_role_policy" "standard_ci" {
  for_each = local.standard_ci_roles
  role     = aws_iam_role.standard_ci[each.key].id
  name     = "standard-${each.key}"
  policy   = jsonencode({ Version = "2012-10-17", Statement = local.standard_ci_policies[each.key] })
}
output "standard_ci_roles" {
  value = var.standard_ci_enabled ? { for name, role in aws_iam_role.standard_ci : name => role.arn } : null
}
