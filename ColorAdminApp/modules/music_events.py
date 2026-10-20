"""Página operacional dos ensaios e RTs, sobre a migração 029."""
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4

import requests
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .access_control import can_access, service_headers, user_scope, common_catalog
from .gem import can_open_module
from .music_events_import import parse_workbook, norm
from .music_events_dashboard import aggregate, code, REGIONAL
from .music_events_identity import CommonResolver


def _allowed(request):
    return bool(request.session.get('authenticated')) and can_open_module(request)


def _read(table, **params):
    rows = []
    while True:
        response = requests.get(
            f'{settings.SUPABASE_URL}/rest/v1/{table}', headers=service_headers(),
            params={'select': '*', **params, 'offset': len(rows), 'limit': 1000}, timeout=15,
        )
        response.raise_for_status()
        batch = response.json()
        rows.extend(batch)
        if len(batch) < 1000:
            return rows


def _visible_events(request):
    events = _read('musica_eventos', order='data_evento.desc,id.asc')
    scope = user_scope(request)
    if scope['level'] in {'regional', 'global'}:
        return events
    # A permissão segue a comum de origem, não o município físico do encontro.
    commons = {row['codigo']: row for row in _read('musica_evento_comuns', order='codigo.asc')}
    authorized = set()
    for row in _read('musica_evento_convocacoes', order='evento_id.asc,comum_codigo.asc'):
        common = commons.get(row['comum_codigo'], {})
        location = {'comum': f"{row['comum_codigo']} - {common.get('nome', '')}",
                    'cidade': common.get('municipio')}
        if can_access(scope, location) or (scope['level'] == 'local' and
                str(scope.get('comum', '')).split(' - ')[0] == row['comum_codigo']):
            authorized.add(row['evento_id'])
    # Contagens preliminares ainda não têm convocações SAM; autorizar pela origem,
    # mantendo o filtro por pessoa antes de calcular qualquer indicador.
    from .music_events_dashboard import code
    catalog=common_catalog()
    canonical = {code(x.get('comum')):x for x in catalog}
    resolver=CommonResolver(catalog)
    for row in _read('musica_evento_presencas',situacao='eq.PRESENTE',order='id.asc'):
        common = row.get('comum_codigo') or row.get('comum_informada') or ''
        location = canonical.get(code(common)) or resolver.resolve(common,row.get('municipio_informado')) or {'comum':common,'cidade':row.get('municipio_informado')}
        if can_access(scope,location) or (scope['level']=='local' and code(scope.get('comum'))==code(common)):
            authorized.add(row['evento_id'])
    return [event for event in events if event['id'] in authorized]


def page(request):
    if not _allowed(request):
        return render(request, 'pages/403.html', {'message': 'Seu perfil não possui acesso à pasta Música.'}, status=403)
    return render(request, 'pages/music_events.html')


@require_http_methods(['GET', 'POST'])
def api_events(request):
    if not _allowed(request):
        return JsonResponse({'error': 'Acesso não autorizado à pasta Música.'}, status=403)
    try:
        scope = user_scope(request)
        manager = scope['level'] in {'regional', 'global'}
        if request.method == 'POST':
            if not manager:
                return JsonResponse({'error': 'Somente a administração regional pode criar eventos.'}, status=403)
            raw = json.loads(request.body or '{}')
            title = str(raw.get('titulo') or '').strip()
            event_date = date.fromisoformat(str(raw.get('data_evento') or '')).isoformat()
            kind, family = raw.get('tipo'), raw.get('familia', 'GERAL')
            if not title or len(title) > 180 or kind not in {'ENSAIO_REGIONAL', 'REUNIAO_TECNICA'}:
                raise ValueError('Informe título, data e tipo válidos.')
            if family not in {'GERAL', 'CORDAS', 'MADEIRAS', 'METAIS'}:
                raise ValueError('Família inválida.')
            if kind == 'ENSAIO_REGIONAL':
                family = 'GERAL'
            bases = _read('musica_evento_bases', id=f"eq.{raw.get('base_id')}", homologada_em='not.is.null')
            if not bases:
                raise ValueError('Selecione uma base SAM homologada.')
            profile = request.session.get('user_profile') or {}
            user_id = request.session.get('user_id') or profile.get('user_id')
            actor = profile.get('full_name') or profile.get('nome') or profile.get('name') or profile.get('email')
            if not user_id or not actor:
                return JsonResponse({'error': 'Atualize sua sessão para identificar o responsável.'}, status=401)
            payload = {'titulo': title, 'data_evento': event_date, 'tipo': kind, 'familia': family,
                       'base_id': bases[0]['id'], 'status': 'RASCUNHO',
                       'created_by_user_id': str(user_id), 'created_by_name': actor,
                       'updated_by_user_id': str(user_id), 'updated_by_name': actor,
                       'observacoes': str(raw.get('observacoes') or '')[:4000]}
            response = requests.post(f'{settings.SUPABASE_URL}/rest/v1/musica_eventos',
                                     headers=service_headers('return=representation'), json=payload, timeout=15)
            response.raise_for_status()
            return JsonResponse({'item': response.json()[0]}, status=201)
        events = _visible_events(request)
        bases = _read('musica_evento_bases', order='referencia.desc,id.asc') if manager else []
        # A lista não expõe documentos, hashes, observações privadas ou população nominal.
        bases = [{'id': row['id'], 'referencia': row['referencia'], 'origem': row['origem'],
                  'homologada': bool(row.get('homologada_em'))} for row in bases]
        return JsonResponse({'items': events, 'bases': bases, 'can_manage': manager})
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Confira título, data, tipo, família e base SAM homologada.'}, status=400)
    except requests.RequestException:
        return JsonResponse({'error': 'Não foi possível consultar ou salvar os eventos. Confira a conexão e a migração 029.'}, status=502)


@require_http_methods(['GET'])
def api_detail(request, event_id):
    if not _allowed(request):
        return JsonResponse({'error': 'Acesso não autorizado.'}, status=403)
    try:
        event = next((row for row in _visible_events(request) if row['id'] == str(event_id)), None)
        if event is None:
            return JsonResponse({'error': 'Evento não encontrado ou fora do seu escopo.'}, status=404)
        scope = user_scope(request)
        frequency = _read('musica_evento_frequencia', evento_id=f'eq.{event_id}', order='municipio.asc,comum.asc')
        if scope['level'] not in {'global', 'regional'}:
            frequency = [row for row in frequency if can_access(scope, {
                'comum': f"{row['comum_codigo']} - {row['comum']}", 'cidade': row['municipio']}) or
                (scope['level'] == 'local' and str(scope.get('comum', '')).split(' - ')[0] == row['comum_codigo'])]
        # Resumos físicos podem conter outras comuns: só a administração regional os recebe.
        locations = _read('musica_evento_resumo_local', evento_id=f'eq.{event_id}', order='nome.asc') if scope['level'] in {'global', 'regional'} else []
        counts = []
        instruments, roles, families = Counter(), Counter(), Counter()
        if scope['level'] in {'global', 'regional'}:
            grouped = {}
            for row in _read('musica_evento_presencas', evento_id=f'eq.{event_id}', situacao='eq.PRESENTE', order='id.asc'):
                common = row.get('comum_informada') or row.get('comum_codigo') or 'Não informada'
                code = re.match(r'^(BR-\d+-\d+)', common)
                key = (code.group(1) if code else norm(common), norm(row.get('municipio_informado')))
                group = grouped.setdefault(key, {'comum': common, 'municipio': row.get('municipio_informado') or 'Não informado',
                    'MUSICO': 0, 'ORGANISTA': 0, 'MINISTERIO': 0, 'APOIO': 0, 'IRMANDADE': 0, 'total': 0})
                group[row['categoria']] += 1
                group['total'] += 1
                roles[row.get('cargo') or 'Não informado'] += 1
                if row['categoria'] in {'MUSICO', 'ORGANISTA'}:
                    instruments[row.get('instrumento') or 'Não informado'] += 1
                    families[row.get('familia') or 'OUTROS'] += 1
            counts = sorted(grouped.values(), key=lambda x: (x['municipio'], x['comum']))
        return JsonResponse({'item': event, 'frequency': frequency, 'locations': locations,
                             'counts': counts, 'instruments': dict(instruments), 'roles': dict(roles), 'families': dict(families)})
    except requests.RequestException:
        return JsonResponse({'error': 'Não foi possível carregar o evento.'}, status=502)


@require_http_methods(['POST'])
def api_import(request, action):
    if not _allowed(request) or user_scope(request)['level'] not in {'regional', 'global'}:
        return JsonResponse({'error': 'Importação restrita à administração regional.'}, status=403)
    profile = request.session.get('user_profile') or {}
    actor_id = request.session.get('user_id') or profile.get('user_id')
    actor = profile.get('full_name') or profile.get('nome') or profile.get('name') or profile.get('email')
    if not actor_id or not actor:
        return JsonResponse({'error': 'Entre novamente para identificar o responsável.'}, status=401)
    try:
        if action == 'previa':
            upload = request.FILES.get('arquivo')
            if not upload or not upload.name.lower().endswith('.xlsx') or upload.size > 15 * 1024 * 1024:
                raise ValueError('Selecione um arquivo .xlsx de até 15 MB.')
            result = parse_workbook(upload.read())
            token = uuid4().hex
            cache.set(f'music-events-import:{actor_id}:{token}', result, 1800)
            return JsonResponse({'token': token, **{key: value for key, value in result.items() if key != 'records'}})
        if action != 'confirmar':
            return JsonResponse({'error': 'Operação inválida.'}, status=404)
        raw = json.loads(request.body or '{}')
        token = str(raw.get('token') or '')
        result = cache.get(f'music-events-import:{actor_id}:{token}')
        if not result:
            raise ValueError('A prévia expirou. Selecione o arquivo novamente.')
        day = date.fromisoformat(str(raw.get('data_evento') or '')).isoformat()
        if raw.get('conferido') is not True:
            raise ValueError('Confirme a conferência de datas, duplicidades e classificação.')
        title = str(raw.get('titulo') or '').strip()
        kind, family = raw.get('tipo'), raw.get('familia') or 'GERAL'
        if not title or len(title) > 180 or kind not in {'ENSAIO_REGIONAL', 'REUNIAO_TECNICA'} or family not in {'GERAL', 'CORDAS', 'MADEIRAS', 'METAIS'}:
            raise ValueError('Confira título, tipo e família.')
        if kind == 'ENSAIO_REGIONAL':
            family = 'GERAL'
        response = requests.post(f'{settings.SUPABASE_URL}/rest/v1/rpc/musica_evento_importar_appcont',
            headers=service_headers(), json={'p_hash': result['sha256'], 'p_titulo': title, 'p_data': day,
                'p_tipo': kind, 'p_familia': family, 'p_usuario_id': str(actor_id), 'p_usuario_nome': actor,
                'p_resumo': {k: v for k, v in result.items() if k != 'records'}, 'p_registros': result['records']}, timeout=90)
        response.raise_for_status()
        return JsonResponse(response.json())
    except (ValueError, TypeError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except requests.RequestException:
        return JsonResponse({'error': 'Não foi possível confirmar a importação. Verifique a conexão e se a migração 030 foi aplicada. Você pode repetir a confirmação; o mesmo arquivo não será duplicado.'}, status=502)


def dashboard_data(request):
    events = _visible_events(request)
    filters = {key:request.GET.get(key,'').strip() for key in
               ('evento','ano','mes','inicio','fim','tipo','status','busca','local','origem')}
    filters.update(municipios=request.GET.getlist('municipio'), comuns=request.GET.getlist('comum'))
    filters['origem'] = filters.get('origem') or 'regional'
    if filters['origem'] not in {'regional','visitantes','todos'}:
        raise ValueError('Origem inválida.')
    chosen = aggregate(events,[],[],[],filters)['events']
    history_filters=dict(filters);history_filters.pop('evento',None)
    history_events=aggregate(events,[],[],[],history_filters)['events']
    records, locations, frequencies, eligible = [],[],[],[]
    # Lotes limitam o comprimento da URL; cada fonte é paginada em _read.
    for start in range(0,len(history_events),40):
        batch = history_events[start:start+40]
        ids = 'in.(' + ','.join(e['id'] for e in batch) + ')'
        with ThreadPoolExecutor(max_workers=4) as executor:
            people_future=executor.submit(_read,'musica_evento_presencas',evento_id=ids,situacao='eq.PRESENTE',order='id.asc')
            sites_future=executor.submit(_read,'musica_evento_locais',evento_id=ids,order='id.asc')
            if any(e.get('base_id') for e in batch):
                frequency_future=executor.submit(_read,'musica_evento_frequencia',evento_id=ids,order='evento_id.asc,comum_codigo.asc')
                eligible_future=executor.submit(_read,'musica_evento_elegiveis',evento_id=ids,order='evento_id.asc,sam_pessoa_id.asc')
                frequencies.extend(frequency_future.result());eligible.extend(eligible_future.result())
            records.extend(people_future.result());locations.extend(sites_future.result())
    scope = user_scope(request)
    catalog = common_catalog() if chosen else []
    records=CommonResolver(catalog).records(records)
    if scope['level'] not in {'regional','global'}:
        canonical = {code(x.get('comum')):x for x in catalog}
        resolver=CommonResolver(catalog)
        def permitted(row):
            common = row.get('comum_codigo') or row.get('comum_informada') or ''
            location = canonical.get(code(common)) or resolver.resolve(common,row.get('municipio_informado')) or {'comum':common,'cidade':row.get('municipio_informado')}
            return can_access(scope,location) or (scope['level']=='local' and code(scope.get('comum'))==code(common))
        records = [x for x in records if permitted(x)]
        frequencies = [x for x in frequencies if permitted({'comum_codigo':x['comum_codigo'],'municipio_informado':x['municipio']})]
        eligible = [x for x in eligible if permitted(x)]
    result = aggregate(events,records,locations,frequencies,filters,catalog,eligible)
    from .music_events_registry import attach_registry
    registry=cache.get('music-events:registry:v2')
    if registry is None:
        registry=_read('musica_acompanhamento_aluno',select='id,nome_aluno,cargo_ministerio,status,nivel,instrumento,comum_congregacao,municipio,updated_at',order='id.asc')
        cache.set('music-events:registry:v2',registry,300)
    if scope['level'] not in {'regional','global'}:
        registry=[r for r in registry if permitted({'comum_codigo':r.get('comum_congregacao'),'municipio_informado':r.get('municipio')})]
    attach_registry(result,registry,catalog)
    from .music_events_conductors import summarize
    reviews=[];review_available=True
    for event in chosen:
        try:reviews.extend(_read('musica_evento_encarregados',evento_id='eq.'+event['id'],order='comum_chave.asc'))
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code==404:review_available=False;break
            raise
    if scope['level'] not in {'regional','global'}:
        reviews=[r for r in reviews if permitted({'comum_codigo':r['comum_chave'],'municipio_informado':r['municipio']})]
    result['conductors']=summarize(chosen,records,locations,reviews,filters,catalog,frequencies,registry)
    from .music_events_leaders import attach_leaders
    members=cache.get('music-events:registered-leaders:v1')
    if members is None:
        members=_read(settings.SUPABASE_TABLE_VISITAS_IRMANDADE,select='id,nome,cargo_outros,codigo_comum,comum,cidade,status',cargo_outros='ilike.*encarregado local*',order='id.asc')
        cache.set('music-events:registered-leaders:v1',members,300)
    if scope['level'] not in {'regional','global'}:
        members=[r for r in members if permitted({'comum_codigo':r.get('codigo_comum') or r.get('comum'),'municipio_informado':r.get('cidade')})]
    attach_leaders(result,registry,catalog,members)
    result['conductors']['available']=review_available
    result['conductors']['catalog']=[{'key':code(x['comum']),'name':x['comum'],'city':x['cidade']}
        for x in catalog if norm(x.get('cidade')) in {norm(c) for c in REGIONAL}
        and can_access(scope,x)]
    result['conductors']['sites']=[{'id':x['id'],'evento_id':x['evento_id'],'nome':x['nome']} for x in locations if x['evento_id'] in {e['id'] for e in chosen}]
    if len(chosen)==1:
        by_key={r['comum_chave']:r for r in result['conductors']['rows']}
        for row in result['rows']:
            entry=by_key.get(code(row['comum']))
            if entry:
                row['encarregado']=entry['registro']
                row['encarregado_situacao']=entry['situacao']
                row['encarregado_local']=' / '.join(entry.get('locais',[]))
                row['encarregado_situacao_label']=entry['situacao_label']+(' · '+entry['registro'] if entry['situacao']=='PRESENTE' else '')
    elif len(chosen)>1:
        for row in result['rows']:row['encarregado']='Ver conferência por evento'
    from .music_events_evolution import evolution
    result['evolution']=evolution(events,records,locations,filters,catalog)
    # Não listar locais de outros territórios a perfis restritos.
    if scope['level'] not in {'regional','global'}:
        visible_sites = {x['local_id'] for x in records}
        result['options']['locations'] = [x for x in result['options']['locations'] if x['id'] in visible_sites]
        result['conductors']['sites'] = [x for x in result['conductors']['sites'] if x['id'] in visible_sites]
    return result


@require_http_methods(['POST'])
def api_conductor(request,event_id):
    if not _allowed(request):return JsonResponse({'error':'Acesso não autorizado.'},status=403)
    try:
        from .music_events_conductors import LABELS
        event=next((e for e in _visible_events(request) if e['id']==str(event_id)),None)
        if not event:return JsonResponse({'error':'Evento não encontrado ou fora do seu escopo.'},status=404)
        if event['status']=='ENCERRADO':return JsonResponse({'error':'Reabra o evento antes de alterar a conferência.'},status=409)
        raw=json.loads(request.body or '{}');key=str(raw.get('comum_chave') or '')
        common=next((x for x in common_catalog() if code(x.get('comum'))==key),None)
        if not common:
            rows=_read('musica_evento_presencas',evento_id=f'eq.{event_id}',order='id.asc')
            source=next((x for x in rows if code(x.get('comum_codigo') or x.get('comum_informada'))==key),None)
            if source:common={'comum':source.get('comum_informada') or key,'cidade':source.get('municipio_informado') or 'Não informado'}
        scope=user_scope(request)
        if not common or not (can_access(scope,common) or (scope['level']=='local' and code(scope.get('comum'))==key)):
            return JsonResponse({'error':'Comum não identificada ou fora do seu escopo.'},status=403)
        status=raw.get('situacao');notes=str(raw.get('observacoes') or '').strip()
        if len(notes)>500:raise ValueError('Use até 500 caracteres na observação.')
        if status not in LABELS:raise ValueError('Situação inválida.')
        if status=='JUSTIFICOU' and not notes:raise ValueError('Informe a justificativa ou a referência recebida.')
        local=raw.get('local_id') if status=='PRESENTE' else None
        if status=='PRESENTE' and not local:raise ValueError('Selecione o local de comparecimento.')
        if status=='PRESENTE' and not _read('musica_evento_locais',evento_id=f'eq.{event_id}',id='eq.'+str(local)):
            raise ValueError('Selecione o local em que o encarregado esteve presente.')
        profile=request.session.get('user_profile') or {};actor_id=request.session.get('user_id') or profile.get('user_id')
        actor=profile.get('full_name') or profile.get('nome') or profile.get('name') or profile.get('email')
        if not actor_id or not actor:return JsonResponse({'error':'Entre novamente para identificar o responsável.'},status=401)
        existing=_read('musica_evento_encarregados',evento_id=f'eq.{event_id}',comum_chave='eq.'+key)
        payload={'municipio':common['cidade'],'comum_nome':common['comum'],'situacao':status,'local_id':local,
                 'observacoes':notes,'updated_by_user_id':str(actor_id),'updated_by_name':actor}
        params=None
        if existing:method=requests.patch;params={'id':'eq.'+existing[0]['id']}
        else:
            method=requests.post;payload.update(evento_id=str(event_id),comum_chave=key,created_by_user_id=str(actor_id),created_by_name=actor)
        response=method(f'{settings.SUPABASE_URL}/rest/v1/musica_evento_encarregados',headers=service_headers('return=representation'),json=payload,params=params,timeout=15)
        response.raise_for_status();return JsonResponse({'item':response.json()[0]})
    except (ValueError,TypeError) as exc:return JsonResponse({'error':str(exc)},status=400)
    except requests.RequestException:return JsonResponse({'error':'Não foi possível salvar. Confira a conexão e aplique a migração 031 para habilitar a conferência dos encarregados.'},status=502)


@require_http_methods(['GET'])
def api_dashboard(request):
    if not _allowed(request):
        return JsonResponse({'error':'Acesso não autorizado.'},status=403)
    try:
        return JsonResponse(dashboard_data(request))
    except requests.RequestException:
        return JsonResponse({'error':'Não foi possível carregar os indicadores. Tente atualizar novamente.'},status=502)


@require_http_methods(['GET'])
def export_dashboard(request, file_format):
    if not _allowed(request):
        return JsonResponse({'error':'Acesso não autorizado.'},status=403)
    if file_format not in {'excel','pdf'}:
        return JsonResponse({'error':'Formato inválido.'},status=404)
    try:
        from .music_events_reports import export_response
        return export_response(dashboard_data(request),request,file_format)
    except requests.RequestException:
        return JsonResponse({'error':'Não foi possível consultar os dados para exportação.'},status=502)
