mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "000000000000"
    }
  }
}

variables {
  bucket_suffix     = "localtest123"
  lambda_zip_path   = "tests/fixtures/package-placeholder.txt"
  pillow_layer_path = "tests/fixtures/package-placeholder.txt"
}

run "pipeline_safety_defaults" {
  command = plan

  assert {
    condition     = aws_lambda_event_source_mapping.images.enabled == false
    error_message = "Processing must default to disabled."
  }

  assert {
    condition     = contains(aws_lambda_event_source_mapping.images.function_response_types, "ReportBatchItemFailures")
    error_message = "Failed SQS messages must be reported separately."
  }

  assert {
    condition     = aws_sqs_queue.images.visibility_timeout_seconds >= 6 * aws_lambda_function.processor.timeout
    error_message = "SQS visibility must be at least six times the Lambda timeout."
  }

  assert {
    condition     = aws_sqs_queue.dead_letter.message_retention_seconds > aws_sqs_queue.images.message_retention_seconds
    error_message = "DLQ retention must exceed source queue retention."
  }

  assert {
    condition = alltrue([
      aws_lambda_function.processor.reserved_concurrent_executions == -1,
      aws_lambda_function.worker.reserved_concurrent_executions == -1,
      aws_lambda_function.api.reserved_concurrent_executions == -1
    ])
    error_message = "Use unreserved concurrency so the project works with low account quotas."
  }

  assert {
    condition     = aws_lambda_event_source_mapping.images.scaling_config[0].maximum_concurrency == 2
    error_message = "Keep SQS dispatch limited to two concurrent invocations."
  }

  assert {
    condition     = one(aws_s3_bucket_notification.input.queue).filter_prefix == "uploads/"
    error_message = "Only uploads/ should produce queue notifications."
  }

  assert {
    condition = alltrue([for block in aws_s3_bucket_public_access_block.images :
      block.block_public_acls && block.block_public_policy && block.ignore_public_acls && block.restrict_public_buckets
    ])
    error_message = "Both buckets must block all public access."
  }

  assert {
    condition     = alltrue([for bucket in aws_s3_bucket.images : bucket.force_destroy == false])
    error_message = "Terraform must not automatically empty buckets during destruction."
  }

  assert {
    condition     = aws_lambda_function.processor.runtime == "python3.12" && contains(aws_lambda_function.processor.architectures, "x86_64")
    error_message = "Runtime and architecture must match the package builder."
  }

  assert {
    condition     = aws_sfn_state_machine.images.type == "STANDARD"
    error_message = "Use a Standard workflow for named-execution deduplication."
  }

  assert {
    condition     = aws_cloudfront_distribution.images.enabled == false && aws_cloudfront_origin_access_control.images.signing_behavior == "always"
    error_message = "CloudFront must default disabled and sign origin requests."
  }

  assert {
    condition     = alltrue([for route in aws_apigatewayv2_route.images : route.authorization_type == "AWS_IAM"])
    error_message = "Upload and status routes must require IAM authentication."
  }

  assert {
    condition     = aws_dynamodb_table.images.billing_mode == "PROVISIONED" && aws_dynamodb_table.images.read_capacity == 1 && aws_dynamodb_table.images.write_capacity == 1
    error_message = "Metadata capacity must remain at the small provisioned defaults."
  }

  assert {
    condition     = length(aws_lambda_function.worker.layers) == 1 && contains(aws_lambda_layer_version.pillow.compatible_runtimes, "python3.12")
    error_message = "The image worker must use the Python 3.12 Pillow layer."
  }

  assert {
    condition     = aws_lambda_function.worker.handler == "workflow.lambda_handler" && aws_lambda_function.processor.handler == "workflow_starter.lambda_handler"
    error_message = "SQS dispatch and workflow processing must have distinct handlers."
  }

  assert {
    condition     = one([for rule in aws_s3_bucket_lifecycle_configuration.output.rule : rule if rule.id == "remove-intermediate-images"]).expiration[0].days == 1
    error_message = "Intermediate images must expire after one day."
  }

}
