"""Confirmacao diaria, previa assinada e gravacao atomica dos roteiros regionais."""
import hashlib
import json
import re
import logging
import io
import zipfile
from urllib.parse import quote, urlencode
from copy import deepcopy
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.core import signing
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods
from django.views.decorators.cache import never_cache

from .access_control import user_scope, visible_commons, service_headers
from .regional_routes import build_plan, finalize_plan
from .congregation_distribution import common_code
from .regional_route_geometry import enrich_plan_geometry
from .regional_route_roads import enrich_road_distances
from ColorAdminApp.utils.routing import normalize_text, route_address_key

SALT = 'visitas-regional-preview-v3-geometry-and-coordinators'
DELETE_SALT = 'visitas-regional-delete-v1'
DELETE_MIGRATION = 'scripts/migrations/059_visitas_excluir_agendamentos_roteiro.sql'
REMOVE_SALT = 'visitas-regional-remove-commons-v1'
REMOVE_MIGRATION = 'scripts/migrations/060_visitas_exclusao_seletiva_comuns.sql'
MIGRATION = 'scripts/migrations/057_visitas_planejamento_regional.sql'
MEMBER_FIELDS = ('id,nome,comum,endereco,setor,status,categoria,ultima_visita,equipe_id,equipe_visita,'
                 'grupo_regional_id,grupo_regional_nome,preferencia_periodo_visita')
logger = logging.getLogger(__name__)


def day_agenda_summary(day, city, groups=None):
    """Conta casas da agenda com campos minimos, somente ao carregar/confirmar."""
    if groups is None:
        groups = read('visitas_equipes',select='id,nome',municipio='eq.'+city,
                      tipo='eq.REGIONAL',order='id.asc')
        groups = [g for g in groups if re.fullmatch(r'GRUPO [A-Z]',normalize_text(g['nome']))]
    if not groups:
        return {'families':0,'groups':0}
    rows = read(settings.SUPABASE_TABLE_VISITAS_AGENDA,
                select='id,irmandade_id,equipe_id,endereco_visitado,status',
                equipe_id=in_values([g['id'] for g in groups]),roteiro_regional_id='not.is.null',
                data_inicio='gte.'+day+'T00:00:00-03:00',
                **{'and':'(data_inicio.lt.'+(date.fromisoformat(day)+timedelta(days=1)).isoformat()+'T00:00:00-03:00)'},
                order='id.asc')
    active = [r for r in rows if normalize_text(r.get('status')) not in {'CANCELADA','NAO REALIZADA'}]
    houses = {route_address_key(r,fallback=str(r.get('irmandade_id') or r['id'])) for r in active}
    return {'families':len(houses),'groups':len({str(r['equipe_id']) for r in active})}


def safe_day_summary(day, city, groups=None):
    try:
        return day_agenda_summary(day,city,groups)
    except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
        logger.warning('Regional route indicators unavailable: %s',type(exc).__name__)
        return None


def refresh_missing_preferences(groups,permitted):
    missing={str(m['id']):m for g in groups for h in g['houses'] for m in h['members'] if not m.get('preferencia_periodo_visita')}
    ids=sorted(missing)
    for start in range(0,len(ids),100):
        rows=read(settings.SUPABASE_TABLE_VISITAS_IRMANDADE,
                  select='id,comum,preferencia_periodo_visita',id=in_values(ids[start:start+100]),order='id.asc')
        for row in rows:
            if str(row['id']) in missing and row.get('comum') in permitted:
                missing[str(row['id'])]['preferencia_periodo_visita']=row.get('preferencia_periodo_visita') or ''


def allowed(request):
    return bool(request.session.get('authenticated') and request.session.get('user_id')
                and user_scope(request)['level'] in {'global','regional','municipal'})


def read(table, **params):
    rows = []
    for offset in range(0, 20000, 500):
        response = requests.get(settings.SUPABASE_URL + '/rest/v1/' + table,
                                headers=service_headers(), params={**params, 'limit':500, 'offset':offset}, timeout=(3.05,15))
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list):
            raise ValueError('Resposta invalida do banco.')
        rows.extend(batch)
        if len(batch) < 500:
            return rows
    raise ValueError('O recorte excede 20 mil registros. Selecione menos comuns.')


def rpc(name, **payload):
    response = requests.post(settings.SUPABASE_URL + '/rest/v1/rpc/' + name,
                             headers=service_headers(), json=payload, timeout=(3.05,30))
    response.raise_for_status()
    return response.json() if response.content else None


def in_values(values):
    return 'in.(' + ','.join('"' + str(v).replace('\\','\\\\').replace('"','\\"') + '"' for v in values) + ')'


def common_member_filter(commons):
    """Busca pelo codigo estavel, inclusive em cadastros com nome legado."""
    codes = sorted({common_code(c) for c in commons} - {''})
    if not codes:
        return {'comum': in_values(commons)}
    clauses = ['comum.' + in_values(commons), 'codigo_comum.' + in_values(codes)]
    clauses.extend('comum.ilike.' + code + '*' for code in codes)
    return {'or': '(' + ','.join(clauses) + ')'}


def canonical_members(members, commons):
    """Normaliza somente vinculos reconhecidos dentro do catalogo autorizado."""
    by_code = {common_code(c): c for c in commons if common_code(c)}
    by_name = {normalize_text(c): c for c in commons}
    result = []
    for member in members:
        code = common_code(member.get('comum')) or common_code(member.get('codigo_comum'))
        common = by_code.get(code) if code else by_name.get(normalize_text(member.get('comum')))
        if common:
            result.append({**member, 'comum_cadastro': member.get('comum_cadastro', member.get('comum')), 'comum': common})
    return result


def database_plan(plan):
    """Preserva o texto original exigido pela validacao atomica do cadastro."""
    payload = deepcopy(plan)
    for house in payload['houses']:
        for member in house['members']:
            code = common_code(member['comum'])
            if code:
                member['codigo_comum'] = code
            member['comum'] = member.get('comum_cadastro', member['comum'])
    return payload


def location(request, raw):
    try:
        day = date.fromisoformat(str(raw.get('data') or '')).isoformat()
    except ValueError:
        raise ValueError('Informe uma data valida para as visitas.') from None
    city = str(raw.get('municipio') or '').strip()
    catalog = [c for c in visible_commons(user_scope(request)) if c.get('cidade') == city]
    if not catalog:
        raise PermissionError('Municipio fora do seu escopo de acesso.')
    return day, city, catalog


def regional_integrants(city):
    try:
        people=read('visitas_integrantes_regionais',select='id,nome,municipio,ministerio,comum_origem,ativo',
                    municipio='eq.'+city,ativo='eq.true',order='nome.asc,id.asc')
        return [p for p in people if p.get('municipio')==city and p.get('ativo')]
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in {404,406}:return []
        raise


def daily_groups(day, city):
    params={'municipio':'eq.'+city,'tipo':'eq.REGIONAL','order':'nome.asc,id.asc'}
    try:
        teams = read('visitas_equipes',select='id,nome,tipo,municipio,ativo,coordenador_nome,exige_confirmacao_data',**params)
    except requests.HTTPError as exc:
        if exc.response is not None and 'exige_confirmacao_data' in exc.response.text:
            teams = read('visitas_equipes',select='id,nome,tipo,municipio,ativo,coordenador_nome',**params)
        else:
            if exc.response is None or 'coordenador_nome' not in exc.response.text:raise
            teams = read('visitas_equipes',select='id,nome,tipo,municipio,ativo',**params)
    # RF/RE e outros grupos especificos preservam seu calendario independente.
    teams = [t for t in teams if re.fullmatch(r'GRUPO [A-Z]',normalize_text(t['nome']))]
    participation = read('visitas_participacao_regional', select='equipe_id,confirmado,coordenador_nome,updated_at',
                         data='eq.' + day, municipio='eq.' + city, order='equipe_id.asc')
    by_id = {str(p['equipe_id']): p for p in participation}
    members = read(settings.SUPABASE_TABLE_VISITAS_IRMANDADE,
                   select='id,nome,status,cargo_outros,equipe_id,grupo_regional_id',
                   grupo_regional_id=in_values([t['id'] for t in teams]), order='nome.asc,id.asc') if teams else []
    result = []
    for team in teams:
        identity = str(team['id'])
        linked = [m for m in members if str(m.get('grupo_regional_id')) == identity
                  and 'INATIV' not in normalize_text(m.get('status'))]
        explicit = [m for m in linked if re.search(r'COORDENADOR(?:A)?',normalize_text(m.get('cargo_outros')))]
        # Mesma regra de reconhecimento da tela de Equipes; cargo explicito
        # tem precedencia sobre o vinculo regional sem equipe local.
        registered = ' / '.join(dict.fromkeys(m['nome'] for m in (explicit or [m for m in linked if not m.get('equipe_id')]) if m.get('nome')))
        if team.get('coordenador_nome') is not None:registered=team['coordenador_nome']
        saved = by_id.get(identity)
        result.append({**team, 'confirmado': saved['confirmado'] if saved else bool(registered and team['ativo'] and not team.get('exige_confirmacao_data')),
                       'coordenador_nome': saved['coordenador_nome'] if saved else registered,
                       'coordenador_cadastrado': registered, 'coordenador_cadastro_valor':team.get('coordenador_nome'),
                       'cadastro_disponivel':'coordenador_nome' in team,'participacao_salva': saved is not None,
                       'participacao_updated_at': saved.get('updated_at','') if saved else ''})
    return result


def sources(request, options):
    day, city, catalog = location(request, options)
    if day < datetime.now(ZoneInfo('America/Sao_Paulo')).date().isoformat():
        raise ValueError('O planejamento de visitas deve ser de hoje ou de uma data futura.')
    selected = options.get('comuns')
    if not isinstance(selected, list) or not selected or len(selected) > 30:
        raise ValueError('Selecione de 1 a 30 comuns para atendimento.')
    permitted = {c['comum'] for c in catalog}
    if any(c not in permitted for c in selected) or len(selected) != len(set(selected)):
        raise PermissionError('Comum fora do municipio ou do seu escopo.')
    version = rpc('visitas_versao_agenda_regional', p_data=day)
    groups = daily_groups(day, city)
    if any(g['ativo'] and g['confirmado'] and not g.get('participacao_salva') for g in groups):
        raise ValueError('Salve as confirmacoes e os coordenadores desta data antes de calcular a distribuicao.')
    selected_groups = options.get('grupos')
    if selected_groups is not None:
        if not isinstance(selected_groups, list) or not selected_groups:
            raise ValueError('Selecione ao menos um grupo confirmado.')
        valid = {str(g['id']) for g in groups if g['ativo'] and g['confirmado']}
        if any(str(g) not in valid for g in selected_groups):
            raise ValueError('O grupo selecionado nao esta confirmado para a data.')
        for group in groups:
            group['confirmado'] = group['confirmado'] and str(group['id']) in selected_groups
    fields=MEMBER_FIELDS
    if int((user_scope(request).get('profile') or {}).get('role_id') or 99)<=3:
        fields+=',apontamentos_restritos'
    members = read(settings.SUPABASE_TABLE_VISITAS_IRMANDADE, select=fields+',codigo_comum',
                   **common_member_filter(selected), order='id.asc')
    # A agenda do dia identifica visitas fixas e evita consumir a mesma casa
    # por cadastros de outra comum. O restante do historico e restrito aos IDs.
    agenda = read(settings.SUPABASE_TABLE_VISITAS_AGENDA,
                  select='id,irmandade_id,equipe_id,equipe_responsavel,equipe_tipo,data_inicio,data_fim,status,endereco_visitado',
                  data_inicio='gte.' + day + 'T00:00:00-03:00',
                  **{'and': '(data_inicio.lt.' + (date.fromisoformat(day)+timedelta(days=1)).isoformat() + 'T00:00:00-03:00)'},
                  order='id.asc')
    missing = sorted({str(v['irmandade_id']) for v in agenda if v.get('irmandade_id')} - {str(m['id']) for m in members})
    for start in range(0,len(missing),100):
        members.extend(read(settings.SUPABASE_TABLE_VISITAS_IRMANDADE, select=MEMBER_FIELDS+',codigo_comum',
                            id=in_values(missing[start:start+100]), order='id.asc'))
    members = canonical_members(members, permitted)
    selected_ids = [str(m['id']) for m in members if m.get('comum') in selected]
    for start in range(0,len(selected_ids),100):
        agenda.extend(read(settings.SUPABASE_TABLE_VISITAS_AGENDA,
                           select='id,irmandade_id,equipe_id,equipe_responsavel,equipe_tipo,data_inicio,data_fim,status,endereco_visitado',
                           irmandade_id=in_values(selected_ids[start:start+100]),
                           data_inicio='gte.'+(date.fromisoformat(day)-timedelta(days=15)).isoformat()+'T00:00:00-03:00', order='id.asc'))
    agenda = list({str(v['id']): v for v in agenda}.values())
    for visit in agenda:
        visit['local_date'] = datetime.fromisoformat(visit['data_inicio'].replace('Z','+00:00')).astimezone(ZoneInfo('America/Sao_Paulo')).date().isoformat()
    fingerprint = hashlib.sha256(json.dumps([members,sorted(agenda,key=lambda v:str(v['id'])),groups,version],
                                            sort_keys=True, default=str).encode()).hexdigest()
    plan = build_plan(members, agenda, groups, day, city, selected)
    enrich_plan_geometry(plan)
    origins=plan['origins']
    plan = build_plan(members,agenda,groups,day,city,selected,
                      resolved_coordinates={h['key']:h['coords'] for h in plan['houses']},route_origins=origins)
    plan['origins']=origins
    return plan, version, fingerprint


@never_cache
@require_GET
def page(request):
    if not allowed(request):
        return render(request, 'pages/403.html', {'message':'A gestao regional requer acesso municipal, regional ou global.'}, status=403)
    scope=user_scope(request)
    catalog = visible_commons(scope)
    cities={c['cidade'] for c in catalog}
    home=next((c['cidade'] for c in catalog if c['comum']==scope.get('comum')),'')
    selected_city=request.GET.get('municipio')
    if selected_city not in cities:selected_city=scope.get('municipio') if scope.get('municipio') in cities else home
    return render(request, 'pages/visitas-roteiro-regional.html', {
        'comuns':catalog, 'municipios': sorted({c['cidade'] for c in catalog}),
        'municipio_padrao': selected_city,
        'data_padrao': request.GET.get('data','') if re.fullmatch(r'\d{4}-\d{2}-\d{2}',request.GET.get('data','')) else '',
        'scope_level': {'global':'Global','regional':'Regional','municipal':'Municipal'}.get(scope['level'],'Regional'),
    })


@never_cache
@require_http_methods(['GET','POST'])
def api(request):
    if not allowed(request):
        return JsonResponse({'error':'Acesso nao autorizado.'}, status=403)
    try:
        raw = request.GET if request.method == 'GET' else json.loads(request.body)
        if not isinstance(raw, dict) and request.method == 'POST':
            raise ValueError('Envie os dados do planejamento.')
        actor = str(UUID(str(request.session['user_id'])))
        if request.method == 'GET':
            day, city, _ = location(request, raw)
            if raw.get('action')=='integrants':
                people=regional_integrants(city)
                by_person={str(p['id']):p['nome'] for p in people}
                titular_roles=read('visitas_funcoes_regionais',select='municipio,equipe_id,integrante_id',
                                   municipio='eq.'+city,funcao='eq.COORDENADOR',ativo='eq.true') if people else []
                titulares={str(role['equipe_id']):by_person[str(role['integrante_id'])] for role in titular_roles
                           if role.get('municipio')==city and role.get('equipe_id') and str(role.get('integrante_id')) in by_person}
                return JsonResponse({'integrantes':people,'titulares':titulares})
            if raw.get('somente_grupos') == '1':
                return JsonResponse({'groups':daily_groups(day,city)})
            # Uma falha no historico nao deve impedir o carregamento dos grupos.
            groups = daily_groups(day,city)
            warning = ''
            try:
                plans = read('visitas_roteiros_regionais', select='id,comuns:plano->commons,created_at,substituido_em',
                             data='eq.'+day,municipio='eq.'+city,order='created_at.desc,id.asc',**{'plano->>deleted_at':'is.null'})
            except requests.RequestException:
                plans=[]
                warning='Grupos carregados, mas o histórico de roteiros está indisponível. Atualize para tentar novamente.'
            permitted = {c['comum'] for c in visible_commons(user_scope(request)) if c.get('cidade')==city}
            return JsonResponse({'groups':groups,'warning':warning,
                **({'agenda_summary':safe_day_summary(day,city,groups)} if raw.get('incluir_indicadores')=='1' else {}), 'plans':[
                {'id':p['id'],'created_at':p['created_at'],'historical':bool(p.get('substituido_em')),
                 'print_url':reverse('ColorAdminApp:regionalRoutePrint',args=[p['id']])}
                for p in plans if set(p.get('comuns') or []) <= permitted]})
        action = raw.get('action')
        if action == 'remove_commons':
            signed=signing.loads(raw.get('token',''),salt=REMOVE_SALT,max_age=1800)
            if signed['actor'] != actor:
                raise PermissionError('A confirmacao de exclusao pertence a outro usuario.')
            day,city,catalog=location(request,signed)
            plan_id=str(UUID(signed['id']))
            current=read('visitas_roteiros_regionais',select='id,comuns:plano->commons',id='eq.'+plan_id,
                         data='eq.'+day,municipio='eq.'+city,order='id.asc')
            if not current or not isinstance(current[0].get('comuns'),list) or not set(current[0]['comuns']) <= {c['comum'] for c in catalog}:
                raise PermissionError('Roteiro fora do seu escopo de acesso.')
            selected=raw.get('comuns')
            cleanup=raw.get('agenda_comuns')
            if (not isinstance(selected,list) or not selected or not all(isinstance(c,str) for c in selected)
                    or len(selected)!=len(set(selected)) or not set(selected)<=set(current[0]['comuns'])
                    or not isinstance(cleanup,list) or not all(isinstance(c,str) for c in cleanup)
                    or len(cleanup)!=len(set(cleanup)) or not set(cleanup)<=set(selected)):
                raise ValueError('Selecione as comuns deste roteiro e confira quais devem ser excluidas tambem da agenda.')
            result=rpc('visitas_remover_comuns_roteiro',p_id=plan_id,p_data=day,p_municipio=city,p_actor=actor,
                       p_expected_version=signed['version'],p_comuns=selected,p_agenda_comuns=cleanup)
            from ColorAdminApp.views import log_audit
            log_audit(request,'REMOVE_REGIONAL_ROUTE_COMMONS','VISITAS_AGENDA',{
                'roteiro_id':plan_id,'data':day,'municipio':city,'comuns':selected,
                'agenda_comuns':cleanup,'agendamentos_excluidos':result['deleted']})
            return JsonResponse(result)
        if action=='delete':
            signed=signing.loads(raw.get('token',''),salt=DELETE_SALT,max_age=1800)
            if signed['actor']!=actor:raise PermissionError('A confirmação de exclusão pertence a outro usuário.')
            day,city,catalog=location(request,signed)
            plan_id=str(UUID(signed['id']))
            current=read('visitas_roteiros_regionais',select='id,comuns:plano->commons',id='eq.'+plan_id,
                         data='eq.'+day,municipio='eq.'+city,order='id.asc')
            if not current or not isinstance(current[0].get('comuns'),list) or not set(current[0]['comuns'])<={c['comum'] for c in catalog}:
                raise PermissionError('Roteiro fora do seu escopo de acesso.')
            removed=rpc('visitas_excluir_agendamentos_roteiro_regional',p_id=plan_id,p_data=day,p_municipio=city,
                        p_actor=actor,p_expected_version=signed['version'])
            from ColorAdminApp.views import log_audit
            log_audit(request,'DELETE_REGIONAL_VISIT_SCHEDULES','VISITAS_AGENDA',{
                'roteiro_id':plan_id,'data':day,'municipio':city,'comuns':current[0]['comuns'],'agendamentos_excluidos':removed})
            return JsonResponse({'deleted':removed})
        if action == 'participation':
            day, city, _ = location(request, raw)
            teams = daily_groups(day, city)
            supplied = raw.get('groups')
            valid = {str(t['id']) for t in teams if t['ativo']}
            if not isinstance(supplied, list) or {str(g.get('id')) for g in supplied} != valid or len(supplied) != len(valid):
                raise ValueError('Confira a lista completa de grupos ativos.')
            chosen={str(g.get('coordenador_integrante_id')) for g in supplied if g.get('coordenador_integrante_id')}
            people={str(p['id']):p for p in regional_integrants(city)} if chosen else {}
            if not chosen<=set(people):raise PermissionError('Selecione um integrante ativo deste municipio.')
            confirmed_people=set()
            for group in supplied:
                if not isinstance(group.get('confirmado'), bool) or not isinstance(group.get('coordenador_nome'),str):
                    raise ValueError('Confirmacao ou coordenador invalido.')
                group['coordenador_nome'] = group['coordenador_nome'].strip()
                person_id=group.get('coordenador_integrante_id')
                if person_id:
                    group['coordenador_nome']=people[str(person_id)]['nome']
                    if group['confirmado'] and str(person_id) in confirmed_people:
                        raise ValueError('O mesmo integrante nao pode assumir dois grupos nesta data.')
                    if group['confirmado']:confirmed_people.add(str(person_id))
                prior=next(t for t in teams if str(t['id'])==str(group['id']))
                update=group.get('atualizar_cadastro',False)
                if not isinstance(update,bool):raise ValueError('Alteracao do cadastro invalida.')
                # O planejador altera a escala do dia. Titulares sao geridos no cadastro.
                update=False
                group['atualizar_cadastro']=False
                group.setdefault('expected_coordenador_cadastrado',prior.get('coordenador_cadastro_valor'))
                if update and not prior.get('cadastro_disponivel'):
                    return JsonResponse({'error':'A atualização do coordenador no cadastro da equipe requer a migration 058.',
                        'migration':'scripts/migrations/058_visitas_coordenador_cadastrado.sql'},status=503)
                if len(group['coordenador_nome']) > 180 or (group['confirmado'] and not group['coordenador_nome']):
                    raise ValueError('Informe o coordenador de cada grupo confirmado (ate 180 caracteres).')
            rpc('visitas_salvar_participacao_regional', p_data=day,p_municipio=city,p_actor=actor,p_grupos=supplied)
            from ColorAdminApp.views import log_audit
            log_audit(request,'UPDATE_REGIONAL_VISIT_PARTICIPATION','VISITAS_EQUIPES',{
                'data':day,'municipio':city,'grupos':supplied,
            })
            return JsonResponse({'saved':True,'groups':daily_groups(day,city)})
        if action == 'preview':
            plan, version, fingerprint = sources(request, raw)
            if not plan['houses']:
                raise ValueError('Nao ha casas disponiveis nesse recorte. Confira a agenda, os cadastros e as ultimas visitas.')
            token = signing.dumps({'actor':actor,'options':{k:raw[k] for k in ('data','municipio','comuns','grupos') if k in raw},
                                   'fingerprint':fingerprint,'version':version,'id':str(uuid4())}, salt=SALT, compress=True)
            finalize_plan(plan)
            enrich_road_distances(plan)
            return JsonResponse({'plan':finalize_plan(plan),'token':token})
        if action == 'confirm':
            signed = signing.loads(raw.get('token',''), salt=SALT, max_age=1800)
            if signed['actor'] != actor:
                raise PermissionError('A previa pertence a outro usuario.')
            day, city, catalog = location(request, signed['options'])
            existing = read('visitas_roteiros_regionais', select='id,criado_por,comuns:plano->commons,deleted_at:plano->deleted_at', id='eq.'+signed['id'], order='id.asc')
            if existing:
                if (str(existing[0]['criado_por']) != actor or not isinstance(existing[0].get('comuns'),list)
                        or not set(existing[0]['comuns']) <= {c['comum'] for c in catalog}):
                    raise PermissionError('Roteiro fora do seu escopo.')
                if existing[0].get('deleted_at'):
                    return JsonResponse({'error':'Este roteiro foi excluído. Gere uma nova distribuição.'},status=409)
                return JsonResponse({'saved':True,'agenda_summary':safe_day_summary(day,city),
                                     'print_url':reverse('ColorAdminApp:regionalRoutePrint',args=[signed['id']])})
            plan, version, fingerprint = sources(request, signed['options'])
            if fingerprint != signed['fingerprint'] or version != signed['version']:
                return JsonResponse({'error':'A agenda, os cadastros ou os grupos mudaram. Gere uma nova previa.'}, status=409)
            finalize_plan(plan, raw.get('assignments'))
            enrich_road_distances(plan)
            finalize_plan(plan, raw.get('assignments'))
            plan['issued_at'] = datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M')
            rpc('visitas_confirmar_roteiro_regional',p_id=signed['id'],p_data=day,p_municipio=city,
                p_actor=actor,p_versao=version,p_plano=database_plan(plan))
            from ColorAdminApp.views import log_audit
            log_audit(request,'CONFIRM_REGIONAL_VISIT_ROUTES','VISITAS_AGENDA',{
                'roteiro_id':signed['id'],'data':day,'municipio':city,
                'comuns':plan['commons'],'casas':len(plan['houses']),
            })
            return JsonResponse({'saved':True,'agenda_summary':safe_day_summary(day,city),
                                 'print_url':reverse('ColorAdminApp:regionalRoutePrint',args=[signed['id']])})
        raise ValueError('Acao invalida.')
    except PermissionError as exc:
        return JsonResponse({'error':str(exc)}, status=403)
    except signing.BadSignature:
        if raw.get('action') in {'delete','remove_commons'}:
            return JsonResponse({'error':'A confirmação de exclusão expirou. Carregue o planejamento novamente.'},status=409)
        return JsonResponse({'error':'A previa expirou ou foi alterada. Gere uma nova previa.'}, status=409)
    except ValueError as exc:
        return JsonResponse({'error':str(exc) if not isinstance(exc,json.JSONDecodeError) else 'Envie dados validos para o planejamento.'}, status=400)
    except (TypeError,KeyError,AttributeError):
        return JsonResponse({'error':'Confira a data, as comuns e os grupos. Todos os grupos confirmados precisam de coordenador.'}, status=400)
    except requests.HTTPError as exc:
        missing = exc.response is not None and exc.response.status_code in {404,406}
        if raw.get('action')=='remove_commons':
            if missing:return JsonResponse({'error':'A exclusão por comum precisa ser habilitada com a migration 060.','migration':REMOVE_MIGRATION},status=503)
            return JsonResponse({'error':'O roteiro ou a agenda mudou. Carregue novamente antes de excluir.'},status=409)
        if raw.get('action')=='delete':
            if missing:return JsonResponse({'error':'A exclusão de agendamentos precisa ser habilitada com a migration 059.','migration':DELETE_MIGRATION},status=503)
            return JsonResponse({'error':'Os agendamentos mudaram ou existem visitas encerradas/em andamento. Carregue novamente antes de excluir.'},status=409)
        if not missing and exc.response is not None:
            try:
                message = exc.response.json().get('message','')
            except (ValueError,AttributeError):
                message = ''
            if 'As confirmacoes mudaram' in message or 'coordenador cadastrado mudou' in message:
                return JsonResponse({'error':'As confirmacoes foram alteradas por outro operador. Carregue os grupos novamente.'}, status=409)
        return JsonResponse({'error': ('O planejamento regional ainda precisa ser habilitado no banco.' if missing else
                                      'Nao foi possivel confirmar a operacao. Atualize a previa; se a confirmacao perdeu a conexao, repita a mesma confirmacao.'),
                             **({'migration':MIGRATION} if missing else {})}, status=503 if missing else 409)
    except requests.RequestException:
        return JsonResponse({'error':'Conexao indisponivel. Tente novamente; a mesma confirmacao nao duplica visitas.'}, status=503)


@never_cache
@require_GET
def print_plan(request, plan_id):
    if not allowed(request):
        return render(request,'pages/403.html',status=403)
    try:
        rows = read('visitas_roteiros_regionais',select='id,data,municipio,plano,substituido_em',id='eq.'+str(plan_id),order='id.asc')
        if not rows:
            return JsonResponse({'error':'Roteiro nao encontrado.'},status=404)
        plan = rows[0]['plano']
        if plan.get('deleted_at'):return JsonResponse({'error':'Este roteiro foi excluído.'},status=410)
        _, _, catalog = location(request, {'data':plan['date'],'municipio':plan['city']})
        if not set(plan['commons']) <= {c['comum'] for c in catalog}:
            raise PermissionError
        for house in plan['houses']:
            house['members'] = canonical_members(house['members'], plan['commons'])
        selected = request.GET.get('grupo')
        groups = [{**g,'houses':sorted((h for h in plan['houses'] if h['group_id']==str(g['id'])),key=lambda h:h['number'])}
                  for g in plan['groups'] if not selected or str(g['id'])==selected]
        if not groups:
            return JsonResponse({'error':'Grupo nao encontrado neste roteiro.'},status=404)
        from .regional_route_reports import prepare_navigation, decorate_groups, route_filename, build_group_pdf, build_workbook
        # Dados restritos nunca atravessam o escopo de quem exporta um snapshot.
        groups=deepcopy(groups)
        if int((user_scope(request).get('profile') or {}).get('role_id') or 99)>3:
            for group in groups:
                for house in group['houses']:
                    for member in house['members']:member.pop('apontamentos_restritos',None)
        decorate_groups(groups)
        base=reverse('ColorAdminApp:regionalRoutePrint',args=[plan_id])
        output=request.GET.get('formato','html')
        if output=='manifesto':
            removal={'available':False,'reason':'Não foi possível consultar a exclusão por comum. Carregue novamente.'}
            try:
                stats=rpc('visitas_previa_remocao_comuns_roteiro',p_id=str(plan_id),p_data=plan['date'],p_municipio=plan['city'])
                removal={'available':True,'commons':stats['commons'],'token':signing.dumps({
                    'actor':str(request.session['user_id']),'id':str(plan_id),'data':plan['date'],
                    'municipio':plan['city'],'version':stats['version']},salt=REMOVE_SALT,compress=True)}
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code in {404,406}:
                    removal={'available':False,'reason':'Aplique a migration 060 para habilitar a exclusão por comum.','migration':REMOVE_MIGRATION}
            except (requests.RequestException,KeyError,TypeError):pass
            deletion={'available':False,'reason':'Não foi possível consultar a exclusão. Carregue o planejamento novamente.'}
            try:
                stats=rpc('visitas_previa_exclusao_roteiro_regional',p_id=str(plan_id),p_data=plan['date'],p_municipio=plan['city'])
                protected=int(stats['protegidos'])
                deletion={'available':not protected,'count':int(stats['agendamentos']),
                    'reason':'Existem visitas encerradas ou em andamento neste roteiro.' if protected else '',
                    'token':signing.dumps({'actor':str(request.session['user_id']),'id':str(plan_id),'data':plan['date'],
                        'municipio':plan['city'],'version':stats['version']},salt=DELETE_SALT,compress=True) if not protected else ''}
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code in {404,406}:
                    deletion['reason']='Aplique a migration 059 para habilitar a exclusão de agendamentos.'
                    deletion['migration']=DELETE_MIGRATION
            except requests.RequestException:pass
            coverage=plan.get('coverage') or [{'common':c,'records':None,
                'included_records':sum(m['comum']==c for h in plan['houses'] for m in h['members']),
                'families':sum(any(m['comum']==c for m in h['members']) for h in plan['houses'])} for c in plan['commons']]
            return JsonResponse({'id':str(plan_id),'deletion':deletion,'removal':removal,'coverage':coverage,'commons':plan['commons'],
                'requires_route_refresh':not rows[0].get('substituido_em') and not plan.get('origins'),
                'historical':bool(rows[0].get('substituido_em')),'groups':[
                {'id':str(g['id']),'name':g['nome'],'coordinator':g.get('coordenador_nome',''),
                 'families':len(g['houses']),'commons':g['commons'],'filename':route_filename(plan,g),
                 'pdf_url':base+'?'+urlencode({'grupo':g['id'],'formato':'pdf'}),
                 'print_url':base+'?'+urlencode({'grupo':g['id']}),
                 'google_url':base+'?'+urlencode({'grupo':g['id'],'mapa':'google'}) if settings.GOOGLE_MAPS_API_KEY else None} for g in groups],
                 'zip_url':base+'?formato=zip','excel_url':base+'?formato=excel'})
        def download(content,name,mime):
            response=HttpResponse(content,content_type=mime)
            response['Content-Disposition']="attachment; filename*=UTF-8''"+quote(name)
            return response
        if not rows[0].get('substituido_em'):
            refresh_missing_preferences(groups,{c['comum'] for c in catalog})
            decorate_groups(groups)
        if output=='excel':
            return download(build_workbook(plan,groups,request),'ROTEIROS_VISITAS_'+date.fromisoformat(plan['date']).strftime('%d_%m_%Y')+'.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        if output not in {'pdf','zip','html'}:return JsonResponse({'error':'Formato de exportação inválido.'},status=400)
        # Roteiros antigos ganham distancias sem mudar a ordem ou a agenda salva.
        geometry={**plan,'houses':[h for g in groups for h in g['houses']]}
        enrich_plan_geometry(geometry)
        for group in groups:group['origins']=geometry.get('origins',{})
        prepare_navigation(groups, plan['city'], request)
        if output=='pdf':
            if len(groups)!=1:return JsonResponse({'error':'Selecione um grupo ou baixe os PDFs individuais em ZIP.'},status=400)
            return download(build_group_pdf(plan,groups[0],request,bool(rows[0].get('substituido_em')),request.GET.get('mapa')!='none'),route_filename(plan,groups[0]),'application/pdf')
        if output=='zip':
            buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
                for group in groups:
                    if group['houses']:archive.writestr(route_filename(plan,group),build_group_pdf(plan,group,request,bool(rows[0].get('substituido_em')),request.GET.get('mapa')!='none'))
            return download(buffer.getvalue(),'ROTEIROS_VISITAS_'+plan['city'].replace(' ','_')+'_'+date.fromisoformat(plan['date']).strftime('%d_%m_%Y')+'.zip','application/zip')
        if len(groups)==1:
            from .regional_route_reports import original_route_context
            mode=request.GET.get('mapa','google')
            if mode not in {'none','google'}:mode='google'
            return render(request,'pages/visitas-roteiro-impresso.html',original_route_context(plan,groups[0],request,mode,bool(rows[0].get('substituido_em'))))
        return render(request,'pages/visitas-roteiro-regional-impresso.html',{
            'plan':plan,'groups':groups,'historical':bool(rows[0].get('substituido_em')),
            'visit_date':date.fromisoformat(plan['date']).strftime('%d/%m/%Y'),
            'file_date':date.fromisoformat(plan['date']).strftime('%d_%m_%Y'),
        })
    except PermissionError:
        return render(request,'pages/403.html',status=403)
    except requests.RequestException:
        return JsonResponse({'error':'Nao foi possivel carregar o roteiro.'},status=503)
    except ValueError as exc:
        return JsonResponse({'error':str(exc)},status=422)
