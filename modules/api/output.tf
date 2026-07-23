
output "api_id" {
  value = aws_api_gateway_rest_api.api.id
}

output "upload_resource_id" {
  value = aws_api_gateway_resource.upload.id
}

output "authorizer_id" {
  value = aws_api_gateway_authorizer.cognito.id
}