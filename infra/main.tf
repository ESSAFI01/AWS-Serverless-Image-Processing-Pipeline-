locals {
  name = var.project_name
  buckets = {
    input  = "${local.name}-input-${var.bucket_suffix}"
    output = "${local.name}-output-${var.bucket_suffix}"
  }
  lambda_zip = "${path.module}/${var.lambda_zip_path}"
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "images" {
  for_each      = local.buckets
  bucket        = each.value
  force_destroy = false
}

resource "aws_s3_bucket_public_access_block" "images" {
  for_each                = local.buckets
  bucket                  = aws_s3_bucket.images[each.key].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "images" {
  for_each = local.buckets
  bucket   = aws_s3_bucket.images[each.key].id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "images" {
  for_each = local.buckets
  bucket   = aws_s3_bucket.images[each.key].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_sqs_queue" "dead_letter" {
  name                      = "${local.name}-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "images" {
  name                       = "${local.name}-queue"
  visibility_timeout_seconds = 180
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter.arn
    maxReceiveCount     = 5
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "images" {
  queue_url = aws_sqs_queue.dead_letter.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.images.arn]
  })
}

resource "aws_sqs_queue_policy" "s3" {
  queue_url = aws_sqs_queue.images.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowInputBucketNotifications"
      Effect    = "Allow"
      Principal = { Service = "s3.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.images.arn
      Condition = {
        ArnEquals    = { "aws:SourceArn" = aws_s3_bucket.images["input"].arn }
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
      }
    }]
  })
}

resource "aws_s3_bucket_notification" "input" {
  bucket = aws_s3_bucket.images["input"].id
  queue {
    queue_arn     = aws_sqs_queue.images.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "uploads/"
  }
  depends_on = [aws_sqs_queue_policy.s3]
}

