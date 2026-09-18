variable "account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "Explicit account ID required."
  }
}
variable "region" {
  type = string
  validation {
    condition     = var.region == "ap-northeast-1"
    error_message = "P4 dev uses Tokyo."
  }
}
variable "run_id" {
  type    = string
  default = ""
  validation {
    condition     = var.run_id == "" || can(regex("^[a-z0-9-]{1,24}$", var.run_id))
    error_message = "Run ID must be a short lowercase identifier."
  }
}
variable "boundary_arn" { type = string }
variable "artifact_bucket" { type = string }
variable "artifact_key" {
  type = string
  validation {
    condition     = try(can(regex("^lambda/[A-Za-z0-9/_-]+[.]zip$", var.artifact_key)) && !strcontains(var.artifact_key, "REPLACE_ME"), false)
    error_message = "A confirmed lambda/ ZIP key without placeholders is required."
  }
}
variable "artifact_version" {
  type = string
  validation {
    condition     = try(length(var.artifact_version) > 0 && trimspace(var.artifact_version) == var.artifact_version && var.artifact_version != "null" && !strcontains(var.artifact_version, "REPLACE_ME"), false)
    error_message = "An explicit S3 VersionId without whitespace or placeholders is required."
  }
}
variable "artifact_sha256_base64" {
  type = string
  validation {
    condition     = can(regex("^[A-Za-z0-9+/]{43}=$", var.artifact_sha256_base64))
    error_message = "A Base64 SHA-256 digest of the same ZIP is required."
  }
}
variable "ses_email" { type = string }
variable "ses_identity_arn" {
  type = string
  validation {
    condition     = startswith(var.ses_identity_arn, "arn:aws:ses:${var.region}:${var.account_id}:identity/")
    error_message = "The project SES identity must belong to the configured account and region."
  }
}
variable "alarm_email" { type = string }
variable "cors_origins" {
  type = set(string)
  validation {
    condition     = length(var.cors_origins) > 0 && alltrue([for o in var.cors_origins : can(regex("^https?://[^/*]+$", o))])
    error_message = "Explicit origins without wildcards or paths are required."
  }
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
variable "api_enabled" {
  type    = bool
  default = false
}
variable "monthly_budget_usd" {
  type = number
  validation {
    condition     = var.monthly_budget_usd > 0
    error_message = "A positive monthly notification budget is required."
  }
}
locals {
  prefix        = var.run_id == "" ? "ai-interview-dev" : "ai-interview-test-${var.run_id}"
  environment   = var.run_id == "" ? "dev" : "test"
  tags          = { Project = "ai-interview", Environment = local.environment, ManagedBy = "Terraform", RunId = var.run_id }
  table_arn     = "arn:aws:dynamodb:${var.region}:${var.account_id}:table/${local.prefix}-main"
  schedule_arn  = "arn:aws:scheduler:${var.region}:${var.account_id}:schedule/${local.prefix}/recovery"
  function_arns = { for role in ["api", "worker", "dispatcher"] : role => "arn:aws:lambda:${var.region}:${var.account_id}:function:${local.prefix}-${role}" }
}
