
resource "aws_s3_bucket_policy" "deny_non_kms" { 
    bucket = aws_s3_bucket.bucket.id 
    policy = jsonencode(
        { 
            Version = "2012-10-17" 
            Statement = [ 
                { 
                    Sid = "DenyUnencryptedUploads" 
                    Effect = "Deny" 
                    Principal = "*" 
                    Action = "s3:PutObject"
                    Resource = "${aws_s3_bucket.bucket.arn}/*" 
                    Condition = { 
                        StringNotEquals = { 
                            "s3:x-amz-server-side-encryption" = "aws:kms" 
                        } 
                    } 
                } 
            ] 
        }) 
}
