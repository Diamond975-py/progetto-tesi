
resource "aws_api_gateway_method" "post_upload" {
    rest_api_id = aws_api_gateway_rest_api.api.id
    resource_id = aws_api_gateway_resource.upload.id
    http_method = "POST"
    authorization = "NONE"
}

resource "aws_api_gateway_integration" "upload_lambda" {
    rest_api_id = aws_api_gateway_rest_api.api.id
    resource_id = aws_api_gateway_resource.upload.id
    http_method = aws_api_gateway_method.post_upload.http_method
    
    type = "AWS_PROXY"
    timeout_milliseconds = 29000    
    uri = aws_lambda_function.upload_presign.invoke_arn
}



