terraform {
  required_version = "= 1.14.9"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}
provider "aws" {
  region              = var.region
  allowed_account_ids = [var.account_id]
}
variable "account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "Explicit account ID required."
  }
}
variable "region" {
  type    = string
  default = "ap-northeast-1"
  validation {
    condition     = var.region == "ap-northeast-1"
    error_message = "P4 dev uses Tokyo; region changes require a separate decision."
  }
}
variable "oidc_provider_arn" {
  type    = string
  default = ""
}
variable "oidc_subjects" {
  type = map(string)
  validation {
    condition     = toset(keys(var.oidc_subjects)) == toset(["artifact", "plan", "deploy", "test"]) && alltrue([for s in values(var.oidc_subjects) : can(regex("^repo:yonegen0(@[0-9]+)?/ai_interview(@[0-9]+)?:environment:dev$", s))])
    error_message = "Exact verified dev subjects for artifact/plan/deploy/test are required."
  }
}
locals {
  prefix  = "ai-interview"
  buckets = { state = "ai-interview-state-${var.account_id}-${var.region}", artifacts = "ai-interview-artifacts-${var.account_id}-${var.region}" }
  tags    = { Project = "ai-interview", Environment = "bootstrap", ManagedBy = "Terraform" }
}
resource "aws_s3_bucket" "storage" {
  for_each      = local.buckets
  bucket        = each.value
  force_destroy = false
  lifecycle { prevent_destroy = true }
  tags = local.tags
}
resource "aws_s3_bucket_versioning" "storage" {
  for_each = local.buckets
  bucket   = aws_s3_bucket.storage[each.key].id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "storage" {
  for_each = local.buckets
  bucket   = aws_s3_bucket.storage[each.key].id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_public_access_block" "storage" {
  for_each                = local.buckets
  bucket                  = aws_s3_bucket.storage[each.key].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_policy" "tls" {
  for_each = local.buckets
  bucket   = aws_s3_bucket.storage[each.key].id
  policy   = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.storage[each.key].arn, "${aws_s3_bucket.storage[each.key].arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } }] })
}
resource "aws_iam_openid_connect_provider" "github" {
  count          = var.oidc_provider_arn == "" ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  tags           = local.tags
}
resource "aws_iam_policy" "runtime_boundary" {
  name = "ai-interview-runtime-boundary"
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:ConditionCheckItem", "dynamodb:Query", "dynamodb:DescribeStream", "dynamodb:GetRecords", "dynamodb:GetShardIterator"], Resource = ["arn:aws:dynamodb:${var.region}:${var.account_id}:table/ai-interview-*"] },
    { Effect = "Allow", Action = ["dynamodb:ListStreams"], Resource = ["*"] },
    { Effect = "Allow", Action = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = ["arn:aws:sqs:${var.region}:${var.account_id}:ai-interview-*"] },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = ["arn:aws:logs:${var.region}:${var.account_id}:log-group:/aws/lambda/ai-interview-*:*"] },
    { Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = ["arn:aws:lambda:${var.region}:${var.account_id}:function:ai-interview-*-dispatcher:recovery"] }
  ] })
  tags = local.tags
}
resource "aws_iam_role" "ci" {
  for_each             = var.oidc_subjects
  name                 = "ai-interview-ci-${each.key}"
  max_session_duration = 7200
  assume_role_policy   = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRoleWithWebIdentity", Principal = { Federated = var.oidc_provider_arn == "" ? aws_iam_openid_connect_provider.github[0].arn : var.oidc_provider_arn }, Condition = { StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com", "token.actions.githubusercontent.com:sub" = each.value } } }] })
  tags                 = local.tags
}
output "state_bucket" { value = aws_s3_bucket.storage["state"].id }
output "artifact_bucket" { value = aws_s3_bucket.storage["artifacts"].id }
output "oidc_provider_arn" { value = var.oidc_provider_arn == "" ? aws_iam_openid_connect_provider.github[0].arn : var.oidc_provider_arn }
output "boundary_arn" { value = aws_iam_policy.runtime_boundary.arn }
output "roles" { value = { for name, role in aws_iam_role.ci : name => role.arn } }
