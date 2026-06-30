
resource "aws_api_gateway_method" "get_test" {
    rest_api_id = aws_api_gateway_rest_api.api.id
    resource_id = aws_api_gateway_resource.test.id
    http_method = "GET"
    authorization = "NONE"
}

resource "aws_api_gateway_integration" "get_test_mock" {
  rest_api_id          = aws_api_gateway_rest_api.api.id
  resource_id          = aws_api_gateway_resource.test.id
  http_method          = aws_api_gateway_method.get_test.http_method  
  type                 = "MOCK"
  timeout_milliseconds = 29000

  request_parameters = {
    "integration.request.header.X-Authorization" = "'static'"
  }

    request_templates = {
    "application/json" = <<EOF
    {
    "statusCode": 200
    }
    EOF
    }
}

resource "aws_api_gateway_method_response" "response_200" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_resource.test.id
  http_method = aws_api_gateway_method.get_test.http_method
  status_code = "200"
}

resource "aws_api_gateway_integration_response" "response_200" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  resource_id = aws_api_gateway_resource.test.id
  http_method = aws_api_gateway_method.get_test.http_method
  status_code = aws_api_gateway_method_response.response_200.status_code

  response_templates = {
    "application/json" = jsonencode({
      message = "Test completato"
      status  = "ok"
    })
  }

  depends_on = [aws_api_gateway_integration.get_test_mock]
}


