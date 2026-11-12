"""Página e APIs autenticadas do acompanhamento individual do ministério."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4

import requests
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from . import music_events
from .access_control import can_access, common_catalog, service_headers, user_scope, scope_details
from .music_ministry_domain import TITLE, ROLES, KINDS, STATES, roster, history, parse_meeting, match_person, event_payload, include_directory, code, regional_city
from .sam_temporal import temporal_roster


def _people(sources):
    people = temporal_roster(sources['registry'], sources['members'], sources['catalog'], sources.get('transitions', []))
    people = include_directory(people, sources.get('directory', []), [*sources['entries'], *sources.get('identity_links', [])])
    for person in people:
        person['temporal'] = True
    return people


def _actor(request):
    profile = request.session.get('user_profile') or {}
    identity = request.session.get('user_id') or profile.get('user_id')
    name = profile.get('full_name') or profile.get('nome') or profile.get('name') or profile.get('email')
    if not identity or not name:
        raise ValueError('Entre novamente para identificar o responsável.')
    return str(identity), str(name)


def _read_optional(table, **filters):
    try:
        return music_events._read(table, **filters)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return []
        raise


def _sources(year, refresh=False):
    key = f'music-ministry:sources:v6:{year}'
    cached = None if refresh else cache.get(key)
    if cached is not None:
        return cached
    read = music_events._read
    with ThreadPoolExecutor(max_workers=8) as executor:
        catalog = executor.submit(common_catalog)
        registry = executor.submit(music_events._registry)
        members = executor.submit(read, settings.SUPABASE_TABLE_VISITAS_IRMANDADE,
            select='id,nome,cargo_outros,codigo_comum,comum,cidade,status',
            **{'or': '(cargo_outros.ilike.*encarregado*,cargo_outros.ilike.*examinadora*,cargo_outros.ilike.*ancião*,cargo_outros.ilike.*anciao*,cargo_outros.ilike.*cooperador*)'}, order='id.asc')
        legacy = executor.submit(read, 'musica_eventos', data_evento=f'gte.{year}-01-01',
                                 **{'and': f'(data_evento.lt.{year + 1}-01-01)'}, order='data_evento.asc,id.asc')
        own = executor.submit(read, 'musica_ministerio_eventos', data_evento=f'gte.{year}-01-01',
                              **{'and': f'(data_evento.lt.{year + 1}-01-01)'}, order='data_evento.asc,id.asc')
        directory_future = executor.submit(read, 'musica_ministerio_pessoas', order='person_key.asc')
        identity_future = executor.submit(read, 'musica_ministerio_participacoes', select='person_key,nome,source', **{'source->>canonical_person_key': 'not.is.null'}, order='event_id.asc,person_key.asc')
        transitions_future = executor.submit(read, 'sam_cadastro_transicoes', order='effective_at.asc,id.asc')
        events = legacy.result()
        available = True
        try:
            own_events = own.result()
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 404:
                raise
            own_events, available = [], False
        directory = directory_future.result() if available else []
        identity_links = identity_future.result() if available else []
        records, entries, legacy_reviews, legacy_sites = [], [], [], []
        pending = []
        for table, ids, target, select in [
            ('musica_evento_presencas', [e['id'] for e in events], records,
             'id,evento_id,local_id,sam_pessoa_id,nome,comum_codigo,comum_informada,municipio_informado,cargo,situacao'),
            ('musica_evento_locais', [e['id'] for e in events], legacy_sites, 'id,evento_id,nome,municipio'),
            ('musica_ministerio_participacoes', [e['id'] for e in own_events], entries, '*')]:
            batch_size = 1 if table == 'musica_evento_presencas' else 40
            for start in range(0, len(ids), batch_size):
                field = 'event_id' if table == 'musica_ministerio_participacoes' else 'evento_id'
                pending.append((target, executor.submit(read, table, select=select,
                    **{field: 'in.(' + ','.join(ids[start:start + batch_size]) + ')'},
                    order='event_id.asc,person_key.asc' if field == 'event_id' else 'id.asc')))
        if available:
            for start in range(0, len(events), 40):
                ids = 'in.(' + ','.join(e['id'] for e in events[start:start + 40]) + ')'
                pending.append((legacy_reviews, executor.submit(read, 'musica_ministerio_legado_conferencias',
                                                               event_id=ids, order='event_id.asc,person_key.asc')))
        legacy_frequency, legacy_conductor_reviews = [], []
        for table, target, select in [
            ('musica_evento_frequencia', legacy_frequency,
             'evento_id,comum_codigo,comum,municipio,encarregado_situacao'),
            ('musica_evento_encarregados', legacy_conductor_reviews,
             'evento_id,comum_chave,comum_nome,municipio,situacao')]:
            for start in range(0, len(events), 40):
                ids = 'in.(' + ','.join(e['id'] for e in events[start:start + 40]) + ')'
                pending.append((target, executor.submit(_read_optional, table, select=select,
                    evento_id=ids, order='evento_id.asc')))
        for target, future in pending:
            target.extend(future.result())
        from .music_events_calendar import validated_sites
        result = {'catalog': catalog.result(), 'registry': registry.result(), 'members': members.result(),
                  'events': own_events, 'entries': entries, 'legacy_events': events,
                  'legacy_records': records, 'available': available, 'directory': directory, 'legacy_reviews': legacy_reviews,
                  'legacy_frequency': legacy_frequency, 'legacy_conductor_reviews': legacy_conductor_reviews,
                  'legacy_sites': validated_sites(events, legacy_sites), 'identity_links': identity_links,
                  'transitions': transitions_future.result()}
    cache.set(key, result, 60)
    return result


def dashboard_data(request):
    year = int(request.GET.get('ano') or timezone.localdate().year)
    if not 2000 <= year <= 2100:
        raise ValueError('Selecione um ano entre 2000 e 2100.')
    role = request.GET.get('cargo', 'ENCARREGADO_LOCAL')
    kind = request.GET.get('tipo', '')
    state = request.GET.get('situacao', '')
    if role and role not in ROLES or kind and kind not in KINDS or state and state not in STATES:
        raise ValueError('Filtro de cargo ou evento inválido.')
    sources = _sources(year, request.GET.get('atualizar') == '1')
    people = _people(sources)
    filters = {'ano': year, 'municipios': request.GET.getlist('municipio'), 'comuns': request.GET.getlist('comum'),
               'cargo': role, 'tipo': kind, 'busca': request.GET.get('busca', '')[:120],
               'evento': request.GET.get('evento', ''), 'situacao': state}
    scope = user_scope(request)
    result = history(people, sources['events'], sources['entries'], sources['legacy_events'],
                     sources['legacy_records'], sources['catalog'], scope, filters, sources['legacy_reviews'], sources.get('legacy_sites', []))
    conductor_statuses = {}
    catalog_by_code = {code(item['comum']): item for item in sources['catalog']}
    for row in sources.get('legacy_frequency', []):
        common_code = code(row.get('comum_codigo') or row.get('comum'))
        canonical = catalog_by_code.get(common_code, {})
        common = canonical.get('comum') or row.get('comum') or common_code
        municipality = regional_city(canonical.get('cidade') or row.get('municipio') or '')
        if can_access(scope, {'comum': common, 'cidade': municipality}):
            key = (row['evento_id'], common_code)
            conductor_statuses[key] = {'event_id': row['evento_id'], 'comum_codigo': common_code,
                'comum': common, 'municipio': municipality, 'situacao': row.get('encarregado_situacao') or 'NAO_INFORMADO'}
    for row in sources.get('legacy_conductor_reviews', []):
        common_code = code(row.get('comum_chave') or row.get('comum_nome'))
        canonical = catalog_by_code.get(common_code, {})
        common = canonical.get('comum') or row.get('comum_nome') or common_code
        municipality = regional_city(canonical.get('cidade') or row.get('municipio') or '')
        if can_access(scope, {'comum': common, 'cidade': municipality}):
            key = (row['evento_id'], common_code)
            conductor_statuses[key] = {'event_id': row['evento_id'], 'comum_codigo': common_code,
                'comum': common, 'municipio': municipality, 'situacao': row['situacao']}
    result.update(available=sources['available'], can_manage=scope['level'] in {'regional', 'global'},
                  legacy_conductor_statuses=list(conductor_statuses.values()),
                  filters=filters, events=[e for e in sources['events'] if any(
                      cell['event_id'] == e['id'] for row in result['rows'] for cell in row['cells'])])
    return result


@require_GET
def page(request):
    if not music_events._allowed(request):
        return render(request, 'pages/403.html', status=403)
    return render(request, 'pages/music_ministry.html', {'page_title': TITLE, 'year': timezone.localdate().year,
        'can_manage': user_scope(request)['level'] in {'regional', 'global'},
        'roles': ROLES, 'kinds': KINDS, 'states': STATES, 'scope': scope_details(user_scope(request))})


@require_GET
def api_dashboard(request):
    if not music_events._allowed(request):
        return JsonResponse({'error': 'Acesso não autorizado.'}, status=403)
    try:
        return JsonResponse(dashboard_data(request))
    except (ValueError, TypeError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except requests.RequestException:
        return JsonResponse({'error': 'Não foi possível carregar o acompanhamento. Tente atualizar.'}, status=502)


def _rpc(name, payload):
    response = requests.post(f'{settings.SUPABASE_URL}/rest/v1/rpc/{name}', headers=service_headers(), json=payload, timeout=90)
    if response.status_code == 409:
        raise ValueError('Já existe um encontro com essa data, título e modalidade. Abra o encontro existente para conferir.')
    response.raise_for_status()
    return response.json()


@require_POST
def api_manage(request, action):
    if not music_events._allowed(request) or user_scope(request)['level'] not in {'regional', 'global'}:
        return JsonResponse({'error': 'Alterações restritas à administração regional.'}, status=403)
    try:
        identity, actor = _actor(request)
        if action == 'previa':
            upload = request.FILES.get('arquivo')
            if not upload or not upload.name.lower().endswith('.xlsx') or upload.size > 15 * 1024 * 1024:
                raise ValueError('Selecione um arquivo .xlsx de até 15 MB.')
            sources = _sources(timezone.localdate().year)
            result = parse_meeting(upload.read(), sources['catalog'])
            people = _people(sources)
            token = uuid4().hex
            cache.set(f'music-ministry:preview:{identity}:{token}', {**result, 'filename': upload.name[:180]}, 1800)
            return JsonResponse({'token': token, 'count': result['count'], 'duplicates': result['duplicate_rows'], 'suggested_date': result['suggested_date'],
                'commons': [{'key': c['comum'], 'city': c['cidade']} for c in sources['catalog']],
                'rows': [dict(r, candidates=[{'key': p['key'], 'nome': p['nome'], 'comum': p['comum']}
                                           for p in match_person(r, people)]) for r in result['records']]})
        raw = json.loads(request.body or '{}')
        if action == 'conferir':
            if raw.get('situacao') not in STATES or len(str(raw.get('observacoes') or '')) > 1000:
                raise ValueError('Situação ou observação inválida.')
            if raw['situacao'] == 'JUSTIFICOU' and not str(raw.get('observacoes') or '').strip():
                raise ValueError('Informe a justificativa.')
            if str(raw.get('event_id', '')).startswith('legado:'):
                event_id = raw['event_id'].removeprefix('legado:')
                event = music_events._read('musica_eventos', id=f'eq.{event_id}')
                if not event:
                    raise ValueError('Encontro não encontrado.')
                year = int(str(event[0]['data_evento'])[:4])
                sources = _sources(year, True)
                people = _people(sources)
                person = next((p for p in people if raw['person_key'] in p['aliases']), None)
                if person is None:
                    raise ValueError('Pessoa não encontrada no cadastro individual.')
                current = history(people, [], [], sources['legacy_events'], sources['legacy_records'], sources['catalog'],
                                  user_scope(request), {'ano': year}, sources['legacy_reviews'])
                cell = next((c for p in current['rows'] if p['key'] == person['key'] for c in p['cells'] if c['event_id'] == raw['event_id']), None)
                if cell and cell['nominal_present'] and raw['situacao'] != 'PRESENTE':
                    raise ValueError('Há presença nominal importada. Corrija a fonte do evento antes de registrar outra situação.')
                if not cell or not cell.get('historical_role_known', True):
                    raise ValueError('Confirme o cargo e a comum vigentes na data do evento antes de registrar a conferência.')
                result = _rpc('musica_ministerio_conferir_legado', {'p_evento': event_id,
                    'p_pessoa': {'person_key': raw['person_key'], 'nome': person['nome'], 'comum': cell['comum'],
                                 'municipio': cell['municipio'], 'roles': cell['roles'],
                                 'situacao': raw['situacao'], 'observacoes': str(raw.get('observacoes') or '').strip()},
                    'p_version': int(raw['version']), 'p_usuario_id': identity, 'p_usuario_nome': actor})
                cache.delete(f'music-ministry:sources:v5:{year}')
                return JsonResponse({'item': result})
            records = music_events._read('musica_ministerio_participacoes', event_id=f'eq.{raw["event_id"]}',
                                        person_key=f'eq.{raw["person_key"]}')
            if not records:
                raise ValueError('Registro não encontrado.')
            result = _rpc('musica_ministerio_conferir', {'p_evento': raw['event_id'], 'p_pessoa': raw['person_key'],
                'p_situacao': raw['situacao'], 'p_observacoes': str(raw.get('observacoes') or '').strip(),
                'p_version': int(raw['version']), 'p_usuario_id': identity, 'p_usuario_nome': actor})
            event = music_events._read('musica_ministerio_eventos', id=f'eq.{raw["event_id"]}')[0]
            cache.delete(f'music-ministry:sources:v5:{str(event["data_evento"])[:4]}')
            return JsonResponse({'item': result})
        if action != 'salvar':
            return JsonResponse({'error': 'Operação inválida.'}, status=404)
        year = date.fromisoformat(raw.get('data_evento') or '').year
        if not 2000 <= year <= 2100 or raw.get('conferido') is not True:
            raise ValueError('Confira o evento e confirme a conferência antes de salvar.')
        sources = _sources(year, True)
        people = _people(sources)
        preview = None
        if raw.get('token'):
            preview = cache.get(f'music-ministry:preview:{identity}:{raw["token"]}')
            if preview is None:
                raise ValueError('A prévia expirou. Selecione o arquivo novamente.')
        if raw.get('lista_completa') and preview is None:
            raise ValueError('Uma lista nominal é necessária para confirmar a cobertura.')
        records = [dict(r) for r in preview['records']] if preview else []
        from .music_events_dashboard import regional_city
        by_common = {c['comum']: c for c in sources['catalog']}
        overrides = {str(m['row']): m.get('common') for m in raw.get('mappings', []) if m.get('common')}
        for row in records:
            if str(row['row']) in overrides:
                common = by_common.get(overrides[str(row['row'])])
                if not common:
                    raise ValueError('Comum selecionada inválida.')
                row.update(comum=common['comum'], municipio=regional_city(common['cidade']), common_resolved=True)
        payload = event_payload(raw, people, records, raw.get('mappings'))
        if raw.get('event_id'):
            target = next((e for e in sources['events'] if e['id'] == raw['event_id']), None)
            if not target or target.get('arquivo_sha256') or preview is None:
                raise ValueError('Selecione um encontro sem lista para receber a importação.')
            for field in ['titulo', 'tipo', 'data_evento', 'modalidade', 'local', 'familia', 'municipios', 'cargos']:
                expected = sorted(target[field]) if isinstance(target[field], list) else str(target[field])
                actual = sorted(payload[field]) if isinstance(payload[field], list) else str(payload[field])
                if actual != expected:
                    raise ValueError('A importação deve preservar a data e o público do encontro cadastrado.')
            # Não cria ausências retroativas para novos cadastros, nem altera o público histórico.
            snapshots = {r['person_key']: r for r in sources['entries'] if r['event_id'] == target['id']}
            present_keys = {m['key'] for m in raw.get('mappings', [])}
            payload['registros'] = [r for r in payload['registros'] if r['person_key'] in snapshots or r['person_key'] in present_keys]
            for key, snapshot in snapshots.items():
                if key not in {r['person_key'] for r in payload['registros']}:
                    payload['registros'].append(dict(snapshot) if snapshot['situacao'] == 'NAO_APLICA' else
                        {**snapshot, 'situacao': 'CONFERIR', 'observacoes': 'Cadastro atual divergente do público histórico. Conferir.'})
            for entry in payload['registros']:
                previous = snapshots.get(entry['person_key'])
                if previous:
                    # Reimporting attendance must retain the public captured for
                    # this event, even if the current directory has changed.
                    for field in ('roles', 'comum', 'municipio'):
                        entry[field] = previous[field]
                    if previous['situacao'] == 'NAO_APLICA':
                        entry.update(situacao='NAO_APLICA', observacoes=previous['observacoes'])
                if previous and previous['situacao'] == 'PRESENTE' and entry['situacao'] != 'PRESENTE':
                    entry.update(situacao='PRESENTE', observacoes=previous['observacoes'])
            payload['event_id'] = target['id']
        if not payload['registros']:
            raise ValueError('Nenhuma pessoa foi encontrada para o público selecionado.')
        result = _rpc('musica_ministerio_salvar', {'p_evento': payload, 'p_hash': preview['sha256'] if preview else None,
            'p_arquivo': preview['filename'] if preview else None, 'p_usuario_id': identity, 'p_usuario_nome': actor})
        cache.delete(f'music-ministry:sources:v5:{year}')
        return JsonResponse(result)
    except (ValueError, TypeError, KeyError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except requests.RequestException:
        return JsonResponse({'error': 'Não foi possível salvar. Verifique a conexão e a aplicação da migração 036. A mesma lista pode ser reenviada com segurança.'}, status=502)


@require_GET
def export(request, file_format):
    if not music_events._allowed(request):
        return JsonResponse({'error': 'Acesso não autorizado.'}, status=403)
    if file_format not in {'pdf', 'excel'}:
        return JsonResponse({'error': 'Formato inválido.'}, status=404)
    try:
        from .music_ministry_reports import export_response
        return export_response(dashboard_data(request), request, file_format)
    except (ValueError, TypeError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except requests.RequestException:
        return JsonResponse({'error': 'Não foi possível gerar o relatório.'}, status=502)
