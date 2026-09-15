variable "account_id" { type = string }
variable "region" { type = string }
variable "boundary_arn" { type = string }
variable "artifact_bucket" { type = string }
variable "artifact_key" { type = string }
variable "artifact_version" { type = string }
variable "artifact_sha256_base64" { type = string }
variable "ses_email" { type = string }
variable "ses_identity_arn" { type = string }
variable "alarm_email" { type = string }
variable "cors_origins" { type = set(string) }
variable "monthly_budget_usd" { type = number }
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
variable "run_id" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9-]{1,24}$", var.run_id))
    error_message = "A run-specific ID is mandatory."
  }
}
