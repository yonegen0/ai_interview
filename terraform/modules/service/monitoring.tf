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
  monitoring_enabled  = local.environment == "test" ? var.test_monitoring_enabled : anytrue([var.api_enabled, var.worker_enabled, var.streams_enabled, var.scheduler_enabled])
  dev_emf_alarm_names = toset(["api-IntegrityError", "worker-IntegrityError", "dispatcher-IntegrityError", "admin-IntegrityError", "OutcomeUnknown", "RecoveryHeartbeat", "RecoverySweepLag"])
  emf_alarms = merge(
    { for n in ["PendingAge", "QueuedAge"] : n => { metric = n, component = "dispatcher", threshold = 120, comparison = "GreaterThanThreshold", periods = 1, period = 60, stat = "Maximum", missing = "notBreaching" } },
    { RecoveryHeartbeat = { metric = "RecoveryHeartbeat", component = "dispatcher", threshold = 1, comparison = "LessThanThreshold", periods = 3, period = 60, stat = "Sum", missing = "breaching" },
    RecoverySweepLag = { metric = "RecoverySweepLag", component = "dispatcher", threshold = 180, comparison = "GreaterThanThreshold", periods = 1, period = 60, stat = "Maximum", missing = "notBreaching" } },
    { for n in ["ExpiredLease", "DeadlineOverdue"] : n => { metric = n, component = "dispatcher", threshold = 1, comparison = "GreaterThanOrEqualToThreshold", periods = 2, period = 60, stat = "Sum", missing = "notBreaching" } },
    { for pair in setproduct(keys(local.function_arns), ["DBError", "IntegrityError", "InvalidEvent", "InvalidConfiguration", "InternalInvocationFailed"]) : "${pair[0]}-${pair[1]}" => { metric = pair[1], component = pair[0], threshold = 1, comparison = "GreaterThanOrEqualToThreshold", periods = 1, period = 300, stat = "Sum", missing = "notBreaching" } },
    { OutcomeUnknown = { metric = "OutcomeUnknown", component = "dispatcher", threshold = 1, comparison = "GreaterThanOrEqualToThreshold", periods = 1, period = 60, stat = "Sum", missing = "notBreaching" } }
  )
}
resource "aws_cloudwatch_metric_alarm" "emf" {
  for_each            = { for name, alarm in local.emf_alarms : name => alarm if local.monitoring_enabled && (local.environment != "dev" || contains(setunion(local.dev_emf_alarm_names, var.log_usage == "customer" ? toset(["PendingAge", "QueuedAge"]) : toset([])), name)) }
  alarm_name          = "${local.prefix}-${each.key}"
  namespace           = each.key == "OutcomeUnknown" ? null : "AIInterview"
  metric_name         = each.key == "OutcomeUnknown" ? null : each.value.metric
  dimensions          = each.key == "OutcomeUnknown" ? null : { Project = "ai-interview", Environment = local.environment, Component = each.value.component }
  comparison_operator = each.value.comparison
  threshold           = each.value.threshold
  evaluation_periods  = each.key == "OutcomeUnknown" ? 5 : each.value.periods
  datapoints_to_alarm = each.key == "OutcomeUnknown" ? 1 : null
  period              = each.key == "OutcomeUnknown" ? null : each.value.period
  statistic           = each.key == "OutcomeUnknown" ? null : each.value.stat
  treat_missing_data  = each.value.missing
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
  actions_enabled     = (each.key != "RecoveryHeartbeat" && (local.environment != "dev" || each.key != "RecoverySweepLag")) || var.scheduler_enabled
  # Keep the existing address/name/topic; one sparse count from either role is sufficient.
  dynamic "metric_query" {
    for_each = each.key == "OutcomeUnknown" ? [1] : []
    content {
      id          = "unknown"
      expression  = "SUM([wo,do])"
      return_data = true
    }
  }
  dynamic "metric_query" {
    for_each = each.key == "OutcomeUnknown" ? { wo = "worker", do = "dispatcher" } : {}
    content {
      id          = metric_query.key
      return_data = false
      metric {
        namespace   = "AIInterview"
        metric_name = "OutcomeUnknown"
        dimensions  = { Project = "ai-interview", Environment = local.environment, Component = metric_query.value }
        period      = 60
        stat        = "Sum"
      }
    }
  }
  tags = local.tags
}
resource "aws_cloudwatch_metric_alarm" "dlq" {
  for_each            = { for name, queue in { worker = aws_sqs_queue.worker_dlq.name, stream = aws_sqs_queue.stream_failure.name } : name => queue if local.monitoring_enabled }
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
  for_each            = { for pair in setproduct(keys(local.function_arns), ["Errors", "Throttles"]) : "${pair[0]}-${pair[1]}" => pair if local.monitoring_enabled }
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
  count               = local.environment == "test" && local.monitoring_enabled ? 1 : 0
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
  count               = local.environment == "test" && local.monitoring_enabled ? 1 : 0
  alarm_name          = "${local.prefix}-failure-rate"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 20
  evaluation_periods  = 3
  datapoints_to_alarm = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  metric_query {
    id          = "rate"
    expression  = "IF(SUM([wc,wf,dc,df])>=10,100*SUM([wf,df])/SUM([wc,wf,dc,df]),0)"
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
    for_each = { actual_80 = { threshold = 80, type = "ACTUAL" }, actual_100 = { threshold = 100, type = "ACTUAL" }, forecast_100 = { threshold = 100, type = "FORECASTED" } }
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value.threshold
      threshold_type             = "PERCENTAGE"
      notification_type          = notification.value.type
      subscriber_email_addresses = [var.alarm_email]
    }
  }
}

moved {
  from = aws_cloudwatch_metric_alarm.iterator
  to   = aws_cloudwatch_metric_alarm.iterator[0]
}

moved {
  from = aws_cloudwatch_metric_alarm.failure_rate
  to   = aws_cloudwatch_metric_alarm.failure_rate[0]
}

# Standard API-wide metrics: no route-level detailed metrics or new EMF series.
resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  count               = local.environment == "dev" && var.log_usage == "customer" && local.monitoring_enabled ? 1 : 0
  alarm_name          = "${local.prefix}-api-5xx"
  namespace           = "AWS/ApiGateway"
  metric_name         = "5xx"
  dimensions          = { ApiId = aws_apigatewayv2_api.main.id }
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 1
  period              = 60
  statistic           = "Sum"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  tags                = local.tags
}
resource "aws_cloudwatch_metric_alarm" "evaluation_failed" {
  count               = local.environment == "dev" && var.log_usage == "customer" && local.monitoring_enabled ? 1 : 0
  alarm_name          = "${local.prefix}-evaluation-failed"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 5
  datapoints_to_alarm = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  metric_query {
    id          = "failed"
    expression  = "SUM([wf,df])"
    return_data = true
  }
  dynamic "metric_query" {
    for_each = { wf = "worker", df = "dispatcher" }
    content {
      id          = metric_query.key
      return_data = false
      metric {
        namespace   = "AIInterview"
        metric_name = "EvaluationFailed"
        dimensions  = { Project = "ai-interview", Environment = local.environment, Component = metric_query.value }
        period      = 60
        stat        = "Sum"
      }
    }
  }
  tags = local.tags
}
