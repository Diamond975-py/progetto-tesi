import boto3 # type: ignore
import json
import uuid
import os

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

table = dynamodb.Table(
    "FileMetaData"
)

BUCKET_NAME = os.environ.get("BUCKET_NAME", "documenti")
KMS_KEY_ID = os.environ.get("KMS_KEY_ID")

EXPIRATION = 300


def s3_trigger(event, context):

    try:
        print("[!] Evento S3 ricevuto")

        if "Records" not in event:
            raise Exception("Evento senza Records")

        for record in event["Records"]:

            bucket = record["s3"]["bucket"]["name"]
            key = record["s3"]["object"]["key"]

            timestamp = record["eventTime"]
            event_name = record["eventName"]

            metadata = s3.head_object(
                Bucket=bucket,
                Key=key
            )

            file_size = metadata["ContentLength"]
            mime_type = metadata.get(
                "ContentType",
                "unknown"
            )

            print("[+] File processato")
            print(f"Bucket: {bucket}")
            print(f"Nome file: {key}")
            print(f"Dimensione: {file_size} bytes")
            print(f"MIME type: {mime_type}")
            print(f"Timestamp: {timestamp}")
            print(f"Evento: {event_name}")
            print("==============================")


            table.put_item(
               Item={
                  "file_id": key,
                  "bucket": bucket,
                  "size": file_size,
                  "mime_type": mime_type,
                  "timestamp": timestamp,
                  "status": "PROCESSED"
               }
            )


        return {
            "statusCode": 200,
            "body": "Processing completato"
        }


    except Exception as e:

        print(f"[ERROR] Errore durante processing S3: {str(e)}")

        raise e



def upload_presign(event, context):

   print(f"[!] Evento riconosciuto: {event}")


   file_id = str(uuid.uuid4())

   file_name = f"{file_id}"


   try:

      params = {
          "Bucket": BUCKET_NAME,
          "Key": file_name,
          "ContentType": "application/octet-stream",
          "ServerSideEncryption": "aws:kms",
          "SSEKMSKeyId": KMS_KEY_ID
      }


      url = s3.generate_presigned_url(
         ClientMethod="put_object",
         Params=params,
         ExpiresIn=EXPIRATION
      )


      print("[*] URL Generato")


      return {

         "statusCode": 200,

         "headers": {
            "Content-Type": "application/json"
         },

         "body": json.dumps({

            "file_id": file_id,

            "file_name": file_name,

            "upload_url": url,

            "expires_in": EXPIRATION

         })

      }


   except Exception as e:

      print(f"[!] Errore: {str(e)}")


      return {

         "statusCode": 500,

         "body": json.dumps({

            "error": str(e)

         })

      }
   