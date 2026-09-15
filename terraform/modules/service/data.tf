resource "aws_dynamodb_table" "main" {
  name         = "${local.prefix}-main"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"
  dynamic "attribute" {
    for_each = toset(["PK", "SK", "work_pk", "work_sk"])
    content {
      name = attribute.value
      type = "S"
    }
  }
  global_secondary_index {
    name            = "WorkIndex"
    hash_key        = "work_pk"
    range_key       = "work_sk"
    projection_type = "KEYS_ONLY"
  }
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"
  point_in_time_recovery { enabled = false }
  # Omit SSE configuration to retain DynamoDB's AWS-owned key default. No TTL.
  tags = local.tags
}
resource "aws_sqs_queue" "worker_dlq" {
  name                      = "${local.prefix}-worker-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
  tags                      = local.tags
}
resource "aws_sqs_queue" "stream_failure" {
  name                      = "${local.prefix}-stream-failure"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
  tags                      = local.tags
}
resource "aws_sqs_queue" "main" {
  name                       = "${local.prefix}-main"
  message_retention_seconds  = 345600
  visibility_timeout_seconds = 360
  sqs_managed_sse_enabled    = true
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.worker_dlq.arn, maxReceiveCount = 5 })
  tags                       = local.tags
}
resource "aws_sqs_queue_redrive_allow_policy" "worker" {
  queue_url            = aws_sqs_queue.worker_dlq.url
  redrive_allow_policy = jsonencode({ redrivePermission = "byQueue", sourceQueueArns = [aws_sqs_queue.main.arn] })
}
