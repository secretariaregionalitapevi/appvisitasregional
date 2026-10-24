"""Acompanhamento por comum de origem; uma oportunidade por data, não por local."""
from collections import Counter, defaultdict

from .access_control import can_access
from .music_events_dashboard import REGIONAL, code, regional_city
from .music_events_identity import CommonResolver
from .music_events_import import norm
from .music_events_registry import attach_registry
from .music_events_leaders import attach_leaders
from .music_events_conductors import summarize, attendance_status
from .music_events_calendar import validated_sites
from .music_events_closing import physical_closings

JOINT_ADMINISTRATION = {'COTIA', 'CAUCAIA DO ALTO', 'VARGEM GRANDE PAULISTA'}
FIRST_CIRCUIT = {'ITAPEVI', 'PIRAPORA DO BOM JESUS'}
SECOND_CIRCUIT = set(REGIONAL) - FIRST_CIRCUIT
EXPECTED_SESSIONS = 3


def session_cities(day, sites):
    """Calendário regular já utilizado no histórico; extras exigem local reconhecido."""
    month = int(day[5:7])
    if month in {1, 5, 9}:
        return FIRST_CIRCUIT
    if month in {3, 7, 11}:
        return SECOND_CIRCUIT
    cities = {regional_city(site.get('municipio') or site.get('nome')) for site in sites}
    if cities & JOINT_ADMINISTRATION:
        cities |= JOINT_ADMINISTRATION
    return cities & set(REGIONAL)


def rate(present, base):
    return round(100 * present / base, 2) if base else None


def annual_comparison(data, day):
    """Mesmas comuns nos dois períodos; ignora datas de outro circuito e sem carga."""
    cohort = [row for row in data['rows'] if any(cell['date'] == day and cell['loaded'] for cell in row['cells'])]
    available = [{cell['date'] for cell in row['cells'] if cell['loaded'] and cell['date'] <= day} for row in cohort]
    days = sorted(set.intersection(*available)) if available else []
    def metrics(date):
        cells = [cell for row in cohort for cell in row['cells'] if cell['date'] == date and cell['loaded']]
        states = Counter(attendance_status(cell) for cell in cells)
        m, o = sum(c['musicians'] for c in cells), sum(c['organists'] for c in cells)
        represented = sum(bool(c['musicians'] or c['organists'] or attendance_status(c) == 'PRESENTE') for c in cells)
        return {'date': date, 'musicians': m, 'organists': o, 'leaders': states['PRESENTE'],
                'total': m + o + sum(c['others'] for c in cells), 'commons': len(cells),
                'represented': represented, 'without_participation': len(cells) - represented, 'states': dict(states)}
    previous = [date for date in days if date < day]
    return {'current': metrics(day), 'previous': metrics(previous[-1]) if previous else None,
            'series': [metrics(date) for date in days]}


def annual_data(events, records, sites, registry, catalog, reviews, members, invitations,
                year, scope, cities=(), commons=(), review_available=True):
    """Zeros só pertencem a datas carregadas; ausência de conferência nunca vira NJ."""
    events = [e for e in events if e['tipo'] == 'ENSAIO_REGIONAL'
              and str(e['data_evento'])[:4] == str(year) and e.get('status') != 'RASCUNHO']
    event_map = {e['id']: e for e in events}
    closings = physical_closings(events, records, sites) if scope['level'] in {'regional', 'global'} else []
    site_map = {site['id']: site for site in validated_sites(events, sites) if site['evento_id'] in event_map}
    resolver = CommonResolver(catalog)
    records = resolver.records(r for r in records if r['evento_id'] in event_map
                               and r.get('situacao', 'PRESENTE') == 'PRESENTE')
    loaded_event_ids = {r['evento_id'] for r in records}
    cities = {norm(regional_city(city)) for city in cities}
    commons = set(commons)
    all_catalog = [r for r in catalog if regional_city(r.get('cidade')) in REGIONAL and can_access(scope, r)]
    selected_catalog = [r for r in all_catalog if (not cities or norm(regional_city(r['cidade'])) in cities)
                        and (not commons or code(r['comum']) in commons)]
    all_keys = {code(r['comum']) for r in all_catalog}
    records = [r for r in records if code(r.get('comum_codigo') or r.get('comum_informada')) in all_keys
               or (r.get('comum_nao_reconhecida') and can_access(scope, {
                   'comum': r.get('comum_informada'), 'cidade': r.get('municipio_informado')}))]
    registry = [r for r in registry if can_access(scope, {'comum': r.get('comum_congregacao'), 'cidade': r.get('municipio')})]
    members = [r for r in members if can_access(scope, {'comum': r.get('comum'), 'cidade': r.get('cidade')})]
    reviews = [r for r in reviews if code(r['comum_chave']) in all_keys]
    reviewed = {(r['evento_id'], code(r['comum_chave'])) for r in reviews}
    canonical = {code(r['comum']): r for r in all_catalog}
    for invitation in invitations:
        key = code(invitation['comum_codigo'])
        state = invitation.get('encarregado_situacao', 'NAO_INFORMADO')
        if key not in canonical or state == 'NAO_INFORMADO' or (invitation['evento_id'], key) in reviewed:
            continue
        common = canonical[key]
        reviews.append({'evento_id': invitation['evento_id'], 'comum_chave': key,
                        'comum_nome': common['comum'], 'municipio': common['cidade'], 'situacao': state,
                        'local_id': invitation.get('local_referencia_id') if state == 'PRESENTE' else None,
                        'observacoes': invitation.get('encarregado_observacoes') or ''})
    # A conferência nominal também usa encarregados existentes no cadastro de irmandade.
    leader_registry = registry + [dict(r, nome_aluno=r.get('nome'), cargo_ministerio=r.get('cargo_outros'),
                                     comum_congregacao=r.get('codigo_comum') or r.get('comum'),
                                     municipio=r.get('cidade')) for r in members]
    conductors = summarize(events, records, list(site_map.values()), reviews, {'origem': 'regional'},
                           catalog, leaders=leader_registry)
    reviews_by_key = {(r['evento_id'], r['comum_chave']): r for r in conductors['rows']}
    by_date = defaultdict(list)
    for event in events:
        by_date[str(event['data_evento'])[:10]].append(event['id'])
    invitations_by_event = defaultdict(set)
    for row in invitations:
        invitations_by_event[row['evento_id']].add(code(row['comum_codigo']))
    rows_by_date = defaultdict(list)
    people_by_date_common = defaultdict(lambda: defaultdict(list))
    unresolved_by_date_city = Counter()
    for row in records:
        day = str(event_map[row['evento_id']]['data_evento'])[:10]
        rows_by_date[day].append(row)
        people_by_date_common[day][code(row.get('comum_codigo') or row.get('comum_informada'))].append(row)
        if row.get('comum_nao_reconhecida'):
            unresolved_by_date_city[(day, norm(regional_city(row.get('municipio_informado'))))] += 1
    sessions = []
    for day, ids in sorted(by_date.items()):
        date_sites = [s for s in site_map.values() if s['evento_id'] in ids]
        # Evento vazio/rascunho não é comprovação de que a lista de presença foi carregada.
        loaded = bool(set(ids) & loaded_event_ids) or all(event_map[i].get('status') == 'ENCERRADO' for i in ids)
        invited = set().union(*(invitations_by_event[i] for i in ids))
        visible_sites = date_sites if scope['level'] in {'regional', 'global'} else [
            site for site in date_sites if any(r['local_id'] == site['id'] for r in records)]
        sessions.append({'date': day, 'event_ids': ids, 'loaded': loaded,
                         'cities': sorted(session_cities(day, date_sites)), 'invited': sorted(invited),
                         'locations': sorted({s['nome'] for s in visible_sites}),
                         'unresolved': sum(bool(r.get('comum_nao_reconhecida')) for r in rows_by_date[day])})
    base_data = {'rows': [{'comum': c['comum'], 'municipio': regional_city(c['cidade'])} for c in selected_catalog],
                 'events': events, 'conductors': {}}
    attach_registry(base_data, registry, catalog)
    attach_leaders(base_data, registry, catalog, members)
    output = []
    for base in base_data['rows']:
        key = code(base['comum'])
        row = {**base, 'key': key, 'cells': [], 'musicians': 0, 'organists': 0,
               'musician_sessions': 0, 'organist_sessions': 0, 'leader_sessions': 0,
               'loaded_sessions': 0, 'expected_sessions': EXPECTED_SESSIONS}
        for session in sessions:
            day, ids = session['date'], session['event_ids']
            applicable = key in session['invited'] if session['invited'] else base['municipio'] in session['cities']
            if not applicable:
                continue
            people, seen = [], set()
            for person in people_by_date_common[day].get(key, []):
                # Nunca unir homônimos por nome. IDs estáveis eliminam duplicação entre locais.
                identity = ('sam', person['sam_pessoa_id']) if person.get('sam_pessoa_id') else (
                    ('source', person['origem_registro_id']) if person.get('origem_registro_id') else
                    ('person', person['pessoa_chave']) if person.get('pessoa_chave') else ('row', person.get('id', id(person))))
                if identity in seen:
                    continue
                seen.add(identity)
                people.append(person)
            counts = Counter(person['categoria'] for person in people)
            entries = [reviews_by_key[(event, key)] for event in ids if (event, key) in reviews_by_key]
            present = [entry for entry in entries if attendance_status(entry) == 'PRESENTE']
            states = {entry['situacao'] for entry in entries}
            status = 'PRESENTE' if present else next(iter(states)) if len(states) == 1 else 'NAO_INFORMADO'
            loaded = session['loaded']
            m, o = counts['MUSICO'], counts['ORGANISTA']
            unresolved = unresolved_by_date_city[(day, norm(base['municipio']))]
            locations = sorted({site_map[p['local_id']]['nome'] for p in people if p['local_id'] in site_map})
            attendance_by_location = {}
            for person in people:
                name = site_map.get(person['local_id'], {}).get('nome', 'Não informado')
                group = attendance_by_location.setdefault(name, {'MUSICO': 0, 'ORGANISTA': 0, 'total': 0})
                if person['categoria'] in {'MUSICO', 'ORGANISTA'}:
                    group[person['categoria']] += 1
                group['total'] += 1
            cell = {'date': day, 'loaded': loaded, 'musicians': m if loaded else None,
                    'organists': o if loaded else None, 'leader_status': status,
                    'leader_on_list': bool(present),
                    'leader_attendance': next((state for state in ['PRESENTE', 'JUSTIFICOU', 'ENFERMO', 'SEM_ENCARREGADO'] if state in states), 'NAO_JUSTIFICOU'),
                    'leader_valid_locations': sorted({local for entry in present for local in entry['locais_validos']}),
                    'leader_locations': sorted({local for entry in present for local in entry['locais']}),
                    'locations': locations, 'unresolved': unresolved,
                    'attendance_by_location': attendance_by_location,
                    'instruments': dict(Counter(p.get('instrumento') or 'Não informado' for p in people if p['categoria'] == 'MUSICO')),
                    'roles': dict(Counter(p.get('cargo') for p in people if p.get('cargo'))),
                    'families': dict(Counter(p.get('familia') or 'OUTROS' for p in people if p['categoria'] == 'MUSICO')),
                    'categories': dict(counts),
                    'musician_percent': rate(m, base.get('cadastro_musicos')) if loaded else None,
                    'organist_percent': rate(o, base.get('cadastro_organistas')) if loaded else None,
                    'others': sum(v for cat, v in counts.items() if cat not in {'MUSICO', 'ORGANISTA'})}
            row['cells'].append(cell)
            if loaded:
                row['loaded_sessions'] += 1
                row['musicians'] += m
                row['organists'] += o
                row['musician_sessions'] += bool(m)
                row['organist_sessions'] += bool(o)
                row['leader_sessions'] += bool(present)
        n = row['loaded_sessions']
        row['no_musicians'] = bool(n and not row['musicians'])
        row['no_organists'] = bool(n and not row['organists'])
        row['no_leader'] = bool(n and not row['leader_sessions'])
        row['unresolved'] = sum(c['unresolved'] for c in row['cells'])
        row['no_participation'] = bool(n and not (row['musicians'] or row['organists'] or row['leader_sessions']))
        row['year_complete'] = n >= EXPECTED_SESSIONS
        row['absence_review_pending'] = bool(row['no_participation'] and (not row['year_complete'] or row['unresolved']
                                            or any(c['leader_status'] == 'NAO_INFORMADO' for c in row['cells'])))
        row['musician_percent'] = rate(row['musicians'], (base.get('cadastro_musicos') or 0) * n)
        row['organist_percent'] = rate(row['organists'], (base.get('cadastro_organistas') or 0) * n)
        row['reading'] = ('Sem dados de presença' if not n else 'Sem registro; conciliação pendente' if row['no_participation'] and row['unresolved'] else
                          f'Sem participação registrada em {n} ensaios' if row['no_participation'] else 'Com participação registrada')
        output.append(row)
    output.sort(key=lambda r: (norm(r['municipio']), norm(r['comum'].split(' - ', 1)[-1])))
    unresolved_count = sum(bool(r.get('comum_nao_reconhecida')) and
                           (not cities or norm(regional_city(r.get('municipio_informado'))) in cities)
                           for r in records)
    pending_note = (f' Há {unresolved_count} presenças com comum não conciliada no recorte; os totais por comum '
                    'consideram apenas origens reconhecidas. Conferir antes de concluir ausência.') if unresolved_count else ''
    return {'year': int(year), 'sessions': sessions, 'rows': output, 'unresolved_count': unresolved_count,
            'physical_closings': closings,
            'allow_original': scope['level'] in {'regional', 'global'},
            'cities': sorted({regional_city(r['cidade']) for r in all_catalog}),
            'selected_cities': sorted({r['municipio'] for r in output}), 'registry': base_data['registry'],
            'review_available': review_available,
            'summary': {'commons': len(output), 'no_participation': sum(r['no_participation'] for r in output),
                        'no_musicians': sum(r['no_musicians'] for r in output),
                        'no_organists': sum(r['no_organists'] for r in output),
                        'no_leader': sum(r['no_leader'] for r in output)},
            'note': 'Base SAM atual: Ativo, Alerta e Concluído, todos os níveis. Percentuais por ensaio = presentes / cadastro da comum. '
                    'Percentual anual = soma das presenças / (cadastro atual × ensaios carregados do circuito). '
                    'Datas simultâneas são uma oportunidade; locais não multiplicam a base. '
                    'Encarregado local: PRESENTE, J, NJ, SE (sem encarregado) ou EF (enfermo). Ano completo exige os três ensaios carregados. '
                    'O local de comparecimento só é exibido quando validado e não altera a presença nominal. '
                    'O cadastro atual não representa uma captura histórica da data do ensaio.' + pending_note}
