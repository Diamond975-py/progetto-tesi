import boto3  # type: ignore
import json
import os
import uuid
from urllib.parse import unquote_plus


# =========================================================
# AWS CLIENTS
# =========================================================

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

table = dynamodb.Table("FileMetaData")


# =========================================================
# CONFIGURATION
# =========================================================

BUCKET_NAME = os.environ.get(
    "BUCKET_NAME",
    "documenti"
)

KMS_KEY_ID = os.environ.get(
    "KMS_KEY_ID"
)

QUARANTINE_BUCKET_NAME = os.environ.get(
    "QUARANTINE_BUCKET_NAME",
    "documenti-quarantine"
)

EXPIRATION = 300  # 5 minuti

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


# =========================================================
# FILE TYPE DETECTION
# =========================================================

def detect_file_type(file_content):

    # PDF
    if file_content.startswith(b"%PDF"):
        return "application/pdf"

    # PNG
    if file_content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    # JPEG
    if file_content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    # DOCX
    if file_content.startswith(b"PK"):
        return (
            "application/"
            "vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    return "unknown"


# =========================================================
# MOCK ANTIVIRUS
# =========================================================

def antivirus_scan(bucket, key):

    """
    Mock antivirus.

    Attualmente tutti i file vengono considerati sicuri.
    Questa funzione potrà essere sostituita successivamente
    con un vero motore antivirus.
    """

    print(f"[*] Mock AV: scansione di {key}")

    return True


# =========================================================
# PRESIGNED UPLOAD
# =========================================================

def upload_presign(event, context):

    try:

        print("[!] Richiesta presigned upload ricevuta")


        # -------------------------------------------------
        # Recupera il body
        # -------------------------------------------------

        body = json.loads(
            event.get("body") or "{}"
        )

        content_type = body.get(
            "content_type",
            ""
        )


        # -------------------------------------------------
        # Controllo MIME
        # -------------------------------------------------

        if content_type not in ALLOWED_CONTENT_TYPES:

            print(
                "[!] Tipo di file non consentito: "
                f"{content_type}"
            )

            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps({
                    "error": "Tipo di file non consentito"
                })
            }


        # -------------------------------------------------
        # Generazione ID
        # -------------------------------------------------

        file_id = str(uuid.uuid4())

        key = f"{file_id}"


        # -------------------------------------------------
        # Controllo KMS
        # -------------------------------------------------

        if not KMS_KEY_ID:

            print("[ERROR] KMS_KEY_ID non configurato")

            return {
                "statusCode": 500,
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps({
                    "error": "Configurazione KMS mancante"
                })
            }


        # -------------------------------------------------
        # Presigned POST conditions
        # -------------------------------------------------

        conditions = [

            {
                "bucket": QUARANTINE_BUCKET_NAME
            },

            [
                "eq",
                "$key",
                key
            ],

            [
                "eq",
                "$Content-Type",
                content_type
            ],

            [
                "content-length-range",
                1,
                MAX_FILE_SIZE
            ],

            {
                "x-amz-server-side-encryption": "aws:kms"
            },

            {
                "x-amz-server-side-encryption-aws-kms-key-id":
                    KMS_KEY_ID
            }
        ]


        # -------------------------------------------------
        # Presigned POST fields
        # -------------------------------------------------

        fields = {

            "Content-Type": content_type,

            "x-amz-server-side-encryption":
                "aws:kms",

            "x-amz-server-side-encryption-aws-kms-key-id":
                KMS_KEY_ID
        }


        # -------------------------------------------------
        # Generate presigned POST
        # -------------------------------------------------

        presigned = s3.generate_presigned_post(

            Bucket=QUARANTINE_BUCKET_NAME,

            Key=key,

            Fields=fields,

            Conditions=conditions,

            ExpiresIn=EXPIRATION
        )


        print("[+] Presigned POST generato")


        # -------------------------------------------------
        # Response
        # -------------------------------------------------

        return {

            "statusCode": 200,

            "headers": {
                "Content-Type": "application/json"
            },

            "body": json.dumps({

                "file_id": file_id,

                "upload_url":
                    presigned["url"],

                "upload_fields":
                    presigned["fields"],

                "expires_in":
                    EXPIRATION

            })
        }


    except Exception as e:

        print(
            "[ERROR] Errore durante la generazione "
            f"del presigned POST: {str(e)}"
        )


        return {

            "statusCode": 500,

            "headers": {
                "Content-Type": "application/json"
            },

            "body": json.dumps({
                "error": "Errore interno del server"
            })
        }


# =========================================================
# S3 TRIGGER
# =========================================================

def s3_trigger(event, context):

    try:
        print("[DEBUG] EVENTO COMPLETO:")
        print(json.dumps(event, indent=2))

        print("[!] Evento S3 ricevuto")


        # -------------------------------------------------
        # Controllo evento
        # -------------------------------------------------

        if "Records" not in event:

            raise Exception(
                "Evento senza Records"
            )


        # -------------------------------------------------
        # Processa ogni record
        # -------------------------------------------------

        for record in event["Records"]:


            bucket = record["s3"]["bucket"]["name"]


            key = unquote_plus(
                record["s3"]["object"]["key"]
            )


            timestamp = record["eventTime"]

            event_name = record["eventName"]


            print(
                f"[*] Evento: {event_name}"
            )

            print(
                f"[*] Bucket: {bucket}"
            )

            print(
                f"[*] File ricevuto: {key}"
            )


            # -------------------------------------------------
            # Recupera metadata S3
            # -------------------------------------------------

            metadata = s3.head_object(

                Bucket=bucket,

                Key=key
            )


            file_size = metadata[
                "ContentLength"
            ]


            declared_mime_type = metadata.get(
                "ContentType",
                "unknown"
            )


            # =================================================
            # 1. CONTROLLO DIMENSIONE
            # =================================================

            if file_size > MAX_FILE_SIZE:

                print(
                    "[!] File rifiutato: "
                    f"dimensione {file_size} bytes"
                )


                table.put_item(
                    Item={

                        "file_id": key,

                        "bucket": bucket,

                        "size": file_size,

                        "mime_type":
                            declared_mime_type,

                        "timestamp":
                            timestamp,

                        "status":
                            "REJECTED"
                    }
                )

                continue


            # =================================================
            # 2. CONTROLLO MIME
            # =================================================

            if declared_mime_type not in ALLOWED_CONTENT_TYPES:

                print(
                    "[!] File rifiutato: "
                    "MIME type non consentito"
                )


                table.put_item(
                    Item={

                        "file_id": key,

                        "bucket": bucket,

                        "size": file_size,

                        "mime_type":
                            declared_mime_type,

                        "timestamp":
                            timestamp,

                        "status":
                            "REJECTED"
                    }
                )

                continue


            # =================================================
            # 3. CONTROLLO MAGIC BYTES
            # =================================================

            response = s3.get_object(

                Bucket=bucket,

                Key=key,

                Range="bytes=0-15"
            )


            file_header = response[
                "Body"
            ].read()


            detected_mime_type = detect_file_type(
                file_header
            )


            print(
                "[*] MIME dichiarato: "
                f"{declared_mime_type}"
            )


            print(
                "[*] MIME rilevato: "
                f"{detected_mime_type}"
            )


            if detected_mime_type != declared_mime_type:

                print(
                    "[!] File rifiutato: "
                    "MIME dichiarato diverso "
                    "dal contenuto rilevato"
                )


                table.put_item(
                    Item={

                        "file_id": key,

                        "bucket": bucket,

                        "size": file_size,

                        "mime_type":
                            declared_mime_type,

                        "detected_mime_type":
                            detected_mime_type,

                        "timestamp":
                            timestamp,

                        "status":
                            "REJECTED"
                    }
                )

                continue


            # =================================================
            # 4. ANTIVIRUS
            # =================================================

            antivirus_result = antivirus_scan(
                bucket,
                key
            )


            if not antivirus_result:

                print(
                    "[!] Antivirus: "
                    "file potenzialmente malevolo"
                )


                table.put_item(
                    Item={

                        "file_id": key,

                        "bucket": bucket,

                        "size": file_size,

                        "mime_type":
                            declared_mime_type,

                        "detected_mime_type":
                            detected_mime_type,

                        "timestamp":
                            timestamp,

                        "status":
                            "REJECTED"
                    }
                )

                continue


            # =================================================
            # 5. FILE VALIDATO
            # =================================================

            print("[+] File validato")

            print("[+] Mock AV: CLEAN")


            # -------------------------------------------------
            # Copia nel bucket principale
            # -------------------------------------------------

            s3.copy_object(

                CopySource={
                    "Bucket": bucket,
                    "Key": key
                },

                Bucket=BUCKET_NAME,

                Key=key
            )


            # =================================================
            # 6. DYNAMODB
            # =================================================

            table.put_item(
                Item={

                    "file_id": key,

                    "bucket": BUCKET_NAME,

                    "quarantine_bucket": bucket,

                    "size": file_size,

                    "mime_type":
                        declared_mime_type,

                    "detected_mime_type":
                        detected_mime_type,

                    "timestamp":
                        timestamp,

                    "status":
                        "PROCESSED"
                }
            )


            print(
                "[+] File trasferito nel bucket "
                f"{BUCKET_NAME}"
            )


        # -------------------------------------------------
        # Fine processing
        # -------------------------------------------------

        return {

            "statusCode": 200,

            "body": json.dumps({
                "message":
                    "Processing completato"
            })
        }


    except Exception as e:

        print(
            "[ERROR] Errore durante "
            f"processing S3: {str(e)}"
        )

        raise