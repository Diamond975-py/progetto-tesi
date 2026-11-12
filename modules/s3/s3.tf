
resource "aws_s3_bucket" "bucket" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_versioning" "versioning" {
  for_each = {
    main       = aws_s3_bucket.bucket.id
    logs       = aws_s3_bucket.logs.id
    quarantine = aws_s3_bucket.quarantine.id
  }

  bucket = each.value

  versioning_configuration {
    status = "Enabled"
  }
}