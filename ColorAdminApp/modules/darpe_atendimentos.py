"""Papeletas DARPE: uma API para a administração e o aplicativo mobile."""
import json
import logging
from copy import copy
from datetime import date, datetime, time
from urllib.parse import quote
from uuid import UUID
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import darpe
from .access_control import can_access, common_catalog, scope_details, service_headers, user_scope
from .darpe_library import SECTORS
from .module_access import MODULE_DARPE, can_access_module

logger = logging.getLogger(__name__)
TABLE = {'table': 'darpe_papeletas'}
ROLES = {'atendente': ('darpe_atendente',), 'colaborador': ('darpe_colaborador',),
         'musico': ('darpe_musico',), 'organista': ('darpe_organista',),
         'oracao': ('darpe_atendente', 'darpe_colaborador', 'darpe_ministerio'),
         'palavra': ('darpe_atendente', 'darpe_ministerio')}
PRAYERS = ('enfermidades', 'acidentados', 'tribulacoes', 'familias', 'causas', 'testemunhados', 'viagens')
# A papeleta possui sete categorias; “Todas” é exclusivo de famílias.


def rows(config, filters=None):
    return darpe._read_all_rows(config, filters=filters)


def read_profile(user_id):
    # profiles tem user_id como identidade; não possui a coluna id usada
    # pelo leitor genérico de cadastros/papeletas.
    response = requests.get(settings.SUPABASE_URL + '/rest/v1/profiles', headers=service_headers(),
                            params={'user_id': 'eq.' + user_id, 'select': '*', 'limit': 2}, timeout=15)
    response.raise_for_status()
    return response.json()


def audit_mobile(request, action, details):
    profile = request.session['user_profile']
    payload = {
        'user_id': request.session['user_id'],
        'action': action,
        'module': 'DARPE',
        'details': {
            'schema_version': 2,
            'source': 'APP_DARPE',
            'actor': {
                'user_id': request.session['user_id'],
                'name': profile.get('full_name') or profile.get('username') or 'Usuário autenticado',
                'role_id': profile.get('role_id'),
                'scope': profile.get('sector') or profile.get('setor'),
            },
            'request': {'method': request.method, 'path': request.path},
            **details,
        },
        'ip_address': request.META.get('REMOTE_ADDR'),
        'user_agent': str(request.META.get('HTTP_USER_AGENT') or '')[:1000],
    }
    response = requests.post(
        settings.SUPABASE_URL + '/rest/v1/audit_logs',
        headers=service_headers('return=minimal'), json=payload, timeout=15,
    )
    response.raise_for_status()


def database_error(exc):
    response = getattr(exc, 'response', None)
    try:
        code = response.json().get('code') if response is not None else None
    except (ValueError, AttributeError):
        code = None
    if code in {'PGRST204', 'PGRST205', '42P01', '42703'}:
        return JsonResponse({'error': 'O servidor precisa concluir a atualização das papeletas DARPE antes de registrar atendimentos. Informe a administração.',
                             'code': 'darpe_schema_missing'}, status=503)
    return JsonResponse({'error': 'Não foi possível confirmar a operação. Confira a lista antes de tentar novamente.'}, status=503)


def in_scope(scope, row):
    if not can_access(scope, row):
        return False
    # Comuns homônimas (como Central) de municípios diferentes não se confundem.
    return scope['level'] != 'local' or bool(scope['municipio'] and
        darpe._norm(scope['municipio']) == darpe._norm(row.get('municipio') or row.get('cidade')))


def people(request):
    data = rows(darpe.RESOURCES['cadastros'], {'status': 'eq.ATIVO'})
    scope = user_scope(request)
    return [r for r in [{**p, 'comum': p.get('comum_congregacao')} for p in data] if in_scope(scope, r)]


def eligible(row, role):
    if role in ('musico', 'organista') and not any(
            field in row for field in ('darpe_musico', 'darpe_organista')):
        musician, organist = darpe._musical_flags(
            row.get('instrumento_oficializado'), row.get('sexo'),
            row.get('darpe_musico_organista') is True)
        return row.get('status') == 'ATIVO' and (musician if role == 'musico' else organist)
    return row.get('status') == 'ATIVO' and any(row.get(field) is True for field in ROLES.get(role, ()))


def public_person(row):
    return {'id': row['id'], 'nome': row['nome_completo'], 'comum': row.get('comum_congregacao'),
            'municipio': row.get('cidade'), 'instrumento': row.get('instrumento_oficializado') or ''}


def selected_filters(params, key):
    values = params.getlist(key) if hasattr(params, 'getlist') else params.get(key, [])
    if isinstance(values, str):
        values = [values]
    return [str(value).strip() for value in values if str(value).strip()]


def filtered(data, params):
    for key in ('municipio', 'comum', 'setor'):
        selected = {darpe._norm(v) for v in selected_filters(params, key)}
        if selected:
            data = [r for r in data if darpe._norm(str(r.get(key))) in selected]
    if params.get('data'):
        data = [r for r in data if r['data'] == params['data']]
    if params.get('ano'):
        data = [r for r in data if r['data'][:4] == params['ano']]
    if params.get('mes'):
        data = [r for r in data if int(r['data'][5:7]) == int(params['mes'])]
    for key, comparison in [('inicio', lambda a, b: a >= b), ('fim', lambda a, b: a <= b)]:
        if params.get(key):
            limit = date.fromisoformat(params[key]).isoformat()
            data = [r for r in data if comparison(r['data'], limit)]
    if params.get('q'):
        terms = darpe._norm(params['q']).split()
        data = [r for r in data if all(t in darpe._norm(' '.join([r['local'], r['municipio'], r['comum'],
                    ' '.join(p['nome'] for p in r['equipe'])])) for t in terms)]
    return data


def visible_records(request):
    scope = user_scope(request)
    return [r for r in rows(TABLE) if in_scope(scope, r)]


def localities(scope):
    """Catálogo oficial independente da existência de papeletas no período."""
    result, seen = [], set()
    for row in common_catalog():
        city, common = str(row.get('cidade') or '').strip(), str(row.get('comum') or '').strip()
        key = (darpe._norm(city), darpe._norm(common))
        if city and common and key not in seen and in_scope(scope, {'municipio': city, 'comum': common}):
            seen.add(key)
            result.append({'municipio': city, 'comum': common})
    return sorted(result, key=lambda r: (darpe._norm(r['municipio']), darpe._norm(r['comum'])))


def validate(payload, request):
    if not isinstance(payload, dict):
        raise ValueError('Informe os dados do atendimento.')
    result = {}
    for key, limit in [('local', 200), ('municipio', 100), ('comum', 200), ('palavra', 200),
                       ('participacao', 1000), ('observacoes', 3000),
                       ('whatsapp', 20), ('telefone', 20)]:
        value = payload.get(key, '')
        if not isinstance(value, str) or len(value.strip()) > limit:
            raise ValueError(f'Campo {key}: limite de {limit} caracteres.')
        result[key] = value.strip()
    for key in ('whatsapp', 'telefone'):
        digits = ''.join(char for char in result[key] if char.isdigit())
        if result[key] and (len(digits) < 8 or len(digits) > 15 or
                            any(char not in '+ ()-.' and not char.isdigit() for char in result[key])):
            raise ValueError(f'Informe um número válido para {key}.')
    if not all(result[k] for k in ('local', 'municipio', 'comum')):
        raise ValueError('Informe local, município e comum responsável pelo atendimento.')
    scope = user_scope(request)
    if scope['comum']:
        if darpe._norm(result['comum']) != darpe._norm(scope['comum']):
            raise PermissionError('A comum do atendimento deve ser a comum vinculada ao seu cadastro DARPE.')
        result['comum'] = scope['comum']
        if scope['municipio']:
            if darpe._norm(result['municipio']) != darpe._norm(scope['municipio']):
                raise PermissionError('O município do atendimento deve corresponder ao município do seu cadastro DARPE.')
            result['municipio'] = scope['municipio']
    if not in_scope(scope, result):
        raise PermissionError('O atendimento está fora do seu escopo territorial.')
    result['data'] = date.fromisoformat(payload.get('data', '')).isoformat()
    if result['data'] > timezone.localdate().isoformat():
        raise ValueError('Lance apenas atendimentos já realizados.')
    for key in ('hora_inicio', 'hora_fim'):
        value = payload.get(key, '')
        result[key] = time.fromisoformat(value).strftime('%H:%M')
    if result['hora_fim'] < result['hora_inicio']:
        raise ValueError('O horário final deve ser igual ou posterior ao inicial.')
    sector = payload.get('setor')
    if type(sector) is not int or sector not in {1, 2, 3, 4}:
        raise ValueError('Selecione um dos quatro setores do DARPE.')
    result['setor'] = sector
    hymns = payload.get('hinos', [])
    if not isinstance(hymns, list) or len(hymns) > 30 or any(type(h) is not int or not 1 <= h <= 480 for h in hymns):
        raise ValueError('Informe hinos entre 1 e 480.')
    result['hinos'] = hymns
    prayers = payload.get('pedidos_oracao', {})
    if not isinstance(prayers, dict) or set(prayers) - set(PRAYERS):
        raise ValueError('Pedidos de oração inválidos.')
    result['pedidos_oracao'] = {}
    for key in PRAYERS:
        count = prayers.get(key, 0)
        if not (key == 'familias' and count == 'todas') and (type(count) is not int or not 0 <= count <= 99999):
            raise ValueError('Pedidos de oração: use quantidades inteiras; famílias também admite Todas.')
        result['pedidos_oracao'][key] = count
    participants = payload.get('equipe', [])
    if not isinstance(participants, list) or not 1 <= len(participants) <= 200:
        raise ValueError('Informe a equipe do atendimento (até 200 participações).')
    available = {str(r['id']): r for r in people(request)}
    team, seen = [], set()
    for item in participants:
        if not isinstance(item, dict):
            raise ValueError('Participação inválida.')
        key, role = str(item.get('cadastro_id', '')), item.get('funcao')
        person = available.get(key)
        if not person or not eligible(person, role):
            raise ValueError('Selecione somente pessoas ativas e habilitadas para a função no cadastro DARPE.')
        if (key, role) in seen:
            raise ValueError('A pessoa já foi selecionada nesta função.')
        seen.add((key, role))
        team.append({'cadastro_id': key, 'funcao': role, 'nome': person['nome_completo']})
    if sum(p['funcao'] == 'atendente' for p in team) != 1:
        raise ValueError('Selecione exatamente um atendente responsável.')
    if sum(p['funcao'] == 'palavra' for p in team) > 1:
        raise ValueError('Selecione apenas um irmão para a palavra.')
    result['equipe'] = team
    return result


@never_cache
def page(request):
    if not request.session.get('user_id') or not can_access_module(request, MODULE_DARPE):
        return render(request, 'pages/403.html', status=403)
    return render(request, 'pages/darpe_atendimentos.html', {'scope': scope_details(user_scope(request))})


@never_cache
@require_http_methods(['GET', 'POST', 'PATCH', 'DELETE'])
def api(request, action='atendimentos'):
    if not request.session.get('user_id') or not can_access_module(request, MODULE_DARPE):
        return JsonResponse({'error': 'Acesso DARPE não autorizado.'}, status=403)
    try:
        if action == 'contexto' and request.method == 'GET':
            scope = user_scope(request)
            return JsonResponse({'setores': [{'id': n, 'nome': title} for n, title, _ in SECTORS],
                                 'escopo': {k: scope[k] for k in ('level', 'municipio', 'comum')},
                                 'usuario': {'nome': darpe._actor(request)['name']},
                                 'localidades': localities(scope)})
        if action == 'pessoas' and request.method == 'GET':
            role = request.GET.get('funcao', '')
            query = darpe._norm(request.GET.get('q', '')).split()
            if role not in ROLES:
                raise ValueError('Selecione uma função válida.')
            if len(request.GET.get('q', '').strip()) < 2:
                return JsonResponse({'items': []})
            matches = [public_person(r) for r in people(request) if eligible(r, role)
                       and all(t in darpe._norm(r['nome_completo']) for t in query)]
            matches.sort(key=lambda r: r['nome'])
            return JsonResponse({'items': matches[:40]})
        if action != 'atendimentos':
            raise ValueError('Operação inválida.')
        if request.method == 'GET':
            data = filtered(visible_records(request), request.GET)
            data.sort(key=lambda r: (r['data'], r['hora_inicio']), reverse=True)
            return JsonResponse({'items': data})
        payload = json.loads(request.body)
        if request.method in ('PATCH', 'DELETE'):
            record_id = str(UUID(str(payload.get('id', ''))))
            existing = rows(TABLE, {'id': 'eq.' + record_id})
            if not existing:
                return JsonResponse({'error': 'Atendimento não encontrado.'}, status=404)
            if not in_scope(user_scope(request), existing[0]):
                raise PermissionError('O atendimento está fora do seu escopo territorial.')
            headers = {**service_headers(), 'Prefer': 'return=representation'}
            params = {'id': 'eq.' + record_id}
            if request.method == 'DELETE':
                response = requests.delete(darpe._url(TABLE), headers=headers, params=params, timeout=30)
            else:
                result = validate(payload, request)
                for key in ('whatsapp', 'telefone'):
                    if key not in payload:
                        result[key] = existing[0].get(key, '')
                response = requests.patch(darpe._url(TABLE), headers=headers, params=params, json=result, timeout=30)
            response.raise_for_status()
            changed = response.json()
            if not changed:
                return JsonResponse({'error': 'O atendimento não está mais disponível. Atualize a lista.'}, status=404)
            return JsonResponse({'item': changed[0], 'message': 'Atendimento excluído.' if request.method == 'DELETE' else 'Atendimento atualizado.'})
        result = validate(payload, request)
        # ID da submissão torna a repetição após perda de conexão idempotente.
        result['id'] = str(UUID(str(payload.get('id', ''))))
        actor = darpe._actor(request)
        result.update(created_by=actor['id'], created_by_name=actor['name'])
        response = requests.post(darpe._url(TABLE), headers={**service_headers(), 'Prefer': 'return=representation'}, json=result, timeout=30)
        if response.status_code == 409:
            existing = rows(TABLE, {'id': 'eq.' + result['id']})
            if existing and existing[0].get('created_by') == actor['id'] and in_scope(user_scope(request), existing[0]):
                return JsonResponse({'item': existing[0], 'message': 'Atendimento já registrado.'})
            return JsonResponse({'error': 'Identificador já utilizado. Atualize a página.'}, status=409)
        response.raise_for_status()
        return JsonResponse({'item': response.json()[0], 'message': 'Atendimento registrado.'}, status=201)
    except PermissionError as exc:
        return JsonResponse({'error': str(exc)}, status=403)
    except (ValueError, TypeError, AttributeError) as exc:
        return JsonResponse({'error': str(exc) or 'Confira os campos da papeleta.'}, status=400)
    except requests.RequestException as exc:
        return database_error(exc)


@csrf_exempt
@never_cache
@require_http_methods(['GET', 'POST', 'PATCH'])
def mobile_api(request, action='atendimentos'):
    """Exceção CSRF restrita a Bearer validado; cookies nunca autenticam esta rota."""
    token = request.headers.get('Authorization', '')
    if not token.startswith('Bearer ') or len(token) > 10000:
        return JsonResponse({'error': 'Faça login para continuar.'}, status=401)
    try:
        auth = requests.get(settings.SUPABASE_URL + '/auth/v1/user',
                            headers={'apikey': settings.SUPABASE_ANON_KEY, 'Authorization': token}, timeout=15)
        if not auth.ok:
            return JsonResponse({'error': 'Sessão expirada.'}, status=401)
        user_id = str(UUID(auth.json()['id']))
        profiles = read_profile(user_id)
        if len(profiles) != 1 or profiles[0].get('status') != 'approved':
            return JsonResponse({'error': 'Seu cadastro precisa de aprovação para acessar o DARPE.'}, status=403)
        # Não persistir a autenticação Bearer na sessão de navegação Django.
        proxy = copy(request)
        proxy.session = {'user_id': user_id, 'authenticated': True, 'user_profile': profiles[0]}
        if action == 'audit-login' and request.method == 'POST':
            if not can_access_module(proxy, MODULE_DARPE):
                return JsonResponse({'error': 'Acesso DARPE não autorizado.'}, status=403)
            audit_mobile(proxy, 'LOGIN', {'description': 'Login realizado no aplicativo DARPE.'})
            return JsonResponse({'message': 'Acesso registrado.'}, status=201)
        if action == 'exportar-pdf' and request.method == 'GET':
            from .darpe_atendimentos_exports import build_papeleta_pdf
            from .darpe import _actor

            if not can_access_module(proxy, MODULE_DARPE):
                return JsonResponse({'error': 'Acesso DARPE não autorizado.'}, status=403)
            try:
                record_id = str(UUID(request.GET.get('id', '')))
            except (ValueError, TypeError, AttributeError):
                return JsonResponse({'error': 'Identificador de atendimento inválido.'}, status=400)
            records = rows(TABLE, {'id': 'eq.' + record_id})
            if not records or not in_scope(user_scope(proxy), records[0]):
                return JsonResponse({'error': 'Atendimento não encontrado no seu escopo.'}, status=404)
            now = datetime.now(ZoneInfo('America/Sao_Paulo'))
            response = HttpResponse(
                build_papeleta_pdf(records[0], _actor(proxy)['name'], now),
                content_type='application/pdf',
            )
            filename = f"Papeleta_DARPE_{datetime.strptime(records[0]['data'], '%Y-%m-%d').strftime('%d_%m_%Y')}.pdf"
            response['Content-Disposition'] = "attachment; filename*=UTF-8''" + quote(filename)
            response['Cache-Control'] = 'no-store'
            response['X-Content-Type-Options'] = 'nosniff'
            return response
        response = api(proxy, action)
        changed = (request.method == 'POST' and response.status_code == 201) or (
            request.method == 'PATCH' and response.status_code == 200
        )
        if action == 'atendimentos' and changed:
            saved = json.loads(response.content).get('item') or {}
            try:
                audit_mobile(proxy, 'CREATE' if request.method == 'POST' else 'UPDATE', {
                    'entity': 'darpe_papeletas', 'entity_id': str(saved.get('id') or ''),
                })
            except requests.RequestException:
                logger.exception('Atendimento mobile salvo, mas a auditoria falhou.')
                return JsonResponse({
                    'error': 'O atendimento foi salvo, mas a auditoria falhou. Confira a lista e informe a administração antes de repetir.',
                    'code': 'audit_write_failed',
                }, status=503)
        return response
    except (requests.RequestException, ValueError, KeyError):
        logger.exception('Falha ao validar acesso ou registrar auditoria DARPE mobile.')
        return JsonResponse({'error': 'Não foi possível validar seu acesso.'}, status=503)
