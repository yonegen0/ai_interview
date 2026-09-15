resource "aws_sns_topic" "alarms" {
  name = "${local.prefix}-alarms"
  tags = local.tags
}
resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}
resource "aws_sns_topic_policy" "alarms" {
  arn    = aws_sns_topic.alarms.arn
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "cloudwatch.amazonaws.com" }, Action = "sns:Publish", Resource = aws_sns_topic.alarms.arn, Condition = { StringEquals = { "aws:SourceAccount" = var.account_id }, ArnLike = { "aws:SourceArn" = "arn:aws:cloudwatch:${var.region}:${var.account_id}:alarm:${local.prefix}-*" } } }] })
}
locals {
  emf_alarms = merge(
    { for n in ["PendingAge", "QueuedAge"] : n => { metric = n, component = "dispatcher", threshold = 120, comparison = "GreaterThanThreshold", periods = 1, period = 60, stat = "Maximum", missing = "notBreaching" } },
    { RecoveryHeartbeat = { metric = "RecoveryHeartbeat", component = "dispatcher", threshold = 1, comparison = "LessThanThreshold", periods = 3, period = 60, stat = "Sum", missing = "breaching" },
    RecoverySweepLag = { metric = "RecoverySweepLag", component = "dispatcher", threshold = 180, comparison = "GreaterThanThreshold", periods = 1, period = 60, stat = "Maximum", missing = "notBreaching" } },
    { for n in ["ExpiredLease", "DeadlineOverdue"] : n => { metric = n, component = "dispatcher", threshold = 1, comparison = "GreaterThanOrEqualToThreshold", periods = 2, period = 60, stat = "Sum", missing = "notBreaching" } },
    { for pair in setproduct(["api", "worker", "dispatcher"], ["DBError", "IntegrityError", "InvalidEvent", "InvalidConfiguration", "InternalInvocationFailed"]) : "${pair[0]}-${pair[1]}" => { metric = pair[1], component = pair[0], threshold = 1, comparison = "GreaterThanOrEqualToThreshold", periods = 1, period = 300, stat = "Sum", missing = "notBreaching" } },
    { OutcomeUnknown = { metric = "OutcomeUnknown", component = "dispatcher", threshold = 1, comparison = "GreaterThanOrEqualToThreshold", periods = 1, period = 60, stat = "Sum", missing = "notBreaching" } }
  )
}
resource "aws_cloudwatch_metric_alarm" "emf" {
  for_each            = local.emf_alarms
  alarm_name          = "${local.prefix}-${each.key}"
  namespace           = "AIInterview"
  metric_name         = each.value.metric
  dimensions          = { Project = "ai-interview", Environment = local.environment, Component = each.value.component }
  comparison_operator = each.value.comparison
  threshold           = each.value.threshold
  evaluation_periods  = each.value.periods
  period              = each.value.period
  statistic           = each.value.stat
  treat_missing_data  = each.value.missing
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
  actions_enabled     = each.key != "RecoveryHeartbeat" || var.scheduler_enabled
  tags                = local.tags
}
resource "aws_cloudwatch_metric_alarm" "dlq" {
  for_each            = { worker = aws_sqs_queue.worker_dlq.name, stream = aws_sqs_queue.stream_failure.name }
  alarm_name          = "${local.prefix}-dlq-${each.key}"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = each.value }
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 1
  period              = 60
  statistic           = "Maximum"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  tags                = local.tags
}
resource "aws_cloudwatch_metric_alarm" "lambda" {
  for_each            = { for pair in setproduct(keys(local.function_arns), ["Errors", "Throttles"]) : "${pair[0]}-${pair[1]}" => pair }
  alarm_name          = "${local.prefix}-${each.key}"
  namespace           = "AWS/Lambda"
  metric_name         = each.value[1]
  dimensions          = { FunctionName = "${local.prefix}-${each.value[0]}" }
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 1
  period              = 300
  statistic           = "Sum"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  tags                = local.tags
}
resource "aws_cloudwatch_metric_alarm" "iterator" {
  alarm_name          = "${local.prefix}-iterator-age"
  namespace           = "AWS/Lambda"
  metric_name         = "IteratorAge"
  dimensions          = { FunctionName = "${local.prefix}-dispatcher" }
  comparison_operator = "GreaterThanThreshold"
  threshold           = 120000
  evaluation_periods  = 1
  period              = 300
  statistic           = "Maximum"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  actions_enabled     = var.streams_enabled
  tags                = local.tags
}
resource "aws_cloudwatch_metric_alarm" "failure_rate" {
  alarm_name          = "${local.prefix}-failure-rate"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 20
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  metric_query {
    id          = "rate"
    expression  = "IF((FILL(wc,0)+FILL(wf,0)+FILL(dc,0)+FILL(df,0))>=10,100*(FILL(wf,0)+FILL(df,0))/(FILL(wc,0)+FILL(wf,0)+FILL(dc,0)+FILL(df,0)),0)"
    return_data = true
  }
  dynamic "metric_query" {
    for_each = { wc = ["worker", "EvaluationCompleted"], wf = ["worker", "EvaluationFailed"], dc = ["dispatcher", "EvaluationCompleted"], df = ["dispatcher", "EvaluationFailed"] }
    content {
      id          = metric_query.key
      return_data = false
      metric {
        namespace   = "AIInterview"
        metric_name = metric_query.value[1]
        dimensions  = { Project = "ai-interview", Environment = local.environment, Component = metric_query.value[0] }
        period      = 900
        stat        = "Sum"
      }
    }
  }
  tags = local.tags
}
resource "aws_budgets_budget" "dev" {
  count        = var.run_id == "" ? 1 : 0
  name         = "${local.prefix}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  # Account-wide notification is conservative and does not depend on tag activation.
  dynamic "notification" {
    for_each = toset([50, 80, 100])
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.alarm_email]
    }
  }
}
