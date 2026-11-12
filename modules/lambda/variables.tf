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
  type    = string
  default = null
}

variable "reserved_concurrent_executions" {
  type    = number
  default = -1
}

variable "timeout" {
  type    = number
  default = 30
}

variable "s3_actions" {
  type = list(string)
}

variable "kms_key_arn" {
  type    = string
  default = null
}

variable "additional_kms_key_arns" {
  type    = list(string)
  default = []
}

variable "kms_key_id" {
  type    = string
  default = null
}


variable "quarantine_bucket_name" {
  type    = string
  default = null
}

variable "bucket_name" {
  type = string
}
