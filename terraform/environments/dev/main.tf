terraform {
  required_version = "= 1.14.9"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
  backend "s3" {}
}
provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]
}
module "service" {
  source                 = "../../modules/service"
  account_id             = var.account_id
  region                 = var.region
  boundary_arn           = var.boundary_arn
  artifact_bucket        = var.artifact_bucket
  artifact_key           = var.artifact_key
  artifact_version       = var.artifact_version
  artifact_sha256_base64 = var.artifact_sha256_base64
  ses_email              = var.ses_email
  ses_identity_arn       = var.ses_identity_arn
  alarm_email            = var.alarm_email
  cors_origins           = var.cors_origins
  monthly_budget_usd     = var.monthly_budget_usd
  worker_enabled         = var.worker_enabled
  streams_enabled        = var.streams_enabled
  scheduler_enabled      = var.scheduler_enabled
  api_enabled            = var.api_enabled
}
output "manifest" { value = module.service.manifest }
