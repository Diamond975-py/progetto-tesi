
resource "aws_api_gateway_method" "post_upload" {
    rest_api_id = aws_api_gateway_rest_api.api.id
    resource_id = aws_api_gateway_resource.upload.id
    http_method = "POST"
    authorization = var.authorization
    authorizer_id = aws_api_gateway_authorizer.cognito.id
    /*request_validator_id = aws_api_gateway_request_validator.upload_validator.id
    request_models = {
  "application/json" = aws_api_gateway_model.upload_request.name
  */
}

resource "aws_api_gateway_integration" "upload_lambda" {
    rest_api_id = aws_api_gateway_rest_api.api.id
    resource_id = aws_api_gateway_resource.upload.id
    http_method = aws_api_gateway_method.post_upload.http_method
    
    type = "AWS_PROXY"
    timeout_milliseconds = var.timeout_ms  
    uri = var.upload_lambda_invoke_arn
}




