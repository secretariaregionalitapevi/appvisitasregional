"""Painel territorial de cartas, assistência ministerial e confirmação de exames."""
import hashlib
import io
import json
import uuid
from urllib.parse import quote
import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from openpyxl import load_workbook
from . import music_exams
from .access_control import can_access, service_headers, user_scope, scope_details
from .gem import can_open_module
from .music_letters_domain import MODALITIES, RESULTS, ROLES, GROUPS, matches, summarize, exam_payload, ministry_workbook, norm

TABLE = 'cartas_emissoes'

def can_review(request):
    profile = request.session.get('user_profile') or {}
    cargo = norm(' '.join(str(profile.get(k) or '') for k in ('cargo', 'cargo_ministerio', 'role', 'ministerio')))
    return can_open_module(request) and (user_scope(request)['level'] in {'regional', 'global'} or 'SECRETAR' in cargo)

def read(table, params=None):
    rows = []
    while True:
        response = requests.get(settings.SUPABASE_URL + '/rest/v1/' + table, headers=service_headers(),
            params={'select': '*', 'order': 'id.asc' if table == TABLE else 'common_code.asc',
                    **(params or {}), 'limit': 500, 'offset': len(rows)}, timeout=25)
        response.raise_for_status()
        batch = response.json()
        rows.extend(batch)
        if len(batch) < 500:
            return rows

def filters(request):
    return {key: request.GET.get(key, '').strip()[:160] for key in ('municipio', 'comum', 'ano', 'tipo', 'modalidade', 'resultado', 'evento', 'mes', 'inicio', 'fim', 'busca')}

def visible(request):
    scope = user_scope(request)
    return [row for row in read(TABLE, {'status': 'eq.ready'}) if can_access(scope, {'municipio': row['municipio'], 'comum': row['comum']})]

def find(request, identifier):
    rows = read(TABLE, {'id': 'eq.' + str(identifier)})
    return next((r for r in rows if can_access(user_scope(request), {'municipio': r['municipio'], 'comum': r['comum']})), None)

def unavailable():
    return JsonResponse({'error': 'Não foi possível consultar as cartas. Verifique a conexão e a migração 039.'}, status=503)

@require_GET
def page(request):
    if not can_open_module(request):
        return render(request, 'pages/403.html', {'message': 'Seu perfil não possui acesso à pasta Música.'}, status=403)
    return render(request, 'pages/music_letters.html', {'report_user': music_exams.actor(request), 'can_review': can_review(request),
                  'can_import': user_scope(request)['level'] in {'regional', 'global'}, 'scope': scope_details(user_scope(request))})

@require_GET
def dashboard(request):
    if not can_open_module(request):
        return music_exams.denied()
    try:
        all_rows = visible(request)
        selected = [r for r in all_rows if matches(r, filters(request))]
        groups, totals = summarize(selected)
        events = {r['event_id']: {'id': r['event_id'], **r['event_snapshot']} for r in all_rows}
        items = [{**{k: r.get(k) for k in ('id', 'nome', 'comum', 'municipio', 'tipo', 'modalidade', 'created_at',
                    'review_result', 'review_version', 'reviewed_name', 'reviewed_at', 'review_notes', 'event_id')},
                  'evento': r['event_snapshot'], 'instrumento': (r.get('payload') or {}).get('instrumento'),
                  'tonalidade': (r.get('payload') or {}).get('tonalidade')} for r in selected]
        ministries = [r for r in read('cartas_ministerio_comuns') if can_access(user_scope(request), {'municipio': r['municipio'], 'comum': r['comum']})]
        return JsonResponse({'items': items, 'groups': groups, 'totals': totals, 'municipalities': GROUPS,
                             'events': sorted(events.values(), key=lambda e: (e.get('data', ''), e.get('evento', ''))),
                             'years': sorted({str(r['event_snapshot'].get('data', ''))[:4] for r in all_rows if r['event_snapshot'].get('data')}, reverse=True),
                             'commons': sorted({r['comum'] for r in all_rows}),
                             'modalities': MODALITIES, 'results': RESULTS, 'can_review': can_review(request),
                             'ministry': [{**r, 'missing': [ROLES[k] for k in ROLES if not r.get(k)]} for r in ministries]})
    except requests.RequestException:
        return unavailable()

@require_POST
def confirm(request, letter_id):
    if not can_review(request):
        return JsonResponse({'error': 'A confirmação exige perfil de secretário da música ou gestão regional.'}, status=403)
    try:
        letter = find(request, letter_id)
        if not letter:
            return JsonResponse({'error': 'Carta não encontrada no seu escopo.'}, status=404)
        data = json.loads(request.body or '{}')
        result = data.get('resultado')
        if result not in RESULTS:
            raise ValueError('Selecione um resultado válido.')
        profile = request.session.get('user_profile') or {}
        identity = str(uuid.UUID(str(request.session.get('user_id') or profile.get('user_id') or '')))
        exam = exam_payload(letter, music_exams.actor(request))
        exam['resultado'] = 'AGENDADO' if result == 'PENDENTE' else result
        exam['chave_idempotencia'] = music_exams.idempotency_key(exam)
        _, totals = music_exams.dashboard_summary([], [exam])
        response = requests.post(settings.SUPABASE_URL + '/rest/v1/rpc/cartas_confirmar_resultado', headers=service_headers(),
            json={'p_carta': str(letter_id), 'p_resultado': result, 'p_actor': identity, 'p_nome': music_exams.actor(request),
                  'p_version': int(data.get('version', 0)), 'p_notes': str(data.get('observacoes') or '').strip()[:2000],
                  'p_exame': exam, 'p_totais': totals}, timeout=35)
        if response.status_code == 400:
            error = response.json()
            return JsonResponse({'error': error.get('message', 'Atualize o painel e tente novamente.')}, status=409)
        response.raise_for_status()
        return JsonResponse({'ok': True, 'item': response.json()})
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Confira o candidato, o resultado e a identificação do usuário.'}, status=400)
    except requests.RequestException:
        return JsonResponse({'error': 'Não foi possível confirmar. Carta, exame e totais não foram alterados parcialmente.'}, status=503)

@require_POST
def import_ministry(request):
    if not can_open_module(request) or user_scope(request)['level'] not in {'global', 'regional'}:
        return music_exams.denied()
    file = request.FILES.get('arquivo')
    if not file or file.size > 5 * 1024 * 1024 or not file.name.lower().endswith('.xlsx'):
        return JsonResponse({'error': 'Envie uma planilha .xlsx com até 5 MB.'}, status=400)
    try:
        content = file.read()
        workbook = load_workbook(io.BytesIO(content), data_only=True)
        if workbook.worksheets[0].max_row > 5000:
            raise ValueError('A planilha excede 5.000 linhas.')
        rows = ministry_workbook(workbook, hashlib.sha256(content).hexdigest())
        if not rows:
            raise ValueError('Nenhuma comum válida encontrada na relação.')
        response = requests.post(settings.SUPABASE_URL + '/rest/v1/cartas_ministerio_comuns', headers=service_headers('resolution=merge-duplicates,return=minimal'),
                                 params={'on_conflict': 'common_code'}, json=rows, timeout=40)
        response.raise_for_status()
        return JsonResponse({'ok': True, 'importados': len(rows), 'incompletos': sum(any(not r[k] for k in ROLES) for r in rows)})
    except requests.RequestException:
        return unavailable()
    except Exception:
        return JsonResponse({'error': 'Não foi possível ler a relação. Confira as colunas e as comuns duplicadas.'}, status=400)

@require_GET
def document(request, letter_id):
    if not can_open_module(request):
        return music_exams.denied()
    try:
        letter = find(request, letter_id)
        if not letter or letter.get('status') != 'ready' or not letter.get('pdf_path'):
            return JsonResponse({'error': 'PDF não disponível no seu escopo.'}, status=404)
        path = quote(letter['pdf_path'], safe='/')
        response = requests.get(settings.SUPABASE_URL + '/storage/v1/object/authenticated/cartas-musicais/' + path, headers=service_headers(), timeout=30)
        response.raise_for_status()
        result = HttpResponse(response.content, content_type='application/pdf')
        result['Content-Disposition'] = 'inline; filename="Carta_Exame.pdf"'
        return result
    except requests.RequestException:
        return unavailable()

@require_GET
def export(request, file_format):
    if not can_open_module(request):
        return music_exams.denied()
    if file_format not in {'pdf', 'excel'}:
        return JsonResponse({'error': 'Formato inválido.'}, status=400)
    try:
        from .music_letters_exports import make_pdf, make_excel
        selected = [r for r in visible(request) if matches(r, filters(request))]
        content = make_pdf(selected, music_exams.actor(request), filters(request)) if file_format == 'pdf' else make_excel(selected, music_exams.actor(request), filters(request))
        extension, mime = ('pdf', 'application/pdf') if file_format == 'pdf' else ('xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        result = HttpResponse(content, content_type=mime)
        from django.utils import timezone
        stamp = timezone.localtime().strftime('%d_%m_%Y_%H_%M')
        result['Content-Disposition'] = f'attachment; filename="Cartas_Exames_{stamp}.{extension}"'
        return result
    except requests.RequestException:
        return unavailable()
