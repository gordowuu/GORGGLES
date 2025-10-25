terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.4"
    }
  }
}

provider "aws" {
  region = var.region
}

locals {
  name     = "${var.project_name}-${var.environment}"
  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# -----------------
# S3 Buckets
# -----------------
resource "aws_s3_bucket" "uploads" {
  bucket = "${local.name}-uploads"
  tags   = local.tags
}

resource "aws_s3_bucket_server_side_encryption_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket" "processed" {
  bucket = "${local.name}-processed"
  tags   = local.tags
}

resource "aws_s3_bucket_server_side_encryption_configuration" "processed" {
  bucket = aws_s3_bucket.processed.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Optional static website bucket
resource "aws_s3_bucket" "website" {
  count  = var.enable_website ? 1 : 0
  bucket = "${local.name}-website"
  tags   = local.tags
}

# -----------------
# DynamoDB
# -----------------
resource "aws_dynamodb_table" "jobs" {
  name         = "${local.name}-jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "jobId"

  attribute {
    name = "jobId"
    type = "S"
  }
  tags = local.tags
}

# -----------------
# IAM roles and policies for Lambdas
# -----------------
resource "aws_iam_role" "lambda_exec" {
  name               = "${local.name}-lambda-exec"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# Data source for VPC subnets (for Lambda VPC configuration)
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_iam_role_policy_attachment" "basic_exec" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# VPC execution role for Lambda functions that need EC2 access
resource "aws_iam_role_policy_attachment" "vpc_exec" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy" "pipeline_access" {
  name = "${local.name}-pipeline-access"
  role = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.pipeline_access.json
}

data "aws_iam_policy_document" "pipeline_access" {
  statement {
    actions = [
      "s3:GetObject","s3:PutObject","s3:ListBucket"
    ]
    resources = [
      aws_s3_bucket.uploads.arn,
      "${aws_s3_bucket.uploads.arn}/*",
      aws_s3_bucket.processed.arn,
      "${aws_s3_bucket.processed.arn}/*"
    ]
  }
  statement {
    actions = [
      "transcribe:StartTranscriptionJob","transcribe:GetTranscriptionJob"
    ]
    resources = ["*"]
  }
  statement {
    actions = [
      "rekognition:StartFaceDetection","rekognition:GetFaceDetection"
    ]
    resources = ["*"]
  }
  statement {
    actions = [
      "sagemaker:InvokeEndpoint"
    ]
    resources = ["*"]
  }
  statement {
    actions = ["states:StartExecution","states:SendTaskSuccess","states:SendTaskFailure"]
    resources = ["*"]
  }
  statement {
    actions = ["dynamodb:PutItem","dynamodb:GetItem","dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.jobs.arn]
  }
}

# -----------------
# Package Lambda code via archive_file
# -----------------
data "archive_file" "s3_trigger_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambdas/s3_trigger"
  output_path = "${path.module}/../../dist/s3_trigger.zip"
}

resource "aws_lambda_function" "s3_trigger" {
  function_name = "${local.name}-s3-trigger"
  role          = aws_iam_role.lambda_exec.arn
  runtime       = "python3.11"
  handler       = "handler.handler"
  filename      = data.archive_file.s3_trigger_zip.output_path
  timeout       = 30
  environment { variables = { STATE_MACHINE_ARN = aws_sfn_state_machine.pipeline.arn } }
  tags = local.tags
}

# Extract

data "archive_file" "extract_media_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambdas/extract_media"
  output_path = "${path.module}/../../dist/extract_media.zip"
}

resource "aws_lambda_function" "extract_media" {
  function_name = "${local.name}-extract-media"
  role          = aws_iam_role.lambda_exec.arn
  runtime       = "python3.11"
  handler       = "handler.handler"
  filename      = data.archive_file.extract_media_zip.output_path
  timeout       = 900  # 15 minutes for video processing
  memory_size   = 2048  # Increased for video processing
  
  # Attach FFmpeg layer if available
  layers = var.ffmpeg_layer_arn != "" ? [var.ffmpeg_layer_arn] : []
  
  environment {
    variables = {
      PROCESSED_BUCKET = aws_s3_bucket.processed.bucket
      FFMPEG_PATH      = "/opt/bin/ffmpeg"  # Path in Lambda layer
    }
  }
  
  tags = local.tags
}

# Start Transcribe

data "archive_file" "start_transcribe_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambdas/start_transcribe"
  output_path = "${path.module}/../../dist/start_transcribe.zip"
}

resource "aws_lambda_function" "start_transcribe" {
  function_name = "${local.name}-start-transcribe"
  role          = aws_iam_role.lambda_exec.arn
  runtime       = "python3.11"
  handler       = "handler.handler"
  filename      = data.archive_file.start_transcribe_zip.output_path
  timeout       = 300  # 5 minutes for long transcription jobs
  memory_size   = 512
  
  environment {
    variables = {
      PROCESSED_BUCKET = aws_s3_bucket.processed.bucket
    }
  }
  
  tags = local.tags
}

# Start Rekognition

data "archive_file" "start_rekognition_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambdas/start_rekognition"
  output_path = "${path.module}/../../dist/start_rekognition.zip"
}

resource "aws_lambda_function" "start_rekognition" {
  function_name = "${local.name}-start-rekognition"
  role          = aws_iam_role.lambda_exec.arn
  runtime       = "python3.11"
  handler       = "handler.handler"
  filename      = data.archive_file.start_rekognition_zip.output_path
  timeout       = 300  # 5 minutes for long rekognition jobs
  memory_size   = 512
  
  environment {
    variables = {
      PROCESSED_BUCKET = aws_s3_bucket.processed.bucket
    }
  }
  
  tags = local.tags
}

# Invoke lip reading

data "archive_file" "invoke_lipreading_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambdas/invoke_lipreading"
  output_path = "${path.module}/../../dist/invoke_lipreading.zip"
}

resource "aws_lambda_function" "invoke_lipreading" {
  function_name = "${local.name}-invoke-lipreading"
  role          = aws_iam_role.lambda_exec.arn
  runtime       = "python3.11"
  handler       = "handler.handler"
  filename      = data.archive_file.invoke_lipreading_zip.output_path
  timeout       = 600  # 10 minutes for lip reading inference
  memory_size   = 1024
  
  # Attach requests layer if available
  layers = var.requests_layer_arn != "" ? [var.requests_layer_arn] : []
  
  # VPC configuration for EC2 access
  vpc_config {
    subnet_ids         = data.aws_subnets.default.ids
    security_group_ids = [aws_security_group.lambda.id]
  }
  
  environment {
    variables = {
      AVHUBERT_ENDPOINT = var.avhubert_endpoint != "" ? var.avhubert_endpoint : "http://PLACEHOLDER:8000"
      PROCESSED_BUCKET  = aws_s3_bucket.processed.bucket
    }
  }
  
  tags = local.tags
}

# Fuse results

data "archive_file" "fuse_results_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambdas/fuse_results"
  output_path = "${path.module}/../../dist/fuse_results.zip"
}

resource "aws_lambda_function" "fuse_results" {
  function_name = "${local.name}-fuse-results"
  role          = aws_iam_role.lambda_exec.arn
  runtime       = "python3.11"
  handler       = "handler.handler"
  filename      = data.archive_file.fuse_results_zip.output_path
  timeout       = 300  # 5 minutes for result fusion
  memory_size   = 1024
  
  # Attach requests layer if available
  layers = var.requests_layer_arn != "" ? [var.requests_layer_arn] : []
  
  # VPC configuration for EC2 access (if needed)
  vpc_config {
    subnet_ids         = data.aws_subnets.default.ids
    security_group_ids = [aws_security_group.lambda.id]
  }
  
  environment {
    variables = {
      PROCESSED_BUCKET = aws_s3_bucket.processed.bucket
      JOBS_TABLE       = aws_dynamodb_table.jobs.name
    }
  }
  
  tags = local.tags
}

# API get results

data "archive_file" "get_results_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../../lambdas/get_results"
  output_path = "${path.module}/../../dist/get_results.zip"
}

resource "aws_lambda_function" "get_results" {
  function_name = "${local.name}-get-results"
  role          = aws_iam_role.lambda_exec.arn
  runtime       = "python3.11"
  handler       = "handler.handler"
  filename      = data.archive_file.get_results_zip.output_path
  timeout       = 30
  environment { variables = { PROCESSED_BUCKET = aws_s3_bucket.processed.bucket, JOBS_TABLE = aws_dynamodb_table.jobs.name } }
  tags = local.tags
}

# -----------------
# S3 Event -> Lambda trigger -> Step Functions
# -----------------
resource "aws_s3_bucket_notification" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.s3_trigger.arn
    events              = ["s3:ObjectCreated:Put"]
    filter_prefix       = "uploads/"
    filter_suffix       = ".mp4"
  }

  depends_on = [aws_lambda_permission.allow_s3_to_invoke]
}

resource "aws_lambda_permission" "allow_s3_to_invoke" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.s3_trigger.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.uploads.arn
}

# -----------------
# Step Functions State Machine
# -----------------
resource "aws_iam_role" "sfn_role" {
  name               = "${local.name}-sfn-role"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "sfn_invoke_lambdas" {
  name = "${local.name}-sfn-invoke-lambdas"
  role = aws_iam_role.sfn_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"],
      Resource = [
        aws_lambda_function.extract_media.arn,
        aws_lambda_function.start_transcribe.arn,
        aws_lambda_function.start_rekognition.arn,
        aws_lambda_function.invoke_lipreading.arn,
        aws_lambda_function.fuse_results.arn
      ]
    }]
  })
}

locals {
  sfn_definition = jsonencode({
    Comment = "Gorggle processing pipeline with retry logic",
    StartAt = "ExtractMedia",
    States = {
      ExtractMedia = {
        Type = "Task",
        Resource = aws_lambda_function.extract_media.arn,
        Next     = "ParallelProcessing"
        Retry = [{
          ErrorEquals     = ["States.TaskFailed", "Lambda.ServiceException", "Lambda.TooManyRequestsException"]
          IntervalSeconds = 2
          MaxAttempts     = 3
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "ProcessingFailed"
        }]
      },
      # Run Transcribe, Rekognition, and Lip Reading in parallel
      ParallelProcessing = {
        Type = "Parallel",
        Branches = [
          {
            StartAt = "StartTranscribe",
            States = {
              StartTranscribe = {
                Type = "Task",
                Resource = aws_lambda_function.start_transcribe.arn,
                End = true
                Retry = [{
                  ErrorEquals     = ["States.TaskFailed"]
                  IntervalSeconds = 2
                  MaxAttempts     = 2
                  BackoffRate     = 2.0
                }]
              }
            }
          },
          {
            StartAt = "StartRekognition",
            States = {
              StartRekognition = {
                Type = "Task",
                Resource = aws_lambda_function.start_rekognition.arn,
                End = true
                Retry = [{
                  ErrorEquals     = ["States.TaskFailed"]
                  IntervalSeconds = 2
                  MaxAttempts     = 2
                  BackoffRate     = 2.0
                }]
              }
            }
          },
          {
            StartAt = "InvokeLipReading",
            States = {
              InvokeLipReading = {
                Type = "Task",
                Resource = aws_lambda_function.invoke_lipreading.arn,
                End = true
                Retry = [{
                  ErrorEquals     = ["States.TaskFailed"]
                  IntervalSeconds = 5
                  MaxAttempts     = 2
                  BackoffRate     = 2.0
                }]
              }
            }
          }
        ]
        Next = "FuseResults"
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "ProcessingFailed"
        }]
      },
      FuseResults = {
        Type     = "Task",
        Resource = aws_lambda_function.fuse_results.arn,
        End      = true
        Retry = [{
          ErrorEquals     = ["States.TaskFailed"]
          IntervalSeconds = 2
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "ProcessingFailed"
        }]
      },
      ProcessingFailed = {
        Type  = "Fail",
        Error = "ProcessingError",
        Cause = "One or more processing steps failed after retries"
      }
    }
  })
}

resource "aws_sfn_state_machine" "pipeline" {
  name     = "${local.name}-pipeline"
  role_arn = aws_iam_role.sfn_role.arn
  definition = local.sfn_definition
  tags = local.tags
}

# -----------------
# API Gateway (HTTP API) for getting results
# -----------------
resource "aws_apigatewayv2_api" "results_api" {
  name          = "${local.name}-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.results_api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_apigatewayv2_integration" "get_results" {
  api_id                 = aws_apigatewayv2_api.results_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.get_results.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "get_results" {
  api_id    = aws_apigatewayv2_api.results_api.id
  route_key = "GET /results/{jobId}"
  target    = "integrations/${aws_apigatewayv2_integration.get_results.id}"
}

resource "aws_lambda_permission" "allow_apigw_to_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.get_results.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.results_api.execution_arn}/*/*"
}
