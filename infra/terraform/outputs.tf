output "upload_bucket" {
  value = aws_s3_bucket.uploads.bucket
}

output "api_url" {
  value = aws_apigatewayv2_api.results_api.api_endpoint
}

output "state_machine_arn" {
  value = aws_sfn_state_machine.pipeline.arn
}
