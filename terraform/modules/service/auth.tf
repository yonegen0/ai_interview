resource "aws_cognito_user_pool" "main" {
  name                     = "${local.prefix}-pool"
  user_pool_tier           = "ESSENTIALS"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = "OFF"
  admin_create_user_config { allow_admin_create_user_only = true }
  sign_in_policy { allowed_first_auth_factors = ["EMAIL_OTP"] }
  email_configuration {
    email_sending_account = "DEVELOPER"
    source_arn            = var.ses_identity_arn
    from_email_address    = var.ses_email
  }
  tags = local.tags
}
resource "aws_cognito_user_pool_client" "web" {
  name                   = "${local.prefix}-web"
  user_pool_id           = aws_cognito_user_pool.main.id
  generate_secret        = false
  explicit_auth_flows    = ["ALLOW_USER_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  access_token_validity  = 5
  id_token_validity      = 5
  refresh_token_validity = 1
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
  enable_token_revocation       = true
  prevent_user_existence_errors = "ENABLED"
}
resource "aws_cognito_user_group" "groups" {
  for_each     = toset(["USER", "ADMIN"])
  name         = each.value
  user_pool_id = aws_cognito_user_pool.main.id
}
resource "aws_apigatewayv2_api" "main" {
  name                         = "${local.prefix}-api"
  protocol_type                = "HTTP"
  disable_execute_api_endpoint = !var.api_enabled
  cors_configuration {
    allow_origins     = sort(tolist(var.cors_origins))
    allow_methods     = ["GET", "POST", "OPTIONS"]
    allow_headers     = ["Authorization", "Content-Type", "Idempotency-Key"]
    expose_headers    = ["Allow"]
    allow_credentials = false
    max_age           = 300
  }
  tags = local.tags
}
resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.main.id
  name             = "cognito-access"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  jwt_configuration {
    audience = [aws_cognito_user_pool_client.web.id]
    issuer   = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
  }
}
resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_alias.entry["api"].invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 15000
}
locals {
  routes = toset(["POST /sessions", "GET /sessions/{sessionId}/question", "POST /sessions/{sessionId}/answers", "GET /evaluations/{evaluationId}", "GET /attempts/{attemptId}/feedback", "POST /sessions/{sessionId}/questions/next", "$default"])
}
resource "aws_apigatewayv2_route" "business" {
  for_each           = local.routes
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
  target             = "integrations/${aws_apigatewayv2_integration.api.id}"
}
resource "aws_apigatewayv2_route" "preflight" {
  for_each           = toset(["OPTIONS /{proxy+}", "OPTIONS /"])
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = each.value
  authorization_type = "NONE"
  target             = "integrations/${aws_apigatewayv2_integration.api.id}"
}
resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/apigateway/${local.prefix}"
  retention_in_days = 30
  tags              = local.tags
}
resource "aws_apigatewayv2_stage" "dev" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "dev"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 10
    throttling_rate_limit  = 5
  }
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format          = jsonencode({ requestId = "$context.requestId", routeKey = "$context.routeKey", status = "$context.status", responseLength = "$context.responseLength" })
  }
  tags = local.tags
}
resource "aws_lambda_permission" "api" {
  statement_id   = "OnlyThisApiDev"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.main["api"].function_name
  qualifier      = aws_lambda_alias.entry["api"].name
  principal      = "apigateway.amazonaws.com"
  source_account = var.account_id
  source_arn     = "${aws_apigatewayv2_api.main.execution_arn}/dev/*"
}
