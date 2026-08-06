resource "aws_kms_key" "dynamodb" {
  description             = "KMS key for DynamoDB"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}