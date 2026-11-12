resource "aws_iam_role_policy" "lambda_policy" {

  name = "${var.lambda_role_name}-policy"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = concat(

      [
        {
          Effect = "Allow"

          Action = var.s3_actions

          Resource = "${var.bucket_arn}/*"
        },
        {
          Effect = "Allow"

          Action = [
            "xray:PutTraceSegments",
            "xray:PutTelemetryRecords"
          ]

          Resource = "*"
        }
      ],

      var.dynamodb_table_arn != null ? [
        {
          Effect = "Allow"

          Action = [
            "dynamodb:PutItem"
          ]

          Resource = var.dynamodb_table_arn
        }
      ] : [],

      var.kms_key_arn != null || length(var.additional_kms_key_arns) > 0 ? [
        {
          Effect = "Allow"

          Action = [
            "kms:Encrypt",
            "kms:Decrypt",
            "kms:DescribeKey",
            "kms:GenerateDataKey"
          ]

          Resource = concat(
            var.kms_key_arn != null ? [var.kms_key_arn] : [],
            var.additional_kms_key_arns
          )
        }
      ] : []
    )
  })
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
