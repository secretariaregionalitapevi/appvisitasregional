"""Scope-checked group deletion with an explicit, session-bound preview."""
import hashlib
import json
import uuid
from datetime import datetime

import requests
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from . import music_exams as exams
from .access_control import can_access, user_scope, service_headers

TTL = 600
BATCH_SIZE = 20


def row_version(row):
    # Older installations do not refresh updated_at on every edit.
    return hashlib.sha256(json.dumps(row,sort_keys=True,default=str).encode()).hexdigest()


def owner(request):
    if not request.session.get('exam_delete_owner'):
        request.session['exam_delete_owner'] = uuid.uuid4().hex
    return hashlib.sha256((request.session['exam_delete_owner'] + json.dumps(request.session.get('user_profile') or {}, sort_keys=True)).encode()).hexdigest()


def parse_group(value):
    if not isinstance(value, dict):
        raise ValueError('Informe o grupo de exames.')
    administration = exams.norm(value.get('administracao'))
    category = exams.norm(value.get('categoria'))
    day = datetime.strptime(str(value.get('data_exame') or ''), '%Y-%m-%d').date().isoformat()
    if administration not in {*exams.GROUPS, 'OUTRAS ADMINISTRACOES'} or category not in {'MUSICOS', 'ORGANISTAS'}:
        raise ValueError('Administração ou categoria inválida.')
    return {'administracao':administration, 'categoria':category, 'data_exame':day}


def matches_group(row, group):
    city = exams.norm(row.get('municipio'))
    known = any(token in city for token in ('ITAPEVI','JANDIRA','COTIA','CAUCAIA','VARGEM GRANDE','VGP','SANTANA','PIRAPORA','FAZENDINHA'))
    administration = exams.regional_group(city) if known else 'OUTRAS ADMINISTRACOES'
    if 'FAZENDINHA' in city:
        administration = exams.GROUPS[3]
    organist = 'ORGANISTA' in exams.norm(row.get('categoria')) or exams.norm(row.get('instrumento')) in {'ORGAO','ORGANISTA'}
    category = 'ORGANISTAS' if organist else 'MUSICOS'
    return administration == group['administracao'] and category == group['categoria'] and str(row.get('data_exame') or '')[:10] == group['data_exame']


def group_rows(request, group):
    scope = user_scope(request)
    params = {'select':'*','data_exame':'eq.'+group['data_exame'],'order':'id','limit':1000,'offset':0}
    if scope['level'] == 'municipal':
        if not scope['municipio']:
            return []
        params['municipio'] = 'eq.'+scope['municipio']
    elif scope['level'] == 'local':
        if not scope['comum']:
            return []
        params['comum'] = 'eq.'+scope['comum']
    result = []
    while True:
        response = requests.get(exams.rest_url(), headers=service_headers(), params=params, timeout=(5,20))
        response.raise_for_status()
        rows = response.json()
        result.extend(r for r in rows if matches_group(r,group) and can_access(scope,{'municipio':r.get('municipio'),'comum':r.get('comum')}))
        if len(rows) < 1000:
            break
        params['offset'] += 1000
    return result


def delete_batch(rows):
    """Remove mirrors first, restoring only exams confirmed to still exist on failure."""
    ids = 'in.('+','.join(str(uuid.UUID(str(r['id']))) for r in rows)+')'
    mirror_url = settings.SUPABASE_URL+'/rest/v1/musica_exames_lancamentos'
    response = requests.delete(mirror_url,headers=service_headers('return=minimal'),params={'id':ids},timeout=(5,20))
    response.raise_for_status()
    try:
        response = requests.delete(exams.rest_url(),headers=service_headers('return=representation'),params={'id':ids},timeout=(5,20))
        response.raise_for_status()
        deleted = {str(r['id']) for r in response.json()}
        expected = {str(r['id']) for r in rows}
        if deleted != expected:
            raise requests.RequestException('O grupo mudou durante a exclusão.')
    except requests.RequestException:
        # A timeout may occur after the DELETE commits. Never recreate orphan counts.
        remaining = requests.get(exams.rest_url(),headers=service_headers(),params={'select':'*','id':ids},timeout=(5,20))
        remaining.raise_for_status()
        for row in remaining.json():
            exams.sync_shared_exam(row)
        raise
    return deleted


def api_delete_group(request):
    if not exams.can_open_module(request):
        return exams.denied()
    if request.method != 'POST':
        return JsonResponse({'error':'Método não permitido.'},status=405)
    try:
        data = json.loads(request.body or '{}')
        if not isinstance(data, dict):
            raise ValueError('Pedido inválido.')
        if data.get('acao') == 'previa':
            group = parse_group(data.get('grupo'))
            mode = data.get('modo')
            if mode not in {'todos','selecionados'}:
                raise ValueError('Escolha todos ou os registros selecionados.')
            rows = group_rows(request,group)
            if mode == 'selecionados':
                raw_ids = data.get('ids')
                if not isinstance(raw_ids,list) or not raw_ids or len(raw_ids)>5000:
                    raise ValueError('Selecione de 1 a 5.000 registros.')
                ids = {str(uuid.UUID(str(value))) for value in raw_ids}
                visible = {str(r['id']) for r in rows}
                if not ids.issubset(visible):
                    return JsonResponse({'error':'Há registros fora deste exame ou do seu acesso. Atualize a lista.'},status=409)
                rows = [r for r in rows if str(r['id']) in ids]
            if not rows:
                raise ValueError('Nenhum registro disponível neste grupo.')
            if len(rows)>5000:
                raise ValueError('Exclua em partes de até 5.000 registros.')
            token = uuid.uuid4().hex
            cache.set('exam-delete:'+token,{'owner':owner(request),'group':group,'mode':mode,
                'remaining':{str(r['id']):row_version(r) for r in rows},'deleted':0,'total':len(rows)},TTL)
            return JsonResponse({'token':token,'grupo':group,'quantidade':len(rows)})
        if data.get('acao') != 'confirmar':
            raise ValueError('Ação inválida.')
        token = str(uuid.UUID(str(data.get('token') or ''))).replace('-','')
        key = 'exam-delete:'+token
        lock = key+':lock'
        batch = cache.get(key)
        if not batch or batch['owner'] != owner(request):
            return JsonResponse({'error':'A confirmação expirou. Selecione o grupo novamente.'},status=409)
        if not cache.add(lock,True,120):
            return JsonResponse({'error':'A exclusão deste grupo já está em andamento.'},status=409)
        try:
            batch = cache.get(key)
            current = {str(r['id']):r for r in group_rows(request,batch['group'])}
            remaining = batch['remaining']
            changed = not set(remaining).issubset(current) or any(row_version(current[k]) != value for k,value in remaining.items() if k in current)
            if batch['mode']=='todos' and set(current)!=set(remaining):
                changed = True
            if changed:
                return JsonResponse({'error':'O grupo foi alterado após a confirmação. Atualize a lista e confira novamente.','excluidos':batch['deleted']},status=409)
            selected = [current[key] for key in list(remaining)[:BATCH_SIZE]]
            if selected:
                deleted = delete_batch(selected)
                for record_id in deleted:
                    remaining.pop(record_id,None)
                batch['deleted'] += len(deleted)
                cache.set(key,batch,TTL)
            return JsonResponse({'ok':True,'excluidos':batch['deleted'],'restantes':len(remaining),'total':batch['total']})
        finally:
            cache.delete(lock)
    except (ValueError,TypeError,KeyError) as error:
        return JsonResponse({'error':str(error)},status=400)
    except requests.RequestException:
        return JsonResponse({'error':'A exclusão foi interrompida. Atualize a lista para conferir os registros restantes antes de tentar novamente.'},status=502)
