"""Comparações observadas entre encontros importados do mesmo tipo e local."""
from collections import defaultdict
from .music_events_dashboard import aggregate, event_kind, regional_city
from .music_events_import import norm


def comparison(points, field):
    if not points:
        return {'latest':0,'previous':None,'change':None,'peak':0,'from_peak':None,'count':0}
    last=points[-1][field];previous=points[-2][field] if len(points)>1 else None
    peak=max(p[field] for p in points)
    return {'latest':last,'previous':previous,'change':round(100*(last-previous)/previous,1) if previous else None,
            'peak':peak,'from_peak':round(100*(last-peak)/peak,1) if peak and len(points)>1 else None,'count':len(points)}


def evolution(events,records,locations,filters,catalog=()):
    records_by_event = defaultdict(list)
    locations_by_event = defaultdict(list)
    for row in records:
        records_by_event[row['evento_id']].append(row)
    for row in locations:
        locations_by_event[row['evento_id']].append(row)
    selected=next((e for e in events if e['id']==filters.get('evento')),None)
    public=filters.get('tipo') or (event_kind(selected) if selected else '')
    current=dict(filters);current.pop('evento',None);current['tipo']=public
    local_name=next((x['nome'] for x in locations if x['id']==filters.get('local')),None)
    def circuit(event):
        if event['tipo']!='ENSAIO_REGIONAL':return event_kind(event)
        month=int(str(event['data_evento'])[5:7])
        if month in {1,5,9}:return 'ITAPEVI_PIRAPORA'
        if month in {3,7,11}:return 'COTIA_CAUCAIA_VGP_JANDIRA_FAZENDINHA'
        # Data fora do calendário regular não presume equivalência.
        return 'EXTRA_'+event['id']
    def identity(event):
        names=tuple(sorted({norm(x['nome']) for x in locations if x['evento_id']==event['id']
                            and (not local_name or norm(x['nome'])==norm(local_name))}))
        return (event_kind(event),circuit(event),names)
    identities={identity(e) for e in events if not public or event_kind(e)==public}
    target_identity=identity(selected) if selected else next(iter(identities)) if len(identities)==1 else None
    def city_in_circuit(city,event):
        if event['tipo']!='ENSAIO_REGIONAL':return True
        c=regional_city(city)
        return (c in {'ITAPEVI','PIRAPORA DO BOM JESUS'} if circuit(event)=='ITAPEVI_PIRAPORA' else
                c in {'COTIA','CAUCAIA DO ALTO','VARGEM GRANDE PAULISTA','JANDIRA','SANTANA DE PARNAÍBA'}
                if circuit(event)=='COTIA_CAUCAIA_VGP_JANDIRA_FAZENDINHA' else False)
    by_local={};by_city={};overall=[]
    for event in sorted(events,key=lambda e:(e['data_evento'],e['id'])):
        if selected and event['data_evento']>selected['data_evento']:continue
        event_filters=dict(current)
        if local_name:
            target=next((x for x in locations if x['evento_id']==event['id'] and norm(x['nome'])==norm(local_name)),None)
            if not target:continue
            event_filters['local']=target['id']
        data=aggregate([event],records_by_event[event['id']],locations_by_event[event['id']],[],event_filters,catalog)
        if not data['events']:continue
        # Encontros sem informação do local escolhido não representam ausência.
        if filters.get('local') and not data['locations']:continue
        totals=data['totals']
        point={'date':event['data_evento'],'event_id':event['id'],'label':event['titulo'],
                        'total':totals['total'],'musicians':totals.get('MUSICO',0),'organists':totals.get('ORGANISTA',0),
                        'commons':totals['comuns']}
        if target_identity and identity(event)==target_identity and totals['total']:
            overall.append(point)
        if selected and identity(event)!=target_identity:
            continue
        for city in data['municipalities']:
            if not city_in_circuit(city['municipio'],event):continue
            key=(identity(event),norm(city['municipio']))
            group=by_city.setdefault(key,{'name':city['municipio'],'kind':event_kind(event),'points':[]})
            group['points'].append({'date':event['data_evento'],'event_id':event['id'],'total':city['total'],
                                    'musicians':city['MUSICO'],'organists':city['ORGANISTA'],
                                    'instructors':city['instrutores'],'instructresses':city['instrutoras'],
                                    'candidates':city['candidatos'],
                                    'ministerio':city['MINISTERIO'],'encarregados':city['encarregados']})
        for local in data['locations']:
            name=local['nome'];key=(event_kind(event),circuit(event),norm(name))
            group=by_local.setdefault(key,{'name':name,'kind':event_kind(event),'points':[]})
            group['points'].append({'date':event['data_evento'],'event_id':event['id'],'total':local['total'],
                                    'musicians':local['MUSICO'],'organists':local['ORGANISTA']})
    series=[]
    for group in by_local.values():
        group['summary']=comparison(group['points'],'total');series.append(group)
    municipalities=[]
    for group in by_city.values():
        group['summary']=comparison(group['points'],'musicians')
        group['organists_summary']=comparison(group['points'],'organists')
        group['instructors_summary']=comparison(group['points'],'instructors')
        group['instructresses_summary']=comparison(group['points'],'instructresses')
        group['candidates_summary']=comparison(group['points'],'candidates')
        municipalities.append(group)
    return {'series':sorted(series,key=lambda x:x['name']), 'municipalities':municipalities, 'points':overall,
            'metrics':{field:comparison(overall,field) for field in ['musicians','organists','total','commons']},
            'comparable':bool(public and target_identity and len(overall)>1),
            'comparison_note':'Comparação exige dois encontros do mesmo tipo, circuito e conjunto de locais. Um encontro isolado não indica alta ou queda.'}
