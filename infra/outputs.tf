output "input_bucket" {
  value = aws_s3_bucket.images["input"].id
}

output "output_bucket" {
  value = aws_s3_bucket.images["output"].id
}

output "upload_prefix" {
  value = "uploads/"
}

output "queue_url" {
  value = aws_sqs_queue.images.id
}

output "dead_letter_queue_url" {
  value = aws_sqs_queue.dead_letter.id
}

output "lambda_function_name" {
  value = aws_lambda_function.processor.function_name
}

output "processing_enabled" {
  value = var.enable_processing
}

output "workflow_arn" {
  value = aws_sfn_state_machine.images.arn
}

output "api_url" {
  value = aws_apigatewayv2_api.images.api_endpoint
}

output "cloudfront_domain" {
  value = aws_cloudfront_distribution.images.domain_name
}

output "delivery_enabled" {
  value = var.enable_delivery
}

output "metadata_table" {
  value = aws_dynamodb_table.images.name
}

output "notification_topic_arn" {
  value = aws_sns_topic.jobs.arn
}
