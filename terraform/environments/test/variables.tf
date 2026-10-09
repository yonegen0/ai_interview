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

variable "log_usage" {
  type    = string
  default = "developer"
  validation {
    condition     = contains(["developer", "customer"], var.log_usage)
    error_message = "Declare developer-only or customer use explicitly; customer logs retain 14 days."
  }
}
variable "test_monitoring_enabled" {
  type    = bool
  default = true
  validation {
    condition     = (var.test_monitoring_enabled || (var.run_id != "" && var.test_closure_confirmed && local.test_closure_evidence_valid && !anytrue([var.api_enabled, var.worker_enabled, var.streams_enabled, var.scheduler_enabled]))) && (!var.test_closure_confirmed || (var.run_id != "" && !anytrue([var.api_enabled, var.worker_enabled, var.streams_enabled, var.scheduler_enabled])))
    error_message = "Test alarms may close only after verified closure with all four entry flags disabled."
  }
}
variable "test_closure_confirmed" {
  type    = bool
  default = false
}

variable "test_closure_evidence_path" {
  type    = string
  default = ""
}
variable "test_closure_evidence_sha256" {
  type    = string
  default = ""
}
locals {
  test_closure_evidence = try(jsondecode(file(var.test_closure_evidence_path)), {})
  test_closure_evidence_valid = try(
    var.test_closure_evidence_path != "" &&
    filesha256(var.test_closure_evidence_path) == var.test_closure_evidence_sha256 &&
    can(regex("^[0-9a-f]{64}$", var.test_closure_evidence_sha256)) &&
    local.test_closure_evidence.status == "APPROVED_TEST_DRAIN" &&
    local.test_closure_evidence.account_id == var.account_id &&
    local.test_closure_evidence.region == var.region &&
    local.test_closure_evidence.run_id == var.run_id &&
    local.test_closure_evidence.alarm_count == 39 &&
    local.test_closure_evidence.approved_by != local.test_closure_evidence.observed_by &&
    length(local.test_closure_evidence.approved_by) > 0 &&
    can(regex("^[0-9a-f]{64}$", local.test_closure_evidence.manifest_sha256)) &&
    can(regex("^[0-9a-f]{64}$", local.test_closure_evidence.state_identity.sha256)) &&
    length(local.test_closure_evidence.state_identity.lineage) > 0 &&
    local.test_closure_evidence.state_identity.serial >= 0 &&
    local.test_closure_evidence.state_identity.version_id != "null" &&
    length(local.test_closure_evidence.state_identity.version_id) > 0 &&
    local.test_closure_evidence.expires_at_epoch - local.test_closure_evidence.issued_at_epoch > 0 &&
    local.test_closure_evidence.expires_at_epoch - local.test_closure_evidence.issued_at_epoch <= 900 &&
    timecmp(plantimestamp(), local.test_closure_evidence.issued_at) >= 0 &&
    timecmp(plantimestamp(), local.test_closure_evidence.expires_at) < 0,
    false
  )
}
