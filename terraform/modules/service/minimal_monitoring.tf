# Five alarms / six charged metric references / two bounded custom series.
# A single DLQ alarm deliberately combines the two standard SQS metrics.
resource "aws_cloudwatch_metric_alarm" "minimal" {
  for_each = var.monitoring_profile == "minimal" && local.monitoring_enabled ? {
    CriticalFailure   = { comparison = "GreaterThanOrEqualToThreshold", periods = 1, missing = "notBreaching" }
    RecoveryHeartbeat = { comparison = "LessThanThreshold", periods = 3, missing = "breaching" }
  } : {}
  alarm_name          = "${local.prefix}-${each.key}"
  namespace           = "AIInterview"
  metric_name         = each.key
  dimensions          = { Project = "ai-interview", Environment = local.environment }
  comparison_operator = each.value.comparison
  threshold           = 1
  evaluation_periods  = each.value.periods
  period              = 60
  statistic           = "Sum"
  treat_missing_data  = each.value.missing
  actions_enabled     = each.key != "RecoveryHeartbeat" || var.scheduler_enabled
  alarm_actions       = [aws_sns_topic.alarms.arn]
  tags                = local.tags
}
resource "aws_cloudwatch_metric_alarm" "minimal_dlq" {
  count               = var.monitoring_profile == "minimal" && local.monitoring_enabled ? 1 : 0
  alarm_name          = "${local.prefix}-dlq"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  metric_query {
    id          = "total"
    expression  = "SUM([worker,stream])"
    return_data = true
  }
  dynamic "metric_query" {
    for_each = { worker = aws_sqs_queue.worker_dlq.name, stream = aws_sqs_queue.stream_failure.name }
    content {
      id          = metric_query.key
      return_data = false
      metric {
        namespace   = "AWS/SQS"
        metric_name = "ApproximateNumberOfMessagesVisible"
        dimensions  = { QueueName = metric_query.value }
        period      = 60
        stat        = "Maximum"
      }
    }
  }
  tags = local.tags
}
