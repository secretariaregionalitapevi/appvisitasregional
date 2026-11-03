"""Referência do cadastro local existente, sem simular captura histórica SAM."""
from collections import Counter
from .music_events_identity import CommonResolver
from .music_events_dashboard import code, event_kind, regional_city, REGIONAL
from .music_events_import import norm


def instrument_family(instrument):
    value=norm(instrument)
    if value in {'VIOLINO','VIOLA','VIOLONCELO','ACORDEON'}:return 'CORDAS'
    if any(x in value for x in ['FLAUT','OBO','CLARIN','FAGOT','SAXOF']):return 'MADEIRAS'
    if any(x in value for x in ['TROMP','CORNET','FLUGEL','BARIT','EUPH','EUFO','TUBA','SAX HORN']):return 'METAIS'
    return 'OUTROS'


def attach_registry(data, people, catalog, *, include_zero=False):
    resolver=CommonResolver(catalog);counts=Counter();seen=set();dates=[]
    for row in people:
        identity=str(row.get('id') or '')
        if not identity or identity in seen:continue
        seen.add(identity)
        if norm(row.get('status')) not in {'ATIVO','ALERTA','CONCLUIDO'}:continue
        inst=row.get('instrumento') or ''
        if not inst or norm(inst)=='A DEFINIR':continue
        common=resolver.resolve(row.get('comum_congregacao'),row.get('municipio'))
        if not common:continue
        category='ORGANISTA' if norm(inst)=='ORGAO' else 'MUSICO'
        counts[(code(common['comum']),category,instrument_family(inst))]+=1
        if row.get('updated_at'):dates.append(str(row['updated_at']))
    kinds={event_kind(e) for e in data['events']}
    family=next(iter(kinds)).removeprefix('RT_') if len(kinds)==1 else 'GERAL'
    filters=data.get('filters',{})
    regional={norm(city) for city in REGIONAL}
    present_keys={code(row['comum']) for row in data['rows']}
    if data['events'] and include_zero and not data['base_complete']:
        for common in catalog:
            key=code(common['comum']);city=regional_city(common.get('cidade'))
            if key in present_keys or not any(k[0]==key for k in counts):continue
            if filters.get('municipios') and norm(city) not in {norm(regional_city(c)) for c in filters['municipios']}:continue
            if filters.get('comuns') and key not in filters['comuns']:continue
            origin=filters.get('origem') or 'regional'
            if origin!='todos' and (norm(city) in regional)!=(origin=='regional'):continue
            data['rows'].append({'comum':common['comum'],'municipio':city,
                'MUSICO':0,'ORGANISTA':0,'MINISTERIO':0,'APOIO':0,'IRMANDADE':0,'total':0,
                'musicos_base':None,'organistas_base':None,'percentual_musicos':None,
                'percentual_organistas':None,'encarregado':'Não informado','encarregados':0,
                'cargos':{},'local_referencia':'Não informado','outros_locais':'—'})
            present_keys.add(key)
    for row in data['rows']:
        key=code(row['comum'])
        # Ausência de cadastro reconhecido é desconhecida, não zero.
        known=any(k[0]==key for k in counts)
        for category,field in [('MUSICO','cadastro_musicos'),('ORGANISTA','cadastro_organistas')]:
            row[field]=sum(v for (c,cat,f),v in counts.items() if c==key and cat==category
                          and (family not in {'CORDAS','MADEIRAS','METAIS'} or cat=='MUSICO' and f==family)) if known else None
        # Campos próprios: não substituir os percentuais históricos vinculados.
        for category,field in [('MUSICO','musicos'),('ORGANISTA','organistas')]:
            base=row['cadastro_'+field]
            row['percentual_cadastro_'+field]=round(100*row[category]/base,2) if base and len(data['events'])==1 else None
        row['cadastro_divergente']=any(row.get('percentual_cadastro_'+field,0) is not None
            and row.get('percentual_cadastro_'+field,0)>100 for field in ['musicos','organistas'])
    data['rows'].sort(key=lambda row:(norm(row['municipio']),norm(row['comum'])))
    data['registry']={'available':bool(counts),'updated_at':max(dates) if dates else None,
                      'criterion':'Cadastro local atual: status Ativo, Alerta e Concluido; todos os níveis, inclusive oficializados. Inativos e Excluir fora da referência. Não é captura histórica.'}
    return data
