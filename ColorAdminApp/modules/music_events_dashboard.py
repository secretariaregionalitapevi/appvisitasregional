"""Agregação única para painel, filtros e exportações de ensaios/RTs."""
import re
from collections import Counter

from .music_events_import import norm
from .music_events_identity import CommonResolver

REGIONAL = ['CAUCAIA DO ALTO','COTIA','ITAPEVI','JANDIRA','PIRAPORA DO BOM JESUS',
            'SANTANA DE PARNAÍBA','VARGEM GRANDE PAULISTA']

CITY_LABELS = {'SANTANA DE PARNAÍBA':'Santana de Parnaíba · Fazendinha',
               'PIRAPORA DO BOM JESUS':'Pirapora do Bom Jesus · Parque Laranjeiras II'}


def regional_city(value):
    """Nomes administrativos; apelidos de sede não criam municípios visitantes."""
    aliases = {'CAUCAIA':'CAUCAIA DO ALTO','FAZENDINHA':'SANTANA DE PARNAÍBA',
               'SANTANA DE PARNAIBA (FAZENDINHA)':'SANTANA DE PARNAÍBA',
               'PIRAPORA':'PIRAPORA DO BOM JESUS','PARQUE LARANJEIRAS II':'PIRAPORA DO BOM JESUS',
               'VGP':'VARGEM GRANDE PAULISTA'}
    return aliases.get(norm(value), next((c for c in REGIONAL if norm(c)==norm(value)), value))


def code(value):
    match = re.match(r'^(BR-\d+-\d+)', norm(value))
    return match.group(1) if match else norm(value)


def event_kind(event):
    return 'ENSAIO_REGIONAL' if event['tipo'] == 'ENSAIO_REGIONAL' else 'RT_' + event['familia']


def ministry_role(role):
    return norm(role).startswith(('ANCIAO','DIACONO','COOPERADOR DO OFICIO','COOPERADOR DE JOVENS'))


def instructor_profile(role):
    value = norm(role)
    if value.startswith('INSTRUTORA'):
        return 'INSTRUTORA'
    if value.startswith('INSTRUTOR'):
        return 'INSTRUTOR'
    return ''


def candidate_level(level):
    return norm(level).startswith(('CANDIDATO','CANDIDATA'))


def aggregate(events, records, locations, frequency, filters, catalog=(), eligible=()):
    """Filtra antes de agregar; percentuais usam só vínculos SAM elegíveis."""
    filters = {**filters, 'origem': filters.get('origem') or 'regional'}
    by_code = {code(x.get('comum')): x for x in catalog}
    site = {x['id']: x for x in locations}
    reference_site = {(x['evento_id'],code(x['comum_codigo'])):x.get('local_referencia_id') for x in frequency}
    event_map = {x['id']: x for x in events}
    chosen = []
    for e in events:
        day = str(e['data_evento'])[:10]
        if filters.get('evento') and e['id'] != filters['evento']: continue
        if filters.get('ano') and day[:4] != filters['ano']: continue
        if filters.get('mes') and day[5:7] != filters['mes']: continue
        if filters.get('inicio') and day < filters['inicio']: continue
        if filters.get('fim') and day > filters['fim']: continue
        if filters.get('tipo') and event_kind(e) != filters['tipo']: continue
        if filters.get('status') and e['status'] != filters['status']: continue
        if filters.get('busca') and norm(filters['busca']) not in norm(e['titulo']): continue
        chosen.append(e)
    selected_ids = {x['id'] for x in chosen}
    records = CommonResolver(catalog).records(x for x in records if x['evento_id'] in selected_ids)
    all_rows = []
    for original in records:
        if original['evento_id'] not in selected_ids or original.get('situacao','PRESENTE') != 'PRESENTE': continue
        row = dict(original)
        common = row.get('comum_informada') or row.get('comum_codigo') or 'Não informada'
        canonical = by_code.get(code(row.get('comum_codigo') or common), {})
        row['common_key'] = code(row.get('comum_codigo') or common)
        row['common'] = canonical.get('comum') or ('A conferir: '+common if row.get('comum_nao_reconhecida') else common)
        row['city'] = regional_city(canonical.get('cidade') or row.get('municipio_informado') or 'Não informado')
        row['local'] = site.get(row['local_id'],{}).get('nome') or 'Não informado'
        all_rows.append(row)
    regional_names = {norm(c) for c in REGIONAL}
    cities = list(REGIONAL)
    if filters['origem'] != 'regional':
        cities += sorted({x['city'] for x in all_rows if norm(x['city']) not in regional_names})
    common_options_rows = [x for x in all_rows if filters['origem']=='todos' or
                          ((norm(x['city']) in regional_names)==(filters['origem']=='regional'))]
    common_options = sorted({(x['common_key'],x['common'],x['city']) for x in common_options_rows})
    def in_area(city, common):
        return (not filters.get('municipios') or norm(regional_city(city)) in {norm(regional_city(x)) for x in filters['municipios']}) and (
            not filters.get('comuns') or common in filters['comuns'])
    rows = [x for x in all_rows if in_area(x['city'],x['common_key']) and
            (not filters.get('local') or x['local_id'] == filters['local']) and
            (filters['origem']=='todos' or (norm(x['city']) in regional_names) == (filters['origem']=='regional'))]
    groups, municipal, local_counts = {}, {}, {}
    instruments, roles, families, musician_families = Counter(), Counter(), Counter(), Counter()
    def empty(common='', city=''):
        return {'comum':common,'municipio':city,'MUSICO':0,'ORGANISTA':0,'MINISTERIO':0,
                'APOIO':0,'IRMANDADE':0,'total':0,'musicos_base':None,'organistas_base':None,
                'percentual_musicos':None,'percentual_organistas':None,'encarregado':'Não informado',
                'encarregados':0,'ministerio_cargos':0,'instrutores':0,'instrutoras':0,
                'candidatos':0,'cargos':{},'musicos_outro_local':0,'organistas_outro_local':0,
                '_locais_referencia':set(),'_locais_outros':set()}
    def increment(target, row):
        target[row['categoria']] += 1
        target['total'] += 1
        if row.get('cargo'):
            target['cargos'][row['cargo']] = target['cargos'].get(row['cargo'],0)+1
        if norm(row.get('cargo'))=='ENCARREGADO LOCAL': target['encarregados'] += 1
        if ministry_role(row.get('cargo')): target['ministerio_cargos'] += 1
        profile = instructor_profile(row.get('cargo'))
        if profile == 'INSTRUTOR': target['instrutores'] += 1
        if profile == 'INSTRUTORA': target['instrutoras'] += 1
        if candidate_level(row.get('nivel')): target['candidatos'] += 1
        reference_id=reference_site.get((row['evento_id'],row['common_key']))
        if reference_id:
            target['_locais_referencia'].add(site.get(reference_id,{}).get('nome') or 'Não informado')
            if row.get('local_id')!=reference_id and row['categoria'] in {'MUSICO','ORGANISTA'}:
                target['musicos_outro_local' if row['categoria']=='MUSICO' else 'organistas_outro_local'] += 1
                target['_locais_outros'].add(row['local'])
    for row in rows:
        group = groups.setdefault(row['common_key'],empty(row['common'],row['city']))
        increment(group,row)
        if norm(row.get('cargo'))=='ENCARREGADO LOCAL':
            group['encarregado']='Presente'
        increment(municipal.setdefault(row['city'],empty(city=row['city'])),row)
        increment(local_counts.setdefault(row['local_id'],{**empty(), 'nome':row['local']}),row)
        roles[row.get('cargo') or 'Não informado'] += 1
        if row['categoria'] in {'MUSICO','ORGANISTA'}:
            instruments['Organistas' if row['categoria']=='ORGANISTA' else row.get('instrumento') or 'Não informado'] += 1
            families[row.get('familia') or 'OUTROS'] += 1
        if row['categoria']=='MUSICO':
            musician_families[row.get('familia') or 'OUTROS'] += 1
    # Para múltiplos eventos: soma de oportunidades de presença, nunca pessoas únicas no período.
    eligible_by_id = {(x['evento_id'],str(x['sam_pessoa_id'])): x for x in eligible}
    matched = Counter()
    for row in rows:
        person = eligible_by_id.get((row['evento_id'],str(row.get('sam_pessoa_id'))))
        if person and person['categoria'] == row['categoria']:
            matched[(row['evento_id'],person['comum_codigo'],person['categoria'])] += 1
    valid_keys, invalid_keys = set(), set()
    for f in frequency:
        if f['evento_id'] not in selected_ids or not in_area(f['municipio'],f['comum_codigo']): continue
        if filters['origem']!='todos' and ((norm(regional_city(f['municipio'])) in regional_names) != (filters['origem']=='regional')): continue
        group = groups.setdefault(f['comum_codigo'],empty(f['comum'],f['municipio']))
        if f.get('local_referencia_id'):
            group['_locais_referencia'].add(site.get(f['local_referencia_id'],{}).get('nome') or 'Não informado')
        situation=f.get('encarregado_situacao','NAO_INFORMADO')
        if situation!='NAO_INFORMADO':
            group['encarregado']={'PRESENTE':'Presente','JUSTIFICOU':'Justificou','NAO_JUSTIFICOU':'Não justificou',
                'SEM_ENCARREGADO':'Sem encarregado','ENFERMO':'Enfermo'}.get(situation,'Não informado')
        if not f.get('base_validada'):
            invalid_keys.add(f['comum_codigo']); continue
        valid_keys.add(f['comum_codigo'])
        for category, field in [('MUSICO','musicos'),('ORGANISTA','organistas')]:
            group[field+'_base'] = (group[field+'_base'] or 0) + f[field+'_base']
            group['_'+field+'_elegiveis'] = group.get('_'+field+'_elegiveis',0) + matched[(f['evento_id'],f['comum_codigo'],category)]
    covered_events = {x['evento_id'] for x in frequency if x.get('base_validada')}
    base_complete = bool(chosen) and all(e.get('base_id') and e['id'] in covered_events for e in chosen) and not invalid_keys
    base_m, base_o, present_m, present_o = 0,0,0,0
    for key, group in groups.items():
        if key in invalid_keys or not base_complete:
            group['musicos_base']=group['organistas_base']=None
        elif key in valid_keys:
            for field in ['musicos','organistas']:
                denominator=group[field+'_base']
                group['percentual_'+field]=round(100*group.get('_'+field+'_elegiveis',0)/denominator,2) if denominator else None
            base_m += group['musicos_base'] or 0; base_o += group['organistas_base'] or 0
            present_m += group.get('_musicos_elegiveis',0); present_o += group.get('_organistas_elegiveis',0)
    totals = Counter(x['categoria'] for x in rows)
    totals.update({'total':len(rows),'eventos':len(chosen),'comuns':len(groups),
                   'locais':len(local_counts),'municipios':len(municipal)})
    totals['encarregados'] = sum(norm(x.get('cargo'))=='ENCARREGADO LOCAL' for x in rows)
    totals['ministerio_cargos'] = sum(ministry_role(x.get('cargo')) for x in rows)
    totals['instrutores'] = sum(instructor_profile(x.get('cargo'))=='INSTRUTOR' for x in rows)
    totals['instrutoras'] = sum(instructor_profile(x.get('cargo'))=='INSTRUTORA' for x in rows)
    totals['candidatos'] = sum(candidate_level(x.get('nivel')) for x in rows)
    # Contexto complementar respeita período, comum e local, mas não mistura visitantes nos KPIs regionais.
    context = [x for x in all_rows if (not filters.get('local') or x['local_id']==filters['local'])
               and (not filters.get('comuns') or x['common_key'] in filters['comuns'])]
    context_counts = Counter('regional' if norm(x['city']) in regional_names else 'visitantes' for x in context)
    for group in list(groups.values())+list(municipal.values())+list(local_counts.values()):
        group['local_referencia']=' / '.join(sorted(group.pop('_locais_referencia'))) or 'Não informado'
        group['outros_locais']=' / '.join(sorted(group.pop('_locais_outros'))) or '—'
    regional_overview=[]
    for city in REGIONAL:
        if filters.get('municipios') and norm(city) not in {norm(regional_city(x)) for x in filters['municipios']}: continue
        entry = dict(municipal.get(city,empty(city=city)))
        entry.pop('_locais_referencia',None);entry.pop('_locais_outros',None)
        entry.update(label=CITY_LABELS.get(city,city.title()),
                     comuns=sum(norm(g['municipio'])==norm(city) for g in groups.values()))
        regional_overview.append(entry)
    return {'events':chosen,'rows':sorted(groups.values(),key=lambda x:(norm(x['municipio']),norm(x['comum']))),
            'municipalities':sorted(municipal.values(),key=lambda x:-x['total']),
            'locations':sorted(local_counts.values(),key=lambda x:-x['total']),
            'instruments':dict(instruments),'families':dict(families),'musician_families':dict(musician_families),'roles':dict(roles),'totals':dict(totals),
            'base_complete':base_complete,'percent_m':round(100*present_m/base_m,2) if base_complete and base_m else None,
            'percent_o':round(100*present_o/base_o,2) if base_complete and base_o else None,
            'options':{'cities':cities,'commons':[{'value':a,'label':b,'city':c} for a,b,c in common_options],
                       'locations':[{'id':k,'nome':v['nome']} for k,v in site.items() if v['evento_id'] in selected_ids]},
            'regional_overview':regional_overview,'origin_context':dict(context_counts),'filters':filters}
