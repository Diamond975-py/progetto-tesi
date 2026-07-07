
resource "aws_api_gateway_method" "post_upload" {
    rest_api_id = aws_api_gateway_rest_api.api.id
    resource_id = aws_api_gateway_resource.upload.id
    http_method = "POST"
    authorization = var.authorization
}

resource "aws_api_gateway_integration" "upload_lambda" {
    rest_api_id = aws_api_gateway_rest_api.api.id
    resource_id = aws_api_gateway_resource.upload.id
    http_method = aws_api_gateway_method.post_upload.http_method
    
    type = "AWS_PROXY"
    timeout_milliseconds = var.timeout_ms  
    uri = var.upload_lambda_invoke_arn
}




