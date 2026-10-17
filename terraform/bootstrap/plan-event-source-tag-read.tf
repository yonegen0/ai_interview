# Provider refresh reads tags on mapping ARNs, which are not function ARNs.
# Existing mappings are pinned by explicit maintenance inputs; no wildcard grant.
variable "plan_event_source_mapping_arns" {
  description = "Exact existing dev Worker and Streams mapping ARNs approved for Plan tag reads. Keep the approved maintenance var-file on subsequent bootstrap runs. Empty preserves initial-bootstrap compatibility."
  type        = set(string)
  default     = []
  validation {
    condition = length(var.plan_event_source_mapping_arns) == 0 || (
      length(var.plan_event_source_mapping_arns) == 2 && alltrue([
        for arn in var.plan_event_source_mapping_arns : can(regex(
          "^arn:aws:lambda:${var.region}:${var.account_id}:event-source-mapping:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
          arn
        ))
      ])
    )
    error_message = "Use exactly two distinct UUID mapping ARNs in this account/region, or an empty set before dev mappings exist. Wildcards are forbidden."
  }
}

locals {
  plan_event_source_tag_read_policy = {
    Version = "2012-10-17"
    Statement = [{
      Sid      = "DevEventSourceMappingTagRead"
      Effect   = "Allow"
      Action   = ["lambda:ListTags"]
      Resource = sort(tolist(var.plan_event_source_mapping_arns))
    }]
  }
}

