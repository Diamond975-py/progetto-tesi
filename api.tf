
resource "aws_api_gateway_rest_api" "api" {
    name = "rest-api"
}

resource "aws_lambda_permission" "apigw_upload" {
  statement_id  = "AllowUploadInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.upload_presign.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.api.execution_arn}/*/*"
}


resource "aws_api_gateway_deployment" "deploy" {
  rest_api_id = aws_api_gateway_rest_api.api.id
}

resource "aws_api_gateway_stage" "prod" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  deployment_id = aws_api_gateway_deployment.deploy.id
  stage_name    = "prod"
}

