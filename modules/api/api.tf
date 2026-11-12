
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
      aws_api_gateway_method.post_upload.id,

      aws_api_gateway_integration.get_test_mock.id,
      aws_api_gateway_integration.upload_lambda.id,
      aws_api_gateway_resource.files.path,
      aws_api_gateway_method.get_files.authorization,
      aws_api_gateway_method.get_files.authorizer_id,
      aws_api_gateway_integration.list_files.type,
      aws_api_gateway_integration.list_files.uri,
      aws_api_gateway_integration.list_files.timeout_milliseconds
    ]))
  }

  depends_on = [aws_lambda_permission.apigw_list_files]

  lifecycle {
    create_before_destroy = true
  }
}


resource "aws_api_gateway_stage" "prod" {

  rest_api_id   = aws_api_gateway_rest_api.api.id
  deployment_id = aws_api_gateway_deployment.deploy.id
  stage_name    = var.stage_name

  access_log_settings {

    destination_arn = aws_cloudwatch_log_group.api_gateway.arn


    format = jsonencode({

      requestId = "$context.requestId"

      ip = "$context.identity.sourceIp"

      caller = "$context.identity.caller"

      user = "$context.identity.user"

      requestTime = "$context.requestTime"

      httpMethod = "$context.httpMethod"

      resourcePath = "$context.resourcePath"

      status = "$context.status"

      protocol = "$context.protocol"

      responseLength = "$context.responseLength"

    })

  }


  xray_tracing_enabled = true

}

resource "aws_api_gateway_method_settings" "prod" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  stage_name  = aws_api_gateway_stage.prod.stage_name
  method_path = "*/*"

  settings {
    throttling_rate_limit  = var.rate_limit
    throttling_burst_limit = var.burst_limit
    logging_level          = "INFO"
    metrics_enabled        = true
  }
}

resource "aws_api_gateway_authorizer" "cognito" {

  name = "cognito-authorizer"

  rest_api_id = aws_api_gateway_rest_api.api.id

  type = "COGNITO_USER_POOLS"

  provider_arns = [
    var.cognito_user_pool_arn
  ]

}