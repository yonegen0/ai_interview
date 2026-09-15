output "manifest" {
  value = {
    schema_version = 2
    configuration = {
      boundary_arn       = var.boundary_arn
      ses_email          = var.ses_email
      ses_identity_arn   = var.ses_identity_arn
      alarm_email        = var.alarm_email
      monthly_budget_usd = tostring(var.monthly_budget_usd)
      cors_origins       = sort(tolist(var.cors_origins))
      worker_enabled     = var.worker_enabled
      streams_enabled    = var.streams_enabled
      scheduler_enabled  = var.scheduler_enabled
      api_enabled        = var.api_enabled
    }
    account_id         = var.account_id
    region             = var.region
    environment        = local.environment
    run_id             = var.run_id
    table_name         = aws_dynamodb_table.main.name
    queue_url          = aws_sqs_queue.main.url
    queue_arn          = aws_sqs_queue.main.arn
    worker_dlq_url     = aws_sqs_queue.worker_dlq.url
    stream_failure_url = aws_sqs_queue.stream_failure.url
    stream_arn         = aws_dynamodb_table.main.stream_arn
    schedule_arn       = aws_scheduler_schedule.recovery.arn
    api_endpoint       = "${aws_apigatewayv2_api.main.api_endpoint}/dev"
    api_id             = aws_apigatewayv2_api.main.id
    client_id          = aws_cognito_user_pool_client.web.id
    user_pool_id       = aws_cognito_user_pool.main.id
    versions           = { for k, f in aws_lambda_function.main : k => f.version }
    aliases            = { for k, a in aws_lambda_alias.entry : k => a.arn }
    mappings           = { worker = aws_lambda_event_source_mapping.worker.uuid, streams = aws_lambda_event_source_mapping.streams.uuid }
    artifact           = { bucket = var.artifact_bucket, key = var.artifact_key, version = var.artifact_version, sha256_base64 = var.artifact_sha256_base64 }
    log_groups         = { for k, g in aws_cloudwatch_log_group.lambda : k => g.name }
    alarm_topic_arn    = aws_sns_topic.alarms.arn
  }
}
