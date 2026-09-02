output "bucket_arn" {
  value = aws_s3_bucket.bucket.arn
}

output "bucket_id" {
  value = aws_s3_bucket.bucket.id
}

output "bucket_name" {
  value = aws_s3_bucket.bucket.bucket
}

output "kms_key_arn" {
  value = aws_kms_key.KMS.arn
}

output "kms_key_id" {
  value = aws_kms_key.KMS.key_id
}

output "quarantine_bucket_name" {
  value = aws_s3_bucket.quarantine.bucket
}

output "quarantine_bucket_arn" {
  value = aws_s3_bucket.quarantine.arn
}

output "quarantine_bucket_id" {
  value = aws_s3_bucket.quarantine.id
}