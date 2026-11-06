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
from .access_control import can_access, common_catalog, service_headers, user_scope, scope_details
from .gem import can_open_module
from .music_letters_domain import MODALITIES, RESULTS, ROLES, GROUPS, matches, summarize, exam_payload, ministry_workbook, norm, letter_filename, canonical_ministries

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
    from .music_letters_activity import annotate_activity
    return annotate_activity([row for row in read(TABLE, {'status': 'eq.ready', 'deleted_at': 'is.null'}) if can_access(scope, {'municipio': row['municipio'], 'comum': row['comum']})])

def find(request, identifier):
    rows = read(TABLE, {'id': 'eq.' + str(identifier), 'deleted_at': 'is.null'})
    return next((r for r in rows if can_access(user_scope(request), {'municipio': r['municipio'], 'comum': r['comum']})), None)

def unavailable():
    return JsonResponse({'error': 'Não foi possível consultar as cartas. Verifique a conexão e a migração 039.'}, status=503)

@require_GET
def page(request):
    if not can_open_module(request):
        return render(request, 'pages/403.html', {'message': 'Seu perfil não possui acesso à pasta Música.'}, status=403)
    return render(request, 'pages/music_letters.html', {'report_user': music_exams.actor(request), 'can_review': can_review(request),
                  'can_import': user_scope(request)['level'] in {'regional', 'global'}, 'scope': scope_details(user_scope(request))})

def ministry_municipalities(request):
    from .musicalizacao import REGIONAL_MUNICIPALITIES
    from .music_events_identity import normalized_city
    scope = user_scope(request)
    if scope['level'] in {'global', 'regional'}:
        return REGIONAL_MUNICIPALITIES
    return sorted({normalized_city(r['cidade']) for r in common_catalog() if can_access(scope, r)})


@require_GET
def notifications(request):
    """Internal bell notifications, restricted to the user's music territory."""
    if not can_open_module(request):
        return music_exams.denied()
    try:
        pending = [r for r in visible(request) if (r.get('activity_review') or {}).get('status') == 'pending']
        return JsonResponse({'pending_count': len(pending)})
    except requests.RequestException:
        return unavailable()


@require_GET
def dashboard(request):
    if not can_open_module(request):
        return music_exams.denied()
    try:
        all_rows = canonical_ministries(visible(request), common_catalog())
        selected = [r for r in all_rows if matches(r, filters(request))]
        from .music_letters_program import assess_letters
        selected = assess_letters(selected)
        groups, totals = summarize(selected)
        events = {r['event_id']: {'id': r['event_id'], **r['event_snapshot']} for r in all_rows}
        items = [{**{k: r.get(k) for k in ('id', 'nome', 'comum', 'municipio', 'tipo', 'modalidade', 'created_at',
                    'review_result', 'review_version', 'reviewed_name', 'reviewed_at', 'review_notes', 'event_id')},
                  'evento': r['event_snapshot'], 'instrumento': (r.get('payload') or {}).get('instrumento'),
                  'tonalidade': (r.get('payload') or {}).get('tonalidade'),
                  'program_assessment': r.get('program_assessment'),
                  'student_activity': r.get('student_activity'), 'activity_review': r.get('activity_review'),
                  'program_student_id': (r.get('payload') or {}).get('pessoa_id')} for r in selected]
        ministries = [r for r in canonical_ministries(read('cartas_ministerio_comuns', {'deleted_at': 'is.null'}), common_catalog()) if can_access(user_scope(request), {'municipio': r['municipio'], 'comum': r['comum']})]
        return JsonResponse({'items': items, 'groups': groups, 'totals': totals, 'municipalities': GROUPS,
                             'events': sorted(events.values(), key=lambda e: (e.get('data', ''), e.get('evento', ''))),
                             'years': sorted({str(r['event_snapshot'].get('data', ''))[:4] for r in all_rows if r['event_snapshot'].get('data')}, reverse=True),
                             'commons': sorted({r['comum'] for r in all_rows}),
                             'modalities': MODALITIES, 'results': RESULTS, 'can_review': can_review(request),
                             'can_manage_ministry': user_scope(request)['level'] in {'global', 'regional'},
                             'list_municipalities': ministry_municipalities(request),
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
        rows = canonical_ministries(ministry_workbook(workbook, hashlib.sha256(content).hexdigest()), common_catalog())
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
        from django.utils.http import content_disposition_header
        result['Content-Disposition'] = content_disposition_header(False, letter_filename(letter))
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


def management_identity(request):
    profile = request.session.get('user_profile') or {}
    return str(uuid.UUID(str(request.session.get('user_id') or profile.get('user_id') or '')))


def management_response(response):
    if response.status_code in (400, 409):
        return JsonResponse({'error': response.json().get('message', 'Atualize o painel e tente novamente.')}, status=409)
    response.raise_for_status()
    return JsonResponse({'ok': True})


@require_POST
def delete_letter(request, letter_id):
    if not can_review(request):
        return music_exams.denied()
    try:
        row = find(request, letter_id)
        if not row:
            return JsonResponse({'error': 'Carta não encontrada no seu escopo.'}, status=404)
        data = json.loads(request.body or '{}')
        response = requests.post(settings.SUPABASE_URL + '/rest/v1/rpc/cartas_excluir', headers=service_headers(),
            json={'p_carta': str(letter_id), 'p_version': int(data.get('version', 0)),
                  'p_actor': management_identity(request), 'p_nome': music_exams.actor(request)}, timeout=35)
        return management_response(response)
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'error': 'Dados de exclusão inválidos.'}, status=400)
    except requests.RequestException:
        return JsonResponse({'error': 'Não foi possível excluir a carta. Nenhuma alteração parcial foi aplicada.'}, status=503)


@require_POST
def manage_ministry(request, common_code):
    if not can_open_module(request) or user_scope(request)['level'] not in {'global', 'regional'}:
        return music_exams.denied()
    try:
        row = next((r for r in read('cartas_ministerio_comuns', {'common_code': 'eq.' + common_code, 'deleted_at': 'is.null'})
                    if can_access(user_scope(request), {'municipio': r['municipio'], 'comum': r['comum']})), None)
        if not row:
            return JsonResponse({'error': 'Relação não encontrada no seu escopo.'}, status=404)
        data = json.loads(request.body or '{}')
        deleting = data.get('action') == 'delete'
        if data.get('action') not in {'save', 'delete'}:
            raise ValueError()
        values = {key: str(data.get(key) or '').strip() for key in (*ROLES, 'secretario')}
        if not deleting and (any(not values[key] for key in ROLES) or any(len(v) > 160 for v in values.values())):
            return JsonResponse({'error': 'Preencha os quatro responsáveis com até 160 caracteres. Quando não houver cooperador, informe Sem Cooperador do Ofício.'}, status=400)
        response = requests.post(settings.SUPABASE_URL + '/rest/v1/rpc/cartas_gerir_ministerio', headers=service_headers(),
            json={'p_codigo': common_code, 'p_version': int(data.get('version', 0)), 'p_actor': management_identity(request),
                  'p_nome': music_exams.actor(request), 'p_values': values, 'p_excluir': deleting}, timeout=35)
        return management_response(response)
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'error': 'Dados da relação inválidos.'}, status=400)
    except requests.RequestException:
        return unavailable()


@require_GET
def export_program(request, file_format='excel'):
    if not can_open_module(request):
        return music_exams.denied()
    from .music_letters_program import assess_letters
    from .music_letters_program_export import make_program_excel, make_program_pdf
    from django.utils import timezone
    if file_format not in {'excel', 'pdf'}:
        return JsonResponse({'error': 'Formato inválido.'}, status=400)
    try:
        selected = [r for r in canonical_ministries(visible(request), common_catalog()) if matches(r, filters(request))]
        city, common = request.GET.get('list_city', ''), request.GET.get('list_common', '')
        selected = [r for r in selected if (not city or norm(r.get('municipio')) == norm(city))
                    and (not common or norm(r.get('comum')) == norm(common))]
        renderer = make_program_pdf if file_format == 'pdf' else make_program_excel
        content = renderer(assess_letters(selected), music_exams.actor(request),
                                     {**filters(request), 'comum': common or filters(request).get('comum'),
                                      'municipio': city or filters(request).get('municipio')})
        extension, mime = ('pdf', 'application/pdf') if file_format == 'pdf' else ('xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response = HttpResponse(content, content_type=mime)
        response['Content-Disposition'] = 'attachment; filename="Programa_Minimo_Cartas_' + timezone.localtime().strftime('%d_%m_%Y_%H_%M') + '.' + extension + '"'
        return response
    except requests.RequestException:
        return unavailable()
