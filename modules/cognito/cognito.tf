resource "aws_cognito_user_pool" "this" {

  name = "${var.project_name}-${var.environment}-user-pool"

  username_attributes = [
    "email"
  ]

  auto_verified_attributes = [
    "email"
  ]

  /*
  schema {

    name = "email"

    attribute_data_type = "String"

    required = true

    mutable = true

  }
  */
}
resource "aws_cognito_user_pool_client" "this" {
  name         = "${var.project_name}-${var.environment}-app-client"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH"
  ]

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows = ["code"]
  allowed_oauth_scopes = ["email", "openid", "profile"]

  callback_urls = var.callback_urls
  logout_urls   = var.logout_urls

  supported_identity_providers = ["COGNITO"]
}