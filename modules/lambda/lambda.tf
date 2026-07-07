
# Package the Lambda function code
data "archive_file" "archive" {
  type        = "zip"
  source_dir = "${path.module}/lambda"
  output_path = "${path.module}/lambda.zip"
}

resource "aws_lambda_function" "this" {
  filename      = data.archive_file.archive.output_path  
  function_name = var.function_name
  role          = var.role_arn
  handler       = var.handler
  runtime       = var.runtime
  source_code_hash =  data.archive_file.archive.output_base64sha256

}