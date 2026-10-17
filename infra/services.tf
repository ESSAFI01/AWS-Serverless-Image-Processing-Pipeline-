resource "aws_dynamodb_table" "images" {
  name           = "${local.name}-metadata"
  billing_mode   = "PROVISIONED"
  read_capacity  = 1
  write_capacity = 1
  hash_key       = "job_id"
  attribute {
    name = "job_id"
    type = "S"
  }
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

resource "aws_sns_topic" "jobs" {
  name = "${local.name}-jobs"
  # No subscriptions: adding recipients requires an explicit choice by the user.
}

resource "aws_s3_bucket_lifecycle_configuration" "input" {
  bucket = aws_s3_bucket.images["input"].id
  rule {
    id     = "expire-demo-uploads"
    status = "Enabled"
    filter {
      prefix = "uploads/"
    }
    expiration {
      days = 7
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "output" {
  bucket = aws_s3_bucket.images["output"].id
  rule {
    id     = "remove-intermediate-images"
    status = "Enabled"
    filter {
      prefix = "staging/"
    }
    expiration {
      days = 1
    }
  }
  rule {
    id     = "expire-demo-results"
    status = "Enabled"
    filter {
      prefix = "processed/"
    }
    expiration {
      days = 7
    }
  }
}

resource "aws_cloudfront_origin_access_control" "images" {
  name                              = local.name
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "images" {
  enabled         = var.enable_delivery
  is_ipv6_enabled = true
  comment         = "Graduation project: processed demo images only"
  price_class     = "PriceClass_100"
  origin {
    domain_name              = aws_s3_bucket.images["output"].bucket_regional_domain_name
    origin_id                = "processed-images"
    origin_access_control_id = aws_cloudfront_origin_access_control.images.id
    s3_origin_config {
      origin_access_identity = ""
    }
  }
  default_cache_behavior {
    target_origin_id       = "processed-images"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    min_ttl                = 0
    default_ttl            = 86400
    max_ttl                = 86400
    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }
  }
  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }
  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

resource "aws_s3_bucket_policy" "output" {
  bucket = aws_s3_bucket.images["output"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowCloudFrontProcessedImagesOnly"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.images["output"].arn}/processed/*"
      Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.images.arn } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.images]
}

resource "aws_apigatewayv2_api" "images" {
  name          = "${local.name}-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "images" {
  api_id                 = aws_apigatewayv2_api.images.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
  timeout_milliseconds   = 15000
}

resource "aws_apigatewayv2_route" "images" {
  for_each           = toset(["POST /uploads", "GET /jobs/{job_id}"])
  api_id             = aws_apigatewayv2_api.images.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.images.id}"
  authorization_type = "AWS_IAM"
}

resource "aws_apigatewayv2_stage" "images" {
  api_id      = aws_apigatewayv2_api.images.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 2
    throttling_rate_limit  = 1
  }
}

resource "aws_lambda_permission" "api" {
  statement_id  = "AllowImageAPI"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.images.execution_arn}/*/*"
}
