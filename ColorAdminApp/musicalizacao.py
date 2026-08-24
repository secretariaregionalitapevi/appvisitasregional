"""Módulo gerencial de Musicalização com autorização obrigatória no servidor."""
import json
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import requests
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render

from .access_control import can_access, common_catalog, filter_rows, scope_details, service_headers, user_scope
from .module_access import MODULE_MUSICALIZACAO, can_access_module


RESOURCES = {
    "criancas": {
        "table": "musicalizacao_criancas", "order": "nome_crianca.asc",
        "fields": {"nome_crianca", "sexo", "data_nascimento", "comum_congregacao", "polo_participacao",
                   "nome_pai", "pai_e_crente", "nome_mae", "mae_e_crente", "pais_vivem_juntos",
                   "crianca_vive_com_os_pais", "se_nao_vive_com_pais_com_quem_vive", "nome_responsavel",
                   "celular_responsavel", "tem_whatsapp", "participa_reunioes_jovens_menores",
                   "participa_espaco_infantil", "logradouro_numero", "complemento", "bairro", "cidade", "cep",
                   "dificuldade_aprendizagem", "dificuldade_descricao", "faz_terapia", "terapia_especialidade", "status"},
        "location": lambda row: {"comum": row.get("polo_participacao") or row.get("comum_congregacao"), "cidade": _child_polo_city(row)},
    },
    "instrutores": {
        "table": "musicalizacao_monitores", "order": "nome_completo.asc",
        "fields": {"nome_completo", "comum_congregacao", "data_nascimento", "idade", "batizado", "data_batismo",
                   "celular", "email", "polo_auxilio", "musico_ou_musicista", "oficializado", "data_oficializacao",
                   "instrutor_atualmente", "instrutor_em_qual_igreja", "formacao_musica", "formacao_qual", "formacao_data",
                   "pedagogo", "pedagogo_desde", "atua_na_area", "afinidade_criancas", "cursos_conhecimentos",
                   "de_acordo_voluntario", "autoriza_tratamento_dados", "status", "role"},
        "location": lambda row: {"comum": row.get("comum_congregacao")},
    },
    "polos": {
        "table": "musicalizacao_polos", "order": "nome_polo.asc",
        "fields": {"nome_polo", "localidade", "encarregado"},
        "location": lambda row: {"cidade": row.get("cidade") or row.get("localidade"), "comum": row.get("nome_polo")},
    },
    "aulas": {
        "table": "musicalizacao_aulas", "order": "data_aula.desc",
        "fields": {"data_aula", "cidade", "polo", "ciclo", "numero_aula", "meninos_presentes", "meninas_presentes",
                   "instrutores_presentes", "colaboradores_presentes", "coordenadores_presentes", "nome_atividade", "observacoes"},
        "location": lambda row: {"cidade": row.get("cidade"), "comum": row.get("polo")},
    },
}

# Catálogo regional oficial usado pelo módulo original. Ele não pode ser
# inferido dos lançamentos: municípios sem atividade no período também devem
# aparecer nos filtros e relatórios com valores zerados.
REGIONAL_MUNICIPALITIES = [
    "CAUCAIA DO ALTO",
    "COTIA",
    "ITAPEVI",
    "JANDIRA",
    "PIRAPORA DO BOM JESUS",
    "SANTANA DE PARNAIBA",
    "VARGEM GRANDE PAULISTA",
]


def _norm(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in value if not unicodedata.combining(c)).strip().upper()


def _child_polo_city(row):
    """Município gerencial vem do polo; cidade da residência não define o projeto."""
    polo = row.get("polo_participacao") or row.get("comum_congregacao")
    try:
        match = next((item for item in common_catalog() if _norm(item.get("comum")) == _norm(polo)), None)
    except requests.RequestException:
        match = None
    return (match or {}).get("cidade") or row.get("cidade")


def can_open_module(request):
    return can_access_module(request, MODULE_MUSICALIZACAO)


def _denied():
    return JsonResponse({"error": "Seu perfil não possui acesso à pasta Musicalização."}, status=403)


def _url(config):
    return f"{settings.SUPABASE_URL}/rest/v1/{config['table']}"


def _coordinators_by_polo():
    response = requests.get(
        f"{settings.SUPABASE_URL}/rest/v1/musicalizacao_monitores",
        headers=service_headers(),
        params={"select": "nome_completo,polo_auxilio,role,status", "role": "ilike.Coordenadora", "status": "ilike.Ativo"},
        timeout=10,
    )
    response.raise_for_status()
    result = {}
    for row in response.json():
        polo = _norm(row.get("polo_auxilio"))
        if polo:
            result.setdefault(polo, []).append(row.get("nome_completo"))
    return {polo: " / ".join(filter(None, names)) for polo, names in result.items()}


def _visible(scope, config, rows):
    enriched = []
    for row in rows:
        item = dict(row)
        if config["table"] == "musicalizacao_criancas":
            item["cidade_residencial"] = row.get("cidade")
        item.update(config["location"](row))
        enriched.append(item)
    return filter_rows(scope, enriched)


def page(request, section="dashboard"):
    if not can_open_module(request):
        return render(request, "pages/403.html", {"message": "Seu perfil não possui acesso à pasta Musicalização."}, status=403)
    if section not in {"dashboard", *RESOURCES.keys(), "historico"}:
        section = "dashboard"
    return render(request, "pages/musicalizacao.html", {"section": section, "scope": scope_details(user_scope(request))})


def api_summary(request):
    if not can_open_module(request):
        return _denied()
    if request.method != "GET":
        return JsonResponse({"error": "Método não permitido."}, status=405)
    scope = user_scope(request)
    municipalities = REGIONAL_MUNICIPALITIES
    if scope["level"] in {"municipal", "local"} and scope["municipio"]:
        municipalities = [scope["municipio"].upper()]
    result = {"scope": scope_details(scope), "warnings": [], "municipios": municipalities}
    summary_fields = {
        "criancas": "id,nome_crianca,sexo,data_nascimento,comum_congregacao,polo_participacao,cidade,nome_responsavel,celular_responsavel,status",
        "instrutores": "comum_congregacao,polo_auxilio,role,status",
        "polos": "nome_polo,localidade",
        "aulas": "id,data_aula,cidade,polo,ciclo,numero_aula,meninos_presentes,meninas_presentes,instrutores_presentes,colaboradores_presentes,coordenadores_presentes,nome_atividade",
        "presencas": "aula_id,aluno_id,status,presente",
    }
    try:
        cached = cache.get("musicalizacao:dashboard:v6")

        def fetch(item):
            name, config = item
            source_key = f"musicalizacao:source:v6:{name}"
            source_cached = cache.get(source_key)
            if source_cached is not None:
                return name, source_cached, None
            try:
                response = requests.get(_url(config), headers=service_headers(), params={"select": summary_fields[name], "order": config["order"]}, timeout=6)
                response.raise_for_status()
                rows = response.json()
                cache.set(source_key, rows, 300)
                return name, rows, None
            except requests.RequestException:
                return name, [], f"A fonte {name} não respondeu a tempo."

        if cached is None:
            # As fontes são independentes: o tempo passa a ser o da consulta mais
            # lenta e uma falha parcial não derruba todo o painel.
            sources = list(RESOURCES.items()) + [("presencas", {"table": "musicalizacao_presenca", "order": "created_at.desc"})]
            with ThreadPoolExecutor(max_workers=5) as executor:
                datasets = list(executor.map(fetch, sources))
            raw = {name: rows for name, rows, warning in datasets}
            warnings = [warning for name, rows, warning in datasets if warning]
            if not warnings:
                cache.set("musicalizacao:dashboard:v6", raw, 300)
        else:
            raw, warnings = cached, []

        result["warnings"] = warnings
        for name, config in RESOURCES.items():
            rows = _visible(scope, config, raw.get(name, []))
            result[name] = rows
            result[f"total_{name}"] = len(rows)
        allowed_aulas = {str(row.get("id")) for row in result["aulas"] if row.get("id")}
        allowed_children = {str(row.get("id")) for row in result["criancas"] if row.get("id")}
        result["presencas"] = [row for row in raw.get("presencas", []) if (
            str(row.get("aula_id")) in allowed_aulas and str(row.get("aluno_id")) in allowed_children
        )]
        return JsonResponse(result)
    except requests.RequestException:
        return JsonResponse({"error": "Não foi possível consultar os dados de Musicalização."}, status=502)


def api_resource(request, resource, record_id=None):
    if not can_open_module(request):
        return _denied()
    config = RESOURCES.get(resource)
    if not config:
        return JsonResponse({"error": "Recurso inválido."}, status=404)
    scope = user_scope(request)
    try:
        if request.method == "GET" and not record_id:
            response = requests.get(_url(config), headers=service_headers(), params={"select": "*", "order": config["order"]}, timeout=15)
            response.raise_for_status()
            items = _visible(scope, config, response.json())
            if resource == "polos":
                coordinators = _coordinators_by_polo()
                for item in items:
                    item["coordenadora"] = coordinators.get(_norm(item.get("nome_polo")))
            return JsonResponse({"items": items, "scope": scope_details(scope)})

        current = None
        if record_id:
            response = requests.get(_url(config), headers=service_headers(), params={"select": "*", "id": f"eq.{record_id}", "limit": 1}, timeout=15)
            response.raise_for_status()
            rows = response.json()
            current = rows[0] if rows else None
            if not current:
                return JsonResponse({"error": "Registro não encontrado."}, status=404)
            if not can_access(scope, config["location"](current)):
                return _denied()

        if request.method in {"POST", "PATCH"}:
            payload = json.loads(request.body or "{}")
            payload = {key: value for key, value in payload.items() if key in config["fields"]}
            candidate = dict(current or {}, **payload)
            if not payload or not can_access(scope, config["location"](candidate)):
                return _denied()
            params = {"id": f"eq.{record_id}"} if record_id else None
            method = requests.patch if record_id else requests.post
            response = method(_url(config), headers=service_headers("return=representation"), params=params, json=payload, timeout=15)
            response.raise_for_status()
            return JsonResponse({"item": response.json()[0]}, status=200 if record_id else 201)

        if request.method == "DELETE" and record_id:
            response = requests.delete(_url(config), headers=service_headers("return=minimal"), params={"id": f"eq.{record_id}"}, timeout=15)
            response.raise_for_status()
            return JsonResponse({}, status=204)
        return JsonResponse({"error": "Método não permitido."}, status=405)
    except (ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "JSON inválido."}, status=400)
    except requests.RequestException:
        return JsonResponse({"error": "Falha ao acessar os dados de Musicalização."}, status=502)
