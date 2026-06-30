
# IAM role for Lambda execution
data "aws_iam_policy_document" "assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role_policy" "s3_presign_policy" {
  name = "s3-presign-policy"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "s3:PutObject"
        ],
        Resource = "${aws_s3_bucket.bucket-documenti.arn}/*"
      }
    ]
  })
}

resource "aws_iam_role" "lambda_execution_role" {
  name               = "lambda_execution_role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Package the Lambda function code
data "archive_file" "archive" {
  type        = "zip"
  source_dir = "${path.module}/lambda"
  output_path = "${path.module}/lambda.zip"
}

# Trigger di S3
resource "aws_lambda_function" "lambda_function" {
  filename      = data.archive_file.archive.output_path
  function_name = "s3_trigger"
  role          = aws_iam_role.lambda_execution_role.arn
  handler       = "lambda_function.s3_trigger"
  code_sha256   = data.archive_file.archive.output_base64sha256
  runtime = "python3.11"
}

# Upload Presign
resource "aws_lambda_function" "upload_presign" {
  filename = data.archive_file.archive.output_path
  function_name = "upload_presign"
  role = aws_iam_role.lambda_execution_role.arn
  handler = "lambda_function.upload_presign"
  code_sha256 = data.archive_file.archive.output_base64sha256
  runtime = "python3.11"
}