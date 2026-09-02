import argparse
import requests
import sys
import time


API_URL = "http://127.0.0.1:4566/restapis/a493f988/prod/_user_request_/upload"

MAX_FILE_SIZE = 20 * 1024 * 1024


def create_pdf(filename):
    """Crea un PDF minimale valido per il test dei magic bytes."""
    with open(filename, "wb") as f:
        f.write(
            b"%PDF-1.4\n"
            b"1 0 obj\n"
            b"<<>>\n"
            b"endobj\n"
            b"trailer\n"
            b"<<>>\n"
            b"%%EOF\n"
        )


def create_fake_pdf(filename):
    """Crea un file NON PDF con estensione .pdf."""
    with open(filename, "wb") as f:
        f.write(b"QUESTO NON E UN PDF")


def create_oversized_file(filename):
    """Crea un file leggermente superiore al limite di 20 MB."""
    size = MAX_FILE_SIZE + 1

    with open(filename, "wb") as f:
        f.write(b"A" * size)


def request_presigned_post(content_type):
    print("[1] Richiedo il presigned POST...")

    response = requests.post(
        API_URL,
        headers={"Content-Type": "application/json"},
        json={"content_type": content_type},
    )

    print(f"    API status: {response.status_code}")

    if response.status_code != 200:
        print(f"    Risposta: {response.text}")
        return None

    data = response.json()

    print(f"    File ID: {data['file_id']}")
    print(f"    Upload URL: {data['upload_url']}")

    return data


def upload_file(data, filename, content_type):
    print(f"\n[2] Carico {filename} nella quarantine...")

    with open(filename, "rb") as f:
        response = requests.post(
            data["upload_url"],
            data=data["upload_fields"],
            files={
                "file": (
                    filename,
                    f,
                    content_type,
                )
            },
        )

    print(f"    S3 status: {response.status_code}")

    if response.status_code in (200, 201, 204):
        print("    [+] Upload riuscito!")
        return True

    print("    [!] Upload rifiutato:")
    print(response.text)

    return False


def test_valid():
    print("\n" + "=" * 60)
    print("TEST: VALID PDF")
    print("=" * 60)

    filename = "test_valid.pdf"
    create_pdf(filename)

    data = request_presigned_post("application/pdf")

    if data is None:
        return

    upload_file(data, filename, "application/pdf")

    print("\n[3] Attendo la Lambda...")
    time.sleep(3)

    print("\n[+] Il file dovrebbe essere stato:")
    print("    documenti-quarantine/pending/<UUID>")
    print("                ↓")
    print("             s3_trigger")
    print("                ↓")
    print("              CLEAN")
    print("                ↓")
    print("          documenti/<UUID>")


def test_invalid_mime():
    print("\n" + "=" * 60)
    print("TEST: INVALID MIME")
    print("=" * 60)

    data = request_presigned_post("text/plain")

    if data is None:
        print("\n[+] TEST SUPERATO: MIME rifiutato dall'API.")
    else:
        print("\n[!] ATTENZIONE: l'API ha accettato un MIME non consentito.")


def test_fake_pdf():
    print("\n" + "=" * 60)
    print("TEST: FAKE PDF / MAGIC BYTES")
    print("=" * 60)

    filename = "fake.pdf"
    create_fake_pdf(filename)

    data = request_presigned_post("application/pdf")

    if data is None:
        return

    uploaded = upload_file(
        data,
        filename,
        "application/pdf",
    )

    if uploaded:
        print("\n[3] Attendo la Lambda...")
        time.sleep(3)

        print("\n[+] Risultato atteso:")
        print("    MIME dichiarato: application/pdf")
        print("    MIME rilevato:   unknown")
        print("    status:          REJECTED")
        print("    NON deve essere copiato in documenti.")


def test_oversized():
    print("\n" + "=" * 60)
    print("TEST: OVERSIZED FILE (> 20 MB)")
    print("=" * 60)

    filename = "oversized.pdf"

    print("[1] Creo un file da oltre 20 MB...")
    create_oversized_file(filename)

    data = request_presigned_post("application/pdf")

    if data is None:
        return

    uploaded = upload_file(
        data,
        filename,
        "application/pdf",
    )

    if not uploaded:
        print("\n[+] TEST SUPERATO: S3 ha rifiutato il file troppo grande.")
    else:
        print(
            "\n[!] ATTENZIONE: il file è stato accettato "
            "nonostante superi il limite."
        )


def main():
    parser = argparse.ArgumentParser(
        description="Test della pipeline di upload sicuro S3/Lambda"
    )

    parser.add_argument(
        "--test",
        choices=[
            "valid",
            "invalid-mime",
            "fake-pdf",
            "oversized",
            "all",
        ],
        required=True,
        help="Test da eseguire",
    )

    args = parser.parse_args()

    if args.test == "valid":
        test_valid()

    elif args.test == "invalid-mime":
        test_invalid_mime()

    elif args.test == "fake-pdf":
        test_fake_pdf()

    elif args.test == "oversized":
        test_oversized()

    elif args.test == "all":
        test_valid()
        test_invalid_mime()
        test_fake_pdf()
        test_oversized()


if __name__ == "__main__":
    main()