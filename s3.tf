
resource "aws_s3_bucket" "bucket-documenti" {
	bucket = "documenti"
}

resource "aws_s3_bucket" "quarantine" {
	bucket = "quarantine"
}

