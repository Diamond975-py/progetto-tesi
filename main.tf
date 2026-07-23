
module "s3" {
  source = "./modules/s3"

  bucket_name     = "documenti"
  
  lambda_role_arn = [
    module.lambda_s3_trigger.role_arn,
    module.lambda_upload_presign.role_arn
  ]
}

module "lambda_s3_trigger" {
  source = "./modules/lambda"

  function_name    = "s3_trigger"
  handler          = "lambda_function.s3_trigger"
  runtime          = "python3.11"
  lambda_role_name = "s3_trigger_role"
  bucket_arn = module.s3.bucket_arn
  dynamodb_table_arn = module.dynamodb.table_arn
  s3_actions = ["s3:GetObject", "s3:HeadObject"]
}

module "lambda_upload_presign" {
  source = "./modules/lambda"
  function_name    = "upload_presign"
  handler          = "lambda_function.upload_presign"
  runtime          = "python3.11"
  lambda_role_name = "upload_presign_role"
  bucket_arn = module.s3.bucket_arn
  s3_actions = ["s3:PutObject"]
}

module "api" {
  source = "./modules/api"
  api_name = "API"
  upload_lambda_invoke_arn = module.lambda_upload_presign.invoke_arn
  upload_lambda_function_name = module.lambda_upload_presign.name
  cognito_user_pool_arn = module.cognito.user_pool_arn
}

module "dynamodb" {
  source = "./modules/dynamodb"
  table_name = "FileMetaData"
}

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_s3_trigger.name
  principal     = "s3.amazonaws.com"
  source_arn    = module.s3.bucket_arn
}

resource "aws_s3_bucket_notification" "trigger" {
  bucket = module.s3.bucket_id

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
   