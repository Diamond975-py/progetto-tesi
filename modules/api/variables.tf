variable "api_name" {
}

variable "stage_name" {
  default = "prod"
}

variable "test_path" {
  default = "test"
}

variable "upload_path" {
  default = "upload"
}

variable "authorization" {
  default = "NONE"
}

variable "timeout_ms" {
  default = 29000
}

variable "upload_lambda_invoke_arn" {}

variable "upload_lambda_function_name" {}

variable "test_response_message" {
  default = "Test completato"
}

variable "test_response_status" {
  default = "ok"
}

variable "mock_request_template" {
  default = <<EOF
{
  "statusCode": 200
}
EOF
}