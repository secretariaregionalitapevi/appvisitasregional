"""API de relação, prazos e protocolo de entrega de cartas."""
import hashlib
import json
import uuid
import requests
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_GET, require_POST
from . import music_letters as letters
from .access_control import can_access, common_catalog, service_headers, user_scope
from .gem import can_open_module
from .music_letters_domain import canonical_ministries, common_code, matches, norm
from .music_letters_roster import (MODES, candidate_key, delivery_summary, import_rows, merge_candidates,
                                  parse_date, suggested_deadline, effective_deadlines, delivery_state, DELIVERY_LABELS)


class SetupRequired(Exception):
    pass


def read(table, order):
    result = []
    while True:
        response = requests.get(settings.SUPABASE_URL + '/rest/v1/' + table, headers=service_headers(),
                                params={'select': '*', 'order': order, 'limit': 500, 'offset': len(result)}, timeout=20)
        if response.status_code == 404 and response.json().get('code') in {'PGRST205', '42P01'}:
            raise SetupRequired()
        response.raise_for_status()
        batch = response.json(); result.extend(batch)
        if len(batch) < 500:
            return result


def scope_rows(request, rows):
    return [r for r in rows if can_access(user_scope(request), r)]


def agenda_catalog(request):
    """Use the same event identity as APP_CARTAS (including time and venue)."""
    import csv
    import io
    from .music_exams import AGENDA_CSV
    # This is the live source embedded in the official calendar; no legacy fallback.
    key = 'letters:official-agenda:v3:' + hashlib.sha256(AGENDA_CSV.encode()).hexdigest()[:16]
    cached = cache.get(key)
    if cached is None:
        response = requests.get(AGENDA_CSV, timeout=20)
        response.raise_for_status()
        cached = []
        for row in csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))):
            values = {norm(k): v.strip() for k, v in row.items() if k and v}
            if norm(values.get('DEPARTAMENTO')) != 'MUSICA':
                continue
            try:
                dt = parse_date(values.get('DATA'), True).isoformat()
            except ValueError:
                continue
            cached.append({'data': dt, 'hora': values.get('HORA', ''), 'evento': values.get('EVENTO', ''),
                           'local': values.get('LOCAL', ''), 'municipio': values.get('MUNICIPIO', '')})
        cache.set(key, cached, 60)
    from .music_exams import is_exam_agenda_event, event_matches_municipality
    scope = user_scope(request)
    events = []
    for event in cached:
        if not is_exam_agenda_event(event.get('evento', '')):
            continue
        try:
            parse_date(event.get('data'), True)
        except ValueError:
            continue
        if scope['level'] not in {'global', 'regional'} and not event_matches_municipality(
                {'titulo': event.get('evento'), **event}, scope.get('municipio')):
            continue
        identifier = hashlib.sha256('|'.join(str(event.get(k) or '') for k in ('data', 'hora', 'evento', 'local', 'municipio')).encode()).hexdigest()[:32]
        events.append({'id': identifier, **{k: event.get(k) or '' for k in ('data', 'hora', 'evento', 'local', 'municipio')}})
    return events


def state(request):
    issued = canonical_ministries(letters.visible(request), common_catalog())
    enabled = True
    try:
        registrations = scope_rows(request, read('cartas_relacao_candidatos', 'candidate_key.asc'))
        deadlines = {r['event_id']: r for r in read('cartas_entrega_prazos', 'event_id.asc')}
    except SetupRequired:
        registrations, deadlines, enabled = [], {}, False
    items = merge_candidates(issued, registrations, deadlines, timezone.localdate())
    events = {r['event_id']: {'id': r['event_id'], **r['event_snapshot']} for r in items}
    agenda_error = False
    official_events = []
    try:
        official_events = agenda_catalog(request)
        for event in official_events:
            events.setdefault(event['id'], event)
    except (requests.RequestException, ValueError, TypeError):
        agenda_error = True
    allowed_events = set(events)
    deadlines = {key: val for key, val in deadlines.items() if key in allowed_events}
    deadlines, pre_options = effective_deadlines(list(events.values()), deadlines, official_events=official_events)
    for item in items:
        item['delivery_status'] = delivery_state(item, deadlines.get(item['event_id']), timezone.localdate())
        item['delivery_label'] = DELIVERY_LABELS[item['delivery_status']]
    return {'items': items, 'deadlines': deadlines, 'pre_options': pre_options, 'events': sorted(events.values(), key=lambda e: e.get('data', ''), reverse=True),
            'enabled': enabled, 'agenda_unavailable': agenda_error}


def selected(request, items):
    rows = [r for r in items if matches(r, letters.filters(request))]
    for param, field in [('list_city', 'municipio'), ('list_common', 'comum'), ('roster_event', 'event_id'),
                         ('roster_type', 'tipo'), ('roster_mode', 'modalidade'), ('delivery_status', 'delivery_status')]:
        value = request.GET.get(param, '')
        if value:
            rows = [r for r in rows if norm(r.get(field)) == norm(value)]
    return rows


def error_response(exc):
    if isinstance(exc, SetupRequired):
        return JsonResponse({'error': 'O controle de entrega precisa da migração 044_cartas_relacao_entregas.sql no Supabase.'}, status=503)
    if isinstance(exc, (ValueError, TypeError, KeyError, signing.BadSignature)):
        return JsonResponse({'error': str(exc) or 'Confira os dados informados.'}, status=400)
    return JsonResponse({'error': 'Não foi possível consultar ou salvar a relação. Tente novamente.'}, status=503)


@require_GET
def dashboard(request):
    if not can_open_module(request):
        return letters.music_exams.denied()
    try:
        payload = state(request)
        payload['items'] = selected(request, payload['items'])
        payload['summary'] = delivery_summary(payload['items'])
        payload['can_manage'] = letters.can_review(request)
        payload['can_deadline'] = letters.can_review(request) and user_scope(request)['level'] in {'global', 'regional'}
        payload['modalities'] = MODES
        return JsonResponse(payload)
    except (requests.RequestException, ValueError) as exc:
        return error_response(exc)


def rpc(name, payload):
    response = requests.post(settings.SUPABASE_URL + '/rest/v1/rpc/' + name, headers=service_headers(), json=payload, timeout=35)
    if response.status_code == 404:
        raise SetupRequired()
    if response.status_code in {400, 409}:
        return JsonResponse({'error': response.json().get('message', 'Atualize a relação e tente novamente.')}, status=409)
    response.raise_for_status()
    return JsonResponse({'ok': True, 'result': response.json()})


@require_POST
def save_deadline(request):
    if not letters.can_review(request) or user_scope(request)['level'] not in {'global', 'regional'}:
        return letters.music_exams.denied()
    try:
        data = json.loads(request.body or '{}'); payload = state(request)
        event = next((e for e in payload['events'] if e['id'] == data.get('event_id')), None)
        if not event:
            raise ValueError('Selecione um evento disponível no seu escopo.')
        references = payload.get('pre_options', {}).get(event['id'], [])
        reference = next((r for r in references if r['id'] == data.get('pre_event_id')), None)
        if not reference:
            raise ValueError('Selecione uma pr\u00e9-avalia\u00e7\u00e3o do calend\u00e1rio oficial da mesma cidade e do mesmo p\u00fablico.')
        pre = parse_date(reference['data'], True)
        if data.get('pre_date') != pre.isoformat():
            raise ValueError('A data deve corresponder \u00e0 pr\u00e9-avalia\u00e7\u00e3o oficial selecionada.')
        deadline = parse_date(data.get('deadline'), True)
        if pre > parse_date(event['data'], True) or deadline >= pre:
            raise ValueError('A pré-avaliação deve ocorrer até o exame, e o prazo antes da pré-avaliação.')
        return rpc('cartas_salvar_prazo', {'p_event': event['id'], 'p_snapshot': event, 'p_pre': pre.isoformat(),
                   'p_deadline': deadline.isoformat(), 'p_version': int(data.get('version', 0)),
                   'p_actor': letters.management_identity(request), 'p_name': letters.music_exams.actor(request)})
    except (requests.RequestException, ValueError, TypeError, KeyError, SetupRequired) as exc:
        return error_response(exc)


@require_POST
def save_delivery(request):
    if not letters.can_review(request):
        return letters.music_exams.denied()
    try:
        data = json.loads(request.body or '{}'); payload = state(request)
        row = next((r for r in payload['items'] if r['key'] == data.get('key')), None)
        if not row:
            return JsonResponse({'error': 'Candidato não encontrado no seu escopo.'}, status=404)
        if not isinstance(data.get('received'), bool):
            raise ValueError('Informe se a carta foi entregue.')
        received_on = parse_date(data.get('received_on'), required=data['received']) if data['received'] else None
        if received_on and received_on > timezone.localdate():
            raise ValueError('A data de entrega não pode estar no futuro.')
        row['delivery'] = {'received': data['received'], 'received_on': received_on.isoformat() if received_on else None,
                           'recorded_by': letters.music_exams.actor(request), 'recorded_at': timezone.now().isoformat()}
        return rpc('cartas_registrar_entrega', {'p_key': row['key'], 'p_data': row,
                    'p_version': int(data.get('version', -1)), 'p_actor': letters.management_identity(request),
                    'p_name': letters.music_exams.actor(request)})
    except (requests.RequestException, ValueError, TypeError, KeyError, SetupRequired) as exc:
        return error_response(exc)


def prepare_import(request, raw_rows, event, default_type, default_mode):
    catalog = common_catalog()
    scope = user_scope(request)
    # Exact name + common + kind only. No fuzzy links to another student's history.
    students = [s for s in read('musica_acompanhamento_aluno', 'id.asc') if can_access(scope, {'municipio': s.get('municipio'), 'comum': s.get('comum_congregacao') or s.get('comum')})]
    index = {}
    for student in students:
        name = norm(student.get('nome_aluno') or student.get('nome'))
        code = common_code(student.get('comum_congregacao') or student.get('comum'))
        index.setdefault((name, code), []).append(student)
    output, seen = [], set()
    existing = {r['key'] for r in state(request)['items']}
    for raw in raw_rows:
        row = {k: str(raw.get(k) or '').strip() for k in ('nome', 'comum', 'instrumento', 'tonalidade', 'observacao')}
        if any(len(v) > (2000 if k == 'observacao' else 200) for k, v in row.items()):
            raise ValueError(f'Linha {raw["source_row"]}: conteúdo excede o limite permitido.')
        row['tipo'] = {'MUSICO': 'musico', 'ORGANISTA': 'organista'}.get(norm(raw.get('tipo')), default_type)
        mode = str(raw.get('modalidade') or default_mode).strip()
        row['modalidade'] = next((key for key, label in MODES.items() if norm(mode) in {norm(key), norm(label)}), '')
        if row['tipo'] not in {'musico', 'organista'} or row['modalidade'] not in MODES:
            raise ValueError(f'Linha {raw["source_row"]}: tipo ou modalidade inválidos.')
        if row['tipo'] == 'musico' and row['modalidade'] in {'rjm', 'por_chance'}:
            raise ValueError('RJM e Por chance são modalidades de cartas de organistas.')
        if ('ORGANISTA' in norm(event['evento']) and row['tipo'] != 'organista') or ('MUSICO' in norm(event['evento']) and row['tipo'] != 'musico'):
            raise ValueError('O tipo do candidato não corresponde ao evento selecionado.')
        # Resolve by code; never guess a municipality from the uploaded text.
        matching = next((c for c in catalog if common_code(c.get('comum')) == common_code(row['comum'])), None)
        if not matching:
            raise ValueError(f'Linha {raw["source_row"]}: comum não encontrada no cadastro regional.')
        row.update(comum=matching['comum'], municipio=matching.get('cidade'))
        row = canonical_ministries([row], catalog)[0]
        if not can_access(scope, row):
            raise ValueError(f'Linha {raw["source_row"]}: comum fora do seu escopo.')
        row.update(event_id=event['id'], event_snapshot=event, source='Importação manual', source_row=raw['source_row'])
        hits = index.get((norm(row['nome']), common_code(row['comum'])), [])
        hits = [s for s in hits if ('ORGANISTA' in norm(s.get('cargo_ministerio')) or 'ORGAO' in norm(s.get('instrumento'))) == (row['tipo'] == 'organista')]
        provided = str(raw.get('pessoa_id') or '').strip()
        if provided:
            hits = [s for s in hits if s['id'] == provided]
        row['pessoa_id'] = hits[0]['id'] if len(hits) == 1 else None
        row['match_label'] = 'Vínculo confirmado no SAM' if len(hits) == 1 else 'Sem vínculo único no SAM - revisar cadastro'
        row['instrumento'] = row['instrumento'] or (hits[0].get('instrumento') if len(hits) == 1 else '') or ('ÓRGÃO' if row['tipo'] == 'organista' else '')
        key = candidate_key(row)
        if key in seen:
            raise ValueError(f'Linha {raw["source_row"]}: candidato duplicado no arquivo.')
        seen.add(key)
        received = norm(raw.get('received'))
        if received not in {'', 'NAO', 'N', '0', 'FALSE', 'SIM', 'S', '1', 'TRUE', 'X'}:
            raise ValueError(f'Linha {raw["source_row"]}: use Sim ou Não em Carta entregue.')
        is_received = received in {'SIM', 'S', '1', 'TRUE', 'X'}
        received_on = parse_date(raw.get('received_on'))
        if received_on and (not is_received or received_on > timezone.localdate()):
            raise ValueError('Confira a data de entrega e a marcação de Carta entregue.')
        row.update(key=key, version=0, exists=key in existing,
                   delivery={'received': is_received, 'received_on': received_on.isoformat() if received_on else None,
                             'recorded_by': letters.music_exams.actor(request), 'recorded_at': timezone.now().isoformat()})
        output.append(row)
    # Consult the same GEM requirements used on issued letters.
    from .music_letters_program import assess_letters
    assessed = assess_letters([{**r, 'payload': {'pessoa_id': r['pessoa_id']}} for r in output])
    for row, assessment in zip(output, assessed):
        row['program_assessment'] = assessment.get('program_assessment')
    return output


@require_POST
def preview_import(request):
    if not letters.can_review(request):
        return letters.music_exams.denied()
    try:
        upload = request.FILES.get('arquivo')
        if not upload or upload.size > 5 * 1024 * 1024:
            raise ValueError('Envie um arquivo .xlsx ou .csv de até 5 MB.')
        payload = state(request)
        if not payload['enabled']:
            raise SetupRequired()
        event = next((e for e in payload['events'] if e['id'] == request.POST.get('event_id')), None)
        if not event:
            raise ValueError('Selecione o evento da lista antes de importar.')
        rows = prepare_import(request, import_rows(upload.read(), upload.name), event,
                              request.POST.get('tipo'), request.POST.get('modalidade'))
        token = signing.dumps({'actor': letters.management_identity(request), 'rows': rows}, salt='letters-roster', compress=True)
        return JsonResponse({'items': rows, 'token': token, 'new': sum(not r['exists'] for r in rows),
                             'existing': sum(r['exists'] for r in rows)})
    except (requests.RequestException, ValueError, TypeError, KeyError, UnicodeError, SetupRequired) as exc:
        return error_response(exc)


@require_POST
def commit_import(request):
    if not letters.can_review(request):
        return letters.music_exams.denied()
    try:
        data = signing.loads(json.loads(request.body or '{}').get('token', ''), salt='letters-roster', max_age=1200)
        if data['actor'] != letters.management_identity(request):
            raise ValueError('A prévia pertence a outra sessão. Importe novamente.')
        rows = [r for r in data['rows'] if not r['exists']]
        if not rows or any(not can_access(user_scope(request), r) for r in rows):
            raise ValueError('Nenhum candidato novo disponível no seu escopo.')
        return rpc('cartas_importar_relacao', {'p_rows': rows, 'p_actor': letters.management_identity(request),
                                            'p_name': letters.music_exams.actor(request)})
    except (requests.RequestException, ValueError, TypeError, KeyError, signing.BadSignature, SetupRequired) as exc:
        return error_response(exc)


@require_GET
def export(request, file_format):
    if not can_open_module(request):
        return letters.music_exams.denied()
    if file_format not in {'pdf', 'excel'}:
        return JsonResponse({'error': 'Formato inválido.'}, status=400)
    try:
        from .music_letters_roster_exports import make_pdf, make_excel
        payload = state(request)
        rows = [] if request.GET.get('template') == '1' else selected(request, payload['items'])
        content = (make_pdf if file_format == 'pdf' else make_excel)(rows, letters.music_exams.actor(request), payload['deadlines'], template=request.GET.get('template') == '1')
        ext, mime = ('pdf', 'application/pdf') if file_format == 'pdf' else ('xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response = HttpResponse(content, content_type=mime)
        response['Content-Disposition'] = content_disposition_header(True, 'Relacao_Candidatos_' + timezone.localtime().strftime('%d_%m_%Y_%H_%M') + '.' + ext)
        return response
    except (requests.RequestException, ValueError) as exc:
        return error_response(exc)
