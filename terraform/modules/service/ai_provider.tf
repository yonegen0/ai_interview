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
      "INTERVIEW_FAKE_SCENARIO", "INTERVIEW_VALIDATION_ONLY", "INTERVIEW_VALIDATION_OWNER_HASHES"
    ], k)])
    error_message = "Only non-secret, server-owned provider configuration keys are accepted."
  }
  validation {
    condition = length(var.worker_ai_environment) == 0 || (
      contains(["fake", "openai"], lookup(var.worker_ai_environment, "INTERVIEW_AI_PROVIDER", "")) &&
      (lookup(var.worker_ai_environment, "INTERVIEW_AI_PROVIDER", "") != "openai" || lookup(var.worker_ai_environment, "INTERVIEW_OPENAI_ENABLED", "false") == "true")
    )
    error_message = "An explicit provider selection and explicit OpenAI enablement are required."
  }
}
