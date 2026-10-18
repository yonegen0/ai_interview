mock_provider "aws" {}

variables {
  account_id             = "123456789012"
  region                 = "ap-northeast-1"
  log_usage              = "developer"
  boundary_arn           = "arn:aws:iam::123456789012:policy/ai-interview-runtime-boundary"
  artifact_bucket        = "ai-interview-artifacts-123456789012-ap-northeast-1"
  artifact_key           = "lambda/synthetic/app.zip"
  artifact_version       = "synthetic-version"
  artifact_sha256_base64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
  ses_email              = "sender@example.invalid"
  ses_identity_arn       = "arn:aws:ses:ap-northeast-1:123456789012:identity/sender@example.invalid"
  alarm_email            = "alarm@example.invalid"
  cors_origins           = ["http://localhost:3000"]
  monthly_budget_usd     = 10
}

run "bedrock_jp_closed_default" {
  command = plan
  variables {
    worker_ai_environment = {
      INTERVIEW_AI_PROVIDER        = "bedrock"
      INTERVIEW_BEDROCK_ENABLED    = "true"
      INTERVIEW_BEDROCK_PROFILE_ID = "jp.anthropic.claude-haiku-5-5"
    }
  }
  assert {
    condition = (
      aws_lambda_function.main["worker"].environment[0].variables["INTERVIEW_AI_PROVIDER"] == "bedrock" &&
      !aws_lambda_event_source_mapping.worker.enabled &&
      !aws_lambda_event_source_mapping.streams.enabled &&
      aws_scheduler_schedule.recovery.state == "DISABLED"
    )
    error_message = "JP Provider must not open any entrance."
  }
  assert {
    condition = (
      length(local.bedrock_worker_statements) == 2 &&
      local.bedrock_worker_statements[0].Resource[0] == "arn:aws:bedrock:ap-northeast-1:123456789012:inference-profile/jp.anthropic.claude-haiku-5-5" &&
      local.bedrock_worker_statements[1].Condition.StringEquals["bedrock:InferenceProfileArn"] == local.bedrock_profile_arn
    )
    error_message = "Only Worker may call JP Profile."
  }
}

run "reject_global_profile" {
  command = plan
  variables {
    worker_ai_environment = {
      INTERVIEW_AI_PROVIDER        = "bedrock"
      INTERVIEW_BEDROCK_ENABLED    = "true"
      INTERVIEW_BEDROCK_PROFILE_ID = "global.anthropic.claude-haiku-5-5"
    }
  }
  expect_failures = [var.worker_ai_environment]
}

run "reject_mixed_provider" {
  command = plan
  variables {
    worker_ai_environment = {
      INTERVIEW_AI_PROVIDER     = "bedrock"
      INTERVIEW_BEDROCK_ENABLED = "true"
      INTERVIEW_OPENAI_ENABLED  = "true"
    }
  }
  expect_failures = [var.worker_ai_environment]
}

run "reject_unconfigured_live_worker" {
  command = plan
  variables { worker_enabled = true }
  expect_failures = [var.worker_ai_environment]
}

run "reject_validation_key_even_false" {
  command = plan
  variables {
    worker_ai_environment = {
      INTERVIEW_AI_PROVIDER     = "bedrock"
      INTERVIEW_BEDROCK_ENABLED = "true"
      INTERVIEW_VALIDATION_ONLY = "false"
    }
  }
  expect_failures = [var.worker_ai_environment]
}

run "reject_bedrock_nonstandard_effort" {
  command = plan
  variables {
    worker_ai_environment = {
      INTERVIEW_AI_PROVIDER     = "bedrock"
      INTERVIEW_BEDROCK_ENABLED = "true"
      INTERVIEW_BEDROCK_EFFORT  = "medium"
    }
  }
  expect_failures = [var.worker_ai_environment]
}

run "reject_bedrock_above_user_ceiling" {
  command = plan
  variables {
    worker_ai_environment = {
      INTERVIEW_AI_PROVIDER                = "bedrock"
      INTERVIEW_BEDROCK_ENABLED            = "true"
      INTERVIEW_BEDROCK_MONTHLY_USER_LIMIT = "101"
    }
  }
  expect_failures = [var.worker_ai_environment]
}

run "reject_bedrock_above_global_ceiling" {
  command = plan
  variables {
    worker_ai_environment = {
      INTERVIEW_AI_PROVIDER                  = "bedrock"
      INTERVIEW_BEDROCK_ENABLED              = "true"
      INTERVIEW_BEDROCK_MONTHLY_GLOBAL_LIMIT = "3001"
    }
  }
  expect_failures = [var.worker_ai_environment]
}

run "reject_openai_above_shared_ceiling" {
  command = plan
  variables {
    worker_wif_enabled = true
    worker_ai_environment = {
      INTERVIEW_AI_PROVIDER               = "openai"
      INTERVIEW_OPENAI_ENABLED            = "true"
      INTERVIEW_OPENAI_MONTHLY_USER_LIMIT = "101"
    }
  }
  expect_failures = [var.worker_ai_environment]
}
