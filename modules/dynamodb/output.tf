
output "name" {
 value = aws_dynamodb_table.dynamodb_table.name
}

output "table_arn" {
  value = aws_dynamodb_table.dynamodb_table.arn
}
