#!/usr/bin/env python3
"""Controlli aggiuntivi dello stack: AWS read-only e unit test con servizi simulati.
Non rilancia test_aws_stack.py, non crea utenti/oggetti, non modifica AWS.
Exit 0: nessun problema aperto; 1: FAIL; 2: WARN/NON_VERIFICATO/LIMITE.
"""
import argparse
import ast
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import types
from unittest.mock import Mock, patch
import uuid

ACCOUNT = "793452511140"
REGION = "eu-south-1"
BUCKET = "documenti-" + ACCOUNT
KEYS = ["e438dc8b-5101-456b-abec-02795b0d1dbd", "4cf79458-8a9e-4d7b-9c94-b0faf86e6859"]


class FakeClientError(Exception):
    def __init__(self, response, operation):
        self.response = response
        super().__init__(operation + ": " + response["Error"]["Code"])


def load_lambda(path):
    boto = types.ModuleType("boto3")
    boto.client = Mock(return_value=Mock())
    boto.resource = Mock(return_value=Mock())
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = FakeClientError
    spec = importlib.util.spec_from_file_location("tested_lambda", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"boto3": boto, "botocore": types.ModuleType("botocore"),
                                 "botocore.exceptions": exceptions}):
        spec.loader.exec_module(module)
    module.KMS_KEY_ID = "test-key"
    module.BUCKET_NAME = "test-main"
    module.QUARANTINE_BUCKET_NAME = "test-quarantine"
    return module


def local_tests(source, check):
    m = load_lambda(source)
    def fresh():
        m.s3 = Mock()
        m.table = Mock()
        m.antivirus_scan = Mock(return_value=True)
        m.KMS_KEY_ID = "test-key"
        return {"Records": [{"eventTime": "2026-11-11T00:00:00Z",
                            "s3": {"bucket": {"name": "test-quarantine"},
                                   "object": {"key": "test%20key", "versionId": "v1"}}}]}
    def presign_contract(mime):
        fresh()
        m.s3.generate_presigned_post.return_value = {"url": "https://example.invalid", "fields": {}}
        result = m.upload_presign({"body": json.dumps({"content_type": mime})}, None)
        assert result["statusCode"] == 200
        kw = m.s3.generate_presigned_post.call_args.kwargs
        assert kw["ExpiresIn"] == 300
        assert ["content-length-range", 1, 20 * 1024 * 1024] in kw["Conditions"]
        assert ["eq", "$Content-Type", mime] in kw["Conditions"]
        assert ["eq", "$key", kw["Key"]] in kw["Conditions"]
        assert kw["Fields"]["x-amz-server-side-encryption"] == "aws:kms"
        assert kw["Fields"]["x-amz-server-side-encryption-aws-kms-key-id"] == "test-key"
    for mime in sorted(m.ALLOWED_CONTENT_TYPES):
        check("LOCAL", "Contratto firma e scadenza: " + mime, lambda mime=mime: presign_contract(mime))
    def missing_key():
        fresh()
        m.KMS_KEY_ID = None
        assert m.upload_presign({"body": '{"content_type":"image/png"}'}, None)["statusCode"] == 500
        m.s3.generate_presigned_post.assert_not_called()
    check("LOCAL", "KMS assente: nessun presigned generato", missing_key)
    def wrong_json(value):
        fresh()
        code = m.upload_presign({"body": json.dumps(value)}, None)["statusCode"]
        assert code == 400, f"Handler diretto: atteso 400, ricevuto {code}; non prova un bypass del validatore API"
    for value in ([], None, 123, "test"):
        check("LOCAL", "JSON non oggetto: " + repr(value), lambda value=value: wrong_json(value))
    def no_version():
        event = fresh()
        del event["Records"][0]["s3"]["object"]["versionId"]
        try:
            m.s3_trigger(event, None)
        except ValueError:
            m.s3.head_object.assert_not_called()
            return
        raise AssertionError("Evento senza versione accettato")
    check("LOCAL", "Evento privo di versionId", no_version)
    for code in ("404", "403"):
        def head(code=code):
            fresh()
            m.s3.head_object.side_effect = FakeClientError({"Error": {"Code": code}}, "HeadObject")
            if code == "404":
                assert m.object_exists("bucket", "key") is False
            else:
                try:
                    m.object_exists("bucket", "key")
                except FakeClientError:
                    return
                raise AssertionError("AccessDenied ignorato")
        check("LOCAL", "HeadObject distingue errore " + code, head)
    def prepared():
        event = fresh()
        meta = {"ContentLength": 100, "ContentType": "image/png"}
        m.s3.get_object.side_effect = lambda **kw: {"Body": io.BytesIO(b"\x89PNG\r\n\x1a\n")}
        return event, meta
    def av_reject():
        event, meta = prepared()
        m.s3.head_object.return_value = meta
        m.antivirus_scan.return_value = False
        m.s3_trigger(event, None)
        assert m.table.put_item.call_args.kwargs["Item"]["status"] == "REJECTED"
        m.s3.copy_object.assert_not_called()
    check("LOCAL", "Rifiuto AV: ramo simulato, non antivirus reale", av_reject)
    def retry_after_ddb():
        event, meta = prepared()
        exists = False
        def head(**kw):
            if "VersionId" in kw:
                assert kw["Key"] == "test key"
                return meta
            if exists:
                return meta
            raise FakeClientError({"Error": {"Code": "404"}}, "HeadObject")
        def copy(**kw):
            nonlocal exists
            assert kw["CopySource"]["VersionId"] == "v1"
            exists = True
        m.s3.head_object.side_effect = head
        m.s3.copy_object.side_effect = copy
        m.table.put_item.side_effect = [RuntimeError("DynamoDB temporaneamente indisponibile"), {}]
        try:
            m.s3_trigger(event, None)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Errore DynamoDB nascosto")
        m.s3_trigger(event, None)
        assert m.s3.copy_object.call_count == 1
        assert m.table.put_item.call_count == 2
    check("LOCAL", "Retry dopo copia riuscita e PutItem fallito", retry_after_ddb)
    def copy_failure():
        event, meta = prepared()
        m.s3.head_object.side_effect = lambda **kw: meta if "VersionId" in kw else (_ for _ in ()).throw(
            FakeClientError({"Error": {"Code": "404"}}, "HeadObject"))
        m.s3.copy_object.side_effect = RuntimeError("copy failed")
        try:
            m.s3_trigger(event, None)
        except RuntimeError:
            m.table.put_item.assert_not_called()
            return
        raise AssertionError("Copia fallita nascosta")
    check("LOCAL", "Copia fallita non produce PROCESSED", copy_failure)
    def concurrent():
        event, meta = prepared()
        gate = threading.Barrier(2, timeout=5)
        def head(**kw):
            if "VersionId" in kw:
                return meta
            gate.wait()
            raise FakeClientError({"Error": {"Code": "404"}}, "HeadObject")
        m.s3.head_object.side_effect = head
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(m.s3_trigger, event, None) for _ in range(2)]
            for future in futures:
                future.result(timeout=10)
        assert m.s3.copy_object.call_count == 1, (
            f"Due eventi simultanei hanno prodotto {m.s3.copy_object.call_count} copie: check-then-copy non atomico")
    check("LOCAL", "Idempotenza concorrente, assenza iniziale sincronizzata", concurrent)
    def docx():
        assert m.detect_file_type(b"PKnot-a-docx") == "unknown", "Un qualsiasi prefisso PK è classificato DOCX"
    check("LOCAL", "Rifiuto ZIP generico come DOCX", docx, failure="LIMITE")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", type=Path, default=Path.cwd())
    p.add_argument("--baseline", type=Path, required=True, help="Report JSON della suite già eseguita")
    p.add_argument("--waf-report", type=Path, help="Report collaudo_waf_s3.py già eseguito")
    p.add_argument("--profile", default="terraform-online")
    p.add_argument("--offline", action="store_true")
    args = p.parse_args()
    args.project = args.project.resolve()
    baseline = json.loads(args.baseline.read_text())
    if (str(baseline.get("account")), baseline.get("region"), baseline.get("api_id")) != (ACCOUNT, REGION, "or967p4be5"):
        p.error("Baseline di account/regione/API diversi")
    source = args.project / "modules/lambda/lambda/lambda_function.py"
    if not source.is_file():
        p.error("Sorgente Lambda non trovato nel progetto")
    runid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    out = args.project / ("collaudo-finale-" + runid)
    out.mkdir(mode=0o700)
    rows = []
    manifest = {str(f.relative_to(args.project)): hashlib.sha256(f.read_bytes()).hexdigest()
                for f in [args.project / "main.tf", *args.project.glob("modules/**/*.tf"),
                          *args.project.glob("modules/**/*.py")] if f.is_file()}
    def add(kind, name, status, detail=""):
        rows.append(dict(kind=kind, name=name, status=status, detail=detail))
        print(f"[{status}] {kind}: {name}" + (f" — {detail}" if detail else ""), flush=True)
    def check(kind, name, fn, failure="FAIL"):
        try:
            with redirect_stdout(io.StringIO()):
                result = fn()
            add(kind, name, "PASS", result if isinstance(result, str) else "")
        except AssertionError as e:
            add(kind, name, failure, str(e) or "Asserzione non soddisfatta")
        except Exception as e:
            add(kind, name, "NON_VERIFICATO", str(e)[:500])
    def command(cmd, timeout=60):
        r = subprocess.run(cmd, cwd=args.project, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "AWS_PAGER": "", "AWS_PROFILE": args.profile,
                                "AWS_REGION": REGION, "AWS_DEFAULT_REGION": REGION})
        if r.returncode:
            raise RuntimeError(r.stderr[:400] or "Comando fallito")
        return json.loads(r.stdout or "{}")
    def aws(*cmd):
        return command(["aws", *cmd, "--profile", args.profile, "--region", REGION,
                        "--output", "json", "--no-cli-pager"])
    try:
        for item in baseline.get("results", []):
            add("BASELINE_NON_RIESEGUITA", item["name"], item["status"], item.get("detail", ""))
        # Vecchi report non registrano hash del codice: non attestano automaticamente revisioni future.
        add("COPERTURA", "Baseline", "INFO", "Evidenza storica importata; hash sorgenti originali non presenti nel vecchio report")
        if args.waf_report:
            wr = json.loads(args.waf_report.read_text())
            for name, item in wr.get("checks", {}).items():
                add("WAF_NON_RIESEGUITO", name, item["status"], json.dumps(item, ensure_ascii=False))
        else:
            add("COPERTURA", "Report WAF/S3", "NON_VERIFICATO", "Non fornito; nessun burst ripetuto automaticamente")
        local_tests(source, check)
        tree = ast.parse(source.read_text())
        av = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "antivirus_scan"), None)
        mock_av = av and any(isinstance(n, ast.Return) and isinstance(n.value, ast.Constant)
                             and n.value.value is True for n in ast.walk(av))
        add("CODICE", "Antivirus reale", "LIMITE" if mock_av else "NON_VERIFICATO",
            "Mock presente" if mock_av else "Necessaria verifica motore e firme")
        if not args.offline:
            identity = aws("sts", "get-caller-identity")
            if identity.get("Arn") != f"arn:aws:iam::{ACCOUNT}:user/terraform-user":
                raise RuntimeError("Identità inattesa: stop verifiche AWS")
            # Ruoli: simulazione identity policies, NON autorizzazione effettiva end-to-end.
            obj = f"arn:aws:s3:::{BUCKET}/collaudo-permissioni-non-creato"
            quarantine = f"arn:aws:s3:::{BUCKET}-quarantine/collaudo-permissioni-non-creato"
            table = f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/FileMetaData"
            cases = [
                ("upload_presign_role", "s3:PutObject", quarantine, True),
                ("upload_presign_role", "s3:PutObject", obj, False),
                ("upload_presign_role", "s3:GetObject", obj, False),
                ("upload_presign_role", "dynamodb:PutItem", table, False),
                ("s3_trigger_role", "s3:GetObjectVersion", quarantine, True),
                ("s3_trigger_role", "s3:PutObject", obj, True),
                ("s3_trigger_role", "s3:ListBucket", f"arn:aws:s3:::{BUCKET}", True),
                ("s3_trigger_role", "dynamodb:PutItem", table, True),
                ("s3_trigger_role", "s3:DeleteObject", obj, False),
                ("s3_trigger_role", "dynamodb:DeleteTable", table, False),
            ]
            for role, action, resource, allowed in cases:
                def sim(role=role, action=action, resource=resource, allowed=allowed):
                    v = aws("iam", "simulate-principal-policy", "--policy-source-arn",
                            f"arn:aws:iam::{ACCOUNT}:role/{role}", "--action-names", action,
                            "--resource-arns", resource)["EvaluationResults"][0]
                    if v.get("MissingContextValues"):
                        raise RuntimeError("Contesto IAM mancante: " + str(v["MissingContextValues"]))
                    assert (v["EvalDecision"] == "allowed") == allowed, str(v["EvalDecision"])
                    return "Simulazione: " + v["EvalDecision"] + "; escluse resource policy dei ruoli"
                check("IAM_SIMULATO", role + " " + action + " " + resource, sim)
            for key in KEYS:
                def rotation(key=key):
                    v = aws("kms", "get-key-rotation-status", "--key-id", key)
                    assert v.get("KeyRotationEnabled"), "Rotazione disabilitata"
                check("AWS_READ_ONLY", "Rotazione KMS " + key, rotation)
            for name in ("s3_trigger", "upload_presign"):
                def artifact(name=name):
                    zip_path = args.project / "modules/lambda/lambda.zip"
                    if not zip_path.is_file():
                        raise RuntimeError("lambda.zip locale assente; non viene rigenerato")
                    import base64
                    actual = aws("lambda", "get-function-configuration", "--function-name", name)
                    local_hash = base64.b64encode(hashlib.sha256(zip_path.read_bytes()).digest()).decode()
                    assert local_hash == actual["CodeSha256"], "Pacchetto locale diverso dal deploy"
                    import zipfile
                    with zipfile.ZipFile(zip_path) as z:
                        assert z.read("lambda_function.py") == source.read_bytes(), "Sorgente diverso da quello nel pacchetto"
                check("AWS_READ_ONLY", "Codice testato = codice deployato " + name, artifact)
                def logs(name=name):
                    groups = aws("logs", "describe-log-groups", "--log-group-name-prefix", "/aws/lambda/"+name)
                    match = next(g for g in groups["logGroups"] if g["logGroupName"] == "/aws/lambda/"+name)
                    return "Gruppo presente, retention giorni=" + str(match.get("retentionInDays", "illimitata"))
                check("AWS_READ_ONLY", "Gruppo log " + name, logs)
            def auth():
                resources = aws("apigateway", "get-resources", "--rest-api-id", "or967p4be5")["items"]
                count = 0
                for r in resources:
                    for method in r.get("resourceMethods", {}):
                        if method == "OPTIONS":
                            continue
                        m = aws("apigateway", "get-method", "--rest-api-id", "or967p4be5",
                                "--resource-id", r["id"], "--http-method", method)
                        assert m.get("authorizationType") == "COGNITO_USER_POOLS", r["path"]+" "+method
                        count += 1
                assert count >= 2
                return f"{count} metodi configurati con Cognito; controllo config, non test token"
            check("AWS_READ_ONLY", "Autenticazione di tutti i metodi", auth)
            def throttling():
                s = aws("apigateway", "get-stage", "--rest-api-id", "or967p4be5", "--stage-name", "prod")
                settings = s.get("methodSettings", {}).get("*/*", {})
                assert settings.get("throttlingRateLimit") == 10 and settings.get("throttlingBurstLimit") == 20, str(settings)
                return "10 req/s, burst 20; non prova del 429 sotto carico"
            check("AWS_READ_ONLY", "Configurazione throttling API", throttling)
        else:
            add("COPERTURA", "AWS read-only", "NON_VERIFICATO", "--offline")
        # Copia solo sorgenti necessari agli scanner, mai state/credenziali/piani.
        with tempfile.TemporaryDirectory(prefix="collaudo-static-") as td:
            stage = Path(td)
            for rel in manifest:
                f = args.project / rel
                target = stage / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
            for executable, opts in (
                ("checkov", ["-d", str(stage), "--framework", "terraform", "--output", "json"]),
                ("bandit", ["-r", str(stage / "modules/lambda"), "-f", "json"]),
            ):
                if not shutil.which(executable):
                    add("STATICO", executable, "NON_VERIFICATO", "Comando non installato; nessuna installazione automatica")
                    continue
                def scan(executable=executable, opts=opts):
                    r = subprocess.run([executable, *opts], capture_output=True, text=True, timeout=240)
                    (out / (executable + ".json")).write_text(r.stdout)
                    (out / (executable + ".stderr.txt")).write_text(r.stderr)
                    data = json.loads(r.stdout)
                    if r.returncode not in (0, 1):
                        raise RuntimeError("Errore scanner, exit=" + str(r.returncode))
                    if executable == "bandit":
                        findings = len(data.get("results", []))
                        errors = len(data.get("errors", []))
                    else:
                        records = data if isinstance(data, list) else [data]
                        findings = sum(x.get("summary", {}).get("failed", 0) for x in records)
                        errors = sum(x.get("summary", {}).get("parsing_errors", 0) for x in records)
                    if errors:
                        raise RuntimeError(f"Scanner: {errors} errori di parsing")
                    assert findings == 0 and r.returncode == 0, f"{findings} rilievi da classificare; output separato"
                check("STATICO", executable, scan, failure="WARN")
        for name in (
            "Throttling API: prova autenticata concorrente con attribuzione del 429",
            "Token Cognito realmente scaduto, non JWT modificato",
            "Presigned POST scaduto: rifiuto effettivo S3 dopo attesa",
            "Confini reali upload: zero byte, 20 MiB esatti, tutti i formati",
            "Bucket policy/KMS: richieste firmate valide ma non conformi",
            "Ripristino PITR su tabella temporanea e verifica contenuti",
            "Concorrenza e fault injection su AWS isolato",
            "AWSManagedRulesKnownBadInputs: prova attribuita a regola specifica",
        ):
            add("COPERTURA_RESIDUA", name, "NON_VERIFICATO",
                "Non eseguito da questo script read-only; non conteggiato come PASS")
    except KeyboardInterrupt:
        add("ESECUZIONE", "Interruzione", "NON_VERIFICATO")
    except Exception as e:
        add("ESECUZIONE", "Errore", "NON_VERIFICATO", str(e)[:500])
    finally:
        report = {"created_at": datetime.now(timezone.utc).isoformat(),
                  "account": ACCOUNT, "region": REGION, "api_id": "or967p4be5",
                  "baseline": str(args.baseline), "baseline_sha256": hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
                  "source_hashes": manifest, "results": rows,
                  "summary": dict(Counter(x["status"] for x in rows))}
        (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n")
        (out / "report.txt").write_text("\n".join(f"[{r['status']}] {r['kind']} — {r['name']}: {r['detail']}" for r in rows)+"\n")
        print("Report:", out)
    statuses = {r["status"] for r in rows}
    return 1 if "FAIL" in statuses else (2 if statuses & {"WARN", "NON_VERIFICATO", "LIMITE", "SKIP"} else 0)


if __name__ == "__main__":
    raise SystemExit(main())
