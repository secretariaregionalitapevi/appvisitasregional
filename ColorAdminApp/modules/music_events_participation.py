"""Participação por origem comparada ao cadastro SAM atual, por evento."""
from collections import Counter

from .music_events_dashboard import REGIONAL, candidate_level, code, regional_city
from .music_events_identity import CommonResolver
from .music_events_import import norm
from .music_events_registry import instrument_family
from .music_sam_population import musical_category

GROUPS = ('MUSICO', 'ORGANISTA', 'CORDAS', 'MADEIRAS', 'METAIS', 'OUTROS')
LABELS = dict(MUSICO='Músicos', ORGANISTA='Organistas', CORDAS='Cordas',
              MADEIRAS='Madeiras', METAIS='Metais', OUTROS='Outros / sem naipe')
UNASSIGNED='LOCALIDADE A CONFERIR'
CRITERION = ('Catálogo atual do SAM: membros presentes na última sincronização, classificados pelo cargo musical. '
             'A orquestra exclui candidatos e candidatas, que têm base, presenças e percentuais próprios. '
             'Situação de atividade pedagógica no GEM não exclui membros do catálogo SAM. '
             'Presentes por município de origem, não pelo '
             'local do ensaio. Percentual = presentes ÷ cadastrados × 100. '
             'Candidatos(as) não estão incluídos nos totais da orquestra. '
             'As famílias detalham os músicos e não devem ser somadas ao total de músicos. '
             'Registros sem município de origem identificado ficam fora desta comparação. '
             'Referência atual, sem substituir a base histórica do evento.')


def participation(data, people, records, catalog):
    resolver = CommonResolver(catalog)
    filters = data.get('filters', {})
    regional = {norm(city) for city in REGIONAL}
    selected = {norm(regional_city(city)) for city in filters.get('municipios', [])}
    commons = {code(common) for common in filters.get('comuns', [])}

    def area(city,key=''):
        return (norm(city) in regional and (not selected or norm(city) in selected)
                and (not commons or key in commons)
                and filters.get('origem') != 'visitantes')

    cities = sorted({regional_city(c['cidade']) for c in catalog if area(regional_city(c['cidade']),code(c['comum']))}, key=norm)
    base, candidates, seen = Counter(), Counter(), set()
    unresolved, undefined, non_musical, dates = 0, 0, 0, []
    for person in people:
        identity = str(person.get('id') or '')
        if not identity or identity in seen:
            continue
        seen.add(identity)
        instrument = person.get('instrumento') or ''
        category = musical_category(person.get('cargo_ministerio'),instrument)
        if not category:
            if norm(instrument) in {'','A DEFINIR'}:undefined+=1
            non_musical+=1
            continue
        common = resolver.resolve(person.get('comum_congregacao'), person.get('municipio'))
        city = regional_city(common['cidade'] if common else person.get('municipio') or UNASSIGNED)
        key = code(common['comum']) if common else ''
        if not area(city,key):
            continue
        if not common:
            unresolved += 1
        if city not in cities:cities.append(city)
        if norm(instrument) in {'', 'A DEFINIR'}:
            undefined += 1
        groups = [category] + ([instrument_family(instrument)] if category == 'MUSICO' else [])
        for group in groups:
            (candidates if candidate_level(person.get('nivel')) else base)[city,group]+=1
        if person.get('updated_at'):
            dates.append(str(person['updated_at']))

    events = {e['id']: e for e in data['events']}
    present, present_candidates, seen = Counter(), Counter(), set()
    unresolved_present = 0
    for row in resolver.records(records):
        if row['evento_id'] not in events or row.get('situacao', 'PRESENTE') != 'PRESENTE':
            continue
        if filters.get('local') and row.get('local_id') != filters['local']:
            continue
        category = musical_category(row.get('cargo'),row.get('instrumento'))
        if not norm(row.get('cargo')) and not category:category=row.get('categoria')
        if category not in {'MUSICO', 'ORGANISTA'}:
            continue
        common = resolver.resolve(row.get('comum_codigo') or row.get('comum_informada'), row.get('municipio_informado'))
        city = regional_city(common['cidade'] if common else row.get('municipio_informado') or UNASSIGNED)
        if not area(city,code(common['comum']) if common else ''):
            continue
        if not common:unresolved_present+=1
        if city not in cities:cities.append(city)
        identity = (row['evento_id'], category, str(row.get('sam_pessoa_id') or '') or
                    (code(common['comum']) if common else row.get('comum_informada'), norm(row.get('nome')) or str(row.get('id'))))
        if identity in seen:
            continue
        seen.add(identity)
        family = instrument_family(row.get('instrumento'))
        if family == 'OUTROS' and row.get('familia') in {'CORDAS', 'MADEIRAS', 'METAIS'}:
            family = row['familia']
        for group in [category] + ([family] if category == 'MUSICO' else []):
            (present_candidates if candidate_level(row.get('nivel')) else present)[row['evento_id'],city,group]+=1

    def metric(registered, attended, candidate_base, candidate_present):
        return dict(registered=registered, present=attended,
                    percent=round(100 * attended / registered, 2) if registered else None,
                    candidate_base=candidate_base, candidate_present=candidate_present,
                    candidate_percent=round(100 * candidate_present / candidate_base, 2) if candidate_base else None,
                    divergent=attended > registered)

    rows, summaries = [], []
    for event in data['events']:
        family = event.get('familia') if event['tipo'] == 'REUNIAO_TECNICA' else 'GERAL'
        allowed = (family,) if family in {'CORDAS', 'MADEIRAS', 'METAIS'} else GROUPS
        for city in cities:
            for group in allowed:
                if group == 'OUTROS' and not (base[city, group] or present[event['id'], city, group] or candidates[city,group] or present_candidates[event['id'],city,group]):
                    continue
                rows.append(dict(event_id=event['id'], event=event['titulo'], date=str(event['data_evento'])[:10],
                                 city=city, group=group, label=LABELS[group],
                                 **metric(base[city, group], present[event['id'], city, group],
                                          candidates[city, group], present_candidates[event['id'], city, group])))
        for group in allowed:
            selected_rows = [r for r in rows if r['event_id'] == event['id'] and r['group'] == group]
            if group == 'OUTROS' and not selected_rows:
                continue
            summaries.append(dict(event_id=event['id'], event=event['titulo'], date=str(event['data_evento'])[:10],
                                  city='TOTAL DO RECORTE', group=group, label=LABELS[group],
                                  **metric(*(sum(r[key] for r in selected_rows) for key in
                                             ('registered', 'present', 'candidate_base', 'candidate_present')))))
    return dict(rows=rows, summaries=summaries, criterion=CRITERION,
                available=bool(base or candidates), updated_at=max(dates) if dates else None,
                scope_cities=cities,scope_filters=filters,source='Catálogo SAM sincronizado',
                scope_city_count=sum(city!=UNASSIGNED for city in cities),
                non_musical_registry=non_musical,
                unresolved_registry=unresolved, undefined_instrument=undefined,
                unresolved_present=unresolved_present)


def participation_sheets(data):
    overview = data.get('sam_participation', {})
    result = []
    for name, rows in [('SAM resumo regional', overview.get('summaries', [])),
                       ('SAM municípios e naipes', overview.get('rows', []))]:
        result.append((name, ['Evento', 'Data', 'Município de origem', 'Público / naipe',
                             'Orquestra SAM', 'Orquestra presente', '% orquestra',
                             'Candidatos cadastrados', 'Candidatos presentes', '% candidatos'],
                       [[r['event'], r['date'][8:10]+'/'+r['date'][5:7]+'/'+r['date'][:4], r['city'], r['label'],
                         r['registered'], r['present'], r['percent']/100 if r['percent'] is not None else None,
                         r['candidate_base'], r['candidate_present'],
                         r['candidate_percent']/100 if r['candidate_percent'] is not None else None] for r in rows],
                       [38, 15, 30, 22, 18, 16, 18, 20, 20, 18]))
    return result
