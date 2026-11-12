
resource "aws_s3_bucket_server_side_encryption_configuration" "s3-kms-config" {

  for_each = {
    main       = aws_s3_bucket.bucket.id
    quarantine = aws_s3_bucket.quarantine.id
  }

  bucket = each.value

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.KMS.key_id
    }
  }
}

# S3 server access logging does not support a customer-managed KMS key on the
# destination bucket. Use SSE-S3 for the logs bucket.
resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}