import re
import unicodedata
from datetime import datetime


def _norm(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).lower().split())


def _date(value):
    try:
        return datetime.strptime(str(value).strip(), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _value(details, label):
    patterns = {"Fase": "Fase", "Pagina": "P.gina", "Licao": "Li..o"}
    match = re.search(rf"{patterns.get(label, label)}\(s\):\s*de\s*([\d.]+)\s*at[eé]\s*([\d.]+)", details, re.I)
    return f"{match.group(1)} - {match.group(2)}" if match else None


def _clave(details):
    match = re.search(r"Clave\(s\):\s*([^;\n]+)", details, re.I)
    return match.group(1).strip() if match else None


def portal_report_to_export(report):
    history = {key: [] for key in ("msa", "metodo", "hinario", "provas", "escalas", "atividades")}
    tabs = report.get("tabs") or {}
    for table in (tabs.get("MSA") or {}).get("tables", []):
        headers = [_norm(x) for x in table.get("headers", [])]
        for cells in table.get("rows", []):
            row = dict(zip(headers, cells))
            if "data da licao" in row and "fases" in row:
                history["msa"].append({
                    "data_aula": _date(row.get("data da licao")), "fase": row.get("fases"),
                    "paginas": row.get("paginas"), "licoes": row.get("licoes"), "clave": row.get("claves"),
                    "observacoes": row.get("observacoes"), "autorizado_por": row.get("autorizante"),
                })
            elif "paginas" in row and "data da licao" in row:
                details = row.get("paginas") or ""
                history["msa"].append({
                    "data_aula": _date(row.get("data da licao")), "fase": _value(details, "Fase"),
                    "paginas": _value(details, "Pagina"), "licoes": _value(details, "Licao"),
                    "clave": _clave(details),
                    "observacoes": " — ".join(filter(None, [row.get("observacoes"), "MSA em Grupo"])),
                    "autorizado_por": None,
                })
    simple = {
        "Método": ("metodo", {"data_inicio": "data da licao", "metodo": "metodo", "pagina": "paginas", "licao": "licao", "observacoes": "observacoes", "autorizado_por": "autorizante"}),
        "Hinário": ("hinario", {"data": "data da aula", "hino": "hino", "voz": "voz", "observacoes": "observacoes", "autorizado_por": "autorizante"}),
        "Provas": ("provas", {"data_prova": "data da prova", "modulo": "modulo", "nota": "nota", "observacoes": "observacoes", "autorizado_por": "autorizante"}),
        "Escalas": ("escalas", {"data": "data", "escala": "escala", "observacoes": "observacoes", "autorizado_por": "autorizante"}),
    }
    required_date = {"metodo": "data_inicio", "hinario": "data", "provas": "data_prova", "escalas": "data"}
    for tab_name, (source, mapping) in simple.items():
        for table in (tabs.get(tab_name) or {}).get("tables", []):
            headers = [_norm(x) for x in table.get("headers", [])]
            for cells in table.get("rows", []):
                if not cells or "nenhum registro" in _norm(" ".join(cells)):
                    continue
                row = dict(zip(headers, cells))
                event = {target: row.get(origin) or None for target, origin in mapping.items()}
                for field in ("data", "data_inicio", "data_prova"):
                    if field in event:
                        event[field] = _date(event[field])
                if not event.get(required_date[source]):
                    continue
                if any(event.values()):
                    history[source].append(event)
    return {"source": "SAM portal direto", "students": [{"source_id": report.get("student"), "nome": report.get("student"), "history": history}]}
