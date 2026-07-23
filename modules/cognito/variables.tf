variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "callback_urls" {
  type = list(string)
  default = ["http://localhost:4566"]
}

variable "logout_urls" {
  type = list(string)
  default = ["http://localhost:4566"]
}