resource "aws_wafv2_web_acl" "api_waf" {

  name  = "${var.api_name}-waf"
  scope = "REGIONAL"


  default_action {
    allow {}
  }


  #####################################
  # Rate limiting per IP
  #####################################

  rule {

    name     = "RateLimitRequests"
    priority = 1


    action {
      block {}
    }


    statement {

      rate_based_statement {

        limit = var.ip_limit

        aggregate_key_type = "IP"

      }
    }


    visibility_config {

      cloudwatch_metrics_enabled = true

      metric_name = "rate-limit"

      sampled_requests_enabled = true

    }

  }



  #####################################
  # Anonymous IP detection
  #####################################

/*
  rule {

    name     = "AnonymousIPList"
    priority = 2


    action {

      block {}

    }


    statement {

      managed_rule_group_statement {

        name = "AWSManagedRulesAnonymousIpList"

        vendor_name = "AWS"


      }

    }


    visibility_config {

      cloudwatch_metrics_enabled = true

      metric_name = "anonymous-ip"ano

      sampled_requests_enabled = true

    }

  }
*/


  #####################################
  # AWS Managed Common Rules
  #####################################


  rule {

    name     = "AWSManagedRulesCommonRuleSet"

    priority = 3


    override_action {

      none {}

    }


    statement {

      managed_rule_group_statement {

        name = "AWSManagedRulesCommonRuleSet"

        vendor_name = "AWS"


      }

    }


    visibility_config {

      cloudwatch_metrics_enabled = true

      metric_name = "common-rules"

      sampled_requests_enabled = true

    }

  }





  #####################################
  # Known malicious inputs
  #####################################


  rule {


    name = "AWSManagedRulesKnownBadInputs"

    priority = 4


    override_action {

      none {}

    }


    statement {


      managed_rule_group_statement {


        name = "AWSManagedRulesKnownBadInputsRuleSet"

        vendor_name = "AWS"


      }

    }



    visibility_config {


      cloudwatch_metrics_enabled = true

      metric_name = "known-bad-inputs"

      sampled_requests_enabled = true

    }

  }


  visibility_config {


    cloudwatch_metrics_enabled = true

    metric_name = "${var.api_name}-waf"

    sampled_requests_enabled = true


  }
}

resource "aws_wafv2_web_acl_association" "api" {

  resource_arn = aws_api_gateway_stage.prod.arn

  web_acl_arn = aws_wafv2_web_acl.api_waf.arn

}