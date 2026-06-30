
def lambda_handler(event, context):
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

