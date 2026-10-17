locals {
  layer_zip = "${path.module}/${var.pillow_layer_path}"
  function_names = {
    worker = "${local.name}-worker"
    api    = "${local.name}-api"
  }
}

resource "aws_iam_role" "lambda" {
  name = "${local.name}-dispatcher"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role" "functions" {
  for_each           = local.function_names
  name               = each.value
  assume_role_policy = aws_iam_role.lambda.assume_role_policy
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 3
}

resource "aws_cloudwatch_log_group" "functions" {
  for_each          = local.function_names
  name              = "/aws/lambda/${each.value}"
  retention_in_days = 3
}

resource "aws_iam_role_policy" "lambda" {
  name = "${local.name}-dispatch"
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow", Action = ["states:StartExecution"], Resource = aws_sfn_state_machine.images.arn
      },
      {
        Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = aws_sqs_queue.images.arn
      },
      {
        Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.lambda.arn}:*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "worker" {
  name = "${local.name}-worker"
  role = aws_iam_role.functions["worker"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow", Action = ["s3:GetObject", "s3:GetObjectVersion"], Resource = "${aws_s3_bucket.images["input"].arn}/uploads/*"
      },
      {
        Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = "${aws_s3_bucket.images["output"].arn}/staging/*"
      },
      {
        Effect = "Allow", Action = ["s3:PutObject"], Resource = "${aws_s3_bucket.images["output"].arn}/processed/*"
      },
      {
        Effect = "Allow", Action = ["dynamodb:PutItem"], Resource = aws_dynamodb_table.images.arn
      },
      {
        Effect = "Allow", Action = ["sns:Publish"], Resource = aws_sns_topic.jobs.arn
      },
      {
        Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.functions["worker"].arn}:*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "api" {
  name = "${local.name}-api"
  role = aws_iam_role.functions["api"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow", Action = ["s3:PutObject"], Resource = "${aws_s3_bucket.images["input"].arn}/uploads/*"
      },
      {
        Effect = "Allow", Action = ["dynamodb:GetItem"], Resource = aws_dynamodb_table.images.arn
      },
      {
        Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.functions["api"].arn}:*"
      }
    ]
  })
}

resource "aws_lambda_layer_version" "pillow" {
  layer_name               = "${local.name}-pillow"
  filename                 = local.layer_zip
  source_code_hash         = fileexists(local.layer_zip) ? filebase64sha256(local.layer_zip) : null
  compatible_runtimes      = ["python3.12"]
  compatible_architectures = ["x86_64"]
  lifecycle {
    precondition {
      condition     = fileexists(local.layer_zip)
      error_message = "Build the Pillow layer first using scripts/build_lambda.py."
    }
  }
}

resource "aws_lambda_function" "processor" {
  function_name                  = local.name
  role                           = aws_iam_role.lambda.arn
  handler                        = "workflow_starter.lambda_handler"
  runtime                        = "python3.12"
  architectures                  = ["x86_64"]
  filename                       = local.lambda_zip
  source_code_hash               = fileexists(local.lambda_zip) ? filebase64sha256(local.lambda_zip) : null
  timeout                        = 30
  memory_size                    = 128
  reserved_concurrent_executions = 2
  environment {
    variables = {
      SOURCE_BUCKET      = aws_s3_bucket.images["input"].id
      DESTINATION_BUCKET = aws_s3_bucket.images["output"].id
      STATE_MACHINE_ARN  = aws_sfn_state_machine.images.arn
    }
  }
  lifecycle {
    precondition {
      condition     = fileexists(local.lambda_zip)
      error_message = "Build application.zip first using scripts/build_lambda.py."
    }
  }
  depends_on = [aws_iam_role_policy.lambda, aws_cloudwatch_log_group.lambda]
}

resource "aws_lambda_function" "worker" {
  function_name                  = local.function_names.worker
  role                           = aws_iam_role.functions["worker"].arn
  handler                        = "workflow.lambda_handler"
  runtime                        = "python3.12"
  architectures                  = ["x86_64"]
  filename                       = local.lambda_zip
  source_code_hash               = fileexists(local.lambda_zip) ? filebase64sha256(local.lambda_zip) : null
  layers                         = [aws_lambda_layer_version.pillow.arn]
  timeout                        = 45
  memory_size                    = 512
  reserved_concurrent_executions = 2
  environment {
    variables = {
      SOURCE_BUCKET          = aws_s3_bucket.images["input"].id
      DESTINATION_BUCKET     = aws_s3_bucket.images["output"].id
      METADATA_TABLE         = aws_dynamodb_table.images.name
      NOTIFICATION_TOPIC_ARN = aws_sns_topic.jobs.arn
      CLOUDFRONT_DOMAIN      = aws_cloudfront_distribution.images.domain_name
    }
  }
  depends_on = [aws_iam_role_policy.worker, aws_cloudwatch_log_group.functions]
}

resource "aws_lambda_function" "api" {
  function_name                  = local.function_names.api
  role                           = aws_iam_role.functions["api"].arn
  handler                        = "upload_api.lambda_handler"
  runtime                        = "python3.12"
  architectures                  = ["x86_64"]
  filename                       = local.lambda_zip
  source_code_hash               = fileexists(local.lambda_zip) ? filebase64sha256(local.lambda_zip) : null
  timeout                        = 10
  memory_size                    = 128
  reserved_concurrent_executions = 2
  environment {
    variables = {
      SOURCE_BUCKET  = aws_s3_bucket.images["input"].id
      METADATA_TABLE = aws_dynamodb_table.images.name
    }
  }
  depends_on = [aws_iam_role_policy.api, aws_cloudwatch_log_group.functions]
}

resource "aws_iam_role" "workflow" {
  name = "${local.name}-workflow"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow", Principal = { Service = "states.amazonaws.com" }, Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "workflow" {
  name = "${local.name}-invoke-worker"
  role = aws_iam_role.workflow.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = aws_lambda_function.worker.arn
    }]
  })
}

resource "aws_sfn_state_machine" "images" {
  name       = local.name
  type       = "STANDARD"
  role_arn   = aws_iam_role.workflow.arn
  definition = templatefile("${path.module}/workflow.asl.json.tftpl", { worker_arn = aws_lambda_function.worker.arn })
  depends_on = [aws_iam_role_policy.workflow]
}

resource "aws_lambda_event_source_mapping" "images" {
  event_source_arn        = aws_sqs_queue.images.arn
  function_name           = aws_lambda_function.processor.arn
  enabled                 = var.enable_processing
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]
  scaling_config {
    maximum_concurrency = 2
  }
  depends_on = [aws_iam_role_policy.lambda, aws_sqs_queue_redrive_allow_policy.images]
}
