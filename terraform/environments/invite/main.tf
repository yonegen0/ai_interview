# Independent state, data, identities and accounting; never import or migrate dev resources.
terraform {
  required_version = "= 1.14.9"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
  backend "s3" { key = "invite/g1/terraform.tfstate" }
}
provider "aws" {
  region              = "ap-northeast-1"
  allowed_account_ids = [var.account_id]
  max_retries         = 0
}
locals {
  generation  = "g1"
  prefix      = "ai-interview-invite-${local.generation}"
  region      = "ap-northeast-1"
  table_arn   = "arn:aws:dynamodb:${local.region}:${var.account_id}:table/${local.prefix}-main"
  queue_arns  = [for name in ["main", "worker-dlq", "stream-failure"] : "arn:aws:sqs:${local.region}:${var.account_id}:${local.prefix}-${name}"]
  worker_role = "arn:aws:iam::${var.account_id}:role/${local.prefix}-worker-runtime"
}

resource "aws_secretsmanager_secret" "claude" {
  name                    = "${local.prefix}-claude"
  description             = "Invite g1 only; inject the dedicated Anthropic workspace key out of Terraform"
  recovery_window_in_days = 30
  lifecycle { prevent_destroy = true }
}
resource "aws_secretsmanager_secret_policy" "claude" {
  secret_arn          = aws_secretsmanager_secret.claude.arn
  block_public_policy = true
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Sid       = "OnlyGenerationWorkerReadsKey", Effect = "Deny", Principal = "*",
    Action    = ["secretsmanager:GetSecretValue", "secretsmanager:BatchGetSecretValue"], Resource = aws_secretsmanager_secret.claude.arn,
    Condition = { ArnNotEquals = { "aws:PrincipalArn" = [local.worker_role] } }
  }] })
}

# Dedicated boundary. Identity policies still decide each role's actual permissions.
resource "aws_iam_policy" "runtime_boundary" {
  name = "${local.prefix}-runtime-boundary"
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:ConditionCheckItem", "dynamodb:Query", "dynamodb:DescribeStream", "dynamodb:GetRecords", "dynamodb:GetShardIterator"], Resource = [local.table_arn, "${local.table_arn}/index/WorkIndex", "${local.table_arn}/stream/*"] },
    { Effect = "Allow", Action = ["dynamodb:ListStreams"], Resource = ["*"] },
    { Effect = "Allow", Action = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = local.queue_arns },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = ["arn:aws:logs:${local.region}:${var.account_id}:log-group:/aws/lambda/${local.prefix}-*:*"] },
    { Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = ["arn:aws:lambda:${local.region}:${var.account_id}:function:${local.prefix}-dispatcher:recovery"] },
    { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = [aws_secretsmanager_secret.claude.arn] }
  ] })
}
module "service" {
  source                 = "../../modules/service"
  deployment_generation  = local.generation
  isolation_operator_arn = var.deployment_role_arn
  account_id             = var.account_id
  region                 = local.region
  boundary_arn           = aws_iam_policy.runtime_boundary.arn
  artifact_bucket        = var.artifact_bucket
  artifact_key           = var.artifact_key
  artifact_version       = var.artifact_version
  artifact_sha256_base64 = var.artifact_sha256_base64
  ses_email              = var.ses_email
  ses_identity_arn       = var.ses_identity_arn
  alarm_email            = var.alarm_email
  cors_origins           = setunion(var.cors_origins, toset([module.frontend.origin]))
  monthly_budget_usd     = var.monthly_budget_usd
  log_usage              = "customer"
  api_enabled            = var.api_enabled
  worker_enabled         = var.worker_enabled
  streams_enabled        = var.streams_enabled
  scheduler_enabled      = var.scheduler_enabled
  worker_ai_environment = {
    INTERVIEW_AI_PROVIDER                    = "anthropic"
    INTERVIEW_ANTHROPIC_ENABLED              = "true"
    INTERVIEW_ANTHROPIC_AUTH                 = "secret"
    INTERVIEW_ANTHROPIC_SECRET_ARN           = aws_secretsmanager_secret.claude.arn
    INTERVIEW_ANTHROPIC_MODEL                = "claude-haiku-5-5"
    INTERVIEW_ANTHROPIC_API_VERSION          = "2026-10-21"
    INTERVIEW_ANTHROPIC_EFFORT               = "medium"
    INTERVIEW_ANTHROPIC_MAX_OUTPUT_TOKENS    = "4096"
    INTERVIEW_ANTHROPIC_MONTHLY_USER_LIMIT   = "20"
    INTERVIEW_ANTHROPIC_MONTHLY_GLOBAL_LIMIT = "600"
    INTERVIEW_ANTHROPIC_WORKSPACE_ID         = var.anthropic_workspace_id
  }
  depends_on = [aws_secretsmanager_secret_policy.claude, aws_iam_role_policy.legacy_quarantine]
}

# Reuse hosting implementation, with independent bucket/distribution and closed default.
module "frontend" {
  source      = "../../modules/frontend"
  bucket_name = "ai-interview-invite-g1-web-${var.account_id}"
  enabled     = var.frontend_enabled
  depends_on  = [aws_iam_role_policy.legacy_quarantine]
}
output "manifest" { value = module.service.manifest }
output "frontend" {
  value = { bucket_name = module.frontend.bucket_name, distribution_id = module.frontend.distribution_id, origin = module.frontend.origin, enabled = var.frontend_enabled }
}
