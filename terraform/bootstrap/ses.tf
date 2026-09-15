variable "ses_identity_type" {
  type = string
  validation {
    condition     = contains(["email", "domain"], var.ses_identity_type)
    error_message = "Choose email or domain explicitly."
  }
}
variable "ses_from_email" {
  type      = string
  sensitive = true
  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+$", var.ses_from_email))
    error_message = "A sender email is required."
  }
}
variable "ses_domain" {
  type    = string
  default = ""
  validation {
    condition     = var.ses_identity_type != "domain" || (can(regex("^[A-Za-z0-9.-]+\\.[A-Za-z]+$", var.ses_domain)) && endswith(var.ses_from_email, "@${var.ses_domain}"))
    error_message = "Domain mode requires an owned domain matching the sender."
  }
}
resource "aws_ses_email_identity" "sender" {
  count = var.ses_identity_type == "email" ? 1 : 0
  email = var.ses_from_email
  lifecycle { prevent_destroy = true }
}
resource "aws_ses_domain_identity" "sender" {
  count  = var.ses_identity_type == "domain" ? 1 : 0
  domain = var.ses_domain
  lifecycle { prevent_destroy = true }
}
resource "aws_ses_domain_dkim" "sender" {
  count  = var.ses_identity_type == "domain" ? 1 : 0
  domain = aws_ses_domain_identity.sender[0].domain
}
output "ses_identity_arn" {
  value     = var.ses_identity_type == "email" ? aws_ses_email_identity.sender[0].arn : aws_ses_domain_identity.sender[0].arn
  sensitive = true
}
output "ses_domain_verification" {
  value = var.ses_identity_type == "domain" ? {
    domain      = var.ses_domain
    token       = aws_ses_domain_identity.sender[0].verification_token
    dkim_tokens = aws_ses_domain_dkim.sender[0].dkim_tokens
  } : null
}
