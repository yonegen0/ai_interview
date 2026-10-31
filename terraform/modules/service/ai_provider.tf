# Configuration only. No authentication grant, secret, federation enablement or new resource.
variable "worker_ai_environment" {
  type    = map(string)
  default = {}
  validation {
    condition = alltrue([for k in keys(var.worker_ai_environment) : contains([
      "INTERVIEW_AI_PROVIDER", "INTERVIEW_OPENAI_ENABLED", "INTERVIEW_OPENAI_AUTH",
      "INTERVIEW_OPENAI_IDENTITY_PROVIDER_ID", "INTERVIEW_OPENAI_SERVICE_ACCOUNT_ID",
      "INTERVIEW_OPENAI_SECRET_ARN", "INTERVIEW_OPENAI_EFFORT",
      "INTERVIEW_OPENAI_MAX_OUTPUT_TOKENS", "INTERVIEW_OPENAI_MONTHLY_USER_LIMIT",
      "INTERVIEW_OPENAI_MONTHLY_GLOBAL_LIMIT",
      "INTERVIEW_ANTHROPIC_ENABLED", "INTERVIEW_ANTHROPIC_AUTH",
      "INTERVIEW_ANTHROPIC_SECRET_ARN", "INTERVIEW_ANTHROPIC_WORKSPACE_ID",
      "INTERVIEW_ANTHROPIC_MODEL", "INTERVIEW_ANTHROPIC_API_VERSION",
      "INTERVIEW_ANTHROPIC_EFFORT", "INTERVIEW_ANTHROPIC_MAX_OUTPUT_TOKENS",
      "INTERVIEW_ANTHROPIC_MONTHLY_USER_LIMIT", "INTERVIEW_ANTHROPIC_MONTHLY_GLOBAL_LIMIT",
      "INTERVIEW_BEDROCK_ENABLED", "INTERVIEW_BEDROCK_PROFILE_ID",
      "INTERVIEW_BEDROCK_EFFORT", "INTERVIEW_BEDROCK_MAX_TOKENS",
      "INTERVIEW_BEDROCK_MONTHLY_USER_LIMIT", "INTERVIEW_BEDROCK_MONTHLY_GLOBAL_LIMIT",
      "INTERVIEW_FAKE_SCENARIO", "INTERVIEW_VALIDATION_ONLY", "INTERVIEW_VALIDATION_OWNER_HASHES",
      "INTERVIEW_WIF_SMOKE_ENABLED", "INTERVIEW_WIF_SMOKE_RUN_ID", "INTERVIEW_OPENAI_AWS_ISSUER"
    ], k)])
    error_message = "Only non-secret, server-owned provider configuration keys are accepted."
  }
  validation {
    condition = length(var.worker_ai_environment) == 0 || (
      contains(["fake", "openai", "bedrock", "anthropic"], lookup(var.worker_ai_environment, "INTERVIEW_AI_PROVIDER", "")) &&
      (lookup(var.worker_ai_environment, "INTERVIEW_AI_PROVIDER", "") != "openai" || lookup(var.worker_ai_environment, "INTERVIEW_OPENAI_ENABLED", "false") == "true")
    )
    error_message = "An explicit provider selection and explicit OpenAI enablement are required."
  }
  validation {
    condition = lookup(var.worker_ai_environment, "INTERVIEW_AI_PROVIDER", "fake") != "openai" || (
      (lookup(var.worker_ai_environment, "INTERVIEW_OPENAI_AUTH", "wif") == "wif") == var.worker_wif_enabled
    )
    error_message = "OpenAI WIF requires the explicit Worker grant; Secret mode must not keep a WIF grant."
  }
  validation {
    condition     = lookup(var.worker_ai_environment, "INTERVIEW_WIF_SMOKE_ENABLED", "false") != "true" || (var.worker_wif_enabled && lookup(var.worker_ai_environment, "INTERVIEW_AI_PROVIDER", "") == "fake" && lookup(var.worker_ai_environment, "INTERVIEW_VALIDATION_ONLY", "false") == "true")
    error_message = "WIF Smoke requires an explicit dev Worker grant and validation-only Fake configuration."
  }

  validation {
    condition     = !var.worker_enabled || contains(["bedrock", "openai", "anthropic"], lookup(var.worker_ai_environment, "INTERVIEW_AI_PROVIDER", "")) || (lookup(var.worker_ai_environment, "INTERVIEW_AI_PROVIDER", "") == "fake" && lookup(var.worker_ai_environment, "INTERVIEW_VALIDATION_ONLY", "false") == "true")
    error_message = "Enabled Worker requires explicit real provider or validation-only Fake."
  }
  validation {
    condition = lookup(var.worker_ai_environment, "INTERVIEW_AI_PROVIDER", "") != "bedrock" || (
      var.region == "ap-northeast-1" &&
      lookup(var.worker_ai_environment, "INTERVIEW_BEDROCK_ENABLED", "") == "true" &&
      lookup(var.worker_ai_environment, "INTERVIEW_BEDROCK_PROFILE_ID", "jp.anthropic.claude-haiku-5-5") == "jp.anthropic.claude-haiku-5-5" &&
      lookup(var.worker_ai_environment, "INTERVIEW_BEDROCK_EFFORT", "low") == "low" &&
      can(regex("^[0-9]+$", lookup(var.worker_ai_environment, "INTERVIEW_BEDROCK_MAX_TOKENS", "2048"))) &&
      try(tonumber(lookup(var.worker_ai_environment, "INTERVIEW_BEDROCK_MAX_TOKENS", "2048")) == 2048, false) &&
      can(regex("^[0-9]+$", lookup(var.worker_ai_environment, "INTERVIEW_BEDROCK_MONTHLY_USER_LIMIT", "100"))) &&
      try(tonumber(lookup(var.worker_ai_environment, "INTERVIEW_BEDROCK_MONTHLY_USER_LIMIT", "100")) >= 1 && tonumber(lookup(var.worker_ai_environment, "INTERVIEW_BEDROCK_MONTHLY_USER_LIMIT", "100")) <= 100, false) &&
      can(regex("^[0-9]+$", lookup(var.worker_ai_environment, "INTERVIEW_BEDROCK_MONTHLY_GLOBAL_LIMIT", "3000"))) &&
      try(tonumber(lookup(var.worker_ai_environment, "INTERVIEW_BEDROCK_MONTHLY_GLOBAL_LIMIT", "3000")) >= 1 && tonumber(lookup(var.worker_ai_environment, "INTERVIEW_BEDROCK_MONTHLY_GLOBAL_LIMIT", "3000")) <= 3000, false) &&
      !var.worker_wif_enabled &&
      length([for k in keys(var.worker_ai_environment) : k if startswith(k, "INTERVIEW_VALIDATION_")]) == 0 &&
      length([for k in keys(var.worker_ai_environment) : k if startswith(k, "INTERVIEW_OPENAI_") || startswith(k, "INTERVIEW_ANTHROPIC_") || startswith(k, "INTERVIEW_WIF_") || startswith(k, "INTERVIEW_FAKE_")]) == 0
    )
    error_message = "Bedrock must use JP Geo without OpenAI/WIF/Fake settings."
  }
  validation {
    condition = lookup(var.worker_ai_environment, "INTERVIEW_AI_PROVIDER", "") != "openai" || (
      length([for k in keys(var.worker_ai_environment) : k if startswith(k, "INTERVIEW_BEDROCK_") || startswith(k, "INTERVIEW_ANTHROPIC_") || startswith(k, "INTERVIEW_WIF_") || startswith(k, "INTERVIEW_FAKE_") || startswith(k, "INTERVIEW_VALIDATION_")]) == 0 &&
      can(regex("^[0-9]+$", lookup(var.worker_ai_environment, "INTERVIEW_OPENAI_MONTHLY_USER_LIMIT", "100"))) &&
      try(tonumber(lookup(var.worker_ai_environment, "INTERVIEW_OPENAI_MONTHLY_USER_LIMIT", "100")) >= 1 && tonumber(lookup(var.worker_ai_environment, "INTERVIEW_OPENAI_MONTHLY_USER_LIMIT", "100")) <= 100, false) &&
      can(regex("^[0-9]+$", lookup(var.worker_ai_environment, "INTERVIEW_OPENAI_MONTHLY_GLOBAL_LIMIT", "3000"))) &&
      try(tonumber(lookup(var.worker_ai_environment, "INTERVIEW_OPENAI_MONTHLY_GLOBAL_LIMIT", "3000")) >= 1 && tonumber(lookup(var.worker_ai_environment, "INTERVIEW_OPENAI_MONTHLY_GLOBAL_LIMIT", "3000")) <= 3000, false)
    )
    error_message = "OpenAI and Bedrock share the monthly 100/3000 ceilings."
  }
  validation {
    condition = lookup(var.worker_ai_environment, "INTERVIEW_AI_PROVIDER", "") == "anthropic" || (
      length([for k in keys(var.worker_ai_environment) : k if startswith(k, "INTERVIEW_ANTHROPIC_")]) == 0
    )
    error_message = "Anthropic settings require Anthropic provider selection."
  }
  validation {
    condition = lookup(var.worker_ai_environment, "INTERVIEW_AI_PROVIDER", "") != "anthropic" || (
      lookup(var.worker_ai_environment, "INTERVIEW_ANTHROPIC_ENABLED", "") == "true" &&
      lookup(var.worker_ai_environment, "INTERVIEW_ANTHROPIC_AUTH", "") == "secret" &&
      can(regex("^arn:aws:secretsmanager:${var.region}:${var.account_id}:secret:[A-Za-z0-9/_+=.@-]+$", lookup(var.worker_ai_environment, "INTERVIEW_ANTHROPIC_SECRET_ARN", ""))) &&
      lookup(var.worker_ai_environment, "INTERVIEW_ANTHROPIC_MODEL", "") == "claude-haiku-5-5" &&
      lookup(var.worker_ai_environment, "INTERVIEW_ANTHROPIC_API_VERSION", "") == "2026-10-21" &&
      contains(["low", "medium", "high"], lookup(var.worker_ai_environment, "INTERVIEW_ANTHROPIC_EFFORT", "medium")) &&
      can(regex("^[0-9]+$", lookup(var.worker_ai_environment, "INTERVIEW_ANTHROPIC_MAX_OUTPUT_TOKENS", "4096"))) &&
      try(tonumber(lookup(var.worker_ai_environment, "INTERVIEW_ANTHROPIC_MAX_OUTPUT_TOKENS", "4096")) >= 1024 && tonumber(lookup(var.worker_ai_environment, "INTERVIEW_ANTHROPIC_MAX_OUTPUT_TOKENS", "4096")) <= 8192, false) &&
      can(regex("^[0-9]+$", lookup(var.worker_ai_environment, "INTERVIEW_ANTHROPIC_MONTHLY_USER_LIMIT", "100"))) &&
      try(tonumber(lookup(var.worker_ai_environment, "INTERVIEW_ANTHROPIC_MONTHLY_USER_LIMIT", "100")) >= 1 && tonumber(lookup(var.worker_ai_environment, "INTERVIEW_ANTHROPIC_MONTHLY_USER_LIMIT", "100")) <= 100, false) &&
      can(regex("^[0-9]+$", lookup(var.worker_ai_environment, "INTERVIEW_ANTHROPIC_MONTHLY_GLOBAL_LIMIT", "3000"))) &&
      try(tonumber(lookup(var.worker_ai_environment, "INTERVIEW_ANTHROPIC_MONTHLY_GLOBAL_LIMIT", "3000")) >= 1 && tonumber(lookup(var.worker_ai_environment, "INTERVIEW_ANTHROPIC_MONTHLY_GLOBAL_LIMIT", "3000")) <= 3000, false) &&
      (
        !contains(keys(var.worker_ai_environment), "INTERVIEW_ANTHROPIC_WORKSPACE_ID") ||
        can(regex("^wrkspc_[A-Za-z0-9]+$", lookup(var.worker_ai_environment, "INTERVIEW_ANTHROPIC_WORKSPACE_ID", "")))
      ) &&
      !var.worker_wif_enabled &&
      length([for k in keys(var.worker_ai_environment) : k if startswith(k, "INTERVIEW_BEDROCK_") || startswith(k, "INTERVIEW_OPENAI_") || startswith(k, "INTERVIEW_WIF_") || startswith(k, "INTERVIEW_FAKE_") || startswith(k, "INTERVIEW_VALIDATION_")]) == 0
    )
    error_message = "Anthropic requires a scoped secret ARN, fixed model and version, bounded limits and no fallback provider settings."
  }

}
