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
      ] : []
    )
  })
}


resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}