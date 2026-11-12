
terraform {
  required_version = ">= 1.10, < 2.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.51.0"
    }
  }
}

provider "aws" {
  region              = "eu-south-1"
  allowed_account_ids = ["793452511140"]
}

