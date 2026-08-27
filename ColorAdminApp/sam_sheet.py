"""Leitura segura da planilha intermediária produzida pelo scraper SAM."""
import base64
import json
import time
from datetime import datetime
from pathlib import Path

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


SHEET_HEADERS = [
    "Nome", "Instrumento", "Localidade", "Cargo/Ministerio", "Nivel", "MSA Lancamento", "Fase MSA",
    "Data Metodo", "Licoes do Metodo", "Tipo Metodo", "Hino", "Data Hino", "Status Geral",
    "Data da Verificacao", "Observacoes",
]


def _b64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def service_account_token(credentials_path):
    credentials = json.loads(Path(credentials_path).read_text(encoding="utf-8-sig"))
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claim = _b64url(json.dumps({
        "iss": credentials["client_email"], "scope": "https://www.googleapis.com/auth/spreadsheets.readonly",
        "aud": credentials.get("token_uri", "https://oauth2.googleapis.com/token"), "iat": now, "exp": now + 3600,
    }, separators=(",", ":")).encode())
    unsigned = f"{header}.{claim}".encode("ascii")
    key = serialization.load_pem_private_key(credentials["private_key"].encode(), password=None)
    signature = key.sign(unsigned, padding.PKCS1v15(), hashes.SHA256())
    assertion = f"{header}.{claim}.{_b64url(signature)}"
    response = requests.post(
        credentials.get("token_uri", "https://oauth2.googleapis.com/token"),
        data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}, timeout=20,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def fetch_sheet_rows(sheet_id, credentials_path, worksheet="Dados dos Alunos"):
    token = service_account_token(credentials_path)
    response = requests.get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/'{worksheet}'!A:Z",
        headers={"Authorization": f"Bearer {token}"}, timeout=30,
    )
    response.raise_for_status()
    values = response.json().get("values", [])
    if not values:
        return []
    headers = values[0]
    return [{headers[index]: value for index, value in enumerate(row) if index < len(headers)} for row in values[1:]]


def normalize_date(value):
    text = str(value or "").strip()
    for date_format in ("%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text[:10], date_format).date().isoformat()
        except ValueError:
            continue
    return ""


def rows_to_export(rows):
    students = []
    for row_number, row in enumerate(rows, 2):
        history = {"msa": [], "metodo": [], "hinario": [], "provas": [], "escalas": [], "atividades": []}
        msa_date = normalize_date(row.get("MSA Lancamento"))
        if msa_date and row.get("Fase MSA"):
            history["msa"].append({
                "data_aula": msa_date, "fase": row.get("Fase MSA"),
                "observacoes": row.get("Observacoes") or "Importado da atualização SAM",
            })
        method_date = normalize_date(row.get("Data Metodo"))
        if method_date and (row.get("Licoes do Metodo") or row.get("Tipo Metodo")):
            history["metodo"].append({
                "data_inicio": method_date, "metodo": row.get("Tipo Metodo") or "Não informado",
                "licao": row.get("Licoes do Metodo"), "observacoes": "Importado da atualização SAM",
            })
        hymn_date = normalize_date(row.get("Data Hino"))
        if hymn_date and row.get("Hino"):
            history["hinario"].append({
                "data": hymn_date, "hino": row.get("Hino"), "observacoes": "Importado da atualização SAM",
            })
        students.append({
            "source_id": f"sheet-row-{row_number}", "nome": row.get("Nome"),
            "comum": row.get("Localidade"), "instrumento": row.get("Instrumento"), "history": history,
        })
    return {"source": "SAM Google Sheets", "exported_at": datetime.now().astimezone().isoformat(), "students": students}
