/*
resource "aws_api_gateway_request_validator" "upload_validator" {

  name = "upload-request-validator"

  rest_api_id = aws_api_gateway_rest_api.api.id

  validate_request_body = true

  validate_request_parameters = true

}
*/