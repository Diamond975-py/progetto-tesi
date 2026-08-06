
resource "aws_cloudwatch_log_group" "waf" {

  name = "/aws/waf/${var.api_name}"

  retention_in_days = 30

}

resource "aws_wafv2_web_acl_logging_configuration" "api_waf_logs" {

  count = 0

  log_destination_configs = [
    aws_cloudwatch_log_group.waf.arn
  ]


  resource_arn = aws_wafv2_web_acl.api_waf.arn
}
