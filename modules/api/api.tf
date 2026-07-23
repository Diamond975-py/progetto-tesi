
resource "aws_api_gateway_rest_api" "api" {
    name = var.api_name
}

resource "aws_lambda_permission" "apigw_upload" {
  statement_id  = "AllowUploadInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.upload_lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.api.execution_arn}/*/*"
}


resource "aws_api_gateway_deployment" "deploy" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  triggers = {

  redeployment = sha1(jsonencode([

    aws_api_gateway_resource.test.id,
    aws_api_gateway_resource.upload.id,

    aws_api_gateway_method.get_test.id,
    aws_api_gateway_method.post_upload.id

  ]))

  }
}


resource "aws_api_gateway_stage" "prod" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  deployment_id = aws_api_gateway_deployment.deploy.id
  stage_name    = var.stage_name
}

resource "aws_api_gateway_authorizer" "cognito" {

  name = "cognito-authorizer"

  rest_api_id = aws_api_gateway_rest_api.api.id

  type = "COGNITO_USER_POOLS"

  provider_arns = [
    var.cognito_user_pool_arn
  ]

}