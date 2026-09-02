
resource "aws_s3_bucket" "quarantine" {
  bucket = "${var.bucket_name}-quarantine"
}
