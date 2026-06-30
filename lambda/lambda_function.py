import boto3
import json
import uuid
import os

s3 = boto3.client("s3")
 
BUCKET_NAME = os.environ.get("BUCKET_NAME", "documenti")
EXPIRATION = 3600

def s3_trigger(event, context):
    print(f"[!] Evento S3")
    if "Records" not in event:
       print("[i] Evento di test ignorato")
       return


    for event in event["Records"]:
       bucket = event["s3"]["bucket"]["name"]
       key = event["s3"]["object"]["key"]
       ip_addr = event["requestParameters"]["sourceIPAddress"]

       print(f"[*] Nuovo file: {key} nel bucket {bucket}")
       print(f"[*] Uploaded from {ip_addr}")

    print(f"\n[i] Dettagli tecnici:\n{event}")

    return {
       "statusCode": 200,
       "body": "OK"
    }

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