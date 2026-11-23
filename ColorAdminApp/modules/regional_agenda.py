"""Agenda institucional; transições e reservas ocorrem nas RPCs da migração 064."""
import hmac
import json
import logging
from datetime import date, datetime, timedelta
from functools import wraps
from uuid import UUID
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import service_headers, user_scope, _norm
from .module_access import MODULE_MUSICA, can_access_module, is_global
from .music_events_dashboard import regional_city
from .regional_agenda_catalog import CALENDAR_BY_ID
from .regional_agenda_google import normalize_events, presentation

logger = logging.getLogger(__name__)
TZ = ZoneInfo('America/Sao_Paulo')
ACTIVE = {'PENDENTE_ADM', 'PENDENTE_REGIONAL', 'PRONTO', 'INTEGRANDO', 'CONFIRMADO', 'CANCELANDO', 'ERRO_INTEGRACAO'}


class AgendaError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def guarded(view):
    @wraps(view)
    def call(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except AgendaError as exc:
            return JsonResponse({'error': str(exc)}, status=exc.status)
        except (ValueError, TypeError, KeyError, OverflowError):
            return JsonResponse({'error': 'Dados inválidos. Confira os campos e atualize a página.'}, status=400)
        except requests.RequestException:
            logger.warning('Agenda Regional: serviço de dados indisponível', exc_info=True)
            return JsonResponse({'error': 'Não foi possível consultar a agenda. Tente novamente; o horário não foi confirmado.'}, status=503)
    return call


def actor(request):
    if not request.session.get('authenticated') or not request.session.get('user_id'):
        raise AgendaError('Entre no sistema para acessar a agenda.', 403)
    if not can_access_module(request, MODULE_MUSICA):
        raise AgendaError('Seu perfil não possui acesso à pasta Música.', 403)
    scope = user_scope(request)
    profile = scope['profile']
    return {'p_actor': str(UUID(str(request.session['user_id']))),
            'p_nome': str(profile.get('full_name') or profile.get('nome') or 'Usuário'),
            'p_nivel': scope['level'], 'p_municipio': regional_city(scope.get('municipio', '')),
            'p_master': is_global(profile)}


def body(request, limit=65536):
    if len(request.body) > limit:
        raise AgendaError('Solicitação muito grande.', 413)
    data = json.loads(request.body or b'{}')
    if not isinstance(data, dict):
        raise AgendaError('Envie um objeto JSON.')
    return data


def read(table, **params):
    result = []
    for offset in range(0, 20000, 500):
        response = requests.get(settings.SUPABASE_URL + '/rest/v1/' + table,
                                headers=service_headers(), params={**params, 'offset': offset, 'limit': 500}, timeout=(3.05, 15))
        if response.status_code == 404 and table.startswith('agenda_google_'):
            raise AgendaError('Aplique a migração 066_agenda_leitura_google.sql para exibir os eventos existentes no Google.', 503)
        if response.status_code == 404 and table == 'agenda_calendarios':
            raise AgendaError('Aplique a migração 065_agenda_calendarios_municipais.sql após a 064 para configurar as sete agendas.', 503)
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list):
            raise requests.RequestException('Resposta de dados inválida')
        result.extend(batch)
        if len(batch) < 500:
            return result
    raise AgendaError('Há muitos registros. Reduza o período da consulta.', 422)


def rpc(name, payload):
    response = requests.post(settings.SUPABASE_URL + '/rest/v1/rpc/' + name,
                             headers=service_headers(), json=payload, timeout=(3.05, 25))
    if not response.ok:
        try:
            error = response.json()
        except ValueError:
            response.raise_for_status()
        code = error.get('code')
        if code in {'PGRST202', '42P01', '42883'}:
            if name == 'agenda_google_operar':
                raise AgendaError('Aplique a migração 066_agenda_leitura_google.sql para exibir os eventos existentes no Google.', 503)
            raise AgendaError('A agenda precisa das migrações 064_agenda_regional.sql e 065_agenda_calendarios_municipais.sql no Supabase.', 503)
        if code in {'P0001', '23P01', '23505', '23514', '42501', 'P0002'}:
            status = 403 if code == '42501' else 404 if code == 'P0002' else 409
            message = error.get('message', 'Não foi possível concluir esta operação.')
            if code == '23505':
                message = 'Já existe um titular, vínculo ou parecer para essa seleção. Atualize a página.'
            if code == '23514':
                message = 'Confira os dados, o período e a função do responsável.'
            raise AgendaError(message, status)
        response.raise_for_status()
    return response.json()


def operate(action, data, who):
    return rpc('agenda_operar', {'p_acao': action, 'p_dados': data, **who})


def clean(event):
    return {key: value for key, value in event.items()
            if key not in {'lease_token', 'lease_ate', 'google_calendar_id', 'proxima_tentativa'}}


def roles(who):
    return read('agenda_responsaveis', user_id='eq.' + who['p_actor'], order='papel.asc')


def google_window(start, end, force=False):
    begin = start.isoformat() + 'T00:00:00-03:00'
    finish = end.isoformat() + 'T00:00:00-03:00'
    try:
        rpc('agenda_google_operar', {'p_acao': 'solicitar', 'p_dados': {'inicio': begin, 'fim': finish, 'force': force}})
        rows = read('agenda_google_visiveis', inicio='lt.' + finish, fim='gt.' + begin, order='inicio.asc')
        jobs = read('agenda_google_leituras', inicio='eq.' + begin, fim='eq.' + finish,
                    select='agenda_id,status,concluido_em,mensagem', order='agenda_id.asc')
    except AgendaError as exc:
        if '066_' in str(exc):
            return [], {'instalada': False, 'pending': 0, 'leituras': [], 'mensagem': str(exc)}
        raise
    return [presentation(row) for row in rows], {'instalada': True, 'leituras': jobs,
        'pending': sum(j['status'] in {'PENDENTE', 'EXECUTANDO'} for j in jobs),
        'ok': sum(j['status'] == 'OK' for j in jobs)}


def can_view(event, who, assignments, events):
    if who['p_nivel'] in {'regional', 'global'} or event['criado_por'] == who['p_actor']:
        return True
    if who['p_nivel'] == 'municipal' and _norm(who['p_municipio']) == _norm(event['municipio']):
        return True
    own = {r['administracao_id'] for r in assignments}
    if any(r['papel'] == 'REGIONAL' for r in assignments) or event['administracao_id'] in own:
        return True
    return any(e['id'] in event.get('conflitos', []) and e['administracao_id'] in own for e in events)


@never_cache
@guarded
@require_http_methods(['GET'])
def page(request):
    who = actor(request)
    return render(request, 'pages/regional_agenda.html', {'agenda_master': who['p_master']})


@never_cache
@guarded
@require_http_methods(['GET', 'POST'])
def events_api(request):
    who = actor(request)
    if request.method == 'POST':
        if not getattr(settings, 'AGENDA_N8N_TOKEN', ''):
            raise AgendaError('Configure a integração com o n8n antes de solicitar eventos.', 503)
        data = body(request)
        data = {k: data.get(k) for k in ('id', 'administracao_id', 'municipio', 'titulo', 'categoria', 'local', 'inicio', 'fim')}
        data['id'] = str(UUID(str(data['id'])))
        for key, maximum in (('titulo', 180), ('categoria', 80), ('local', 300), ('municipio', 100), ('administracao_id', 30)):
            value = data[key]
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
                raise AgendaError('Preencha os campos obrigatórios e respeite os tamanhos indicados.')
            data[key] = value.strip()
        for key in ('inicio', 'fim'):
            value = datetime.fromisoformat(data[key])
            if value.tzinfo is None:
                raise AgendaError('Informe os horários com fuso explícito.')
            data[key] = value.isoformat()
        start, end = (datetime.fromisoformat(data[k]) for k in ('inicio', 'fim'))
        if not start < end <= start + timedelta(days=7):
            raise AgendaError('O término deve ser posterior ao início, com duração máxima de sete dias.')
        return JsonResponse({'event': clean(operate('criar', data, who))}, status=201)
    today = datetime.now(TZ).date()
    start = date.fromisoformat(request.GET.get('start', today.replace(day=1).isoformat()))
    end = date.fromisoformat(request.GET.get('end', (start + timedelta(days=42)).isoformat()))
    if not start < end <= start + timedelta(days=93):
        raise AgendaError('Consulte um período de até 93 dias.')
    admins = read('agenda_administracoes', order='nome.asc')
    calendars = read('agenda_calendarios', order='nome.asc')
    assignments = roles(who)
    params = {'order': 'inicio.asc', 'inicio': 'lt.' + end.isoformat() + 'T00:00:00-03:00',
              'fim': 'gt.' + start.isoformat() + 'T00:00:00-03:00'}
    if request.GET.get('pending') == '1':
        params = {'order': 'inicio.asc', 'status': 'in.(PENDENTE_ADM,PENDENTE_REGIONAL,ERRO_INTEGRACAO)'}
    events = read('agenda_eventos', **params)
    if request.GET.get('pending') == '1':
        sync = None
    else:
        external, sync = google_window(start, end, request.GET.get('sync') == '1')
        events.extend(external)
        events.sort(key=lambda e: datetime.fromisoformat(e['inicio']))
    # Na visão de pendências, o compromisso de origem pode já estar confirmado.
    # Busque seu vínculo territorial para não esconder a análise do encarregado.
    context = list(events)
    missing = sorted({identity for e in events for identity in e.get('conflitos', [])}
                     - {e['id'] for e in events})
    for offset in range(0, len(missing), 100):
        context.extend(read('agenda_eventos', id='in.(' + ','.join(missing[offset:offset + 100]) + ')',
                            select='id,administracao_id'))
    result = []
    for event in events:
        if can_view(event, who, assignments, context):
            result.append({**clean(event), 'detalhes': True})
        else:
            result.append({k: event[k] for k in ('id', 'administracao_id', 'agenda_id', 'inicio', 'fim', 'status')} |
                          {'titulo': 'Horário reservado', 'detalhes': False})
    regional = any(r['papel'] == 'REGIONAL' for r in assignments)
    allowed_admins = {r['administracao_id'] for r in assignments}
    choices = []
    for admin in admins:
        municipalities = admin['municipios'] if who['p_nivel'] in {'global', 'regional'} or regional or admin['id'] in allowed_admins else [
            city for city in admin['municipios'] if _norm(city) == _norm(who['p_municipio']) and who['p_nivel'] == 'municipal']
        choices.append({'id': admin['id'], 'nome': admin['nome'], 'municipios': municipalities,
                        'configurada': all(c['calendar_id'] for c in calendars if c['administracao_id'] == admin['id']),
                        'prazo_horas': admin['prazo_horas']})
    public_calendars = [{k: c[k] for k in ('id', 'nome', 'municipio', 'administracao_id')} |
                        {'configurada': bool(c['calendar_id'])} for c in calendars]
    configured = len(calendars) == 7 and all(c['calendar_id'] for c in calendars)
    token_configured = bool(getattr(settings, 'AGENDA_N8N_TOKEN', ''))
    return JsonResponse({'events': result, 'administrations': choices, 'calendars': public_calendars, 'roles': assignments,
                         'regional': regional, 'master': who['p_master'], 'user_id': who['p_actor'],
                         'configurada': configured and token_configured, 'sync': sync,
                         'connection': {'token_configurado': token_configured,
                             'ids_configurados': sum(bool(c['calendar_id']) for c in calendars),
                             'missing_calendars': [c['nome'] for c in calendars if not c['calendar_id']]}})


@never_cache
@guarded
@require_http_methods(['GET', 'POST'])
def event_api(request, event_id):
    who = actor(request)
    if request.method == 'POST':
        data = body(request)
        action = data.pop('acao', '')
        if action not in {'parecer', 'cancelar', 'reenviar'}:
            raise AgendaError('Operação inválida.')
        data['id'] = str(event_id)
        return JsonResponse({'event': clean(operate(action, data, who))})
    rows = read('agenda_eventos', id='eq.' + str(event_id))
    if not rows:
        external = read('agenda_google_visiveis', id='eq.' + str(event_id))
        if not external:
            raise AgendaError('Evento não encontrado.', 404)
        event = presentation(external[0])
        if not can_view(event, who, roles(who), []):
            raise AgendaError('Você não tem acesso aos detalhes deste evento.', 403)
        return JsonResponse({'event': clean(event), 'conflicts': [], 'opinions': [], 'history': []})
    event = rows[0]
    conflicts = read('agenda_eventos', id='in.(' + ','.join(event['conflitos']) + ')') if event['conflitos'] else []
    if not can_view(event, who, roles(who), conflicts):
        raise AgendaError('Você não tem acesso aos detalhes deste evento.', 403)
    history = read('agenda_historico', evento_id='eq.' + str(event_id), order='criado_em.asc')
    return JsonResponse({'event': clean(event),
                         'conflicts': [{k: c[k] for k in ('id', 'titulo', 'administracao_id', 'agenda_id', 'municipio', 'inicio', 'fim', 'status')} for c in conflicts],
                         'opinions': read('agenda_pareceres', evento_id='eq.' + str(event_id), order='criado_em.asc'),
                         'history': history})


@never_cache
@guarded
@require_http_methods(['GET', 'POST'])
def configuration_api(request):
    who = actor(request)
    if not who['p_master']:
        raise AgendaError('Somente o administrador global configura esta agenda.', 403)
    if request.method == 'POST':
        data = body(request)
        if data.get('tipo') not in {'agenda', 'prazo', 'responsavel', 'remover_responsavel'}:
            raise AgendaError('Configuração inválida.')
        if data.get('tipo') == 'agenda':
            if data.get('agenda_id') not in CALENDAR_BY_ID:
                raise AgendaError('Selecione uma das sete agendas municipais.')
            calendar = str(data.get('calendar_id') or '').strip()
            if not calendar or len(calendar) > 300 or any(c in calendar for c in '\r\n'):
                raise AgendaError('Informe o ID da agenda Google.')
            data['calendar_id'] = calendar
        elif data.get('tipo') == 'prazo':
            if data.get('administracao_id') not in {'cotia', 'itapevi', 'jandira', 'santana'}:
                raise AgendaError('Selecione uma administração válida.')
            data['prazo_horas'] = int(data.get('prazo_horas', 48))
            if not 1 <= data['prazo_horas'] <= 720:
                raise AgendaError('O prazo deve ser de 1 a 720 horas.')
        elif data['tipo'] == 'responsavel':
            data['user_id'] = str(UUID(str(data.get('user_id'))))
            if data.get('papel') not in {'ENCARREGADO', 'SUPLENTE', 'REGIONAL'}:
                raise AgendaError('Selecione uma função válida.')
            if data['papel'] == 'REGIONAL':
                data['administracao_id'] = None
            elif data.get('administracao_id') not in {'cotia', 'itapevi', 'jandira', 'santana'}:
                raise AgendaError('Selecione uma administração válida.')
        else:
            data['id'] = str(UUID(str(data.get('id'))))
        return JsonResponse(operate('configurar', data, who))
    return JsonResponse({'administrations': read('agenda_administracoes', order='nome.asc'),
                         'calendars': read('agenda_calendarios', order='nome.asc'),
                         'responsibles': read('agenda_responsaveis', order='nome.asc'),
                         'users': read('profiles', status='eq.approved', select='user_id,full_name,municipio,role_id', order='full_name.asc')})


@csrf_exempt
@never_cache
@guarded
@require_http_methods(['POST'])
def integration_api(request, action):
    # Endpoint máquina a máquina: cookies não autenticam e CSRF não se aplica.
    secret = getattr(settings, 'AGENDA_N8N_TOKEN', '')
    authorization = request.headers.get('Authorization', '')
    if not secret or not hmac.compare_digest(authorization.encode(), ('Bearer ' + secret).encode()):
        raise AgendaError('Credencial de integração inválida.', 401)
    if action not in {'buscar', 'resultado', 'notificacao', 'notificado', 'buscar_leitura', 'resultado_leitura'}:
        raise AgendaError('Operação inválida.', 404)
    data = body(request, 2 * 1024 * 1024 if action == 'resultado_leitura' else 65536)
    if action == 'buscar_leitura':
        return JsonResponse(rpc('agenda_google_operar', {'p_acao': 'buscar', 'p_dados': {}}))
    if action == 'resultado_leitura':
        data['id'] = str(UUID(str(data['id'])))
        data['lease_token'] = str(UUID(str(data['lease_token'])))
        if data.get('resultado') not in {'ok', 'erro'}:
            raise AgendaError('Resultado de leitura inválido.')
        if data['resultado'] == 'ok':
            jobs = read('agenda_google_leituras', id='eq.' + data['id'], select='calendar_id')
            if not jobs:
                raise AgendaError('Leitura não encontrada.', 404)
            try:
                data['eventos'] = normalize_events(data.get('eventos'), jobs[0]['calendar_id'])
            except (ValueError, KeyError, TypeError):
                data = {'id': data['id'], 'lease_token': data['lease_token'], 'resultado': 'erro',
                        'mensagem': 'O Google retornou uma leitura incompleta ou com intervalos inválidos. O espelho anterior foi preservado.'}
        return JsonResponse(rpc('agenda_google_operar', {'p_acao': 'resultado', 'p_dados': data}))
    if action in {'buscar', 'resultado'} and data.get('protocol_version') != 2:
        raise AgendaError('Reimporte o workflow n8n atualizado para sete agendas municipais (protocolo 2).', 409)
    if action in {'resultado', 'notificado'}:
        data['id'] = str(UUID(str(data['id'])))
        data['lease_token'] = str(UUID(str(data['lease_token'])))
    if action == 'resultado':
        if data.get('resultado') not in {'confirmado', 'cancelado', 'conflito_externo', 'erro'}:
            raise AgendaError('Resultado inválido.')
        if data['resultado'] == 'confirmado' and data.get('google_event_id') != UUID(data['id']).hex:
            raise AgendaError('Identificador Google incompatível.')
        if data['resultado'] == 'conflito_externo':
            conflicts = data.get('conflitos')
            if not isinstance(conflicts, list) or not 1 <= len(conflicts) <= 100:
                raise AgendaError('Informe os conflitos encontrados.')
            for item in conflicts:
                if not isinstance(item, dict) or item.get('administracao_id') not in {'cotia', 'itapevi', 'jandira', 'santana'} or not item.get('google_event_id'):
                    raise AgendaError('Conflito inválido.')
                if not item.get('calendar_id'):
                    raise AgendaError('O conflito deve identificar a agenda Google consultada.')
                if item.get('agenda_id') != 'legado' and (item.get('agenda_id') not in CALENDAR_BY_ID or
                        CALENDAR_BY_ID[item['agenda_id']]['administracao_id'] != item['administracao_id']):
                    raise AgendaError('Agenda municipal incompatível com a administração do conflito.')
    return JsonResponse(rpc('agenda_trabalho', {'p_acao': action, 'p_dados': data}))
