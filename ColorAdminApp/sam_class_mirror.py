import hashlib
import json
import re
import unicodedata
from datetime import datetime

from bs4 import BeautifulSoup


BASE_URL = "https://musical.congregacao.org.br"


def norm(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).upper().split())


def fingerprint(value):
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def iso_date(value):
    try:
        return datetime.strptime(str(value).strip(), "%d-%m-%Y").date().isoformat()
    except ValueError:
        return None


def fetch_text(page, url, method="GET", payload=None):
    return page.evaluate(
        """async ({url, method, payload}) => {
            const response = await fetch(url, {
                method, credentials: 'same-origin',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    ...(method === 'POST' ? {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'} : {})
                },
                body: method === 'POST' ? new URLSearchParams(payload || {}) : undefined
            });
            const text = await response.text();
            if (!response.ok) throw new Error(`SAM respondeu ${response.status}: ${text.slice(0, 200)}`);
            return text;
        }""",
        {"url": url, "method": method, "payload": payload or {}},
    )


def fetch_class_page(page, start=0, length=2000):
    payload = {
        "draw": "1", "start": str(start), "length": str(length), "search[value]": "",
        "order[0][column]": "4", "order[0][dir]": "desc",
    }
    return json.loads(fetch_text(page, f"{BASE_URL}/aulas_abertas/listagem", "POST", payload))


def parse_class_row(cells):
    frequency = str(cells[5] if len(cells) > 5 else "")
    match = re.search(r"visualizarFrequencias\((\d+)\s*,\s*(\d+)\)", frequency)
    source_id = str(cells[0] or "").strip()
    turma_source_id = match.group(2) if match else None
    row = {
        "source_id": source_id, "turma_source_id": turma_source_id,
        "congregacao": str(cells[1] or "").strip(), "curso": str(cells[2] or "").strip(),
        "turma": str(cells[3] or "").strip(), "data_aula": iso_date(cells[4]),
    }
    row["source_hash"] = fingerprint(row)
    return row


def parse_class_detail(document):
    soup = BeautifulSoup(document or "", "html.parser")
    values = {}
    date_match = re.search(r"(\d{2}/\d{2}/\d{4})", soup.get_text(" ", strip=True))
    if date_match:
        values["data_aula"] = datetime.strptime(date_match.group(1), "%d/%m/%Y").date().isoformat()
    for row in soup.select("tbody tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) >= 2:
            values[norm(cells[0].get_text(" ", strip=True))] = cells[1].get_text(" ", strip=True)
    return {
        "inicio": values.get("INICIO"), "termino": values.get("TERMINO"),
        "instrutor_responsavel": values.get("INSTRUTOR(A) RESPONSAVEL"),
        "instrutor_aula": values.get("INSTRUTOR(A) QUE MINISTROU A AULA"),
        **({"data_aula": values["data_aula"]} if values.get("data_aula") else {}),
    }


def parse_attendance(document):
    soup = BeautifulSoup(document or "", "html.parser")
    records = {}
    for row in soup.select("tbody tr"):
        link = row.select_one("[data-id-membro]")
        cells = row.find_all("td")
        if not link or not cells:
            continue
        member_match = re.search(r"\d+", str(link.get("data-id-membro") or ""))
        frequency_match = re.search(r"\d+", str(link.get("data-id-freq") or ""))
        if not member_match:
            continue
        record = {
            "source_member_id": member_match.group(0),
            "source_frequency_id": frequency_match.group(0) if frequency_match else None,
            "nome_aluno": cells[0].get_text(" ", strip=True),
            "presente": bool(link.select_one(".fa-check.text-success")),
        }
        record["source_hash"] = fingerprint(record)
        records[record["source_member_id"]] = record
    return list(records.values())
