
resource "aws_kms_key" "KMS" {
  description         = "Chiave KMS per il bucket S3"
  enable_key_rotation = true

  // attesa di quanti giorni prima che la chiave sia eliminata
  deletion_window_in_days = 7

  // policy IAM per l'accesso
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM Root Permissions"
        Effect = "Allow"
        Principal = "*"
        // trattandosi di localhost tutte le azioni sono permesse, ma possono essere definite in base agli utenti IAM
        Action   = "kms:*"
        Resource = "*"
      }
    ]
  })
}

