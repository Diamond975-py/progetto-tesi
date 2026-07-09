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