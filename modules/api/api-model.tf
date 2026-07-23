
resource "aws_api_gateway_model" "upload_request" {

  rest_api_id = aws_api_gateway_rest_api.api.id

  name = "UploadRequest"

  content_type = "application/json"


  schema = jsonencode({

    type = "object"

    required = [
      "filename"
    ]

    properties = {

      filename = {

        type = "string"

      }

    }

  })

}