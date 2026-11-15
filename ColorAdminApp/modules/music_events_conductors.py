"""Uma conferência por evento e comum; não confundir com contagem de pessoas."""
from collections import Counter, defaultdict
from .music_events_dashboard import code, REGIONAL, regional_city
from .music_events_import import is_local_conductor_role, norm, person_names
from .music_events_identity import CommonResolver
from .music_events_calendar import validated_sites

LABELS={'PRESENTE':'Presente','JUSTIFICOU':'J · Justificou','NAO_JUSTIFICOU':'NJ · Não justificou',
        'NAO_INFORMADO':'Não informado','SEM_ENCARREGADO':'Sem encarregado','ENFERMO':'Enfermo'}


def attendance_status(row):
    if any(row.get(field) is True for field in ('consta_lista', 'encarregado_na_lista', 'leader_on_list')):
        return 'PRESENTE'
    raw = row.get('leader_attendance') or row.get('presenca_situacao') or row.get('encarregado_situacao') or row.get('encarregado_status') or row.get('leader_status') or row.get('situacao')
    if not raw:
        raw={'PRESENTE':'PRESENTE','JUSTIFICOU':'JUSTIFICOU','J':'JUSTIFICOU',
             'NAO JUSTIFICOU':'NAO_JUSTIFICOU','NJ':'NAO_JUSTIFICOU',
             'SEM ENCARREGADO':'SEM_ENCARREGADO','SE':'SEM_ENCARREGADO',
             'ENFERMO':'ENFERMO','EF':'ENFERMO'}.get(norm(row.get('encarregado')))
    # The regional rule treats legacy/unclassified absences as NJ.
    return raw if raw in LABELS and raw != 'NAO_INFORMADO' else 'NAO_JUSTIFICOU'


def attendance_label(row):
    return {'PRESENTE': 'PRESENTE', 'JUSTIFICOU': 'JUSTIFICOU', 'NAO_JUSTIFICOU': 'NJ',
            'NAO_INFORMADO': 'NÃO INFORMADO', 'SEM_ENCARREGADO': 'SEM ENCARREGADO',
            'ENFERMO': 'ENFERMO'}[attendance_status(row)]


def common_attendance(entries):
    """One present local conductor confirms the common's representation."""
    states = {attendance_status(entry) for entry in entries}
    if 'PRESENTE' in states:
        return 'PRESENTE'
    return next(iter(states)) if len(states) == 1 else 'NAO_JUSTIFICOU'


def attach_common_attendance(data):
    """Keep individual conferences while projecting the common's attendance."""
    if len(data['events']) != 1:
        return data
    by_common = defaultdict(list)
    for entry in data.get('conductors', {}).get('rows', []):
        if entry['evento_id'] == data['events'][0]['id']:
            by_common[entry['comum_chave']].append(entry)
    for row in data['rows']:
        entries = by_common.get(code(row['comum']), [])
        if not entries:
            continue
        status = common_attendance(entries)
        present = [entry for entry in entries if attendance_status(entry) == 'PRESENTE']
        row.update(encarregado=attendance_label({'situacao':status}),
                   encarregado_na_lista=any(entry.get('consta_lista') for entry in present),
                   encarregado_status=status, encarregado_situacao=status,
                   encarregado_situacao_label=attendance_label({'situacao':status}),
                   encarregado_local=' / '.join(sorted({local for entry in present for local in entry.get('locais_validos', [])})))
    return data


def summarize(events,records,sites,reviews,filters,catalog=(),frequency=(),leaders=(),transitions=None):
    resolver=CommonResolver(catalog)
    registered_leaders={};leaders_by_event_common=defaultdict(dict);leaders_by_city_name={}
    changes_by_person = defaultdict(list)
    for row in transitions or []:
        changes_by_person[str(row['aluno_id'])].append(row)
    dated_leaders = []
    for event in events:
        for person in leaders:
            changes = changes_by_person.get(str(person.get('id')), [])
            if not is_local_conductor_role(person.get('cargo_ministerio')) and not any(
                r['campo'] == 'cargo_ministerio' and any(is_local_conductor_role(v)
                    for v in (r['anterior'], r['posterior'])) for r in changes):
                continue
            if transitions is not None:
                from .sam_temporal import state_at
                person = state_at(person, changes, event['data_evento'])
            dated_leaders.append((event['id'], person))
    for event_id, person in dated_leaders:
        if not is_local_conductor_role(person.get('cargo_ministerio')) or norm(person.get('status')) in {'INATIVO','EXCLUIR'}:continue
        common=resolver.resolve(person.get('codigo_comum') or person.get('comum_congregacao'),person.get('municipio'))
        if not common:continue
        key=code(common['comum'])
        for name in person_names(person.get('nome_aluno')):
            identity=norm(name)
            if not identity:continue
            registered_leaders.setdefault((event_id,key),set()).add(identity)
            leaders_by_event_common[(event_id,key)][identity]=name
            leaders_by_city_name.setdefault((event_id,norm(regional_city(common['cidade'])),identity),set()).add(key)
    records=resolver.records(records)
    canonical_by_code={code(x.get('comum')):x for x in catalog}
    for row in records:
        if not row.get('comum_nao_reconhecida'):continue
        matches=leaders_by_city_name.get((row['evento_id'],norm(regional_city(row.get('municipio_informado'))),norm(row.get('nome'))),set())
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

    def group_for(event_id,key,common,city,name=''):
        identity=norm(name)
        group_key=(event_id,key,identity)
        return groups.setdefault(group_key,{'evento_id':event_id,'evento':event_map[event_id]['titulo'],
            'data':event_map[event_id]['data_evento'],'comum_chave':key,'comum':common,
            'municipio':city,'encarregado_nome':name,'situacao':'NAO_INFORMADO','locais':[],
            'nomes':[name] if name else [],'observacoes':'','fonte':'Não conferido'})

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
        common_name=canonical_common.get('comum') or item.get('comum') or key
        common_city=canonical_common.get('cidade') or city
        names=leaders_by_event_common.get((event['id'],key),{})
        if names:
            for name in sorted(names.values(),key=norm):
                group_for(event['id'],key,common_name,common_city,name)
        else:
            group_for(event['id'],key,common_name,common_city)
    for row in records:
        if row['evento_id'] not in event_map or row.get('situacao','PRESENTE')!='PRESENTE':continue
        common=row.get('comum_codigo') or row.get('comum_informada') or 'Não informada';key=code(common)
        c=canonical.get(key,{});city=regional_city(c.get('cidade') or row.get('municipio_informado') or 'Não informado')
        if not allowed(city,key):continue
        event=event_map[row['evento_id']]
        common_name=c.get('comum') or ('A conferir: '+common if row.get('comum_nao_reconhecida') else common)
        names=person_names(row.get('nome')) or ['']
        imported_local_conductor=is_local_conductor_role(row.get('cargo'))
        if (not imported_local_conductor and not leaders_by_event_common.get((event['id'],key))
                and not any(norm(person_name) in registered_leaders.get((event['id'],key),set())
                            for person_name in names)):
            group_for(event['id'],key,common_name,city)
        for person_name in names:
            registered_identity=norm(person_name) in registered_leaders.get((event['id'],key),set())
            if imported_local_conductor or registered_identity:
                group=group_for(event['id'],key,common_name,city,person_name)
                group['consta_lista']=True
                group['situacao']='PRESENTE';group['fonte']='Presença nominal importada'
                local=site_map.get(row['local_id'],{}).get('nome','Não informado')
                if local not in group['locais']:group['locais'].append(local)
                if person_name and person_name not in group['nomes']:group['nomes'].append(person_name)
    for review in reviews:
        if review['evento_id'] not in event_map or not allowed(review['municipio'],review['comum_chave']):continue
        event=event_map[review['evento_id']];common_key=review['comum_chave']
        person_name=str(review.get('encarregado_nome') or '').strip()
        if not person_name:
            candidates=[group for (event_id,key,identity),group in groups.items()
                        if event_id==event['id'] and key==common_key and identity]
            person_name=candidates[0]['encarregado_nome'] if len(candidates)==1 else ''
        group_key=(event['id'],common_key,norm(person_name))
        prior=groups.get(group_key,{})
        if prior.get('situacao')=='PRESENTE':
            continue
        group=group_for(event['id'],common_key,review['comum_nome'],regional_city(review['municipio']),person_name)
        group.update(situacao=review['situacao'],
            locais=[site_map[review['local_id']]['nome']] if review.get('local_id') in site_map else [],
            observacoes=review.get('observacoes') or '',fonte='Conferência administrativa',
            responsavel=review.get('updated_by_name',''))
    # A musician appearing before the conductor must not leave a second, empty
    # conference behind for the same common. Keep explicit administrative records.
    named = {(event_id,key) for event_id,key,identity in groups if identity}
    rows=[row for (event_id,key,identity),row in groups.items()
          if identity or (event_id,key) not in named or row['fonte'] != 'Não conferido']
    if filters.get('local'):
        target=site_map.get(filters['local'],{}).get('nome')
        rows=[r for r in rows if target in r['locais']] # ausência não é atribuída a um local de comparecimento
    by_city={}
    for row in rows:
        row['consta_lista']=bool(row.get('consta_lista'))
        row['presenca_situacao']=attendance_status(row)
        row['situacao']=row['presenca_situacao']
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
    return {'rows':sorted(rows,key=lambda r:(r['municipio'],r['comum'],r['data'],norm(r.get('encarregado_nome')))),
            'municipalities':sorted(by_city.values(),key=lambda x:x['municipio']),
            'totals':dict(Counter(r['situacao'] for r in rows)),
            'unit':'conferências individuais por encarregado e evento'}
