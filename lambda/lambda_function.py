
def lambda_handler(event, context):
    print(f"[!] Evento S3: {event}")
    if "Records" not in event:
        print("[i] Evento di test ignorato")
        return

    for event in event["Records"]:
        bucket = event["s3"]["bucket"]["name"]
        key = event["s3"]["object"]["key"]
        ip_addr = event["requestParameters"]["sourceIPAddress"]

        print(f"[*] Nuovo file: {key} nel bucket {bucket}")
        p

    return {
        "statusCode": 200,
        "body": "OK"
    }
