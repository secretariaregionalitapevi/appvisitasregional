"""Regras puras para conciliar uma exportação histórica do SAM com o GEM."""
import json
import re
import unicodedata
from hashlib import sha256


SOURCE_CONFIG = {
    "msa": ("musica_acompanhamento_msa", ("data_aula", "fase", "paginas", "licoes", "clave", "observacoes", "autorizado_por")),
    "metodo": ("musica_acompanhamento_metodo", ("data_inicio", "metodo", "pagina", "licao", "observacoes", "autorizado_por")),
    "hinario": ("musica_acompanhamento_hinario", ("data", "hino", "voz", "observacoes", "autorizado_por")),
    "provas": ("musica_acompanhamento_provas", ("data_prova", "modulo", "nota", "observacoes", "autorizado_por")),
    "escalas": ("musica_acompanhamento_escala", ("data", "escala", "observacoes", "autorizado_por")),
    "atividades": ("musica_acompanhamento_atividades", ("tipo_atividade", "titulo", "descricao", "data_atividade", "documento_url", "nome_documento")),
}


def norm(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).upper().split())


def _common_parts(value):
    normalized = norm(value)
    # O código BR identifica a comum mesmo quando a descrição mudou.
    parts = normalized.split(" - ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 and parts[0].startswith("BR-") else ("", normalized)


def _same_common(first, second):
    first_code, first_name = _common_parts(first)
    second_code, second_name = _common_parts(second)
    if first_code and second_code:
        return first_code == second_code
    return bool(first_name and first_name == second_name)


def match_student(source, targets):
    """Retorna vínculo somente quando nome/comum/instrumento produzem um único aluno."""
    candidates = [row for row in targets if norm(row.get("nome_aluno")) == norm(source.get("nome") or source.get("nome_aluno"))]
    source_common = source.get("comum") or source.get("comum_congregacao")
    if source_common:
        common_matches = [row for row in candidates if _same_common(row.get("comum_congregacao"), source_common)]
        candidates = common_matches
    source_instrument = norm(source.get("instrumento"))
    if source_instrument and source_instrument != "A DEFINIR" and len(candidates) > 1:
        candidates = [row for row in candidates if norm(row.get("instrumento")) == source_instrument]
    return candidates[0] if len(candidates) == 1 else None, "matched" if len(candidates) == 1 else "unmatched" if not candidates else "ambiguous"


def event_payload(source_name, event, student):
    _, fields = SOURCE_CONFIG[source_name]
    # PostgREST exige as mesmas chaves em todos os objetos de uma inserção em lote.
    payload = {field: event.get(field) if event.get(field) not in (None, "") else None for field in fields}
    payload.update({
        "aluno_id": student["id"],
        "comum_congregacao": student.get("comum_congregacao"),
        "municipio": student.get("municipio"),
    })
    return payload


def event_signature(source_name, payload):
    """Assinatura estável permite reimportar o mesmo arquivo sem duplicar eventos."""
    _, fields = SOURCE_CONFIG[source_name]
    identity = {"source": source_name, "aluno_id": str(payload.get("aluno_id") or "")}
    identity.update({field: payload.get(field) for field in fields})
    serialized = json.dumps(identity, ensure_ascii=False, sort_keys=True, default=str)
    return sha256(serialized.encode("utf-8")).hexdigest()


def event_match_signature(source_name, payload):
    """Identifica o mesmo lançamento sem usar campos descritivos que podem chegar incompletos."""
    _, fields = SOURCE_CONFIG[source_name]
    identity = {"source": source_name, "aluno_id": str(payload.get("aluno_id") or "")}
    identity.update({field: payload.get(field) for field in fields if field not in {"observacoes", "autorizado_por"}})
    serialized = json.dumps(identity, ensure_ascii=False, sort_keys=True, default=str)
    return sha256(serialized.encode("utf-8")).hexdigest()


def program_minimum_progress(msa_rows):
    """Calcula a cobertura comprovada das 16 faixas do Programa Mínimo."""
    expected_ranges = (
        (1.1, 1.4), (2.1, 2.6), (3.1, 3.4), (4.1, 4.5),
        (4.6, 5.2), (5.3, 6.1), (6.2, 6.6), (6.7, 7.3),
        (7.4, 8.1), (8.2, 11.2), (11.3, 12.2), (12.3, 13.2),
        (13.3, 14.2), (14.3, 15.2), (15.3, 15.6), (15.7, 16.3),
    )
    covered = set()
    for row in msa_rows or []:
        numbers = re.findall(r"\d+(?:[.,]\d+)?", str(row.get("fase") or ""))
        values = [float(number.replace(",", ".")) for number in numbers]
        if not values:
            continue
        start, end = min(values), max(values)
        if end - start > 3:
            continue
        for index, (range_start, range_end) in enumerate(expected_ranges):
            if start <= range_end and end >= range_start:
                covered.add(index)
    return round((len(covered) / len(expected_ranges)) * 100)
