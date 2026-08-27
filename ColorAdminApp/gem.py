"""Painel gerencial do Grupo de Estudos Musicais (GEM)."""
import math
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render

from .access_control import can_access, filter_rows, scope_details, service_headers, user_scope
from .module_access import MODULE_MUSICALIZACAO, can_access_module


TABLE = "musica_acompanhamento_aluno"
SELECT_FIELDS = (
    "id,nome_aluno,status,comum_congregacao,cargo_ministerio,nivel,instrumento,"
    "municipio,programa_minimo_percentual,registro_msa,updated_at"
)
SUMMARY_FIELDS = "id,nome_aluno,nivel,instrumento,municipio,comum_congregacao,programa_minimo_percentual"
GRADUATION_TOKEN = "OFICIALIZAD"


def _norm(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).upper().split())


def is_graduated(row):
    """Oficialização encerra a formação, inclusive em níveis compostos."""
    return GRADUATION_TOKEN in _norm(row.get("nivel"))


def academic_status(row):
    return "graduado" if is_graduated(row) else "formacao"


def _percent(value):
    try:
        return max(0, min(100, int(round(float(value or 0)))))
    except (TypeError, ValueError):
        return 0


def _fetch_students():
    cached = cache.get("gem:students:v4")
    if cached is not None:
        return cached

    page_size = 1000
    url = f"{settings.SUPABASE_URL}/rest/v1/{TABLE}"
    count_response = requests.get(
        url, headers=service_headers("count=exact"),
        params={"select": "id", "limit": 1}, timeout=15,
    )
    count_response.raise_for_status()
    try:
        total = int(count_response.headers.get("Content-Range", "0/0").rsplit("/", 1)[-1])
    except ValueError:
        total = 10000

    def fetch_page(offset):
        response = requests.get(
            url,
            headers=service_headers(),
            params={"select": SUMMARY_FIELDS, "offset": offset, "limit": page_size},
            timeout=20,
        )
        response.raise_for_status()
        return offset, response.json()

    offsets = list(range(0, total, page_size))
    with ThreadPoolExecutor(max_workers=min(10, max(1, len(offsets)))) as executor:
        pages = sorted(executor.map(fetch_page, offsets), key=lambda item: item[0])
    rows = [row for _, page in pages for row in page]
    cache.set("gem:students:v4", rows, 300)
    return rows


def _visible_students(request):
    scope = user_scope(request)
    rows = []
    for source in _fetch_students():
        row = dict(source)
        row["comum"] = row.get("comum_congregacao")
        row["cidade"] = row.get("municipio")
        row["situacao_academica"] = academic_status(row)
        row["programa_minimo_informado"] = row.get("programa_minimo_percentual") is not None
        row["programa_minimo_percentual"] = _percent(row.get("programa_minimo_percentual"))
        rows.append(row)
    return scope, filter_rows(scope, rows)


def _event_date(value):
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10]


def _build_timeline(student, datasets):
    """Converte todas as fontes pedagógicas em uma cronologia única."""
    specs = {
        "msa": ("data_aula", "MSA", "fa-book-open", "fase", "paginas", "licoes"),
        "metodo": ("data_inicio", "Método", "fa-music", "metodo", "pagina", "licao"),
        "hinario": ("data", "Hinário", "fa-book-bible", "hino", "voz", None),
        "provas": ("data_prova", "Prova", "fa-clipboard-check", "modulo", "nota", None),
        "escalas": ("data", "Escala", "fa-wave-square", "escala", None, None),
    }
    events = []
    if student.get("created_at"):
        events.append({
            "date": _event_date(student["created_at"]), "type": "cadastro", "title": "Início do acompanhamento",
            "description": "Aluno incluído no acompanhamento do GEM.", "icon": "fa-user-plus", "source": "Cadastro",
        })
    for source, rows in datasets.items():
        if source == "atividades":
            for row in rows:
                events.append({
                    "date": _event_date(row.get("data_atividade") or row.get("created_at")),
                    "type": row.get("tipo_atividade") or "atividade",
                    "title": row.get("titulo") or "Marco acadêmico",
                    "description": row.get("descricao") or row.get("observacoes") or "",
                    "icon": "fa-flag-checkered", "source": "Marco",
                    "document_url": row.get("documento_url") or "",
                })
            continue
        date_field, label, icon, primary, secondary, tertiary = specs[source]
        for row in rows:
            details = []
            for field in (primary, secondary, tertiary):
                if field and row.get(field) not in (None, ""):
                    details.append(f"{field.replace('_', ' ').title()}: {row[field]}")
            if row.get("observacoes"):
                details.append(str(row["observacoes"]))
            events.append({
                "date": _event_date(row.get(date_field) or row.get("created_at")),
                "type": source, "title": label, "description": " · ".join(details),
                "icon": icon, "source": label, "authorized_by": row.get("autorizado_por") or "",
            })
    return sorted(events, key=lambda item: (item.get("date") or "", item.get("title") or ""), reverse=True)


def _milestones(level):
    normalized = _norm(level)
    current = 0
    if "OFICIALIZAD" in normalized:
        current = 4
    elif "CULTO OFICIAL" in normalized:
        current = 3
    elif "RJM" in normalized or "MEIA HORA" in normalized:
        current = 2
    elif "ENSAIO" in normalized:
        current = 1
    stages = [
        ("Início dos estudos", "Preparação e desenvolvimento inicial"),
        ("Ingresso no Ensaio", "Programa mínimo para ensaio"),
        ("Ingresso na RJM", "Apto para Reunião de Jovens e Menores"),
        ("Culto Oficial", "Apto para tocar nos cultos oficiais"),
        ("Oficialização", "Conclusão da formação musical"),
    ]
    return [{"title": title, "description": description, "status": "achieved" if index < current else "current" if index == current else "future"}
            for index, (title, description) in enumerate(stages)]


def can_open_module(request):
    # Nesta primeira etapa o GEM herda a autorização territorial da Musicalização.
    return can_access_module(request, MODULE_MUSICALIZACAO)


def _denied():
    return JsonResponse({"error": "Seu perfil não possui acesso à pasta GEM."}, status=403)


def page(request):
    if not can_open_module(request):
        return render(request, "pages/403.html", {"message": "Seu perfil não possui acesso à pasta GEM."}, status=403)
    return render(request, "pages/gem.html", {"scope": scope_details(user_scope(request))})


def api_summary(request):
    if not can_open_module(request):
        return _denied()
    if request.method != "GET":
        return JsonResponse({"error": "Método não permitido."}, status=405)
    try:
        requested_scope = user_scope(request)
        summary_key = f"gem:summary:v3:{requested_scope['level']}:{_norm(requested_scope['municipio'])}:{_norm(requested_scope['comum'])}"
        cached_summary = cache.get(summary_key)
        if cached_summary is not None:
            return JsonResponse(cached_summary)
        scope, rows = _visible_students(request)
        formation = [row for row in rows if not is_graduated(row)]
        graduates = [row for row in rows if is_graduated(row)]
        complete = [row for row in formation if row["programa_minimo_percentual"] >= 100]
        with_progress = [row for row in formation if row["programa_minimo_informado"]]

        levels = Counter(_norm(row.get("nivel")) or "NÃO INFORMADO" for row in formation)
        instruments = Counter(_norm(row.get("instrumento")) or "A DEFINIR" for row in formation)
        municipalities = Counter(_norm(row.get("municipio")) or "NÃO INFORMADO" for row in formation)
        payload = {
            "scope": scope_details(scope),
            "totals": {
                "formation": len(formation),
                "graduates": len(graduates),
                "all": len(rows),
                "program_complete": len(complete),
                "program_tracked": len(with_progress),
                "average_progress": round(sum(row["programa_minimo_percentual"] for row in with_progress) / len(with_progress)) if with_progress else 0,
            },
            "levels": [{"label": label, "value": value} for label, value in levels.most_common()],
            "instruments": [{"label": label, "value": value} for label, value in instruments.most_common(8)],
            "instrument_options": sorted(instruments),
            "municipalities": [{"label": label, "value": value} for label, value in municipalities.most_common()],
        }
        cache.set(summary_key, payload, 300)
        return JsonResponse(payload)
    except (requests.RequestException, ValueError):
        return JsonResponse({"error": "Não foi possível consultar os dados do GEM."}, status=502)


def api_students(request):
    if not can_open_module(request):
        return _denied()
    if request.method != "GET":
        return JsonResponse({"error": "Método não permitido."}, status=405)
    try:
        scope = user_scope(request)
        category = request.GET.get("situacao", "formacao")
        try:
            page_number = max(1, int(request.GET.get("page", 1)))
            page_size = max(10, min(100, int(request.GET.get("page_size", 25))))
        except ValueError:
            page_number, page_size = 1, 25
        params = {
            "select": SELECT_FIELDS, "order": "nome_aluno.asc",
            "offset": (page_number - 1) * page_size, "limit": page_size,
        }
        if category == "formacao":
            params["nivel"] = "not.ilike.*OFICIALIZAD*"
        elif category == "graduados":
            params["nivel"] = "ilike.*OFICIALIZAD*"
        if scope["level"] == "local":
            params["comum_congregacao"] = f"eq.{scope['comum']}"
        elif scope["level"] == "municipal":
            params["municipio"] = f"eq.{scope['municipio']}"
        for query_name, column in (("nivel", "nivel"), ("municipio", "municipio"), ("instrumento", "instrumento")):
            value = request.GET.get(query_name, "").strip()
            if value:
                params[column] = f"eq.{value}"
        query = request.GET.get("q", "").strip()
        if query:
            safe_query = "".join(char for char in query if char not in "(),.*")[:80]
            if safe_query:
                params["or"] = "(" + ",".join(
                    f"{column}.ilike.*{safe_query}*" for column in
                    ("nome_aluno", "comum_congregacao", "municipio", "instrumento", "nivel")
                ) + ")"
        response = requests.get(
            f"{settings.SUPABASE_URL}/rest/v1/{TABLE}",
            headers=service_headers("count=exact"), params=params, timeout=15,
        )
        response.raise_for_status()
        rows = []
        for source in response.json():
            row = dict(source)
            row["comum"] = row.get("comum_congregacao")
            row["cidade"] = row.get("municipio")
            row["situacao_academica"] = academic_status(row)
            row["programa_minimo_informado"] = row.get("programa_minimo_percentual") is not None
            row["programa_minimo_percentual"] = _percent(row.get("programa_minimo_percentual"))
            rows.append(row)
        try:
            total = int(response.headers.get("Content-Range", "0/0").rsplit("/", 1)[-1])
        except ValueError:
            total = len(rows)
        return JsonResponse({
            "items": rows,
            "pagination": {
                "page": page_number,
                "page_size": page_size,
                "pages": max(1, math.ceil(total / page_size)),
                "total": total,
            },
        })
    except (requests.RequestException, ValueError):
        return JsonResponse({"error": "Não foi possível consultar os alunos do GEM."}, status=502)


def api_student_timeline(request, student_id):
    if not can_open_module(request):
        return _denied()
    if request.method != "GET":
        return JsonResponse({"error": "Método não permitido."}, status=405)
    try:
        scope = user_scope(request)
        student_response = requests.get(
            f"{settings.SUPABASE_URL}/rest/v1/{TABLE}", headers=service_headers(),
            params={"select": SELECT_FIELDS, "id": f"eq.{student_id}", "limit": 1}, timeout=15,
        )
        student_response.raise_for_status()
        source_rows = student_response.json()
        if not source_rows:
            # Não diferencia registro inexistente de registro fora do escopo.
            return JsonResponse({"error": "Aluno não encontrado neste escopo."}, status=404)
        student = dict(source_rows[0])
        student["comum"] = student.get("comum_congregacao")
        student["cidade"] = student.get("municipio")
        if not can_access(scope, student):
            return JsonResponse({"error": "Aluno não encontrado neste escopo."}, status=404)
        student["situacao_academica"] = academic_status(student)
        student["programa_minimo_informado"] = student.get("programa_minimo_percentual") is not None
        student["programa_minimo_percentual"] = _percent(student.get("programa_minimo_percentual"))

        sources = {
            "msa": ("musica_acompanhamento_msa", "data_aula.desc"),
            "metodo": ("musica_acompanhamento_metodo", "data_inicio.desc"),
            "hinario": ("musica_acompanhamento_hinario", "data.desc"),
            "provas": ("musica_acompanhamento_provas", "data_prova.desc"),
            "escalas": ("musica_acompanhamento_escala", "data.desc"),
            "atividades": ("musica_acompanhamento_atividades", "data_atividade.desc"),
        }

        def fetch(item):
            name, (table, order) = item
            response = requests.get(
                f"{settings.SUPABASE_URL}/rest/v1/{table}", headers=service_headers(),
                params={"select": "*", "aluno_id": f"eq.{student_id}", "order": order}, timeout=15,
            )
            response.raise_for_status()
            return name, response.json()

        with ThreadPoolExecutor(max_workers=6) as executor:
            datasets = dict(executor.map(fetch, sources.items()))
        return JsonResponse({
            "student": student,
            "milestones": _milestones(student.get("nivel")),
            "events": _build_timeline(student, datasets),
            "counts": {name: len(rows) for name, rows in datasets.items()},
        })
    except (requests.RequestException, ValueError):
        return JsonResponse({"error": "Não foi possível carregar a linha do tempo do aluno."}, status=502)
