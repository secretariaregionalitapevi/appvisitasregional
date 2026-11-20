"""Justificativas públicas da agenda, projetadas nos painéis sem criar presenças."""
import csv
import hashlib
import io
import json
import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from uuid import UUID, uuid5, NAMESPACE_URL
from threading import Lock
from concurrent.futures import ThreadPoolExecutor

import requests
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from . import music_events as events
from .access_control import can_access, common_catalog, scope_details, service_headers, user_scope
from .music_events_dashboard import code, regional_city, REGIONAL
from .music_events_import import norm
from .music_ministry_domain import roster, ROLES, AUXILIARY_ROLES, roles_of
from .music_participants import member_directory

TABLE = 'musica_justificativas_publicas'
SALT = 'music-public-conductor-v1'
KINDS = {'ENSAIO_REGIONAL': 'Ensaio regional', 'REUNIAO_TECNICA': 'Reunião técnica',
         'REUNIAO_MINISTERIO': 'Reunião do ministério'}
PUBLIC_ROLES = set(ROLES) - {'ANCIAO', 'COOPERADOR'}
PEOPLE_CACHE_KEY = 'music-justification:prepared-people:v1'
_people_lock = Lock()


def today():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).date().isoformat()


def classify(title):
    value = norm(title)
    if 'ENSAIO REGIONAL' in value:
        return 'ENSAIO_REGIONAL', 'GERAL'
    if ('REUNIAO TECNICA' in value or re.search(r'\bRT\b', value) or 'ENSAIO POR FAMILIA' in value
            or ('ENSAIO TECNICO' in value and 'FAMILIA' in value)):
        families = [f for f in ('CORDAS', 'MADEIRAS', 'METAIS') if f in value]
        return ('REUNIAO_TECNICA', families[0]) if len(families) == 1 else ('REUNIAO_TECNICA', 'GERAL')
    if 'REUNIAO' in value and (any(s in value for s in ('MINISTERIO', 'MUSICAL', 'ENCARREGADOS LOCAIS'))
                             or re.search(r'\bMUSICA\b', value)):
        return 'REUNIAO_MINISTERIO', 'GERAL'
    return None, None


def title_cities(title):
    value = norm(title)
    cities = {city for city in REGIONAL if norm(city) in value}
    if 'FAZENDINHA' in value:
        cities.add('SANTANA DE PARNAÍBA')
    if re.search(r'\bVGP\b', value):
        cities.add('VARGEM GRANDE PAULISTA')
    if 'VARGEM GRANDE' in value:
        cities.add('VARGEM GRANDE PAULISTA')
    # Caucaia pertence a Cotia, mas possui administração própria neste cadastro.
    if 'CAUCAIA DO ALTO' in value and 'COTIA' not in value:
        cities.discard('COTIA')
    return sorted(cities)


def agenda_location(title):
    """A agenda atual descreve a sede no título e não possui coluna LOCAL."""
    value = re.sub(r'\s*\([^()]+\)\s*$', '', title).strip()
    if norm(title).startswith('ENSAIO REGIONAL'):
        return re.sub(r'^ensaio regional\s*[-–—:]?\s*', '', value, flags=re.I).strip()
    if norm(title).startswith('ENSAIO POR FAMILIA'):
        return re.sub(r'^ensaio por fam[ií]lia\s*[-–—:]?\s*\(?\s*(?:cordas|madeiras|metais)\s*\)?\s*', '', value, flags=re.I).strip()
    if norm(title).startswith('ENSAIO TECNICO'):
        return re.sub(r'^ensaio t[eé]cnico\s*[-–—:]?\s*fam[ií]lia\s*\(?\s*(?:cordas|madeiras|metais)\s*\)?\s*[-–—:]?\s*', '', value, flags=re.I).strip()
    # Alguns encontros indicam a sede depois do município.
    suffix = re.search(r'\([^()]+\)\s*[-–—]\s*(.+)$', title)
    return suffix.group(1).strip() if suffix else ''


def agenda():
    from .music_exams import AGENDA_CSV
    key = 'music-justification:agenda:v5:' + hashlib.sha256(AGENDA_CSV.encode()).hexdigest()[:12]
    cached = cache.get(key)
    if cached is not None:
        return cached
    response = requests.get(AGENDA_CSV, timeout=(3.05, 20))
    response.raise_for_status()
    result = {}
    for source in csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))):
        row = {norm(k): v for k, v in source.items()}
        if norm(row.get('DEPARTAMENTO')) != 'MUSICA':
            continue
        title, hour = (row.get('EVENTO') or '').strip(), (row.get('HORA') or '').strip()
        kind, family = classify(title)
        if not kind:
            continue
        try:
            day = datetime.strptime((row.get('DATA') or '').strip(), '%d/%m/%Y').date().isoformat()
        except ValueError:
            continue
        # Mesmo algoritmo já utilizado pela conexão oficial de Exames e Testes.
        identity = hashlib.sha256(f'{day}|{hour}|{norm(title)}'.encode()).hexdigest()[:24]
        location = (row.get('LOCAL') or row.get('LOCALIDADE') or agenda_location(title)).strip()
        municipalities = title_cities(title)
        if kind == 'ENSAIO_REGIONAL':
            municipalities = sorted(REGIONAL)
        if kind == 'REUNIAO_MINISTERIO' and re.search(r'REUNIAO GERAL (?:DA )?MUSICA', norm(title)):
            location = location or ' / '.join(city.title() for city in municipalities)
            municipalities = sorted(REGIONAL)
        if re.search(r'\(REGIONAL\s*[-–—]?\s*ITAPEVI\)', norm(title)):
            municipalities = sorted(REGIONAL)
        # Só reuniões explicitamente regionais abrangem toda a Regional.
        # Não adivinhar a abrangência de um encontro sem município identificado.
        if not municipalities and kind == 'REUNIAO_MINISTERIO' and 'REGIONAL' in norm(title):
            municipalities = sorted(REGIONAL)
        result[identity] = {'id': identity, 'titulo': title, 'data_evento': day, 'hora': hour,
                            'tipo': kind, 'familia': family, 'local': location,
                            'municipios': municipalities}
    output = sorted(result.values(), key=lambda e: (e['data_evento'], e['hora'], e['titulo']))
    cache.set(key, output, 300)
    return output


def catalog():
    return [c for c in common_catalog() if regional_city(c.get('cidade')) in REGIONAL and code(c.get('comum'))]


def event_window(events_list, municipality):
    upcoming = sorted((e for e in events_list if e['data_evento'] >= today()
                       and municipality in e['municipios']),
                      key=lambda e: (e['data_evento'], e.get('hora', ''), e['titulo'], e['id']))
    return [{**event, 'aberto': index < 2} for index, event in enumerate(upcoming[:3])]


def search_sources(common):
    """Carga inicial pequena; confere também os homônimos e transferências dos membros."""
    from .music_events_identity import CommonResolver
    commons = catalog()
    resolver = CommonResolver(commons)
    key = code(common['comum'])
    city = regional_city(common['cidade'])
    cities = [city]
    if city in {'COTIA', 'CAUCAIA DO ALTO', 'VARGEM GRANDE PAULISTA'}:
        cities = ['COTIA', 'CAUCAIA DO ALTO', 'VARGEM GRANDE PAULISTA']
    fields = 'id,nome_aluno,cargo_ministerio,status,instrumento,comum_congregacao,municipio'
    city_filter = ','.join(json.dumps(c, ensure_ascii=False) for c in cities)
    with ThreadPoolExecutor(max_workers=2) as executor:
        registry_future = executor.submit(events._read, 'musica_acompanhamento_aluno', select=fields,
            **{'or': f'(comum_congregacao.ilike.{key}*,municipio.in.({city_filter}))'}, order='id.asc')
        members_future = executor.submit(member_directory)
        members = [p for p in members_future.result() if code((resolver.resolve(
            p.get('codigo_comum') or p.get('comum'), p.get('cidade')) or {}).get('comum')) == key]
        registry = registry_future.result()
    if members:
        # Vogais e cedilha podem vir com ou sem acento nas duas fontes.
        # O resultado ainda passa pela igualdade normalizada de nome e município do roster.
        patterns = {''.join('_' if c in 'AEIOUC' else c for c in norm(p.get('nome'))).replace(' ', '*') for p in members}
        conditions = ','.join('nome_aluno.ilike.' + json.dumps(pattern, ensure_ascii=False) for pattern in sorted(patterns) if pattern)
        if conditions:
            concordance = events._read('musica_acompanhamento_aluno', select=fields,
                                       **{'or': '(' + conditions + ')'}, order='id.asc')
            registry = list({str(p['id']): p for p in [*registry, *concordance]}.values())
    return registry, members, commons


def registered_people(include_inactive=False, common=None, query=None):
    if query:
        terms = norm(query).split()
        patterns = ['*' + ''.join('_' if c in 'AEIOUC' else c for c in term) + '*' for term in terms]
        conditions = ','.join('nome_aluno.ilike.' + json.dumps(pattern) for pattern in patterns)
        registry = events._read('musica_acompanhamento_aluno',
            select='id,nome_aluno,cargo_ministerio,status,instrumento,comum_congregacao,municipio',
            **{'and': '(' + conditions + ')'}, order='id.asc')
        members = [p for p in member_directory() if all(term in norm(p.get('nome')) for term in terms)]
        commons = catalog()
    elif common is not None:
        registry, members, commons = search_sources(common)
    else:
        registry, members, commons = events._registry(), member_directory(), catalog()
    if include_inactive:
        registry = [{**p, 'status': 'ATIVO'} for p in registry]
        members = [{**p, 'status': 'ATIVO'} for p in members]
    result = roster(registry, members, commons)
    from .music_conductor_identity import active_conductor, conductor_name
    output = []
    for person in result:
        if common is not None and code(person['comum']) != code(common['comum']):
            continue
        roles = [role for role in person['roles'] if role in PUBLIC_ROLES]
        if not include_inactive and not active_conductor(person['nome']):
            roles = [role for role in roles if role != 'ENCARREGADO_LOCAL']
        if not roles:
            continue
        output.append({**person, 'roles': roles, 'cargo': role_label(roles),
                       'nome': conductor_name(person['nome'], code(person['comum'])) if 'ENCARREGADO_LOCAL' in roles else person['nome']})
    return output


def people(fresh=False, common=None, query=None):
    # No envio, conferir novamente o cadastro; a pesquisa pode reutilizar a conciliação.
    if fresh:
        return registered_people()
    cache_key = PEOPLE_CACHE_KEY + (':query:' + hashlib.sha256(norm(query).encode()).hexdigest() if query else ':' + code(common['comum']) if common else '')
    prepared = cache.get(cache_key)
    if prepared is None:
        with _people_lock:
            prepared = cache.get(cache_key)
            if prepared is None:
                prepared = [{**person, '_common_code': code(person['comum']), '_search_name': norm(person['nome'])}
                            for person in registered_people(common=common, query=query)]
                cache.set(cache_key, prepared, 60)
    return prepared


def role_label(roles):
    return ' / '.join(ROLES[key] for key in canonical_roles(roles))


def canonical_roles(roles):
    result = list(dict.fromkeys(key for key in roles if key in ROLES))
    if {'SECRETARIO_MUSICA', 'SECRETARIA_MUSICA'}.intersection(result):
        result = [key for key in result if key != 'SECRETARIO_A_MUSICA']
    return result


def ensure_agenda_meeting(event, row, legacy, own, sites):
    """A agenda oficial cria o encontro de acompanhamento sem inventar presenças."""
    target = resolve_target(row, legacy, own, sites)
    if not target and event['tipo'] == 'REUNIAO_TECNICA':
        return ensure_agenda_technical(event, row, legacy, own, sites)
    if target or event['tipo'] != 'REUNIAO_MINISTERIO':
        return target
    matches = target_candidates(row, legacy, own, sites)
    if matches:
        # Mais de um encontro exige conferir a identidade, nunca escolher ao acaso.
        return None
    from .music_ministry import _rpc
    payload = {key: event[key] for key in ('titulo', 'tipo', 'data_evento', 'familia', 'municipios')}
    payload.update(modalidade='PRESENCIAL', local=event.get('local') or event['titulo'],
                   cargos=sorted(PUBLIC_ROLES), lista_completa=False, registros=[])
    try:
        result = _rpc('musica_ministerio_salvar', {'p_evento': payload, 'p_hash': None,
            'p_arquivo': None, 'p_usuario_id': 'agenda-musical', 'p_usuario_nome': 'Integração da Agenda Musical'})
        target = {**payload, 'id': result['id']}
    except ValueError:
        # Outra requisição pode ter criado o mesmo encontro pelo índice único.
        existing = events._read('musica_ministerio_eventos', data_evento='eq.' + event['data_evento'])
        exact = [e for e in target_candidates(row, legacy, existing, sites)
                 if norm(e['titulo']) == norm(event['titulo'])]
        if len(exact) != 1:
            raise
        target = exact[0]
    own.append(target)
    cache.delete(f"music-ministry:sources:v7:{event['data_evento'][:4]}")
    return target


def ensure_agenda_technical(event, row, legacy, own, sites):
    """Cadastra o encontro da agenda sem criar lista nominal ou presenças."""
    if target_candidates(row, legacy, own, sites):
        return None  # Ambiguidade exige conferência, não um terceiro evento.
    host_cities = title_cities(event['titulo'])
    if len(host_cities) != 1:
        raise ValueError('Confira o município da sede do ensaio técnico na agenda.')
    identity = str(uuid5(NAMESPACE_URL, 'regional-itapevi:agenda-tecnica:' + event['id']))
    existing = events._read('musica_eventos', id='eq.' + identity)
    payload = {'id': identity, 'titulo': event['titulo'], 'data_evento': event['data_evento'],
               'tipo': event['tipo'], 'familia': event['familia'], 'base_id': None, 'status': 'RASCUNHO',
               'created_by_user_id': 'agenda-musical', 'created_by_name': 'Integração da Agenda Musical',
               'updated_by_user_id': 'agenda-musical', 'updated_by_name': 'Integração da Agenda Musical',
               'observacoes': 'Evento da agenda oficial. Sem presenças ou base nominal presumidas.'}
    if not existing:
        response = requests.post(f'{settings.SUPABASE_URL}/rest/v1/musica_eventos',
            headers=service_headers('resolution=ignore-duplicates,return=minimal'),
            params={'on_conflict': 'id'}, json=payload, timeout=15)
        response.raise_for_status()
    location = {'id': str(uuid5(NAMESPACE_URL, identity + ':sede')), 'evento_id': identity,
                'nome': event.get('local') or host_cities[0].title(), 'municipio': host_cities[0]}
    if event.get('hora'):
        location['horario'] = event['hora']
    response = requests.post(f'{settings.SUPABASE_URL}/rest/v1/musica_evento_locais',
        headers=service_headers('resolution=ignore-duplicates,return=minimal'),
        params={'on_conflict': 'id'}, json=location, timeout=15)
    response.raise_for_status()
    # Receber justificativas não homologa a base nem abre a conferência de presenças.
    # O rascunho já possui identidade e sede para o vínculo nos painéis.
    target = events._read('musica_eventos', id='eq.' + identity)[0]
    if not any(e['id'] == identity for e in legacy):
        legacy.append(target)
    if not any(s['id'] == location['id'] for s in sites):
        sites.append(location)
    events._invalidate_annual()
    cache.delete(f"music-ministry:sources:v7:{event['data_evento'][:4]}")
    return target


def sync_agenda_links():
    rows = [row for row in submissions(require_available=True)
            if row['tipo'] in {'REUNIAO_MINISTERIO', 'REUNIAO_TECNICA'}
            and not (row.get('ministerio_evento_id') or row.get('evento_id'))]
    if not rows:
        return 0
    official = {event['id']: event for event in agenda()}
    legacy, own, sites = projection_context(rows)
    linked = 0
    for row in rows:
        event = official.get(row['agenda_id'])
        if not event or any(row.get(key) != event[key] for key in ('tipo', 'familia', 'data_evento')):
            continue
        if set(row['municipios']) != set(event['municipios']):
            continue
        target = ensure_agenda_meeting(event, row, legacy, own, sites)
        if not target:
            continue
        field = 'ministerio_evento_id' if row['tipo'] == 'REUNIAO_MINISTERIO' else 'evento_id'
        response = requests.patch(f'{settings.SUPABASE_URL}/rest/v1/{TABLE}',
            headers=service_headers('return=minimal'), params={'id': 'eq.' + row['id'], field: 'is.null'},
            json={field: target['id'], 'vinculado_por_id': 'agenda-musical',
                  'vinculado_por_nome': 'Integração da Agenda Musical'}, timeout=15)
        response.raise_for_status()
        cache.delete(f"music-ministry:sources:v7:{row['data_evento'][:4]}")
        linked += 1
    if linked:
        events._invalidate_annual()
    return linked


def with_roles(rows):
    """O vínculo persistido person_key recupera o cargo no cadastro e sua vigência SAM."""
    missing = [r for r in rows if 'roles' not in r and not str(r.get('person_key', '')).startswith('manual:')]
    aliases, changes, registry, member_roles = {}, {}, {}, {}
    if missing:
        people = registered_people(include_inactive=True)
        aliases = {alias: p for p in people for alias in p['aliases']}
        registry = {str(p['id']): p for p in events._registry() if p.get('id')}
        member_roles = {str(p['id']): set(roles_of(p.get('cargo_outros'))) & AUXILIARY_ROLES
                        for p in member_directory() if p.get('id')}
        for change in events._transitions():
            if change['campo'] == 'cargo_ministerio':
                changes.setdefault(str(change['aluno_id']), []).append(change)
    output = []
    for row in rows:
        roles = list(row.get('roles', []))
        if str(row.get('person_key', '')).startswith('manual:'):
            roles = canonical_roles([row['person_key'].split(':')[1]])
            row = {**row, 'roles': roles, 'cadastro_manual': True}
        if 'roles' not in row:
            person = aliases.get(row.get('person_key'))
            if person:
                roles = list(person['roles'])
                sam_id = next((alias.split(':', 1)[1] for alias in person['aliases'] if alias.startswith('sam:') and alias.split(':', 1)[1] in changes), None)
                if sam_id and sam_id in registry:
                    from .sam_temporal import state_at
                    state = state_at(registry[sam_id], changes[sam_id], row['data_evento'])
                    auxiliary = {role for alias in person['aliases'] if alias.startswith('irmandade:')
                                 for role in member_roles.get(alias.split(':', 1)[1], set())}
                    roles = sorted(auxiliary | (set(roles_of(state.get('cargo_ministerio'))) & PUBLIC_ROLES))
        roles = canonical_roles(roles)
        output.append({**row, 'roles': roles, 'cargo': role_label(roles) or 'Cargo a Conferir'})
    return output


def limited(request, action, maximum):
    # Não confiar em X-Forwarded-For enviado pelo cliente.
    address = request.META.get('REMOTE_ADDR', 'unknown')
    digest = hashlib.sha256(address.encode()).hexdigest()[:24]
    key = f'music-justification:rate:{action}:{digest}'
    if cache.add(key, 1, 60):
        return False
    try:
        return cache.incr(key) > maximum
    except ValueError:
        return False


@never_cache
@require_GET
def public_page(request):
    return render(request, 'pages/music_justification_public.html')


@never_cache
@require_http_methods(['GET', 'POST'])
def public_api(request):
    if limited(request, request.method, 15 if request.method == 'POST' else 90):
        return JsonResponse({'error': 'Aguarde um minuto antes de tentar novamente.'}, status=429)
    try:
        if request.method == 'POST':
            return submit(request)
        common_key, query = request.GET.get('comum', ''), request.GET.get('q', '').strip()
        if common_key:
            common = next((c for c in catalog() if code(c['comum']) == common_key), None)
            if not common:
                raise ValueError('Selecione uma comum válida.')
            if len(query) < 2:
                return JsonResponse({'people': []})
            terms = norm(query).split()
            matches = [p for p in people(common=common)
                       if code(p['comum']) == common_key and all(term in (p.get('_search_name') or norm(p['nome'])) for term in terms)]
            return JsonResponse({'people': [{'nome': p['nome'], 'cargo': p.get('cargo') or role_label(p.get('roles', [])),
                'comum': p['comum'], 'codigo': code(p['comum']), 'municipio': p.get('municipio', ''), 'token': signing.dumps(
                {'key': p['key'], 'nome': p['nome'], 'comum': code(p['comum'])}, salt=SALT)} for p in matches[:20]]})
        commons = catalog()
        official = agenda()
        upcoming = {e['id']: e for city in REGIONAL for e in event_window(official, city)}
        return JsonResponse({'commons': [{'codigo': code(c['comum']), 'nome': c['comum'],
                                          'municipio': regional_city(c['cidade'])} for c in commons],
                             'events': list(upcoming.values()), 'today': today()})
    except (ValueError, TypeError, signing.BadSignature) as exc:
        return JsonResponse({'error': str(exc) if not isinstance(exc, signing.BadSignature)
                             else 'Selecione novamente seu nome.'}, status=400)
    except requests.RequestException:
        return JsonResponse({'error': 'Não foi possível consultar a agenda ou salvar. Tente novamente.'}, status=502)


def submit(request):
    if len(request.body) > 12000:
        raise ValueError('Formulário excede o tamanho permitido.')
    raw = json.loads(request.body or '{}')
    if not isinstance(raw, dict):
        raise ValueError('Formulário inválido.')
    official = agenda()
    event = next((e for e in official if e['id'] == raw.get('evento')), None)
    if not event or event['data_evento'] < today():
        return JsonResponse({'error': 'O prazo deste evento foi encerrado. Selecione um evento futuro.'}, status=409)
    common = next((c for c in catalog() if code(c['comum']) == raw.get('comum')), None)
    if not common:
        raise ValueError('Selecione uma comum válida para identificar sua origem.')
    if raw.get('manual') is not None:
        raise ValueError('Selecione uma pessoa cadastrada na comum.')
    event_city = regional_city(common['cidade'])
    if raw.get('evento_municipio') and regional_city(raw['evento_municipio']) != event_city:
        raise ValueError('O município deve corresponder à comum selecionada.')
    if event_city not in event['municipios']:
        raise ValueError('Este evento não abrange o município da sua comum.')
    if event['id'] not in {e['id'] for e in event_window(official, event_city) if e['aberto']}:
        return JsonResponse({'error': 'Este evento ainda não está disponível. Selecione um dos dois próximos eventos.'}, status=409)
    selected = signing.loads(str(raw.get('pessoa') or ''), salt=SALT, max_age=3600)
    if not isinstance(selected, dict):
        raise ValueError('Selecione novamente seu nome.')
    person = next((p for p in people(fresh=True) if p['key'] == selected.get('key')
                   and code(p['comum']) == code(common['comum'])
                   and code(p['comum']) == selected.get('comum') and p['nome'] == selected.get('nome')), None)
    if not person:
        raise ValueError('Selecione uma pessoa ativa, com cargo musical cadastrado nesta comum.')
    reason = str(raw.get('motivo') or '').strip()
    if reason not in {'Trabalho', 'Viagem', 'Enfermidade', 'Outros'}:
        raise ValueError('Selecione Trabalho, Viagem, Enfermidade ou Outros.')
    if reason == 'Outros':
        detail = str(raw.get('detalhe') or '').strip()
        if not 5 <= len(detail) <= 492:
            raise ValueError('Indique o motivo da ausência, entre 5 e 492 caracteres.')
        reason = 'Outros: ' + detail
    person_identity = hashlib.sha256(f"{code(common['comum'])}|{norm(person['nome'])}".encode()).hexdigest()
    payload = {'agenda_id': event['id'], 'evento_titulo': event['titulo'], 'data_evento': event['data_evento'],
               'hora': event['hora'], 'tipo': event['tipo'], 'familia': event['familia'], 'local': event['local'],
               'municipios': event['municipios'], 'comum_codigo': code(common['comum']),
               'comum': common['comum'], 'municipio': regional_city(common['cidade']),
               'person_key': person['key'], 'pessoa_identidade': person_identity,
               'nome': person['nome'], 'motivo': reason}
    legacy, own, sites = projection_context([payload])
    target = ensure_agenda_meeting(event, payload, legacy, own, sites)
    if target:
        if target.get('status') == 'ENCERRADO':
            return JsonResponse({'error': 'Este evento já foi encerrado para justificativas.'}, status=409)
        field = 'ministerio_evento_id' if event['tipo'] == 'REUNIAO_MINISTERIO' else 'evento_id'
        payload[field] = target['id']
    response = requests.post(f'{settings.SUPABASE_URL}/rest/v1/{TABLE}',
                             headers=service_headers('return=minimal'), json=payload, timeout=15)
    if response.status_code == 409:
        return JsonResponse({'error': 'Já existe uma justificativa desta pessoa para este evento.'}, status=409)
    if response.status_code == 400 and 'Prazo de justificativas encerrado' in response.text:
        return JsonResponse({'error': 'O prazo deste evento foi encerrado.'}, status=409)
    response.raise_for_status()
    cache.delete(f"music-ministry:sources:v7:{event['data_evento'][:4]}")
    events._invalidate_annual()
    return JsonResponse({'saved': True, 'evento': event['titulo'], 'data': event['data_evento']}, status=201)


def submissions(require_available=False, **filters):
    try:
        return events._read(TABLE, order='created_at.desc,id.asc', **filters)
    except requests.HTTPError as exc:
        if not require_available and exc.response is not None and exc.response.status_code == 404:
            return []  # Compatibilidade dos painéis antes de aplicar a migração 062.
        raise


def target_candidates(row, legacy, own, sites):
    """Nunca decidir apenas por título, ou pelo subconjunto visível de um painel."""
    pool = own if row['tipo'] == 'REUNIAO_MINISTERIO' else legacy
    result = []
    for event in pool:
        if (str(event['data_evento']) != row['data_evento'] or event['tipo'] != row['tipo']
                or event.get('familia', 'GERAL') != row['familia']):
            continue
        if row['tipo'] == 'REUNIAO_MINISTERIO':
            municipalities = {norm(regional_city(c)) for c in event.get('municipios', [])}
            compatible = bool(municipalities.intersection(norm(regional_city(c)) for c in row.get('municipios', [row['municipio']])))
        else:
            locations = [s for s in sites if s['evento_id'] == event['id']]
            # O evento consolidado pode reunir várias sedes. Conferir a sede da agenda,
            # não a comum de origem do participante.
            named_location = norm(row.get('local'))
            # Cada sede deve satisfazer as duas condições; não combinar a cidade
            # de uma sede com o nome de outra sede do evento consolidado.
            compatible = any(regional_city(s['municipio']) in row['municipios'] and (
                not named_location or named_location == norm(s['nome']) or
                named_location in norm(s['nome']) or norm(s['nome']) in named_location or
                any(part.strip() == norm(s['nome']) for part in named_location.split('/')))
                for s in locations if s.get('nome'))
        if compatible:
            result.append(event)
    return result


def resolve_target(row, legacy, own, sites):
    explicit = row.get('evento_id') or row.get('ministerio_evento_id')
    if explicit:
        pool = own if row.get('ministerio_evento_id') else legacy
        return next((e for e in pool if e['id'] == explicit and str(e['data_evento']) == row['data_evento']
                     and e['tipo'] == row['tipo'] and e.get('familia', 'GERAL') == row['familia']), None)
    matches = target_candidates(row, legacy, own, sites)
    return matches[0] if len(matches) == 1 else None


def projection_context(rows):
    days = sorted({r['data_evento'] for r in rows})
    if not days:
        return [], [], []
    day_filter = 'in.(' + ','.join(days) + ')'
    legacy = events._latest_event_versions(events._read('musica_eventos', data_evento=day_filter))
    own = events._read('musica_ministerio_eventos', data_evento=day_filter) if any(
        r['tipo'] == 'REUNIAO_MINISTERIO' for r in rows) else []
    sites = []
    for start in range(0, len(legacy), 40):
        ids = 'in.(' + ','.join(e['id'] for e in legacy[start:start + 40]) + ')'
        sites.extend(events._read('musica_evento_locais', evento_id=ids))
    return legacy, own, sites


def public_reviews(chosen_events):
    days = sorted({str(e['data_evento']) for e in chosen_events if e.get('data_evento')})
    if not days:
        return []
    rows = with_roles([r for r in submissions(data_evento='in.(' + ','.join(days) + ')') if r.get('agenda_id')])
    if not rows:
        return []
    legacy, own, sites = projection_context(rows)
    selected = {e['id'] for e in chosen_events}
    result = []
    for row in rows:
        target = resolve_target(row, legacy, own, sites)
        if target and target['id'] in selected and row['tipo'] != 'REUNIAO_MINISTERIO' and 'ENCARREGADO_LOCAL' in row['roles']:
            result.append({'id': row['id'], 'evento_id': target['id'], 'comum_chave': row['comum_codigo'],
                           'comum_nome': row['comum'], 'municipio': row['municipio'],
                           'encarregado_nome': row['nome'], 'situacao': 'JUSTIFICOU', 'local_id': None,
                           'observacoes': row['motivo'], 'updated_at': row['created_at'], 'origem_publica': True})
    return result


def ministry_projection(legacy, own):
    days = sorted({str(e['data_evento']) for e in [*legacy, *own]})
    if not days:
        return [], []
    rows = with_roles([r for r in submissions(data_evento='in.(' + ','.join(days) + ')') if r.get('agenda_id')])
    if not rows:
        return [], []
    all_legacy, all_own, sites = projection_context(rows)
    selected_legacy, selected_own = {e['id'] for e in legacy}, {e['id'] for e in own}
    result_legacy, result_own = [], []
    for row in rows:
        target = resolve_target(row, all_legacy, all_own, sites)
        if not target or not row['roles']:
            continue
        item = {'event_id': target['id'], 'person_key': row['person_key'], 'nome': row['nome'],
                'comum': row['comum'], 'municipio': row['municipio'], 'roles': row['roles'],
                'situacao': 'JUSTIFICOU', 'observacoes': row['motivo'], 'version': 0,
                'source': {'justificativa_publica': row['id']}}
        if row['tipo'] == 'REUNIAO_MINISTERIO' and target['id'] in selected_own:
            result_own.append(item)
        elif row['tipo'] != 'REUNIAO_MINISTERIO' and target['id'] in selected_legacy:
            result_legacy.append(item)
    return result_legacy, result_own


def merge_ministry_entries(existing, projected, people):
    """Concilia aliases SAM/irmandade sem apagar uma presença já conferida."""
    aliases = {alias: person['key'] for person in people for alias in person['aliases']}
    def identity(row):
        known = aliases.get(row['person_key'])
        if known:
            return known
        matches = [p for p in people if norm(p['nome']) == norm(row['nome']) and code(p['comum']) == code(row['comum'])]
        return matches[0]['key'] if len(matches) == 1 else row['person_key']
    result = list(existing)
    for row in projected:
        key = identity(row)
        prior = [r for r in result if r['event_id'] == row['event_id'] and identity(r) == key]
        if any(r['situacao'] == 'PRESENTE' for r in prior):
            continue
        result = [r for r in result if not (r['event_id'] == row['event_id'] and identity(r) == key)]
        result.append({**row, 'person_key': key})
    return result


def historical_sources():
    """Mesmas versões e mesmas justificativas individuais usadas nos ensaios."""
    from .music_events_justifications import individual_items
    legacy = events._latest_event_versions(events._read('musica_eventos', order='data_evento.desc,id.asc'))
    try:
        own = events._read('musica_ministerio_eventos', order='data_evento.desc,id.asc')
    except requests.HTTPError as exc:
        if exc.response is None or exc.response.status_code != 404:
            raise
        own = []
    source = events._read('musica_evento_encarregados', situacao='eq.JUSTIFICOU', order='created_at.desc,id.asc')
    legacy_map = {e['id']: e for e in legacy}
    own_map = {e['id']: e for e in own if e['tipo'] in KINDS}
    rows = []
    for item in individual_items(source):
        event = legacy_map.get(item['evento_id'])
        if not event:
            continue
        rows.append({**item, 'agenda_id': 'legado:' + event['id'], 'evento_id': event['id'],
                     'evento_titulo': event['titulo'], 'data_evento': str(event['data_evento']),
                     'tipo': event['tipo'], 'familia': event.get('familia', 'GERAL'), 'hora': '', 'local': '',
                     'comum_codigo': item['comum_chave'], 'comum': item['comum_nome'],
                     'municipio': regional_city(item['municipio']), 'destino': event['id'],
                     'roles': ['ENCARREGADO_LOCAL'], 'cargo': 'Encarregado Local',
                     'event_key': 'legado:' + event['id'], 'candidates': []})
    for start in range(0, len(own_map), 40):
        ids = list(own_map)[start:start+40]
        for item in events._read('musica_ministerio_participacoes', event_id='in.(' + ','.join(ids) + ')', situacao='eq.JUSTIFICOU'):
            if not PUBLIC_ROLES.intersection(item.get('roles', [])) or item.get('situacao') != 'JUSTIFICOU':
                continue
            event = own_map[item['event_id']]
            rows.append({'id': item['event_id'] + ':' + item['person_key'], 'person_key': item['person_key'],
                         'agenda_id': 'ministerio:' + event['id'], 'ministerio_evento_id': event['id'],
                         'evento_titulo': event['titulo'], 'data_evento': str(event['data_evento']),
                         'tipo': event['tipo'], 'familia': event.get('familia', 'GERAL'), 'hora': '', 'local': event['local'],
                         'comum_codigo': code(item['comum']), 'comum': item['comum'], 'municipio': regional_city(item['municipio']),
                         'nome': item['nome'], 'motivo': item['observacoes'], 'created_at': item['updated_at'],
                         'roles': item['roles'], 'cargo': role_label(item['roles']),
                         'destino': event['id'], 'event_key': 'ministerio:' + event['id'], 'candidates': []})
    sites = []
    for start in range(0, len(legacy), 40):
        sites.extend(events._read('musica_evento_locais', evento_id='in.(' + ','.join(e['id'] for e in legacy[start:start+40]) + ')'))
    return rows, legacy, own, sites


@require_GET
def page(request):
    if not events._allowed(request):
        return render(request, 'pages/403.html', status=403)
    return render(request, 'pages/music_justifications.html', {'scope': scope_details(user_scope(request))})


def delete_record(request, raw):
    # O token assinado identifica as fontes reais, inclusive cópias já conciliadas.
    if user_scope(request)['level'] != 'global':
        return JsonResponse({'error': 'Somente o nível Global pode excluir justificativas.'}, status=403)
    try:
        refs = signing.loads(str(raw.get('token') or ''), salt='music-justification-delete', max_age=3600)
    except signing.BadSignature:
        raise ValueError('Seleção expirada ou inválida. Atualize a lista.')
    from .music_ministry import _actor
    actor_id, actor_name = _actor(request)
    if not actor_id or not actor_name:
        return JsonResponse({'error': 'Entre novamente para identificar o responsável.'}, status=401)
    for ref in refs:
        if ref['source'] == 'legacy':
            from .music_events_justifications import manage_grouped
            result = manage_grouped(request, {'id': ref['event']}, 'excluir', actor_id, {'ids': [ref['id']]})
            if result.status_code != 200:
                return result
        else:
            response = requests.post(f'{settings.SUPABASE_URL}/rest/v1/rpc/musica_justificativa_excluir',
                headers=service_headers(), json={'p_source': ref['source'], 'p_id': ref.get('id'),
                    'p_event': ref.get('event'), 'p_person': ref.get('person'),
                    'p_actor': actor_id, 'p_name': actor_name}, timeout=15)
            if response.status_code == 404:
                return JsonResponse({'error': 'A exclusão requer a migration 063_musica_justificativas_exclusao.sql. A migration 062 já atende ao formulário.'}, status=503)
            response.raise_for_status()
            if not response.json().get('deleted'):
                return JsonResponse({'error': 'O registro já foi alterado. Atualize a lista.'}, status=409)
        cache.delete(f"music-ministry:sources:v7:{ref['year']}")
        events._invalidate_annual()
    from ColorAdminApp.views import log_audit
    log_audit(request, 'DELETE', 'MUSICA_JUSTIFICATIVAS', {'fontes': refs, 'responsavel': actor_name})
    return JsonResponse({'deleted': True})


@require_http_methods(['GET', 'POST'])
def dashboard_api(request):
    if not events._allowed(request):
        return JsonResponse({'error': 'Acesso não autorizado.'}, status=403)
    scope = user_scope(request)
    manager = scope['level'] in {'regional', 'global'}
    try:
        if request.method == 'POST':
            raw = json.loads(request.body or '{}')
            if not isinstance(raw, dict):
                raise ValueError('Informe uma operação válida.')
            if raw.get('action') == 'delete':
                return delete_record(request, raw)
            if raw.get('action') == 'sync_agenda':
                if not manager:
                    return JsonResponse({'error': 'Acesso não autorizado.'}, status=403)
                return JsonResponse({'linked': sync_agenda_links()})
            if not manager:
                return JsonResponse({'error': 'Somente a administração regional pode vincular eventos.'}, status=403)
            raw = json.loads(request.body or '{}')
            if not isinstance(raw, dict):
                raise ValueError('Informe a justificativa e o evento de destino.')
            justification_id = str(UUID(str(raw.get('id') or '')))
            target_id = str(UUID(str(raw.get('destino') or '')))
            rows = submissions(require_available=True, id='eq.' + justification_id)
            if not rows:
                raise ValueError('Justificativa não encontrada.')
            row = rows[0]
            legacy, own, sites = projection_context([row])
            target = next((e for e in target_candidates(row, legacy, own, sites) if e['id'] == target_id), None)
            if not target:
                raise ValueError('Selecione um evento de mesma data, tipo, família e abrangência.')
            from .music_ministry import _actor
            actor_id, actor_name = _actor(request)
            field = 'ministerio_evento_id' if row['tipo'] == 'REUNIAO_MINISTERIO' else 'evento_id'
            response = requests.patch(f'{settings.SUPABASE_URL}/rest/v1/{TABLE}',
                headers=service_headers('return=minimal'), params={'id': 'eq.' + row['id']},
                json={field: target['id'], 'vinculado_por_id': actor_id, 'vinculado_por_nome': actor_name}, timeout=15)
            response.raise_for_status()
            cache.delete(f"music-ministry:sources:v7:{row['data_evento'][:4]}")
            events._invalidate_annual()
            return JsonResponse({'saved': True})
        return JsonResponse(dashboard_data(request))
    except (ValueError, TypeError, KeyError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except requests.RequestException:
        logging.getLogger(__name__).exception('Falha no painel de justificativas (%s)', request.method)
        return JsonResponse({'error': 'Não foi possível concluir a operação no banco. Tente novamente; se persistir, confira o log do servidor.'}, status=502)


def dashboard_data(request):
    from .music_exams import GROUPS, regional_group
    scope = user_scope(request)
    manager = scope['level'] in {'regional', 'global'}
    visible = lambda row: can_access(scope, {'comum': row['comum'], 'cidade': row['municipio']})
    historical, legacy, own, sites = historical_sources()
    historical = [r for r in historical if visible(r)]
    public = with_roles([r for r in submissions() if visible(r)])
    rows = list(historical)
    for row in public:
        target = resolve_target(row, legacy, own, sites)
        key = ('ministerio:' if row['tipo'] == 'REUNIAO_MINISTERIO' else 'legado:') + target['id'] if target else 'agenda:' + row['agenda_id']
        rows.append({**row, 'destino': target['id'] if target else None, 'event_key': key,
                     'candidates': [{'id': e['id'], 'titulo': e['titulo']} for e in target_candidates(row, legacy, own, sites)] if manager and not target else []})
    # Uma justificativa já importada/conferida tem precedência sobre a cópia pública.
    unique = {}
    for row in rows:
        identity = (row['event_key'], code(row['comum']), norm(row['nome']))
        ref = {'year': row['data_evento'][:4]}
        if row['agenda_id'].startswith('legado:'):
            ref.update(source='legacy', event=row['evento_id'], id=row['id'])
        elif row['agenda_id'].startswith('ministerio:'):
            ref.update(source='ministry', event=row['ministerio_evento_id'], person=row['person_key'])
        else:
            ref.update(source='public', id=row['id'])
        existing = unique.setdefault(identity, {**row, '_delete_refs': []})
        existing['_delete_refs'].append(ref)
    rows = list(unique.values())
    for row in rows:
        refs = row.pop('_delete_refs')
        host_cities = title_cities(row['evento_titulo'])
        row['fora_municipio'] = bool(len(row.get('municipios', [])) == 1 and host_cities
                                     and regional_city(row['municipio']) not in host_cities)
        row['cadastro_manual'] = str(row.get('person_key', '')).startswith('manual:')
        if scope['level'] == 'global':
            row['delete_token'] = signing.dumps(refs, salt='music-justification-delete', compress=True)
        path = '/musica/ministerio/' if row['tipo'] == 'REUNIAO_MINISTERIO' else (
            '/musica/ensaios-regionais/' if row['tipo'] == 'ENSAIO_REGIONAL' else '/musica/reunioes-tecnicas/')
        row['destino_url'] = path + (f"?evento={row['destino']}&ano={row['data_evento'][:4]}" if row['destino'] else '')
    visible_catalog = [c for c in catalog() if can_access(scope, c)]
    city_names = {regional_city(c['cidade']) for c in visible_catalog} | {r['municipio'] for r in rows}
    common_options = {(c['comum'], regional_city(c['cidade'])) for c in visible_catalog}
    common_options.update((r['comum'], r['municipio']) for r in rows)
    event_options = {}
    def add_event(key, title, day, kind):
        if kind not in KINDS:
            return
        formatted = '/'.join(day.split('-')[::-1])
        event_options[key] = {'id': key, 'titulo': title if formatted in title else f'{title} · {formatted}',
                              'data': day, 'tipo': kind}
    for row in rows:
        add_event(row['event_key'], row['evento_titulo'], row['data_evento'], row['tipo'])
    if manager:
        for event in legacy:
            add_event('legado:' + event['id'], event['titulo'], str(event['data_evento']), event['tipo'])
        for event in own:
            add_event('ministerio:' + event['id'], event['titulo'], str(event['data_evento']), event['tipo'])
    agenda_unavailable = False
    try:
        for event in agenda():
            if event['data_evento'] < today() or not set(event['municipios']).intersection(city_names):
                continue
            target = resolve_target({**event, 'municipio': event['municipios'][0]}, legacy, own, sites)
            key = ('ministerio:' if event['tipo'] == 'REUNIAO_MINISTERIO' else 'legado:') + target['id'] if target else 'agenda:' + event['id']
            add_event(key, event['titulo'], event['data_evento'], event['tipo'])
    except requests.RequestException:
        agenda_unavailable = True
    options = {'cities': sorted(city_names),
               'commons': [{'id': common, 'titulo': common, 'municipio': city} for common, city in sorted(common_options)],
               'events': sorted(event_options.values(), key=lambda e: (e['data'], e['titulo']), reverse=True)}
    for field, query in [('municipio', 'municipio'), ('comum', 'comum')]:
        if request.GET.get(query):
            rows = [r for r in rows if r[field] == request.GET[query]]
    selected = request.GET.get('evento')
    if selected:
        rows = [r for r in rows if r['event_key'] == selected or r['agenda_id'] == selected or 'agenda:' + r['agenda_id'] == selected]
    groups = []
    for group in GROUPS:
        records = [r for r in rows if regional_group(r['municipio']) == group]
        groups.append({'name': group, 'total': len(records),
                       **{kind: sum(r['tipo'] == kind for r in records) for kind in KINDS}})
    rows.sort(key=lambda r: (r['data_evento'], r.get('created_at') or '', r['nome']), reverse=True)
    return {'items': rows, 'options': options, 'can_manage': manager, 'can_delete': scope['level'] == 'global', 'groups': groups,
            'agenda_unavailable': agenda_unavailable,
            'metrics': {'total': len(rows), **{k: sum(r['tipo'] == k for r in rows) for k in KINDS},
                        'pendentes': sum(not r['destino'] for r in rows)}}
