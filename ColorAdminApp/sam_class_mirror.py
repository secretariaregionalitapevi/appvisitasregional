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


def fetch_group_page(page, start=0, length=5000):
    payload = {
        "draw": "1", "start": str(start), "length": str(length), "search[value]": "",
        "order[0][column]": "2", "order[0][dir]": "asc",
    }
    return json.loads(fetch_text(page, f"{BASE_URL}/turmas/listagem", "POST", payload))


def parse_group_row(cells):
    cells = list(cells or [])
    source_markup = " ".join(str(value or "") for value in (cells[:1] + cells[-1:]))
    match = re.search(r"(?:value|data-id|turma|editar|excluir)[^\d]{0,20}(\d+)", source_markup, re.I)
    if not match:
        numbers = re.findall(r"\d+", str(cells[0] if cells else ""))
        match_value = numbers[0] if numbers else None
    else:
        match_value = match.group(1)
    if not match_value:
        return None
    offset = 1 if len(cells) >= 9 else 0
    enrolled_match = re.search(r"\d+", str(cells[offset + 3] if len(cells) > offset + 3 else ""))
    row = {
        "source_id": str(match_value),
        "congregacao": BeautifulSoup(str(cells[offset] or ""), "html.parser").get_text(" ", strip=True),
        "curso": BeautifulSoup(str(cells[offset + 1] or ""), "html.parser").get_text(" ", strip=True),
        "turma": BeautifulSoup(str(cells[offset + 2] or ""), "html.parser").get_text(" ", strip=True),
        "matriculados": int(enrolled_match.group(0)) if enrolled_match else 0,
        "data_inicio": _slash_date(cells[offset + 4] if len(cells) > offset + 4 else None),
        "data_termino": _slash_date(cells[offset + 5] if len(cells) > offset + 5 else None),
        "dia_horario": BeautifulSoup(str(cells[offset + 6] or ""), "html.parser").get_text(" ", strip=True),
        "ativo": "check" in str(cells[offset + 7] if len(cells) > offset + 7 else "").lower(),
    }
    row["source_hash"] = fingerprint(row)
    return row


def _slash_date(value):
    try:
        return datetime.strptime(BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None

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
