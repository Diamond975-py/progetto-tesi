
resource "aws_dynamodb_table" "dynamodb_table" {
    name = var.table_name
    billing_mode = "PAY_PER_REQUEST"
    hash_key = "file_id"

    attribute {
        name = "file_id"
        type = "S"
    }
}