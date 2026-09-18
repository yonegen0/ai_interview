mock_provider "aws" {}

variables {
  account_id             = "123456789012"
  region                 = "ap-northeast-1"
  boundary_arn           = "arn:aws:iam::123456789012:policy/ai-interview-runtime-boundary"
  artifact_bucket        = "ai-interview-artifacts-123456789012-ap-northeast-1"
  artifact_key           = "lambda/run/app.zip"
  artifact_version       = "v1"
  artifact_sha256_base64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
  ses_email              = "sender@example.invalid"
  ses_identity_arn       = "arn:aws:ses:ap-northeast-1:123456789012:identity/sender@example.invalid"
  alarm_email            = "alarm@example.invalid"
  cors_origins           = ["http://localhost:3000"]
  monthly_budget_usd     = 18.75
}

run "reject_zip_1" {
  command = plan
  variables { artifact_key = "" }
  expect_failures = [var.artifact_key]
}

run "reject_zip_2" {
  command = plan
  variables { artifact_key = "other/app.zip" }
  expect_failures = [var.artifact_key]
}

run "reject_zip_3" {
  command = plan
  variables { artifact_key = "lambda/app.txt" }
  expect_failures = [var.artifact_key]
}

run "reject_zip_4" {
  command = plan
  variables { artifact_key = "lambda/REPLACE_ME.zip" }
  expect_failures = [var.artifact_key]
}

run "reject_zip_5" {
  command = plan
  variables { artifact_key = null }
  expect_failures = [var.artifact_key]
}

run "reject_zip_6" {
  command = plan
  variables { artifact_version = "" }
  expect_failures = [var.artifact_version]
}

run "reject_zip_7" {
  command = plan
  variables { artifact_version = " " }
  expect_failures = [var.artifact_version]
}

run "reject_zip_8" {
  command = plan
  variables { artifact_version = " v1" }
  expect_failures = [var.artifact_version]
}

run "reject_zip_9" {
  command = plan
  variables { artifact_version = "v1 " }
  expect_failures = [var.artifact_version]
}

run "reject_zip_10" {
  command = plan
  variables { artifact_version = "null" }
  expect_failures = [var.artifact_version]
}

run "reject_zip_11" {
  command = plan
  variables { artifact_version = "REPLACE_ME_VERSION" }
  expect_failures = [var.artifact_version]
}

run "reject_zip_12" {
  command = plan
  variables { artifact_version = null }
  expect_failures = [var.artifact_version]
}

run "reject_zip_13" {
  command = plan
  variables { artifact_sha256_base64 = "REPLACE_ME" }
  expect_failures = [var.artifact_sha256_base64]
}

run "reject_zip_14" {
  command = plan
  variables { artifact_sha256_base64 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }
  expect_failures = [var.artifact_sha256_base64]
}

run "reject_zip_15" {
  command = plan
  variables { artifact_sha256_base64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=" }
  expect_failures = [var.artifact_sha256_base64]
}

run "reject_zip_16" {
  command = plan
  variables { artifact_sha256_base64 = "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!=" }
  expect_failures = [var.artifact_sha256_base64]
}

run "reject_zip_17" {
  command = plan
  variables { artifact_sha256_base64 = null }
  expect_failures = [var.artifact_sha256_base64]
}

run "accept_symbol_version" {
  command = plan
  variables { artifact_version = "v1.+/=_-" }
}
