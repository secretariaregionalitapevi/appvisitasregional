"""Gestão individual de exames e testes da Música."""
import csv, hashlib, io, json, re, unicodedata, uuid
from difflib import SequenceMatcher
from datetime import datetime
import requests
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from .access_control import can_access, service_headers, user_scope
from .gem import _fetch_students, can_open_module

TABLE="musica_exames_individuais"; BUCKET="gem_exam_documents"
AGENDA_CSV="https://docs.google.com/spreadsheets/d/e/2PACX-1vSr59qtjfIiXj8PKems0FQzJulSdyUa70QhH8KaJSnNtbh9U0cB0KrRrxaKz93pc9CSLmTAn8btFc-0/pub?output=csv&gid=0&single=true"
RESULTS={"AGENDADO","APROVADO","RETORNOU AO CICLO","AUSENTE"}
LEGACY_FIELDS=("musicos_culto_oficial","musicos_oficializacao","musicos_troca_instrumento","organistas_rjm","organistas_culto_oficial","organistas_oficializacao","organistas_testes_especiais")
GROUPS=["ITAPEVI","JANDIRA","COTIA / CAUCAIA / VGP","SANTANA / PIRAPORA"]

def norm(value):
    text=unicodedata.normalize("NFKD",str(value or ""))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).upper().split())
def regional_group(city):
    value=norm(city)
    if "JANDIRA" in value:return GROUPS[1]
    if any(x in value for x in ("COTIA","CAUCAIA","VARGEM GRANDE","VGP")):return GROUPS[2]
    if any(x in value for x in ("SANTANA","PIRAPORA")):return GROUPS[3]
    return GROUPS[0]
def actor(request):
    p=request.session.get("user_profile") or {}
    return p.get("full_name") or p.get("name") or p.get("email") or "Usuário"
def rest_url():return f"{settings.SUPABASE_URL}/rest/v1/{TABLE}"
def denied():return JsonResponse({"error":"Seu perfil não possui acesso à pasta Música."},status=403)
def query_filters(request):
    return {key:request.GET.get(key,"").strip() for key in ("municipio","comum","mes","inicio","fim","lancamento_inicio","lancamento_fim")}
def matches_filters(row,filters,legacy=False):
    if filters["municipio"] and regional_group(row.get("municipio"))!=filters["municipio"]:return False
    if not legacy and filters["comum"] and norm(row.get("comum"))!=norm(filters["comum"]):return False
    exam=str(row.get("data_exame") or "")[:10];launched=str(row.get("created_at") or "")[:10]
    if filters["mes"] and exam[5:7]!=filters["mes"]:return False
    if filters["inicio"] and exam<filters["inicio"]:return False
    if filters["fim"] and exam>filters["fim"]:return False
    if filters["lancamento_inicio"] and launched<filters["lancamento_inicio"]:return False
    if filters["lancamento_fim"] and launched>filters["lancamento_fim"]:return False
    return True
AGENDA_NOTE = re.compile(r"^Agenda: (.*?) \| (\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}) (.*?) \| ID: ([a-f0-9]+)\s*$", re.MULTILINE)


def agenda_date_iso(value):
    return datetime.strptime(value, "%d/%m/%Y").date().isoformat() if "/" in value else value


def restore_agenda(row):
    row = dict(row)
    notes = row.get("observacoes") or ""
    matches = list(AGENDA_NOTE.finditer(notes))
    if matches:
        title, date, hour, event_id = matches[-1].groups()
        iso_date = agenda_date_iso(date)
        if not row.get("agenda_evento_id"):
            row.update(agenda_evento_id=event_id, agenda_evento_titulo=title, agenda_evento_data=iso_date, agenda_evento_hora=hour, agenda_evento_url="https://ccbagenda.vercel.app/")
        clean = AGENDA_NOTE.sub("", notes).strip()
        display_date = datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d/%m/%Y")
        row["observacoes"] = "\n".join(filter(None, [clean, f"Agenda: {title} | {display_date} {hour} | ID: {event_id}"]))
    return row


def fetch_rows(request,apply_filters=True):
    response=requests.get(rest_url(),headers=service_headers(),params={"select":"*","order":"data_exame.desc,created_at.desc"},timeout=25);response.raise_for_status()
    scope=user_scope(request);rows=[restore_agenda(row) for row in response.json() if can_access(scope,{"municipio":row.get("municipio"),"comum":row.get("comum")})]
    return [row for row in rows if matches_filters(row,query_filters(request))] if apply_filters else rows
def fetch_legacy(request):
    select="id,municipio,data_exame,created_at,lancado_por,"+",".join(LEGACY_FIELDS)
    response=requests.get(f"{settings.SUPABASE_URL}/rest/v1/musica_exames_lancamentos",headers=service_headers(),params={"select":select,"order":"data_exame.desc,created_at.desc"},timeout=25);response.raise_for_status()
    scope=user_scope(request);rows=[row for row in response.json() if can_access(scope,{"municipio":row.get("municipio"),"comum":""})]
    return [row for row in rows if matches_filters(row,query_filters(request),True)]
def legacy_summary(rows):
    groups={name:{"grupo":name,**{field:0 for field in LEGACY_FIELDS}} for name in GROUPS}
    for row in rows:
        item=groups[regional_group(row.get("municipio"))]
        for field in LEGACY_FIELDS:item[field]+=int(row.get(field) or 0)
    for item in groups.values():
        item["musicos_total"]=sum(item[x] for x in LEGACY_FIELDS[:3]);item["organistas_total"]=sum(item[x] for x in LEGACY_FIELDS[3:]);item["total"]=item["musicos_total"]+item["organistas_total"]
    totals={field:sum(item[field] for item in groups.values()) for field in LEGACY_FIELDS};totals["musicos_total"]=sum(totals[x] for x in LEGACY_FIELDS[:3]);totals["organistas_total"]=sum(totals[x] for x in LEGACY_FIELDS[3:]);totals["total"]=totals["musicos_total"]+totals["organistas_total"]
    return list(groups.values()),totals
def dashboard_summary(legacy, exams):
    individual_ids = {str(exam.get("id")) for exam in exams}
    rows = [row for row in legacy if str(row.get("id")) not in individual_ids]
    seen = set()
    for exam in exams:
        if exam.get("origem") not in {"PAINEL", "APP_EXAMES"} or norm(exam.get("resultado")) != "APROVADO":
            continue
        key = exam.get("chave_idempotencia") or exam.get("id")
        if key and key in seen:
            continue
        seen.add(key)
        organist = "ORGANISTA" in norm(exam.get("categoria")) or norm(exam.get("instrumento")) in {"ORGAO", "ORGANISTA"}
        kind = norm(exam.get("tipo_exame"))
        if kind in {"OFICIALIZACAO", "PRE-AVALIACAO DE OFICIALIZACAO"}:
            field = "organistas_oficializacao" if organist else "musicos_oficializacao"
        elif kind in {"CULTO OFICIAL", "EXAME DE CULTO OFICIAL"}:
            field = "organistas_culto_oficial" if organist else "musicos_culto_oficial"
        elif kind == "RJM" and organist:
            field = "organistas_rjm"
        elif kind == "TROCA DE INSTRUMENTO" and not organist:
            field = "musicos_troca_instrumento"
        elif kind in {"TESTE EMERGENCIAL", "TESTE ESPECIAL", "EMERGENCIA"} and organist:
            field = "organistas_testes_especiais"
        else:
            continue
        rows.append({"municipio": exam.get("municipio"), field: 1})
    return legacy_summary(rows)


def idempotency_key(payload):
    fields=("aluno_id","nome_aluno","data_exame","tipo_exame","instrumento")
    return hashlib.sha256("|".join(norm(payload.get(x)) for x in fields).encode()).hexdigest()
def visible_students(request):
    scope=user_scope(request)
    return [s for s in _fetch_students() if can_access(scope,{"municipio":s.get("municipio"),"comum":s.get("comum_congregacao")})]

def match_student(students,name):
    wanted=norm(name).replace("�","")
    exact=next((s for s in students if norm(s.get("nome_aluno"))==norm(name)),None)
    if exact:return exact
    ranked=sorted(((SequenceMatcher(None,wanted,norm(s.get("nome_aluno"))).ratio(),s) for s in students),key=lambda item:item[0],reverse=True)
    return ranked[0][1] if ranked and ranked[0][0]>=.94 and (len(ranked)==1 or ranked[0][0]-ranked[1][0]>=.03) else None

def is_exam_agenda_event(title):
    normalized = norm(title)
    return bool(
        re.match(r"^(?:PRE[\s-]*)?AVALIAC(?:AO|OES)\b|^EXAMES?\b", normalized)
        and re.search(r"\b(?:MUSICOS?|ORGANISTAS?)\b", normalized)
    )

def event_matches_municipality(event, municipality):
    city = norm(municipality)
    if not city:
        return False
    title = norm(event.get("titulo"))
    if any(token in city for token in ("COTIA", "CAUCAIA", "VARGEM GRANDE", "VGP")):
        return "COTIA" in title
    if any(token in city for token in ("SANTANA", "PIRAPORA", "FAZENDINHA")):
        return "SANTANA" in title or "FAZENDINHA" in title
    if "ITAPEVI" in city:
        return "ITAPEVI" in title
    if "JANDIRA" in city:
        return "JANDIRA" in title
    return False


def agenda_events():
    cached=cache.get("musica_exam_agenda_events_v2")
    if cached is not None:return cached
    response=requests.get(AGENDA_CSV,timeout=12);response.raise_for_status();events=[]
    for row in csv.DictReader(io.StringIO(response.text.lstrip("\ufeff"))):
        values={norm(k):v for k,v in row.items()}
        if norm(values.get("DEPARTAMENTO"))!="MUSICA":continue
        try:exam_date=datetime.strptime((values.get("DATA") or "").strip(),"%d/%m/%Y").date().isoformat()
        except ValueError:continue
        title=(values.get("EVENTO") or "").strip();hour=(values.get("HORA") or "").strip()
        if not is_exam_agenda_event(title):continue
        event_id=hashlib.sha256(f"{exam_date}|{hour}|{norm(title)}".encode()).hexdigest()[:24]
        events.append({"id":event_id,"data":exam_date,"hora":hour,"titulo":title,"url":"https://ccbagenda.vercel.app/"})
    events.sort(key=lambda x:(x["data"],x["hora"]),reverse=True);cache.set("musica_exam_agenda_events_v2",events,600);return events

def api_agenda(request):
    if not can_open_module(request):return denied()
    try:
        student_id = request.GET.get("aluno_id")
        student = next((row for row in visible_students(request) if str(row.get("id")) == student_id), None) if student_id else None
        events = [event for event in agenda_events() if student and event_matches_municipality(event, student.get("municipio"))]
        return JsonResponse({"items": events})
    except requests.RequestException:return JsonResponse({"error":"A agenda não respondeu. Tente novamente."},status=502)
def page(request):
    if not can_open_module(request):return render(request,"pages/403.html",{"message":"Seu perfil não possui acesso à pasta Música."},status=403)
    return render(request,"pages/music_exams.html",{"report_user":actor(request)})
def api_dashboard(request):
    if not can_open_module(request):return denied()
    try:
        all_items = fetch_rows(request, apply_filters=False)
        items = [row for row in all_items if matches_filters(row, query_filters(request))]
        individual_ids = {str(row["id"]) for row in all_items}
        legacy = [row for row in fetch_legacy(request) if str(row.get("id")) not in individual_ids]
        groups,totals=dashboard_summary(legacy,items)
        students=[{"id":s.get("id"),"nome":s.get("nome_aluno"),"registro_msa":s.get("registro_msa"),"municipio":s.get("municipio"),"comum":s.get("comum_congregacao"),"instrumento":s.get("instrumento"),"categoria":s.get("cargo_ministerio")} for s in visible_students(request)]
        launches=[{**row,"grupo":regional_group(row.get("municipio")),"total":sum(int(row.get(f) or 0) for f in LEGACY_FIELDS)} for row in legacy]
        return JsonResponse({"items":items,"groups":groups,"totals":totals,"students":students,"legacy_launches":launches,"filters":query_filters(request)})
    except requests.RequestException:return JsonResponse({"error":"Não foi possível consultar os exames. Verifique a migração 022."},status=502)
def approved_stage(exam):
    if norm(exam.get("resultado")) != "APROVADO":
        return None
    return {"OFICIALIZACAO": (4, "oficializacao", "OFICIALIZADO(A)"),
            "CULTO OFICIAL": (3, "ingresso_culto", "CULTO OFICIAL"),
            "EXAME DE CULTO OFICIAL": (3, "ingresso_culto", "CULTO OFICIAL"),
            "RJM": (2, "ingresso_rjm", "RJM")}.get(norm(exam.get("tipo_exame")))


def save_exam(payload, record_id=None):
    # Installations predating the agenda columns still retain the event in notes.
    def write(values):
        if record_id:
            return requests.patch(rest_url(), headers=service_headers("return=representation"), params={"id": f"eq.{record_id}"}, json=values, timeout=25)
        return requests.post(rest_url()+"?on_conflict=chave_idempotencia", headers=service_headers("resolution=merge-duplicates,return=representation"), json=values, timeout=25)
    response = write(payload)
    if response.status_code == 400:
        try:
            missing = response.json()
        except ValueError:
            missing = {}
        if missing.get("code") in {"42703", "PGRST204"} and "agenda_evento_" in str(missing):
            compatible = {k: v for k, v in payload.items() if not k.startswith("agenda_evento_")}
            clean_notes = AGENDA_NOTE.sub("", payload.get("observacoes") or "").strip()
            event_date = datetime.strptime(payload["agenda_evento_data"], "%Y-%m-%d").strftime("%d/%m/%Y")
            compatible["observacoes"] = "\n".join(filter(None, [clean_notes, f"Agenda: {payload.get('agenda_evento_titulo')} | {event_date} {payload.get('agenda_evento_hora') or ''} | ID: {payload.get('agenda_evento_id')}"]))
            response = write(compatible)
    response.raise_for_status()
    return (response.json() or [payload])[0]


def sync_shared_exam(exam, deleting=False):
    """One aggregate row per individual exam, shared with APP_EXAMES."""
    url = f"{settings.SUPABASE_URL}/rest/v1/musica_exames_lancamentos"
    if deleting:
        response = requests.delete(url, headers=service_headers("return=minimal"), params={"id": f"eq.{exam['id']}"}, timeout=15)
    else:
        groups, totals = dashboard_summary([], [dict(exam, origem="PAINEL")])
        payload = {"id": exam["id"], "data_exame": exam["data_exame"], "municipio": exam.get("municipio"), "lancado_por": exam.get("lancado_por") or "Painel de Exames", "total_exames": totals["total"]}
        payload.update({field: totals[field] for field in LEGACY_FIELDS})
        response = requests.post(url, params={"on_conflict": "id"}, headers=service_headers("resolution=merge-duplicates,return=minimal"), json=payload, timeout=15)
    response.raise_for_status()


def update_student_stage(student, exam):
    from .gem import _milestones
    stage = approved_stage(exam)
    if not stage or _milestones(student.get("nivel"))[stage[0]]["status"] != "future":
        return
    level = stage[2]
    if "RJM" in norm(student.get("nivel")) and stage[0] > 2:
        level = "RJM / " + level
    response = requests.patch(f"{settings.SUPABASE_URL}/rest/v1/musica_acompanhamento_aluno", headers=service_headers("return=minimal"), params={"id": f"eq.{student['id']}"}, json={"nivel": level}, timeout=15)
    response.raise_for_status()
    cache.delete("gem:students:v7")


def api_record(request,record_id=None):
    if not can_open_module(request):return denied()
    if request.method not in ({"GET", "POST", "DELETE"} if record_id else {"POST"}):return JsonResponse({"error":"Método não permitido."},status=405)
    try:
        existing = None
        if record_id:
            response = requests.get(rest_url(), headers=service_headers(), params={"select": "*", "id": f"eq.{record_id}", "limit": 1}, timeout=15)
            response.raise_for_status()
            rows = response.json()
            if not rows or not can_access(user_scope(request), {"municipio": rows[0].get("municipio"), "comum": rows[0].get("comum")}):
                return JsonResponse({"error": "Exame nao encontrado neste escopo."}, status=404)
            existing = restore_agenda(rows[0])
            if request.method == "GET":
                return JsonResponse({"item": existing})
            if request.method == "DELETE":
                sync_shared_exam(existing, deleting=True)
                deleted = requests.delete(rest_url(), headers=service_headers("return=minimal"), params={"id": f"eq.{record_id}"}, timeout=15)
                try:
                    deleted.raise_for_status()
                except requests.RequestException:
                    sync_shared_exam(existing)
                    raise
                return JsonResponse({"ok": True})
        data=request.POST.dict() if (request.content_type or "").startswith("multipart/") else json.loads(request.body or "{}")
        student=next((s for s in visible_students(request) if str(s.get("id"))==str(data.get("aluno_id"))),None)
        if not student:return JsonResponse({"error":"Selecione um aluno válido dentro do seu escopo."},status=400)
        organist = "ORGANISTA" in norm(student.get("cargo_ministerio")) or norm(student.get("instrumento")) in {"ORGAO", "ORGANISTA"}
        if not organist and norm(data.get("tipo_exame")) in {"RJM", "TESTE EMERGENCIAL", "TESTE ESPECIAL", "EMERGENCIA"}:
            return JsonResponse({"error": "RJM e Emergencia sao modalidades exclusivas para organistas."}, status=400)
        event_id = str(data.get("agenda_evento_id") or "").strip()
        same_student = existing and str(existing.get("aluno_id")) == str(student["id"])
        if not event_id and same_student:
            event_id = existing.get("agenda_evento_id") or ""
        event=next((item for item in agenda_events() if item["id"]==event_id),None)
        preserving_event = same_student and event_id == existing.get("agenda_evento_id")
        if event and not preserving_event and not event_matches_municipality(event, student.get("municipio")):
            return JsonResponse({"error": "Selecione um evento do polo de exames do aluno."}, status=400)
        if not event and preserving_event and existing.get("agenda_evento_id"):
            event = {"id": existing["agenda_evento_id"], "data": existing.get("agenda_evento_data") or existing["data_exame"], "titulo": existing.get("agenda_evento_titulo"), "hora": existing.get("agenda_evento_hora") or "", "url": existing.get("agenda_evento_url") or "https://ccbagenda.vercel.app/"}
        if not event and same_student and not event_id and existing.get("data_exame"):
            event = {"id": None, "data": existing["data_exame"], "titulo": existing.get("agenda_evento_titulo") or "Registro historico", "hora": "", "url": "https://ccbagenda.vercel.app/"}
        if not event:return JsonResponse({"error":"Selecione o evento correspondente na agenda da Música."},status=400)
        result=norm(data.get("resultado") or "AGENDADO").replace("REPROVADO","RETORNOU AO CICLO")
        if result not in RESULTS:return JsonResponse({"error":"Resultado inválido."},status=400)
        payload={"aluno_id":student["id"],"nome_aluno":student.get("nome_aluno"),"registro_msa":student.get("registro_msa"),"municipio":student.get("municipio"),"comum":student.get("comum_congregacao"),"instrumento":student.get("instrumento"),"categoria":student.get("cargo_ministerio"),"data_exame":event["data"],"tipo_exame":norm(data.get("tipo_exame")),"resultado":result,"encarregado_local":data.get("encarregado_local") or None,"observacoes":data.get("observacoes") or None,"lancado_por":actor(request),"origem":"PAINEL","agenda_evento_id":event["id"],"agenda_evento_titulo":event["titulo"],"agenda_evento_data":event["data"],"agenda_evento_hora":event["hora"] or None,"agenda_evento_url":event["url"]}
        if not payload["data_exame"] or not payload["tipo_exame"]:return JsonResponse({"error":"Informe a data e o tipo do exame."},status=400)
        payload["chave_idempotencia"]=idempotency_key(payload);proof=request.FILES.get("prova")
        if proof:
            if proof.size>12*1024*1024:return JsonResponse({"error":"A prova deve ter no máximo 12 MB."},status=400)
            ext=re.sub(r"[^a-z0-9]","",proof.name.rsplit(".",1)[-1].lower())[:8] or "pdf";path=f"{student['id']}/{uuid.uuid4()}.{ext}"
            upload=requests.post(f"{settings.SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}",headers={"apikey":settings.SUPABASE_SERVICE_ROLE_KEY,"Authorization":f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}","Content-Type":proof.content_type or "application/octet-stream"},data=proof.read(),timeout=40);upload.raise_for_status();payload.update({"prova_url":path,"prova_nome":proof.name})
        if existing and not proof:
            payload.update(prova_url=existing.get("prova_url"), prova_nome=existing.get("prova_nome"))
        item = save_exam(payload, record_id) if record_id else save_exam(payload)
        warning = None
        try:
            sync_shared_exam(item)
        except requests.RequestException:
            warning = "Exame salvo, mas a sincronizacao com APP_EXAMES falhou. Salve novamente para repetir a sincronizacao."
        try:
            update_student_stage(student, item)
        except requests.RequestException:
            warning = "Exame salvo. Nao foi possivel atualizar o nivel do aluno; salve novamente para repetir a sincronizacao."
        return JsonResponse({"ok": True, "item": item, "warning": warning})
    except (ValueError,requests.RequestException) as error:return JsonResponse({"error":f"Não foi possível salvar o exame: {error}"},status=502)

def parse_reference_workbook(file,request):
    sheet=load_workbook(file,data_only=True).worksheets[0];students=visible_students(request);current_type="";current_date=None;parsed=[];unmatched=[]
    for values in sheet.iter_rows(values_only=True):
        cells=[str(v).strip() if v is not None else "" for v in values];joined=" ".join(cells[:6]);normalized=norm(joined);match=re.search(r"(\d{2}/\d{2}/\d{4})",joined)
        if match:current_date=datetime.strptime(match.group(1),"%d/%m/%Y").date().isoformat()
        if "PRE" in normalized and ("OFICIAL" in normalized or "AVALIA" in normalized):current_type="PRÉ-AVALIAÇÃO DE OFICIALIZAÇÃO"
        elif "CULTO OFICIAL" in normalized:current_type="EXAME DE CULTO OFICIAL"
        elif "TROCA DE INSTRUMENT" in normalized:current_type="TROCA DE INSTRUMENTO"
        if len(cells)<6 or not re.fullmatch(r"\d+(?:\.0)?",cells[0]) or not cells[1]:continue
        name,instrument,common,leader,result=cells[1:6];student=match_student(students,name)
        if not student:unmatched.append({"nome":name,"comum":common,"linha":cells[0]});continue
        payload={"aluno_id":student["id"],"nome_aluno":student.get("nome_aluno"),"registro_msa":student.get("registro_msa"),"municipio":student.get("municipio"),"comum":student.get("comum_congregacao") or common,"instrumento":instrument or student.get("instrumento"),"categoria":student.get("cargo_ministerio"),"data_exame":current_date,"tipo_exame":current_type or "APTIDÃO PERIÓDICA","resultado":norm(result) if norm(result) in RESULTS else "AGENDADO","encarregado_local":leader or None,"lancado_por":actor(request),"origem":"IMPORTACAO"}
        payload["chave_idempotencia"]=idempotency_key(payload);parsed.append(payload)
    return parsed,unmatched
def api_import(request):
    if not can_open_module(request):return denied()
    if request.method!="POST" or not request.FILES.get("arquivo"):return JsonResponse({"error":"Envie uma planilha Excel."},status=400)
    try:
        parsed,unmatched=parse_reference_workbook(request.FILES["arquivo"],request);existing={row.get("chave_idempotencia") for row in fetch_rows(request,False)};batch=[row for row in parsed if row["chave_idempotencia"] not in existing];duplicates=len(parsed)-len(batch)
        if batch:
            response=requests.post(rest_url()+"?on_conflict=chave_idempotencia",headers=service_headers("resolution=ignore-duplicates,return=minimal"),json=batch,timeout=40);response.raise_for_status()
        return JsonResponse({"ok":True,"importados":len(batch),"duplicados":duplicates,"nao_encontrados":unmatched})
    except Exception as error:return JsonResponse({"error":f"Não foi possível importar: {error}"},status=400)
def api_participants(request):
    if not can_open_module(request):return denied()
    try:return JsonResponse({"items":[row for row in fetch_rows(request) if norm(row.get("resultado"))=="AGENDADO"]})
    except requests.RequestException:return JsonResponse({"error":"Não foi possível carregar participantes."},status=502)
def document(request,record_id):
    if not can_open_module(request):return denied()
    try:
        response=requests.get(rest_url(),headers=service_headers(),params={"select":"prova_url,prova_nome,municipio,comum","id":f"eq.{record_id}","limit":1},timeout=15);response.raise_for_status();items=response.json()
        if not items or not items[0].get("prova_url") or not can_access(user_scope(request),items[0]):return JsonResponse({"error":"Documento não encontrado."},status=404)
        item=items[0];download=requests.get(f"{settings.SUPABASE_URL}/storage/v1/object/authenticated/{BUCKET}/{item['prova_url']}",headers={"apikey":settings.SUPABASE_SERVICE_ROLE_KEY,"Authorization":f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}"},timeout=30);download.raise_for_status();result=HttpResponse(download.content,content_type=download.headers.get("Content-Type","application/octet-stream"));result["Content-Disposition"]=f'inline; filename="{item.get("prova_nome") or "prova"}"';return result
    except requests.RequestException:return JsonResponse({"error":"Não foi possível abrir o documento."},status=502)
def export_excel(request):
    if not can_open_module(request):return denied()
    groups,totals=legacy_summary(fetch_legacy(request));items=fetch_rows(request);wb=Workbook();ws=wb.active;ws.title="Resumo Regional"
    def title(sheet,last_col,report):
        sheet.merge_cells(start_row=1,start_column=1,end_row=1,end_column=last_col);sheet["A1"]="CONGREGAÇÃO CRISTÃ NO BRASIL";sheet["A1"].font=Font(bold=True,color="FFFFFF",size=15);sheet["A1"].fill=PatternFill("solid",fgColor="1E4B7A");sheet["A1"].alignment=Alignment(horizontal="center")
        for row,text in ((2,"Regional Itapevi - São Paulo · MÚSICA"),(3,report),(4,f"Emissão: {datetime.now():%d/%m/%Y %H:%M} · Responsável: {actor(request)}")):sheet.merge_cells(start_row=row,start_column=1,end_row=row,end_column=last_col);sheet.cell(row,1,text)
    title(ws,9,"Relatório consolidado de Exames e Testes")
    headers=["REGIÃO","Músicos · Culto Oficial","Músicos · Oficialização","Músicos · Troca Instrumento","Organistas · RJM","Organistas · Culto Oficial","Organistas · Oficialização","Organistas · Teste Especial","TOTAL GERAL"]
    for column,value in enumerate(headers,1):cell=ws.cell(6,column,value);cell.font=Font(bold=True,color="FFFFFF");cell.fill=PatternFill("solid",fgColor="1E4B7A");cell.alignment=Alignment(horizontal="center",wrap_text=True)
    fields=list(LEGACY_FIELDS)
    for index,item in enumerate(groups,1):
        for column,value in enumerate([item["grupo"]]+[item[x] for x in fields]+[item["total"]],1):ws.cell(6+index,column,value)
    for column,value in enumerate(["TOTAIS GERAIS"]+[totals[x] for x in fields]+[totals["total"]],1):cell=ws.cell(11,column,value);cell.font=Font(bold=True);cell.fill=PatternFill("solid",fgColor="EAF2F8")
    for index,width in enumerate([26,18,18,22,16,19,19,19,14],1):ws.column_dimensions[chr(64+index)].width=width
    ws.freeze_panes="A7";ws.auto_filter.ref="A6:I10";ws.sheet_view.showGridLines=False;ws.page_setup.orientation="landscape";ws.page_setup.fitToWidth=1
    detail=wb.create_sheet("Registros Individuais");title(detail,10,"Histórico individual de Exames e Testes");detail_headers=["Nº","Aluno(a)","Registro MSA","Município","Comum","Instrumento","Tipo","Data","Resultado","Prova"]
    for column,value in enumerate(detail_headers,1):cell=detail.cell(6,column,value);cell.font=Font(bold=True,color="FFFFFF");cell.fill=PatternFill("solid",fgColor="1E4B7A");cell.alignment=Alignment(horizontal="center")
    for index,item in enumerate(items,1):
        exam_date=datetime.strptime(item["data_exame"],"%Y-%m-%d").strftime("%d/%m/%Y") if item.get("data_exame") else "—"
        for column,value in enumerate([index,item.get("nome_aluno"),item.get("registro_msa"),item.get("municipio"),item.get("comum"),item.get("instrumento"),item.get("tipo_exame"),exam_date,item.get("resultado"),"Sim" if item.get("prova_url") else "Não"],1):detail.cell(6+index,column,value)
    for index,width in enumerate([6,30,14,18,34,20,28,13,20,12],1):detail.column_dimensions[chr(64+index)].width=width
    detail.freeze_panes="A7";detail.auto_filter.ref=f"A6:J{6+len(items)}";detail.sheet_view.showGridLines=False;detail.page_setup.orientation="landscape";detail.page_setup.fitToWidth=1
    stream=io.BytesIO();wb.save(stream);stamp=datetime.now().strftime("%d-%m-%Y_%H-%M");response=HttpResponse(stream.getvalue(),content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");response["Content-Disposition"]=f'attachment; filename="Exames_GEM_{stamp}.xlsx"';return response