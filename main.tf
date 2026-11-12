
module "s3" {
  source = "./modules/s3"

  bucket_name = "documenti-793452511140"

  lambda_role_arn = [
    module.lambda_s3_trigger.role_arn,
    module.lambda_upload_presign.role_arn
  ]
}

module "lambda_s3_trigger" {
  source = "./modules/lambda"

  function_name      = "s3_trigger"
  handler            = "lambda_function.s3_trigger"
  runtime            = "python3.11"
  lambda_role_name   = "s3_trigger_role"
  bucket_name        = module.s3.bucket_name
  bucket_arn         = module.s3.bucket_arn
  dynamodb_table_arn = module.dynamodb.table_arn
  s3_actions         = ["s3:GetObject", "s3:PutObject"]

  kms_key_arn             = module.s3.kms_key_arn
  additional_kms_key_arns = [module.dynamodb.kms_key_arn]
  kms_key_id              = module.s3.kms_key_arn
  quarantine_bucket_name  = module.s3.quarantine_bucket_name
  timeout                 = 60
}

module "lambda_upload_presign" {
  source = "./modules/lambda"

  function_name    = "upload_presign"
  handler          = "lambda_function.upload_presign"
  runtime          = "python3.11"
  lambda_role_name = "upload_presign_role"

  bucket_arn = module.s3.quarantine_bucket_arn

  s3_actions = ["s3:PutObject"]

  kms_key_arn = module.s3.kms_key_arn
  kms_key_id  = module.s3.kms_key_id

  bucket_name            = module.s3.bucket_name
  quarantine_bucket_name = module.s3.quarantine_bucket_name
  timeout                = 15
}

module "lambda_list_files" {
  source = "./modules/lambda"

  function_name    = "list_files"
  handler          = "lambda_function.list_files"
  runtime          = "python3.11"
  lambda_role_name = "list_files_role"

  bucket_name = module.s3.bucket_name
  bucket_arn  = module.s3.bucket_arn
  s3_actions  = ["s3:ListBucket"]
  timeout     = 10
}

module "api" {
  source                      = "./modules/api"
  api_name                    = "API"
  upload_lambda_invoke_arn    = module.lambda_upload_presign.invoke_arn
  upload_lambda_function_name = module.lambda_upload_presign.name
  cognito_user_pool_arn       = module.cognito.user_pool_arn
  list_files_lambda_invoke_arn    = module.lambda_list_files.invoke_arn
  list_files_lambda_function_name = module.lambda_list_files.name
}

module "dynamodb" {
  source     = "./modules/dynamodb"
  table_name = "FileMetaData"
}

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_s3_trigger.name
  principal     = "s3.amazonaws.com"
  source_arn    = module.s3.quarantine_bucket_arn
}

resource "aws_s3_bucket_notification" "trigger" {
  bucket = module.s3.quarantine_bucket_id

  lambda_function {
    lambda_function_arn = module.lambda_s3_trigger.arn
    events              = ["s3:ObjectCreated:*"]
  }

  depends_on = [aws_lambda_permission.allow_s3]
}

module "cognito" {
  source = "./modules/cognito"

  project_name = "serverless-sharepoint"
  environment  = "dev"

  callback_urls = ["http://localhost:4566"]
  logout_urls   = ["http://localhost:4566"]
}

resource "aws_iam_role_policy" "s3_trigger_quarantine_read" {
  name = "s3-trigger-quarantine-read"
  role = module.lambda_s3_trigger.role_name

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Effect = "Allow"

        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion"
        ]

        Resource = "${module.s3.quarantine_bucket_arn}/*"
      },

      {
        Sid      = "ListDestinationBucket"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = module.s3.bucket_arn
      }
    ]
  })
}

resource "aws_iam_role_policy" "list_files_list_bucket" {
  name = "list-final-documents-bucket"
  role = module.lambda_list_files.role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "s3:ListBucket"
      Resource = module.s3.bucket_arn
    }]
  })
}
