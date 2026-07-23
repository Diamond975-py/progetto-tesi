resource "aws_s3_bucket_public_access_block" "block" {

  for_each = {
    main = aws_s3_bucket.bucket.id
    logs = aws_s3_bucket.logs.id
  }

  bucket = each.value

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}