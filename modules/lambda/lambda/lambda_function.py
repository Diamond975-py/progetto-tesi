import hashlib
import json
import os
import uuid
from urllib.parse import unquote_plus

import boto3  # type: ignore
from botocore.exceptions import ClientError  # type: ignore

AWS_REGION = os.environ.get("AWS_REGION", "eu-south-1")
s3 = boto3.client(
    "s3",
    region_name=AWS_REGION,
    endpoint_url=f"https://s3.{AWS_REGION}.amazonaws.com",
)
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("FileMetaData")

BUCKET_NAME = os.environ.get("BUCKET_NAME", "documenti")
KMS_KEY_ID = os.environ.get("KMS_KEY_ID")
QUARANTINE_BUCKET_NAME = os.environ.get("QUARANTINE_BUCKET_NAME", "documenti-quarantine")
EXPIRATION = 300
MAX_FILE_SIZE = 20 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def json_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def detect_file_type(file_header):
    if file_header.startswith(b"%PDF"):
        return "application/pdf"
    if file_header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if file_header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if file_header.startswith(b"PK"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "unknown"


def antivirus_scan(bucket, key, version_id):
    """Mock del progetto: da sostituire con un motore antivirus reale."""
    print(f"[*] Mock AV: s3://{bucket}/{key}?versionId={version_id}")
    return True


def upload_presign(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        content_type = body.get("content_type", "")
        if content_type not in ALLOWED_CONTENT_TYPES:
            return json_response(400, {"error": "Tipo di file non consentito"})
        if not KMS_KEY_ID:
            return json_response(500, {"error": "Configurazione KMS mancante"})

        file_id = str(uuid.uuid4())
        fields = {
            "Content-Type": content_type,
            "x-amz-server-side-encryption": "aws:kms",
            "x-amz-server-side-encryption-aws-kms-key-id": KMS_KEY_ID,
        }
        conditions = [
            {"bucket": QUARANTINE_BUCKET_NAME},
            ["eq", "$key", file_id],
            ["eq", "$Content-Type", content_type],
            ["content-length-range", 1, MAX_FILE_SIZE],
            {"x-amz-server-side-encryption": "aws:kms"},
            {"x-amz-server-side-encryption-aws-kms-key-id": KMS_KEY_ID},
        ]
        presigned = s3.generate_presigned_post(
            Bucket=QUARANTINE_BUCKET_NAME,
            Key=file_id,
            Fields=fields,
            Conditions=conditions,
            ExpiresIn=EXPIRATION,
        )
        return json_response(200, {
            "file_id": file_id,
            "upload_url": presigned["url"],
            "upload_fields": presigned["fields"],
            "expires_in": EXPIRATION,
        })
    except (TypeError, ValueError, json.JSONDecodeError):
        return json_response(400, {"error": "Body JSON non valido"})
    except Exception as error:
        print(f"[ERROR] Presigned POST: {error}")
        return json_response(500, {"error": "Errore interno del server"})


def save_result(event_file_id, source, metadata, timestamp, status, **extra):
    item = {
        "file_id": event_file_id,
        "source_bucket": source["bucket"],
        "source_key": source["key"],
        "source_version_id": source["version_id"],
        "size": metadata["ContentLength"],
        "mime_type": metadata.get("ContentType", "unknown"),
        "timestamp": timestamp,
        "status": status,
    }
    item.update(extra)
    table.put_item(Item=item)


def object_exists(bucket, key):
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in {
            "404",
            "NoSuchKey",
            "NotFound",
        }:
            return False
        raise


def s3_trigger(event, context):
    if "Records" not in event:
        raise ValueError("Evento senza Records")

    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        version_id = record["s3"]["object"].get("versionId")
        timestamp = record["eventTime"]
        if not version_id:
            raise ValueError(f"VersionId mancante per s3://{bucket}/{key}")

        source = {"bucket": bucket, "key": key, "version_id": version_id}
        event_file_id = f"{key}#{version_id}"
        metadata = s3.head_object(Bucket=bucket, Key=key, VersionId=version_id)
        file_size = metadata["ContentLength"]
        declared_mime_type = metadata.get("ContentType", "unknown")

        if file_size > MAX_FILE_SIZE or declared_mime_type not in ALLOWED_CONTENT_TYPES:
            save_result(event_file_id, source, metadata, timestamp, "REJECTED")
            continue

        response = s3.get_object(
            Bucket=bucket, Key=key, VersionId=version_id, Range="bytes=0-15"
        )
        detected_mime_type = detect_file_type(response["Body"].read())
        if detected_mime_type != declared_mime_type:
            save_result(event_file_id, source, metadata, timestamp, "REJECTED",
                        detected_mime_type=detected_mime_type)
            continue

        if not antivirus_scan(bucket, key, version_id):
            save_result(event_file_id, source, metadata, timestamp, "REJECTED",
                        detected_mime_type=detected_mime_type)
            continue

        destination_key = hashlib.sha256(event_file_id.encode("utf-8")).hexdigest()
        if not object_exists(BUCKET_NAME, destination_key):
            s3.copy_object(
                CopySource={"Bucket": bucket, "Key": key, "VersionId": version_id},
                Bucket=BUCKET_NAME,
                Key=destination_key,
                ServerSideEncryption="aws:kms",
                SSEKMSKeyId=KMS_KEY_ID,
                MetadataDirective="COPY",
            )
        else:
            print(f"[*] File già presente in s3://{BUCKET_NAME}/{destination_key}")
        save_result(event_file_id, source, metadata, timestamp, "PROCESSED",
                    bucket=BUCKET_NAME, destination_key=destination_key,
                    detected_mime_type=detected_mime_type)
        print(f"[+] File trasferito in s3://{BUCKET_NAME}/{destination_key}")

def list_files(event, context):
    query = event.get("queryStringParameters") or {}
    params = {"Bucket": BUCKET_NAME, "MaxKeys": 50}
    if query.get("next_token"):
        params["ContinuationToken"] = query["next_token"]

    try:
        page = s3.list_objects_v2(**params)
    except ClientError as error:
        details = error.response.get("Error", {})
        request_id = error.response.get("ResponseMetadata", {}).get("RequestId")
        print(
            f"[ERROR] S3 ListObjectsV2 fallita: bucket={BUCKET_NAME} "
            f"code={details.get('Code')} message={details.get('Message')} "
            f"request_id={request_id}"
        )
        return json_response(500, {"error": "Impossibile elencare i documenti"})

    return json_response(200, {
        "files": [
            {
                "key": item["Key"],
                "size": item["Size"],
                "last_modified": item["LastModified"].isoformat(),
            }
            for item in page.get("Contents", [])
        ],
        "next_token": page.get("NextContinuationToken"),
    })