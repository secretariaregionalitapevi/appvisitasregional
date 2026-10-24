"""Uma conferência por evento e comum; não confundir com contagem de pessoas."""
from collections import Counter
from .music_events_dashboard import code, REGIONAL, regional_city
from .music_events_import import norm
from .music_events_identity import CommonResolver
from .music_events_calendar import validated_sites

LABELS={'PRESENTE':'Presente','JUSTIFICOU':'J · Justificou','NAO_JUSTIFICOU':'NJ · Não justificou',
        'NAO_INFORMADO':'Não informado','SEM_ENCARREGADO':'Sem encarregado','ENFERMO':'Enfermo'}


def attendance_status(row):
    raw = row.get('leader_attendance') or row.get('presenca_situacao') or row.get('encarregado_situacao') or row.get('leader_status') or row.get('situacao')
    return raw if raw in {'PRESENTE', 'JUSTIFICOU', 'SEM_ENCARREGADO', 'ENFERMO'} else 'NAO_JUSTIFICOU'


def attendance_label(row):
    return {'PRESENTE': 'PRESENTE', 'JUSTIFICOU': 'JUSTIFICOU', 'NAO_JUSTIFICOU': 'NJ',
            'SEM_ENCARREGADO': 'SEM ENCARREGADO', 'ENFERMO': 'ENFERMO'}[attendance_status(row)]


def summarize(events,records,sites,reviews,filters,catalog=(),frequency=(),leaders=()):
    resolver=CommonResolver(catalog)
    registered_leaders={};leaders_by_city_name={}
    for person in leaders:
        roles={norm(x) for x in str(person.get('cargo_ministerio') or '').split(',')}
        if 'ENCARREGADO LOCAL' not in roles or norm(person.get('status')) in {'INATIVO','EXCLUIR'}:continue
        common=resolver.resolve(person.get('codigo_comum') or person.get('comum_congregacao'),person.get('municipio'))
        name=norm(person.get('nome_aluno'))
        if not common or not name:continue
        key=code(common['comum']);registered_leaders.setdefault(key,set()).add(name)
        leaders_by_city_name.setdefault((norm(regional_city(common['cidade'])),name),set()).add(key)
    records=resolver.records(records)
    canonical_by_code={code(x.get('comum')):x for x in catalog}
    for row in records:
        if not row.get('comum_nao_reconhecida'):continue
        matches=leaders_by_city_name.get((norm(regional_city(row.get('municipio_informado'))),norm(row.get('nome'))),set())
        if len(matches)!=1:continue
        canonical=canonical_by_code[next(iter(matches))]
        row['comum_codigo']=code(canonical['comum']);row['comum_informada']=canonical['comum']
        row['municipio_informado']=canonical['cidade'];row.pop('comum_nao_reconhecida',None)
    normalized_reviews=[]
    for original in reviews:
        row=dict(original);canonical=resolver.resolve(row['comum_chave'],row['municipio'])
        if canonical:
            row.update(comum_chave=code(canonical['comum']),comum_nome=canonical['comum'],municipio=canonical['cidade'])
        normalized_reviews.append(row)
    reviews=sorted(normalized_reviews,key=lambda r:str(r.get('updated_at') or ''))
    event_map={e['id']:e for e in events};site_map={s['id']:s for s in validated_sites(events, sites)}
    reference={(r['evento_id'],code(r['comum_codigo'])):r.get('local_referencia_id') for r in frequency}
    canonical=canonical_by_code;groups={}
    def allowed(city,key):
        origin=filters.get('origem') or 'regional'
        return (not filters.get('municipios') or norm(regional_city(city)) in {norm(regional_city(x)) for x in filters['municipios']}) and (
            not filters.get('comuns') or key in filters['comuns']) and (origin=='todos' or
            ((norm(regional_city(city)) in {norm(x) for x in REGIONAL})==(origin=='regional')))
    for item in frequency:
        if item['evento_id'] not in event_map:continue
        key=code(item['comum_codigo']);city=regional_city(item.get('municipio') or 'Não informado')
        if not allowed(city,key):continue
        event=event_map[item['evento_id']];canonical_common=canonical.get(key,{})
        groups.setdefault((event['id'],key),{'evento_id':event['id'],'evento':event['titulo'],
            'data':event['data_evento'],'comum_chave':key,'comum':canonical_common.get('comum') or item.get('comum') or key,
            'municipio':canonical_common.get('cidade') or city,'situacao':'NAO_INFORMADO','locais':[],
            'nomes':[],'observacoes':'','fonte':'Não conferido'})
    for row in records:
        if row['evento_id'] not in event_map or row.get('situacao','PRESENTE')!='PRESENTE':continue
        common=row.get('comum_codigo') or row.get('comum_informada') or 'Não informada';key=code(common)
        c=canonical.get(key,{});city=regional_city(c.get('cidade') or row.get('municipio_informado') or 'Não informado')
        if not allowed(city,key):continue
        event=event_map[row['evento_id']]
        group=groups.setdefault((event['id'],key),{'evento_id':event['id'],'evento':event['titulo'],
            'data':event['data_evento'],'comum_chave':key,'comum':c.get('comum') or ('A conferir: '+common if row.get('comum_nao_reconhecida') else common),'municipio':city,
            'situacao':'NAO_INFORMADO','locais':[],'nomes':[],'observacoes':'','fonte':'Não conferido'})
        imported_local_conductor='ENCARREGADO LOCAL' in norm(row.get('cargo'))
        registered_identity=norm(row.get('nome')) in registered_leaders.get(key,set())
        if imported_local_conductor or registered_identity:
            group['consta_lista']=True
            group['situacao']='PRESENTE';group['fonte']='Presença nominal importada'
            local=site_map.get(row['local_id'],{}).get('nome','Não informado')
            if local not in group['locais']:group['locais'].append(local)
            if row.get('nome') and row['nome'] not in group['nomes']:group['nomes'].append(row['nome'])
    for review in reviews:
        if review['evento_id'] not in event_map or not allowed(review['municipio'],review['comum_chave']):continue
        event=event_map[review['evento_id']];key=(event['id'],review['comum_chave']);prior=groups.get(key,{})
        if prior.get('situacao')=='PRESENTE':
            continue
        groups[key]={'evento_id':event['id'],'evento':event['titulo'],'data':event['data_evento'],
            'comum_chave':review['comum_chave'],'comum':review['comum_nome'],'municipio':regional_city(review['municipio']),
            'situacao':review['situacao'],'locais':[site_map[review['local_id']]['nome']] if review.get('local_id') in site_map else [],
            'nomes':prior.get('nomes',[]),'observacoes':review.get('observacoes') or '',
            'fonte':'Conferência administrativa','responsavel':review.get('updated_by_name','')}
    rows=list(groups.values())
    if filters.get('local'):
        target=site_map.get(filters['local'],{}).get('nome')
        rows=[r for r in rows if target in r['locais']] # ausência não é atribuída a um local de comparecimento
    by_city={}
    for row in rows:
        row['consta_lista']=bool(row.get('consta_lista'))
        row['presenca_situacao']=attendance_status(row)
        row['presenca_lista_label']=attendance_label(row)
        row['locais_validos']=[local for local in row.get('locais',[]) if norm(local) not in {'LOCAL A CONFERIR','NAO INFORMADO'}] if row['presenca_situacao']=='PRESENTE' else []
        reference_id=reference.get((row['evento_id'],row['comum_chave']))
        row['local_referencia']=site_map.get(reference_id,{}).get('nome') or 'Não informado'
        row['em_outro_local']=bool(row['situacao']=='PRESENTE' and reference_id and row.get('locais')
                                   and row['local_referencia'] not in row['locais'])
        origin=norm(regional_city(row['municipio']))
        attendance_cities={norm(regional_city(local)) for local in row.get('locais',[]) if local != 'LOCAL A CONFERIR'}
        row['fora_municipio']=bool(row['situacao']=='PRESENTE' and attendance_cities and origin not in attendance_cities)
        row['participacao']=('LOCAL A CONFERIR' if not attendance_cities else
                             'FORA DO MUNICÍPIO' if row['fora_municipio'] else 'NO MUNICÍPIO') if row['situacao']=='PRESENTE' else ''
        row['situacao_label']=LABELS[row['situacao']]
        row['registro']=row['presenca_lista_label']
        group=by_city.setdefault(row['municipio'],{'municipio':row['municipio'],**{k:0 for k in LABELS},
            'PRESENTE_REFERENCIA':0,'PRESENTE_OUTRO':0,'total':0})
        group[row['situacao']]+=1;group['total']+=1
        if row['situacao']=='PRESENTE':group['PRESENTE_OUTRO' if row['em_outro_local'] else 'PRESENTE_REFERENCIA']+=1
    return {'rows':sorted(rows,key=lambda r:(r['municipio'],r['comum'],r['data'])),
            'municipalities':sorted(by_city.values(),key=lambda x:x['municipio']),
            'totals':dict(Counter(r['situacao'] for r in rows)),
            'unit':'conferências de comum por evento, não quantidade de pessoas'}
