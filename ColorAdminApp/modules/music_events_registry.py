"""Referência do cadastro local existente, sem simular captura histórica SAM."""
from collections import Counter
from .music_events_identity import CommonResolver
from .music_events_dashboard import code, event_kind, regional_city, REGIONAL, candidate_level
from .music_sam_population import musical_category
from .music_events_import import norm


def instrument_family(instrument):
    value=norm(instrument)
    if value in {'VIOLINO','VIOLA','VIOLONCELO','CONTRABAIXO','ACORDEON','ACORDEAO'}:return 'CORDAS'
    if any(x in value for x in ['FLAUT','OBO','CLARIN','FAGOT','SAXOF']):return 'MADEIRAS'
    if any(x in value for x in ['TROMP','TROMB','CORNET','FLUGEL','BARIT','EUPH','EUFO','TUBA','SAX HORN','SAXHORN','BOMBARD']):return 'METAIS'
    return 'OUTROS'


def attach_registry(data, people, catalog, *, include_zero=False):
    resolver=CommonResolver(catalog);counts=Counter();seen=set();dates=[];known_commons=set()
    for row in people:
        identity=str(row.get('id') or '')
        if not identity or identity in seen:continue
        seen.add(identity)
        if norm(row.get('status')) not in {'SAM_ATUAL','ATIVO','ALERTA','CONCLUIDO'}:continue
        inst=row.get('instrumento') or ''
        category=musical_category(row.get('cargo_ministerio'),inst)
        if not category:continue
        common=resolver.resolve(row.get('comum_congregacao'),row.get('municipio'))
        if not common:continue
        known_commons.add(code(common['comum']))
        if candidate_level(row.get('nivel')):continue
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
        row['musicos_orquestra']=row.get('MUSICO',0)
        row['organistas_orquestra']=row.get('ORGANISTA',0)
        key=code(row['comum'])
        # Ausência de cadastro reconhecido é desconhecida, não zero.
        known=key in known_commons
        for category,field in [('MUSICO','cadastro_musicos'),('ORGANISTA','cadastro_organistas')]:
            row[field]=sum(v for (c,cat,f),v in counts.items() if c==key and cat==category
                          and (family not in {'CORDAS','MADEIRAS','METAIS'} or cat=='MUSICO' and f==family)) if known else None
        # Campos próprios: não substituir os percentuais históricos vinculados.
        for category,field in [('MUSICO','musicos'),('ORGANISTA','organistas')]:
            base=row['cadastro_'+field]
            row['percentual_cadastro_'+field]=round(100*row[field+'_orquestra']/base,2) if base and len(data['events'])==1 else None
        row['cadastro_divergente']=any(row.get('percentual_cadastro_'+field,0) is not None
            and row.get('percentual_cadastro_'+field,0)>100 for field in ['musicos','organistas'])
    data['rows'].sort(key=lambda row:(norm(row['municipio']),norm(row['comum'])))
    data['registry']={'available':bool(counts),'updated_at':max(dates) if dates else None,
                      'criterion':'Catálogo SAM atual: orquestra por cargo musical, sem candidatos(as). Candidatos têm indicadores próprios. Não é captura histórica.'}
    return data
