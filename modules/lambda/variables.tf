variable "function_name" {}
variable "handler" {}
variable "runtime" {}

variable "lambda_role_name" {
  type = string
}

variable "bucket_arn" {
  type = string
}

variable "dynamodb_table_arn" {
  type = string
  default = null
}

variable "reserved_concurrent_executions" {
  type = number
  default = 10
}

variable "s3_actions" {
  type = list(string)
}

variable "kms_key_arn" {
  type    = string
  default = null
}