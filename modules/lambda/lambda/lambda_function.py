import boto3
import json
import uuid
import os

s3 = boto3.client("s3")
 
BUCKET_NAME = os.environ.get("BUCKET_NAME", "documenti")
EXPIRATION = 3600

def s3_trigger(event, context):
    try:
        print("[!] Evento S3 ricevuto")

        for record in event["Records"]:

            file_name = record["s3"]["object"]["key"]
            file_size = record["s3"]["object"]["size"]
            bucket = record["s3"]["bucket"]["name"]
            timestamp = record["eventTime"]

            print("===== FILE METADATA =====")
            print(f"Bucket: {bucket}")
            print(f"File: {file_name}")
            print(f"Size: {file_size} bytes")
            print(f"Timestamp: {timestamp}")

        return {
            "statusCode": 200,
            "body": "Processed"
        }

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        raise e
    
def upload_presign(event, context):
   print(f"[!] Evento riconosciuto: {event}")

   # STEP 1: Genero UUID File
   file_id = str(uuid.uuid4())

   # STEP 2: Genero nome file
   file_name = f"{file_id}"

   # STEP 3: Genero presigned URL per l'upload
   try:
      url = s3.generate_presigned_url(
         ClientMethod = "put_object",
         Params = {
            "Bucket": BUCKET_NAME,
            "Key": file_name,
            "ContentType": "application/octet-stream"
         },
         ExpiresIn = EXPIRATION
      )

      print("[*] URL Generato")

   # STEP 4: Risposta API Gateway
      return {
         "statusCode": 200,
         "headers": {
            "Content-Type": "application/json"
         },

         "body": json.dumps({
            "file_id": file_id,
            "file_name": file_name,
            "upload_url": url,
            "epires_in": EXPIRATION
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
