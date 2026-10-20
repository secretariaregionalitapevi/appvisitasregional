"""Cadastro e eventos do D.A.R.P.E com autorização e escopo territorial no servidor."""
import io
import json
import unicodedata
from datetime import date, datetime
from urllib.parse import quote

import requests
from django.conf import settings
from django.http import JsonResponse
from django.http import HttpResponse
from django.shortcuts import render
from openpyxl import Workbook
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .access_control import _norm, can_access, common_catalog, filter_rows, scope_details, service_headers, user_scope
from .module_access import MODULE_DARPE, can_access_module
from .music_events_identity import CommonResolver
from .musicalizacao import REGIONAL_MUNICIPALITIES


RESOURCES = {
    "cadastros": {
        "table": "darpe_cadastro", "order": "nome_completo.asc",
        "fields": {
            "cpf", "nome_completo", "instrumento_oficializado", "rg", "data_nascimento", "sexo",
            "estado_civil", "comum_congregacao", "data_batismo", "logradouro", "numero", "complemento",
            "bairro", "cidade", "uf", "cep", "ddd", "telefone", "darpe_ministerio", "darpe_atendente",
            "darpe_colaborador", "darpe_encarregado", "darpe_musico", "darpe_organista",
            "darpe_musico_organista", "darpe_grupo_canto",
            "declaracao_local", "declaracao_data", "nome_ministerio", "nome_encarregado_orquestra",
            "nome_voluntario", "status",
        },
        "location": lambda row: {"comum": row.get("comum_congregacao"), "cidade": row.get("cidade")},
    },
    "eventos": {
        "table": "darpe_eventos", "order": "data_evento.desc",
        "fields": {"titulo", "tipo", "data_evento", "hora_inicio", "hora_fim", "comum", "municipio",
                   "local_evento", "endereco", "status", "observacoes"},
        "location": lambda row: {"comum": row.get("comum"), "municipio": row.get("municipio")},
    },
    "participantes": {
        "table": "darpe_evento_participantes", "order": "created_at.desc",
        "fields": {"evento_id", "cadastro_id", "funcao", "situacao", "observacoes"},
        "location": lambda row: {},
    },
}


def _actor(request):
    profile = request.session.get("user_profile") or {}
    return {
        "id": str(request.session.get("user_id") or profile.get("user_id") or ""),
        "name": str(profile.get("full_name") or profile.get("nome") or profile.get("email") or "Usuário autenticado").strip(),
    }


def _denied():
    return JsonResponse({"error": "Seu perfil não possui acesso à pasta D.A.R.P.E."}, status=403)


def _url(config):
    return f"{settings.SUPABASE_URL}/rest/v1/{config['table']}"


def _phone(value):
    digits = "".join(char for char in str(value or "") if char.isdigit())
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2]} {digits[3:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    return str(value or "")


def _with_canonical_commons(rows):
    """Acrescenta o código BR do catálogo sem modificar o valor legado salvo."""
    try:
        resolver = CommonResolver(common_catalog())
    except (requests.RequestException, ValueError):
        resolver = None
    enriched = []
    for original in rows:
        row = dict(original)
        canonical = resolver.resolve(row.get("comum_congregacao"), row.get("cidade")) if resolver else None
        row["comum_exibicao"] = (canonical or {}).get("comum") or row.get("comum_congregacao")
        enriched.append(row)
    return enriched


def _canonical_city(value):
    """Retorna uma única grafia oficial para cada município regional."""
    cities = {_norm(city): city for city in REGIONAL_MUNICIPALITIES}
    return cities.get(_norm(value))


def _regional_rows(rows):
    normalized = []
    for original in rows:
        city = _canonical_city(original.get("cidade"))
        if city:
            normalized.append({**original, "cidade": city})
    return normalized


def _import_clean(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    value = str(value).strip()
    return value or None


def _import_yes(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(char for char in value if not unicodedata.combining(char)).strip().upper()
    return value in {"SIM", "S", "TRUE", "1", "X"}


def _musical_flags(instrument, sex, selected):
    """Converte a coluna legada em funções mutuamente exclusivas."""
    if not selected:
        return False, False
    organist = "ORGAO" in _norm(instrument) or _norm(sex) == "FEMININO"
    return not organist, organist


def _import_key(row):
    return _norm(row.get("nome_completo")), _norm(row.get("comum_congregacao"))


def _read_imported_cadastros(upload):
    try:
        workbook = load_workbook(upload, read_only=True, data_only=True)
        sheet = workbook["Cadastro"]
    except (KeyError, OSError, ValueError) as exc:
        raise ValueError("Selecione a planilha oficial com a aba Cadastro.") from exc
    resolver = CommonResolver(common_catalog())
    actor_id = "importacao-darpe-planilha"
    actor_name = "Importação do mapeamento regional D.A.R.P.E"
    rows = []
    unresolved = []
    for values in sheet.iter_rows(min_row=4, values_only=True):
        if not _import_clean(values[1]):
            continue
        common = _import_clean(values[7]) or "NÃO INFORMADA"
        city = _import_clean(values[13])
        canonical = resolver.resolve(common, city)
        if canonical:
            common, city = canonical["comum"], canonical["cidade"]
        city = _canonical_city(city)
        if not city:
            unresolved.append(common)
        musician, organist = _musical_flags(values[2], values[5], _import_yes(values[22]))
        rows.append({
            "cpf": _import_clean(values[0]), "nome_completo": _import_clean(values[1]),
            "instrumento_oficializado": _import_clean(values[2]), "rg": _import_clean(values[3]),
            "data_nascimento": _import_clean(values[4]), "sexo": _import_clean(values[5]),
            "estado_civil": _import_clean(values[6]), "comum_congregacao": common,
            "data_batismo": _import_clean(values[8]), "logradouro": _import_clean(values[9]),
            "numero": _import_clean(values[10]), "complemento": _import_clean(values[11]),
            "bairro": _import_clean(values[12]), "cidade": city,
            "uf": (_import_clean(values[14]) or "").upper() or None, "cep": _import_clean(values[15]),
            "ddd": _import_clean(values[16]), "telefone": _import_clean(values[17]),
            "darpe_ministerio": _import_yes(values[18]), "darpe_atendente": _import_yes(values[19]),
            "darpe_colaborador": _import_yes(values[20]), "darpe_encarregado": _import_yes(values[21]),
            "darpe_musico": musician, "darpe_organista": organist,
            "darpe_musico_organista": musician or organist, "darpe_grupo_canto": _import_yes(values[23]),
            "declaracao_local": _import_clean(values[24]), "declaracao_data": _import_clean(values[25]),
            "nome_ministerio": _import_clean(values[26]),
            "nome_encarregado_orquestra": _import_clean(values[27]),
            "nome_voluntario": _import_clean(values[28]), "status": "ATIVO",
            "created_by_user_id": actor_id, "created_by_name": actor_name,
            "updated_by_user_id": actor_id, "updated_by_name": actor_name,
        })
    keys = [_import_key(row) for row in rows]
    if not rows:
        raise ValueError("A aba Cadastro não possui registros para importar.")
    if len(keys) != len(set(keys)):
        raise ValueError(f"A planilha possui {len(keys) - len(set(keys))} cadastro(s) repetido(s).")
    if unresolved:
        raise ValueError(f"Existem {len(unresolved)} cadastro(s) sem município regional confirmado.")
    return rows


def import_cadastros(request):
    if not can_access_module(request, MODULE_DARPE):
        return _denied()
    if request.method != "POST":
        return JsonResponse({"error": "Método não permitido."}, status=405)
    upload = request.FILES.get("arquivo")
    if not upload:
        return JsonResponse({"error": "Selecione a planilha oficial do D.A.R.P.E."}, status=400)
    try:
        rows = _read_imported_cadastros(upload)
        url = _url(RESOURCES["cadastros"])
        current_response = requests.get(url, headers=service_headers(),
                                        params={"select": "id,nome_completo,comum_congregacao"}, timeout=30)
        current_response.raise_for_status()
        current = current_response.json()
        existing = {}
        for row in current:
            existing.setdefault(_import_key(row), []).append(row)
        for start in range(0, len(rows), 50):
            new_rows = [row for row in rows[start:start + 50] if _import_key(row) not in existing]
            if new_rows:
                response = requests.post(url, headers=service_headers("return=minimal"),
                                         json=new_rows, timeout=60)
                response.raise_for_status()
        for row in rows:
            matches = existing.get(_import_key(row)) or []
            if matches:
                response = requests.patch(url, headers=service_headers("return=minimal"),
                                          params={"id": f"eq.{matches[0]['id']}"}, json=row, timeout=30)
                response.raise_for_status()
        refreshed = requests.get(url, headers=service_headers(),
                                 params={"select": "id,nome_completo,comum_congregacao"}, timeout=30)
        refreshed.raise_for_status()
        official = {_import_key(row) for row in rows}
        kept = set()
        for row in refreshed.json():
            row_key = _import_key(row)
            if row_key not in official or row_key in kept:
                response = requests.delete(url, headers=service_headers("return=minimal"),
                                           params={"id": f"eq.{row['id']}"}, timeout=30)
                response.raise_for_status()
            else:
                kept.add(row_key)
        return JsonResponse({"message": "Importação concluída.", "total": len(rows)})
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except requests.RequestException:
        return JsonResponse({"error": "Não foi possível concluir a importação no banco de dados."}, status=502)


def export_cadastros_excel(request):
    if not can_access_module(request, MODULE_DARPE):
        return _denied()
    config = RESOURCES["cadastros"]
    try:
        response = requests.get(_url(config), headers=service_headers(),
                                params={"select": "*", "order": config["order"]}, timeout=30)
        response.raise_for_status()
        rows = filter_rows(user_scope(request), [{**row, **config["location"](row)} for row in response.json()])
        rows = _with_canonical_commons(_regional_rows(rows))
    except requests.RequestException:
        return JsonResponse({"error": "Não foi possível consultar os cadastros para exportação."}, status=502)
    cities = {_norm(value) for value in request.GET.getlist("cidade") if str(value).strip()}
    commons = {str(value).strip().upper() for value in request.GET.getlist("comum") if str(value).strip()}
    search = str(request.GET.get("pesquisa") or "").strip().upper()
    rows = [row for row in rows if (not cities or _norm(row.get("cidade")) in cities)
            and (not commons or str(row.get("comum_congregacao") or "").upper() in commons)
            and (not search or search in json.dumps(row, ensure_ascii=False, default=str).upper())]
    profile = request.session.get("user_profile") or {}
    actor = profile.get("full_name") or profile.get("nome") or profile.get("email") or "Usuário do sistema"
    now = datetime.now()
    wb = Workbook(); ws = wb.active; ws.title = "CADASTROS"
    headers = ["Nome completo", "Comum", "Município", "Telefone", "Instrumento", "Funções", "Status"]
    last = get_column_letter(len(headers)); navy, pale = "1E4B7A", "EAF2F8"; thin = Side(style="thin", color="CCD5DD")
    for number, text, size, color, fill in ((1,"CONGREGAÇÃO CRISTÃ NO BRASIL",15,"FFFFFF",navy),(2,"Regional Itapevi - São Paulo",10,"FFFFFF",navy),(3,"D.A.R.P.E",12,navy,pale)):
        ws.merge_cells(f"A{number}:{last}{number}"); cell=ws.cell(number,1,text); cell.font=Font(size=size,bold=number!=2,color=color); cell.fill=PatternFill("solid",fgColor=fill); cell.alignment=Alignment(horizontal="center")
    city_scope = ", ".join(request.GET.getlist("cidade")) or "Todos os municípios"
    common_scope = ", ".join(request.GET.getlist("comum")) or "Todas as comuns"
    ws.merge_cells("A4:D4"); ws["A4"] = f"Cadastro regional · Municípios: {city_scope} · Comuns: {common_scope}"
    ws.merge_cells(f"E4:{last}4"); ws["E4"] = f"Emissão: {now:%d/%m/%Y %H:%M} · Responsável: {actor}"; ws["E4"].alignment=Alignment(horizontal="right")
    for cell in ws[4]: cell.font=Font(size=9,bold=True,color="536A7D")
    for column,label in enumerate(headers,1):
        cell=ws.cell(6,column,label); cell.font=Font(bold=True,color="FFFFFF"); cell.fill=PatternFill("solid",fgColor=navy); cell.alignment=Alignment(horizontal="center"); cell.border=Border(bottom=thin)
    role_fields=(("darpe_ministerio","Ministério"),("darpe_atendente","Atendente"),("darpe_colaborador","Colaborador"),("darpe_encarregado","Encarregado"),("darpe_musico_organista","Músico / Organista"),("darpe_grupo_canto","Grupo de Canto"))
    for index,row in enumerate(sorted(rows,key=lambda x:(str(x.get("cidade") or ""),str(x.get("comum_congregacao") or ""),str(x.get("nome_completo") or ""))),7):
        functions=", ".join(label for key,label in role_fields if row.get(key))
        values=[row.get("nome_completo"),row.get("comum_exibicao") or row.get("comum_congregacao"),row.get("cidade"),_phone("".join(filter(None,[str(row.get("ddd") or ""),str(row.get("telefone") or "")]))),row.get("instrumento_oficializado"),functions,row.get("status")]
        for column,value in enumerate(values,1):
            cell=ws.cell(index,column,value or "")
            cell.border=Border(bottom=thin)
            cell.alignment=Alignment(vertical="center",wrap_text=column in {1,2,6})
            if index%2==0:
                cell.fill=PatternFill("solid",fgColor="F4F6F8")
    for index,width in enumerate([34,42,22,20,24,38,14],1): ws.column_dimensions[get_column_letter(index)].width=width
    ws.freeze_panes="A7"; ws.auto_filter.ref=f"A6:{last}{max(6,ws.max_row)}"; ws.sheet_view.showGridLines=False; ws.page_setup.orientation="landscape"; ws.page_setup.fitToWidth=1; ws.page_setup.fitToHeight=0; ws.sheet_properties.pageSetUpPr.fitToPage=True; ws.print_title_rows="1:6"
    stream=io.BytesIO(); wb.save(stream); result=HttpResponse(stream.getvalue(),content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    result["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(f'Cadastro_DARPE_{now:%d-%m-%Y_%H-%M}.xlsx')}"
    return result


def page(request, section="dashboard"):
    if not can_access_module(request, MODULE_DARPE):
        return render(request, "pages/403.html", {"message": "Seu perfil não possui acesso à pasta D.A.R.P.E."}, status=403)
    if section not in {"dashboard", "cadastros", "eventos"}:
        section = "dashboard"
    return render(request, "pages/darpe.html", {"section": section, "scope": scope_details(user_scope(request))})


def api_resource(request, resource, record_id=None):
    if not can_access_module(request, MODULE_DARPE):
        return _denied()
    config = RESOURCES.get(resource)
    if not config:
        return JsonResponse({"error": "Recurso inválido."}, status=404)
    scope = user_scope(request)
    try:
        if request.method == "GET" and not record_id:
            response = requests.get(_url(config), headers=service_headers(),
                                    params={"select": "*", "order": config["order"]}, timeout=15)
            response.raise_for_status()
            rows = response.json()
            if resource != "participantes":
                rows = filter_rows(scope, [{**row, **config["location"](row)} for row in rows])
            if resource == "cadastros":
                rows = _with_canonical_commons(_regional_rows(rows))
            return JsonResponse({"items": rows, "scope": scope_details(scope)})

        current = None
        if record_id:
            response = requests.get(_url(config), headers=service_headers(),
                                    params={"select": "*", "id": f"eq.{record_id}", "limit": 1}, timeout=15)
            response.raise_for_status()
            rows = response.json()
            current = rows[0] if rows else None
            if not current:
                return JsonResponse({"error": "Registro não encontrado."}, status=404)
            if resource != "participantes" and not can_access(scope, config["location"](current)):
                return _denied()

        if request.method in {"POST", "PATCH"}:
            payload = {key: value for key, value in json.loads(request.body or "{}").items() if key in config["fields"]}
            if not payload:
                return JsonResponse({"error": "Informe os dados do registro."}, status=400)
            candidate = {**(current or {}), **payload}
            if resource == "cadastros" and candidate.get("darpe_musico") and candidate.get("darpe_organista"):
                return JsonResponse({"error": "Selecione Músico ou Organista, nunca as duas funções."}, status=400)
            if resource == "cadastros" and candidate.get("cidade"):
                canonical_city = _canonical_city(candidate["cidade"])
                if canonical_city:
                    payload["cidade"] = canonical_city
                    candidate["cidade"] = canonical_city
            if resource != "participantes" and not can_access(scope, config["location"](candidate)):
                return _denied()
            if resource == "cadastros" and not str(candidate.get("nome_completo") or "").strip():
                return JsonResponse({"error": "Informe o nome completo."}, status=400)
            actor = _actor(request)
            if not actor["id"]:
                return JsonResponse({"error": "A sessão não possui autoria válida."}, status=401)
            payload.update({"updated_by_user_id": actor["id"], "updated_by_name": actor["name"]})
            if not record_id:
                payload.update({"created_by_user_id": actor["id"], "created_by_name": actor["name"]})
            method = requests.patch if record_id else requests.post
            response = method(_url(config), headers=service_headers("return=representation"),
                              params={"id": f"eq.{record_id}"} if record_id else None, json=payload, timeout=15)
            response.raise_for_status()
            return JsonResponse({"item": response.json()[0]}, status=200 if record_id else 201)

        if request.method == "DELETE" and record_id:
            response = requests.delete(_url(config), headers=service_headers("return=minimal"),
                                       params={"id": f"eq.{record_id}"}, timeout=15)
            response.raise_for_status()
            return JsonResponse({}, status=204)
        return JsonResponse({"error": "Método não permitido."}, status=405)
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido."}, status=400)
    except requests.RequestException:
        return JsonResponse({"error": "Não foi possível acessar os dados do D.A.R.P.E."}, status=502)
