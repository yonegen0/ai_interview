variable "account_id" { type = string }
variable "deployment_role_arn" {
  description = "Exact approved operator role; cannot be an ai-interview runtime or wildcard."
  type        = string
  validation {
    condition     = can(regex("^arn:aws:iam::${var.account_id}:role/[A-Za-z0-9/+=,.@_-]+$", var.deployment_role_arn)) && !strcontains(var.deployment_role_arn, "ai-interview-dev-") && !endswith(var.deployment_role_arn, "-runtime")
    error_message = "Use the approved same-account deployment role, never a legacy runtime role."
  }
}
variable "anthropic_workspace_id" {
  description = "Dedicated new Anthropic workspace. Key is injected separately, never into State."
  type        = string
  validation {
    condition     = can(regex("^wrkspc_[A-Za-z0-9]+$", var.anthropic_workspace_id))
    error_message = "An explicit dedicated Anthropic workspace ID is required."
  }
}
variable "artifact_bucket" { type = string }
variable "artifact_key" { type = string }
variable "artifact_version" { type = string }
variable "artifact_sha256_base64" { type = string }
variable "ses_email" { type = string }
variable "ses_identity_arn" { type = string }
variable "alarm_email" { type = string }
variable "cors_origins" {
  description = "Optional extra HTTPS origins; the dedicated CloudFront origin is always included."
  type        = set(string)
  default     = []
  validation {
    condition     = alltrue([for origin in var.cors_origins : can(regex("^https://[^/*]+$", origin))])
    error_message = "Invite service requires explicit HTTPS origins."
  }
}
variable "monthly_budget_usd" {
  description = "AWS notification threshold only, not a hard cap or Anthropic budget."
  type        = number
  validation {
    condition     = var.monthly_budget_usd > 0 && var.monthly_budget_usd <= 10
    error_message = "Invite MVP notification threshold must be positive and at most USD10."
  }
}
variable "api_enabled" {
  type    = bool
  default = false
}
variable "worker_enabled" {
  type    = bool
  default = false
}
variable "streams_enabled" {
  type    = bool
  default = false
}
variable "scheduler_enabled" {
  type    = bool
  default = false
}
variable "frontend_enabled" {
  type    = bool
  default = false
}
