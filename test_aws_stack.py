#!/usr/bin/env python3
"""Test end-to-end non distruttivi per il progetto Terraform AWS.

Requisiti: Python 3.10+, AWS CLI v2, Terraform e credenziali AWS valide.
Lo script crea un utente Cognito e alcuni oggetti temporanei, poi li elimina.
Non esegue terraform apply/destroy e non modifica il codice Terraform.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import shutil
import string
import subprocess
import sys
import tempfile
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class Suite:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.results: list[dict] = []
        self.started = datetime.now(timezone.utc)
        self.test_email: str | None = None
        self.pool_id: str | None = None
        self.client_id: str | None = None
        self.source_keys: set[str] = set()
        self.destination_keys: set[str] = set()
        self.ddb_ids: set[str] = set()
        self.api_id = args.api_id
        self.endpoint = ""
        self.token = ""

    def record(self, name: str, status: str, detail: str = "") -> None:
        icon = {"PASS": "✓", "FAIL": "✗", "WARN": "!", "SKIP": "-"}[status]
        print(f"[{icon}] {name}: {detail}")
        self.results.append({"name": name, "status": status, "detail": detail})

    def command(self, cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["AWS_PROFILE"] = self.args.profile
        env["AWS_REGION"] = self.args.region
        env["AWS_DEFAULT_REGION"] = self.args.region
        result = subprocess.run(
            cmd,
            cwd=self.args.project,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if check and result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result

    def aws(self, *parts: str, check: bool = True) -> subprocess.CompletedProcess:
        return self.command(
            ["aws", *parts, "--profile", self.args.profile, "--region", self.args.region],
            check=check,
        )

    def aws_json(self, *parts: str) -> dict | list:
        result = self.aws(*parts, "--output", "json")
        return json.loads(result.stdout or "{}")

    @staticmethod
    def http(method: str, url: str, body: bytes | None = None,
             headers: dict[str, str] | None = None, timeout: int = 30) -> tuple[int, bytes, dict]:
        request = Request(url, data=body, headers=headers or {}, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.status, response.read(), dict(response.headers)
        except HTTPError as error:
            return error.code, error.read(), dict(error.headers)
        except URLError as error:
            raise RuntimeError(str(error)) from error

    @staticmethod
    def multipart(fields: dict[str, str], file_name: str,
                  content_type: str, content: bytes) -> tuple[bytes, str]:
        boundary = "----codex-" + secrets.token_hex(16)
        chunks: list[bytes] = []
        for key, value in fields.items():
            chunks.extend([
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                str(value).encode(), b"\r\n",
            ])
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            content, b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ])
        return b"".join(chunks), f"multipart/form-data; boundary={boundary}"

    def api_json(self, method: str, path: str, payload: dict | bytes | None,
                 token: str | None = None) -> tuple[int, dict | str]:
        if isinstance(payload, dict):
            body = json.dumps(payload).encode()
        else:
            body = payload
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = token
        status, raw, _ = self.http(method, self.endpoint + path, body, headers)
        try:
            return status, json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return status, raw.decode(errors="replace")

    def preflight(self) -> None:
        for executable in ("aws", "terraform", "curl"):
            if not shutil.which(executable):
                raise RuntimeError(f"Comando mancante: {executable}")
        identity = self.aws_json("sts", "get-caller-identity")
        account = str(identity.get("Account"))
        if account != self.args.account:
            raise RuntimeError(f"Account AWS {account}, atteso {self.args.account}")
        self.record("Identità AWS", "PASS", f"account {account}")

        plan = self.command(["terraform", "plan", "-detailed-exitcode", "-no-color"], check=False)
        if plan.returncode == 0:
            self.record("Convergenza Terraform", "PASS", "nessuna modifica")
        elif plan.returncode == 2:
            self.record("Convergenza Terraform", "FAIL", "il piano contiene modifiche")
        else:
            self.record("Convergenza Terraform", "FAIL", plan.stderr[-500:])

        if not self.api_id:
            output = self.command(["terraform", "output", "-raw", "api_id"])
            self.api_id = output.stdout.strip()
        self.endpoint = f"https://{self.api_id}.execute-api.{self.args.region}.amazonaws.com/prod"

    def configuration(self) -> None:
        expected = {"s3_trigger": 60, "upload_presign": 15}
        for name, timeout in expected.items():
            cfg = self.aws_json("lambda", "get-function-configuration", "--function-name", name)
            ok = all([
                cfg.get("State") == "Active",
                cfg.get("LastUpdateStatus") == "Successful",
                cfg.get("Timeout") == timeout,
                cfg.get("MemorySize") == 256,
                cfg.get("TracingConfig", {}).get("Mode") == "Active",
            ])
            self.record(f"Configurazione Lambda {name}", "PASS" if ok else "FAIL",
                        f"state={cfg.get('State')}, timeout={cfg.get('Timeout')}, memory={cfg.get('MemorySize')}")

        notification = self.aws_json(
            "s3api", "get-bucket-notification-configuration", "--bucket", self.args.quarantine_bucket
        )
        configs = notification.get("LambdaFunctionConfigurations", [])
        ok = any(x.get("LambdaFunctionArn", "").endswith(":function:s3_trigger") for x in configs)
        self.record("Notifica S3→Lambda", "PASS" if ok else "FAIL", f"configurazioni={len(configs)}")

        for bucket, algorithm in (
            (self.args.main_bucket, "aws:kms"),
            (self.args.quarantine_bucket, "aws:kms"),
            (self.args.logs_bucket, "AES256"),
        ):
            versioning = self.aws_json("s3api", "get-bucket-versioning", "--bucket", bucket)
            encryption = self.aws_json("s3api", "get-bucket-encryption", "--bucket", bucket)
            rule = encryption["ServerSideEncryptionConfiguration"]["Rules"][0]
            actual = rule["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"]
            ok = versioning.get("Status") == "Enabled" and actual == algorithm
            self.record(f"S3 {bucket}", "PASS" if ok else "FAIL",
                        f"versioning={versioning.get('Status')}, encryption={actual}")

        table = self.aws_json("dynamodb", "describe-table", "--table-name", self.args.table)["Table"]
        ok = table.get("TableStatus") == "ACTIVE" and table.get("SSEDescription", {}).get("Status") == "ENABLED"
        self.record("DynamoDB", "PASS" if ok else "FAIL",
                    f"status={table.get('TableStatus')}, SSE={table.get('SSEDescription', {}).get('Status')}")

        pitr = self.aws_json("dynamodb", "describe-continuous-backups", "--table-name", self.args.table)
        pitr_status = pitr["ContinuousBackupsDescription"]["PointInTimeRecoveryDescription"]["PointInTimeRecoveryStatus"]
        self.record("DynamoDB PITR", "PASS" if pitr_status == "ENABLED" else "WARN", pitr_status)

    def create_test_user(self) -> None:
        authorizers = self.aws_json(
            "apigateway", "get-authorizers", "--rest-api-id", self.api_id,
            "--limit", "500",
        ).get("items", [])
        cognito_authorizers = [
            item for item in authorizers
            if item.get("type") == "COGNITO_USER_POOLS" and item.get("providerARNs")
        ]
        if len(cognito_authorizers) != 1:
            raise RuntimeError(
                f"Authorizer Cognito associato all'API {self.api_id}: "
                f"trovati {len(cognito_authorizers)}"
            )
        provider_arn = cognito_authorizers[0]["providerARNs"][0]
        self.pool_id = provider_arn.rsplit("/", 1)[-1]
        pool = self.aws_json(
            "cognito-idp", "describe-user-pool", "--user-pool-id", self.pool_id
        )["UserPool"]
        self.record(
            "User pool collegato all'API", "PASS",
            f"{pool.get('Name')} ({self.pool_id})",
        )

        clients = self.aws_json(
            "cognito-idp", "list-user-pool-clients", "--user-pool-id", self.pool_id,
            "--max-results", "60"
        ).get("UserPoolClients", [])
        matches = [c for c in clients if c.get("ClientName") == self.args.client_name]
        if len(matches) != 1:
            raise RuntimeError(f"App client {self.args.client_name}: trovati {len(matches)}")
        self.client_id = matches[0]["ClientId"]

        suffix = f"{int(time.time())}-{secrets.token_hex(3)}"
        self.test_email = f"terraform-test-{suffix}@example.com"
        alphabet = string.ascii_letters + string.digits
        password = "Tf!9" + "".join(secrets.choice(alphabet) for _ in range(20))
        self.aws(
            "cognito-idp", "admin-create-user", "--user-pool-id", self.pool_id,
            "--username", self.test_email, "--temporary-password", password,
            "--message-action", "SUPPRESS",
            "--user-attributes", f"Name=email,Value={self.test_email}", "Name=email_verified,Value=true",
        )
        self.aws(
            "cognito-idp", "admin-set-user-password", "--user-pool-id", self.pool_id,
            "--username", self.test_email, "--password", password, "--permanent",
        )
        auth = self.aws_json(
            "cognito-idp", "initiate-auth", "--auth-flow", "USER_PASSWORD_AUTH",
            "--client-id", self.client_id,
            "--auth-parameters", f"USERNAME={self.test_email},PASSWORD={password}",
        )
        self.token = auth["AuthenticationResult"]["IdToken"]
        self.record("Utente Cognito temporaneo", "PASS", self.test_email)

    def api_tests(self) -> None:
        status, _ = self.api_json("GET", "/test", None)
        self.record("API senza token", "PASS" if status == 401 else "FAIL", f"HTTP {status}")
        status, _ = self.api_json("GET", "/test", None, "token-non-valido")
        self.record("API con token invalido", "PASS" if status == 401 else "FAIL", f"HTTP {status}")
        status, response = self.api_json("GET", "/test", None, self.token)
        self.record("API autenticata /test", "PASS" if status == 200 else "FAIL",
                    f"HTTP {status}: {str(response)[:160]}")

        cases = [
            ("JSON malformato", b'{"content_type":', 400),
            ("MIME non consentito", {"content_type": "text/plain"}, 400),
            ("Proprietà aggiuntiva", {"content_type": "image/png", "extra": True}, 400),
            ("Campo obbligatorio assente", {}, 400),
        ]
        for name, payload, expected in cases:
            status, response = self.api_json("POST", "/upload", payload, self.token)
            self.record(name, "PASS" if status == expected else "FAIL",
                        f"HTTP {status}: {str(response)[:140]}")

        waf_payload = {"content_type": "' OR 1=1 --"}
        status, _ = self.api_json("POST", "/upload", waf_payload, self.token)
        self.record("WAF/validator input sospetto", "PASS" if status in (400, 403) else "WARN", f"HTTP {status}")

    def get_presigned(self, content_type: str) -> dict:
        status, response = self.api_json("POST", "/upload", {"content_type": content_type}, self.token)
        if status != 200 or not isinstance(response, dict):
            raise RuntimeError(f"Presigned POST fallito: HTTP {status}: {response}")
        self.source_keys.add(response["file_id"])
        return response

    def upload(self, presigned: dict, content: bytes, content_type: str,
               fields_override: dict[str, str] | None = None) -> int:
        fields = dict(presigned["upload_fields"])
        if fields_override:
            fields.update(fields_override)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(prefix="aws-stack-test-", delete=False) as temporary:
                temporary.write(content)
                temporary_path = temporary.name
            command = [
                "curl", "--silent", "--show-error", "--output", "/tmp/aws-stack-s3-response.txt",
                "--write-out", "%{http_code}", "--connect-timeout", "15", "--max-time", "120",
            ]
            for key, value in fields.items():
                command.extend(["--form-string", f"{key}={value}"])
            command.extend(["--form", f"file=@{temporary_path};type={content_type}", presigned["upload_url"]])
            result = self.command(command, check=False)
            if result.returncode != 0:
                raise RuntimeError(f"curl S3 fallito ({result.returncode}): {result.stderr.strip()}")
            return int(result.stdout.strip())
        finally:
            if temporary_path:
                Path(temporary_path).unlink(missing_ok=True)

    @staticmethod
    def decode_item(item: dict) -> dict:
        decoded = {}
        for key, value in item.items():
            decoded[key] = next(iter(value.values())) if value else None
        return decoded

    def ddb_items(self, source_key: str) -> list[dict]:
        values = json.dumps({":k": {"S": source_key}})
        result = self.aws_json(
            "dynamodb", "scan", "--table-name", self.args.table,
            "--filter-expression", "source_key = :k",
            "--expression-attribute-values", values,
        )
        return [self.decode_item(x) for x in result.get("Items", [])]

    def wait_items(self, source_key: str, count: int = 1, timeout: int = 120) -> list[dict]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            items = self.ddb_items(source_key)
            if len(items) >= count:
                for item in items:
                    self.ddb_ids.add(item["file_id"])
                    if item.get("destination_key"):
                        self.destination_keys.add(item["destination_key"])
                return items
            time.sleep(3)
        return self.ddb_items(source_key)

    def object_versions(self, bucket: str, key: str) -> list[dict]:
        result = self.aws_json("s3api", "list-object-versions", "--bucket", bucket, "--prefix", key)
        return [x for x in result.get("Versions", []) if x.get("Key") == key]

    def end_to_end(self) -> None:
        png_one = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2n9sAAAAASUVORK5CYII="
        )
        png_two = png_one + b"second-version"

        print("\n--- Test upload end-to-end ---")
        valid = self.get_presigned("image/png")
        key = valid["file_id"]
        print(f"[*] Upload valido verso quarantine: {key}")
        status = self.upload(valid, png_one, "image/png")
        self.record("Presigned POST valido", "PASS" if status in (200, 201, 204) else "FAIL", f"HTTP {status}")
        if status not in (200, 201, 204):
            response = Path("/tmp/aws-stack-s3-response.txt").read_text(errors="replace")
            raise RuntimeError(f"Upload S3 valido respinto: HTTP {status}: {response[:500]}")
        items = self.wait_items(key)
        processed = [x for x in items if x.get("status") == "PROCESSED"]
        self.record("Trigger e DynamoDB", "PASS" if processed else "FAIL", f"record={len(items)}")
        if processed:
            destination = processed[0].get("destination_key")
            head = self.aws_json("s3api", "head-object", "--bucket", self.args.main_bucket, "--key", destination)
            encrypted = head.get("ServerSideEncryption") == "aws:kms"
            self.record("Copia nel bucket principale", "PASS" if encrypted else "FAIL",
                        f"key={destination}, SSE={head.get('ServerSideEncryption')}")

        status = self.upload(valid, png_two, "image/png")
        if status not in (200, 201, 204):
            response = Path("/tmp/aws-stack-s3-response.txt").read_text(errors="replace")
            raise RuntimeError(f"Seconda versione S3 respinta: HTTP {status}: {response[:500]}")
        items = self.wait_items(key, count=2)
        ids = {x.get("file_id") for x in items}
        version_ok = status in (200, 201, 204) and len(ids) >= 2
        self.record("Due versioni della stessa chiave", "PASS" if version_ok else "FAIL",
                    f"HTTP {status}, record distinti={len(ids)}")

        if items:
            target = sorted(items, key=lambda x: x.get("source_version_id", ""))[-1]
            destination = target.get("destination_key")
            before = len(self.object_versions(self.args.main_bucket, destination))
            event = {
                "Records": [{
                    "eventTime": datetime.now(timezone.utc).isoformat(),
                    "eventName": "ObjectCreated:Put",
                    "s3": {
                        "bucket": {"name": self.args.quarantine_bucket},
                        "object": {"key": key, "versionId": target["source_version_id"]},
                    },
                }]
            }
            payload = json.dumps(event)
            for _ in range(2):
                result = self.aws(
                    "lambda", "invoke", "--function-name", "s3_trigger",
                    "--cli-binary-format", "raw-in-base64-out", "--payload", payload,
                    "/tmp/aws-stack-duplicate-response.json",
                )
                meta = json.loads(result.stdout or "{}")
                if meta.get("FunctionError"):
                    raise RuntimeError(f"Invocazione duplicata fallita: {meta}")
            after = len(self.object_versions(self.args.main_bucket, destination))
            status_name = "PASS" if after == before else "WARN"
            self.record("Idempotenza evento duplicato", status_name,
                        f"versioni destinazione prima={before}, dopo={after}")

        mismatch = self.get_presigned("image/png")
        mismatch_key = mismatch["file_id"]
        status = self.upload(mismatch, b"%PDF-1.7\nnot-a-png", "image/png")
        if status not in (200, 201, 204):
            response = Path("/tmp/aws-stack-s3-response.txt").read_text(errors="replace")
            raise RuntimeError(f"Upload MIME discordante respinto da S3: HTTP {status}: {response[:500]}")
        items = self.wait_items(mismatch_key)
        rejected = items and all(x.get("status") == "REJECTED" for x in items)
        self.record("Magic bytes discordanti", "PASS" if status in (200, 201, 204) and rejected else "FAIL",
                    f"upload HTTP {status}, stato={items[0].get('status') if items else 'assente'}")

        too_large = self.get_presigned("image/png")
        oversized = png_one[:8] + bytes(20 * 1024 * 1024 + 1)
        status = self.upload(too_large, oversized, "image/png")
        self.record("Limite 20 MiB", "PASS" if status >= 400 else "FAIL", f"HTTP {status}")

        wrong_kms = self.get_presigned("image/png")
        field_name = "x-amz-server-side-encryption-aws-kms-key-id"
        status = self.upload(wrong_kms, png_one, "image/png", {field_name: "invalid-kms-key"})
        self.record("Alterazione campo KMS firmato", "PASS" if status >= 400 else "FAIL", f"HTTP {status}")

    def public_access(self) -> None:
        for bucket in (self.args.main_bucket, self.args.quarantine_bucket, self.args.logs_bucket):
            status, _, _ = self.http("HEAD", f"https://{bucket}.s3.{self.args.region}.amazonaws.com/")
            self.record(f"Accesso anonimo {bucket}", "PASS" if status in (401, 403) else "FAIL", f"HTTP {status}")

    def observability(self) -> None:
        start_ms = str(int(self.started.timestamp() * 1000))
        time.sleep(5)
        for group in ("/aws/lambda/s3_trigger", "/aws/apigateway/API"):
            result = self.aws(
                "logs", "filter-log-events", "--log-group-name", group,
                "--start-time", start_ms, "--limit", "5", check=False,
            )
            if result.returncode == 0:
                events = json.loads(result.stdout or "{}").get("events", [])
                self.record(f"Log {group}", "PASS" if events else "WARN", f"eventi={len(events)}")
            else:
                self.record(f"Log {group}", "WARN", result.stderr.strip()[-180:])

        xray = self.aws_json(
            "xray", "get-trace-summaries",
            "--start-time", self.started.isoformat(),
            "--end-time", datetime.now(timezone.utc).isoformat(),
        )
        traces = xray.get("TraceSummaries", [])
        self.record("Tracce X-Ray", "PASS" if traces else "WARN", f"tracce={len(traces)}")
        self.record("S3 access log", "SKIP", "consegna asincrona: verificare il bucket logs dopo alcune ore")
        self.record("WAF full logging", "WARN", "disabilitato nel Terraform con count = 0")

    def source_and_static_checks(self) -> None:
        source = Path(self.args.project) / "modules/lambda/lambda/lambda_function.py"
        if source.exists():
            text = source.read_text(errors="replace")
            self.record("Antivirus reale", "WARN" if "return True" in text else "PASS",
                        "mock rilevato" if "return True" in text else "implementazione non-mock")
            self.record("Validazione DOCX", "WARN" if 'startswith(b"PK")' in text else "PASS",
                        "solo firma ZIP" if 'startswith(b"PK")' in text else "controllo strutturale")

        if shutil.which("checkov"):
            result = self.command(["checkov", "-d", str(self.args.project), "--quiet", "--compact"], check=False)
            status = "PASS" if result.returncode == 0 else "WARN"
            summary = "completato senza rilievi" if result.returncode == 0 else "sono presenti rilievi; consultare output Checkov"
            self.record("Checkov", status, summary)
            Path(self.args.project, "checkov-test-output.txt").write_text(result.stdout + result.stderr)
        else:
            self.record("Checkov", "SKIP", "comando non installato")

    def rate_limit(self) -> None:
        if not self.args.rate_limit:
            self.record("Rate limit WAF/API", "SKIP", "abilitare con --rate-limit")
            return
        statuses = Counter()
        for _ in range(115):
            status, _, _ = self.http("GET", self.endpoint + "/test", headers={"Authorization": self.token})
            statuses[status] += 1
        blocked = statuses[403] + statuses[429]
        self.record("Rate limit WAF/API", "PASS" if blocked else "WARN", dict(statuses).__str__())

    def delete_s3_key(self, bucket: str, key: str) -> None:
        data = self.aws_json("s3api", "list-object-versions", "--bucket", bucket, "--prefix", key)
        for collection in ("Versions", "DeleteMarkers"):
            for version in data.get(collection, []):
                if version.get("Key") == key:
                    self.aws(
                        "s3api", "delete-object", "--bucket", bucket, "--key", key,
                        "--version-id", version["VersionId"], check=False,
                    )

    def cleanup(self) -> None:
        if self.args.keep_test_data:
            self.record("Pulizia", "SKIP", "--keep-test-data specificato")
            return
        errors = []
        for key in self.source_keys:
            try:
                self.delete_s3_key(self.args.quarantine_bucket, key)
            except Exception as error:
                errors.append(str(error))
        for key in self.destination_keys:
            try:
                self.delete_s3_key(self.args.main_bucket, key)
            except Exception as error:
                errors.append(str(error))
        for file_id in self.ddb_ids:
            result = self.aws(
                "dynamodb", "delete-item", "--table-name", self.args.table,
                "--key", json.dumps({"file_id": {"S": file_id}}), check=False,
            )
            if result.returncode != 0:
                errors.append(result.stderr.strip())
        if self.pool_id and self.test_email:
            result = self.aws(
                "cognito-idp", "admin-delete-user", "--user-pool-id", self.pool_id,
                "--username", self.test_email, check=False,
            )
            if result.returncode != 0:
                errors.append(result.stderr.strip())
        self.record("Pulizia dati temporanei", "WARN" if errors else "PASS",
                    "; ".join(errors)[:300] if errors else "completata")

    def save_report(self) -> Path:
        report = {
            "started_at": self.started.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "account": self.args.account,
            "region": self.args.region,
            "api_id": self.api_id,
            "summary": dict(Counter(x["status"] for x in self.results)),
            "results": self.results,
        }
        path = Path(self.args.project) / f"aws-test-report-{int(time.time())}.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(f"\nReport: {path}")
        return path

    def run(self) -> int:
        try:
            self.preflight()
            self.configuration()
            self.create_test_user()
            self.api_tests()
            self.end_to_end()
            self.public_access()
            self.rate_limit()
            self.observability()
            self.source_and_static_checks()
        except KeyboardInterrupt:
            self.record("Esecuzione", "FAIL", "interrotta dall'utente")
        except Exception as error:
            self.record("Esecuzione", "FAIL", str(error))
        finally:
            try:
                self.cleanup()
            except Exception as error:
                self.record("Pulizia dati temporanei", "WARN", str(error))
            self.save_report()
        return 1 if any(x["status"] == "FAIL" for x in self.results) else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test end-to-end dello stack AWS Terraform")
    parser.add_argument("--project", default="/home/giulio/AWS")
    parser.add_argument("--profile", default="terraform-online")
    parser.add_argument("--region", default="eu-south-1")
    parser.add_argument("--account", default="793452511140")
    parser.add_argument("--api-id")
    parser.add_argument("--main-bucket", default="documenti-793452511140")
    parser.add_argument("--quarantine-bucket", default="documenti-793452511140-quarantine")
    parser.add_argument("--logs-bucket", default="documenti-793452511140-logs")
    parser.add_argument("--table", default="FileMetaData")
    parser.add_argument("--pool-name", default="serverless-sharepoint-dev-user-pool")
    parser.add_argument("--client-name", default="serverless-sharepoint-dev-app-client")
    parser.add_argument("--rate-limit", action="store_true", help="invia 115 richieste per verificare throttling/WAF")
    parser.add_argument("--keep-test-data", action="store_true", help="non elimina utente e oggetti temporanei")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(Suite(parse_args()).run())
