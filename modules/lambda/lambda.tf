
# Package the Lambda function code
data "archive_file" "archive" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/lambda.zip"
}

resource "aws_lambda_function" "this" {
  filename         = data.archive_file.archive.output_path
  function_name    = var.function_name
  role             = aws_iam_role.lambda_execution_role.arn
  handler          = var.handler
  runtime          = var.runtime
  source_code_hash = data.archive_file.archive.output_base64sha256
  timeout          = var.timeout
  memory_size      = 256

  depends_on = [
    aws_iam_role_policy.lambda_policy,
    aws_iam_role_policy_attachment.lambda_logs
  ]

  tracing_config {
    mode = "Active"
  }

  reserved_concurrent_executions = var.reserved_concurrent_executions

  environment {
    variables = {
      for key, value in {
        BUCKET_NAME            = var.bucket_name
        QUARANTINE_BUCKET_NAME = var.quarantine_bucket_name
        KMS_KEY_ID             = var.kms_key_id
      } : key => value if value != null
    }
  }
}
