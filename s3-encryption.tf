
resource "aws_s3_bucket_server_side_encryption_configuration" "s3-kms-config" {
  bucket = aws_s3_bucket.bucket-documenti.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.KMS.key_id
    }
  }
}
