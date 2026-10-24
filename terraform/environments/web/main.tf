terraform {
  required_version = "= 1.14.9"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
  backend "s3" { key = "web/terraform.tfstate" }
}
variable "account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "Use the verified development Account ID."
  }
}
variable "enabled" {
  type    = bool
  default = false
}
provider "aws" {
  region              = "ap-northeast-1"
  allowed_account_ids = [var.account_id]
  max_retries         = 0
}
module "frontend" {
  source      = "../../modules/frontend"
  bucket_name = "ai-interview-web-${var.account_id}-ap-northeast-1"
  enabled     = var.enabled
}
output "frontend" {
  value = { bucket_name = module.frontend.bucket_name, distribution_id = module.frontend.distribution_id, origin = module.frontend.origin, enabled = module.frontend.enabled }
}
