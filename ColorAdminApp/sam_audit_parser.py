"""Normalizacao dos logs precarios do SAM em eventos investigaveis."""
import hashlib
import json
import re
import unicodedata
from datetime import datetime


def _norm(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).upper().split())


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _date(value):
    text = _clean(value)
    for pattern in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(text.replace("Z", "+0000"), pattern).isoformat()
        except ValueError:
            continue
    return None


ACTION_RULES = (
    ("presenca", r"marcou\s+presen[cç]a"),
    ("licao", r"(?:li[cç][aã]o|msa|m[eé]todo|hin[aá]rio)"),
    ("aula", r"\baula\b"),
    ("turma", r"\bturma\b"),
    ("tarefa", r"\btarefa\b"),
    ("aluno", r"\balun[oa]\b"),
    ("usuario", r"\busu[aá]ri[oa]\b|recupera[cç][aã]o de senha"),
    ("ata", r"\bata\b"),
    ("acesso", r"acessou o sistema|entrou no sistema|saiu do sistema|login|logout"),
    ("fase", r"\bfase\b"),
)


def classify_action(action):
    normalized = _norm(action).lower()
    for name, pattern in ACTION_RULES:
        if re.search(pattern, normalized, re.I):
            return name
    return "outro"


def parse_references(action):
    text = _clean(action)
    refs = {}
    aliases = {
        "attendance_id": (r"(?:id\s*(?:da\s*)?matr[ií]cula|matr[ií]cula(?:\s*id)?)\s*[=:]?\s*(\d+)", "matricula"),
        "member_id": (r"(?:id\s*(?:do\s*)?membro|membro\s*id)\s*[=:]?\s*(\d+)", "aluno"),
        "student_id": (r"(?:id\s*(?:do\s*)?alun[oa]|alun[oa]\s*id)\s*[=:]?\s*(\d+)", "aluno"),
        "class_id": (r"(?:id\s*(?:da\s*)?aula|aula\s*id)\s*[=:]?\s*(\d+)", "aula"),
        "group_id": (r"(?:id\s*(?:da\s*)?turma|turma\s*id)\s*[=:]?\s*(\d+)", "turma"),
        "task_id": (r"(?:id\s*(?:da\s*)?tarefa|tarefa\s*id)\s*[=:]?\s*(\d+)", "tarefa"),
        "user_id": (r"(?:id\s*(?:do\s*)?usu[aá]ri[oa]|usu[aá]ri[oa]\s*id)\s*[=:]?\s*(\d+)", "usuario"),
    }
    target_type = target_id = None
    for key, (pattern, kind) in aliases.items():
        match = re.search(pattern, text, re.I)
        if match:
            refs[key] = int(match.group(1))
            if target_id is None:
                target_type, target_id = kind, refs[key]
    method_match = re.search(r"li[cç][aã]o\s+do\s+m[eé]todo\s*:\s*(\d+)", text, re.I)
    if method_match:
        refs["method_id"] = int(method_match.group(1))
        return refs, "metodo", refs["method_id"]
    hymn_match = re.search(r"hin[aá]rio\s*:\s*(\d+)", text, re.I)
    student_match = re.search(r"alun[oa]\s*:\s*(\d+)", text, re.I)
    if hymn_match:
        refs["hymn_id"] = int(hymn_match.group(1))
        if student_match:
            refs["student_id"] = int(student_match.group(1))
        return refs, "hinario", refs["hymn_id"]
    # Formato observado no SAM: "Salvou ata: 42534".
    if target_id is None:
        match = re.search(r"\b(ata|turma|tarefa|aula|alun[oa]|usu[aá]ri[oa])\s*:\s*(\d+)", text, re.I)
        if match:
            target_type = _norm(match.group(1)).lower().replace("á", "a")
            target_id = int(match.group(2))
            ref_key = {"aula": "class_id", "turma": "group_id", "aluno": "student_id",
                       "aluna": "student_id", "usuario": "user_id", "usuaria": "user_id",
                       "matricula": "attendance_id", "ata": "ata_id"}.get(target_type, target_type + "_id")
            refs[ref_key] = target_id
    return refs, target_type, target_id


def parse_log_row(row):
    """Aceita dicionario ou linha do DataTables do SAM e preserva o original."""
    if isinstance(row, (list, tuple)):
        cells = list(row) + [None] * 8
        row = {"source_log_id": cells[0], "actor": cells[1], "congregation": cells[2],
               "action": cells[3], "occurred_at": cells[4], "device": cells[5],
               "platform": cells[6], "ip": cells[7]}
    original = dict(row or {})
    get = lambda *keys: next((original.get(k) for k in keys if original.get(k) not in (None, "")), None)
    action = _clean(get("action", "acao", "Ação", "descricao"))
    actor = _clean(get("actor", "usuario", "Usuário", "nome_usuario")) or "USUARIO NAO IDENTIFICADO"
    congregation = _clean(get("congregation", "comum", "Comum Congregação", "congregacao")) or None
    occurred = _date(get("occurred_at", "data_hora", "Data Hora", "created_at"))
    if not action or not occurred:
        return None
    refs, target_type, target_id = parse_references(action)
    stable = {
        "source_log_id": get("source_log_id", "id", "log_id"), "occurred_at": occurred,
        "actor": actor, "congregation": congregation, "action": action,
        "device": _clean(get("device", "dispositivo", "Dispositivo")) or None,
        "platform": _clean(get("platform", "plataforma", "Plataforma")) or None,
        "ip": _clean(get("ip", "IP", "ip_address")) or None,
    }
    fingerprint = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    source_id = stable["source_log_id"]
    return {
        "source_fingerprint": fingerprint,
        "source_log_id": int(source_id) if str(source_id or "").isdigit() else None,
        "occurred_at": occurred, "actor_name_snapshot": actor,
        "congregation_snapshot": congregation, "action_raw": action,
        "action_type": classify_action(action), "target_type": target_type,
        "target_source_id": target_id, "device": stable["device"],
        "platform": stable["platform"], "ip_address": stable["ip"],
        "parsed_refs": refs, "source_payload": original,
    }
