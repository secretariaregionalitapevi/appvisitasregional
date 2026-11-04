"""Histórico individual: evidência nominal e público confirmado por encontro."""
from collections import Counter, defaultdict
from datetime import date
from hashlib import sha256
from io import BytesIO
import re
from uuid import NAMESPACE_URL, uuid5

from openpyxl import load_workbook

from .access_control import can_access
from .music_events_calendar import regular_destinations
from .music_events_dashboard import REGIONAL, code, regional_city
from .music_events_identity import CommonResolver
from .music_events_import import norm

TITLE = 'Acompanhamento'
ROLES = {'ENCARREGADO_LOCAL': 'Encarregado local', 'ENCARREGADO_REGIONAL': 'Encarregado regional',
         'EXAMINADORA': 'Examinadora', 'ANCIAO': 'Ancião', 'COOPERADOR': 'Cooperador'}
KINDS = {'REUNIAO_MINISTERIO': 'Reunião do Ministério da Música', 'ENSAIO_REGIONAL': 'Ensaio regional',
         'ENSAIO_MUNICIPAL': 'Ensaio municipal', 'REUNIAO_TECNICA': 'Reunião técnica',
         'CAPACITACAO': 'Capacitação técnica'}
STATES = {'PRESENTE': 'Presente', 'JUSTIFICOU': 'Justificou', 'SEM_REGISTRO': 'Não participou',
          'CONFERIR': 'Conferência pendente', 'SEM_DADOS': 'Sem dados', 'NAO_APLICA': 'Não se aplica'}
VERIFIED = {'PRESENTE', 'JUSTIFICOU', 'SEM_REGISTRO'}


def roles_of(value):
    value = norm(value)
    result = []
    for key, label in ROLES.items():
        if key == 'COOPERADOR':
            match = 'COOPERADOR' in value
        else:
            match = norm(label) in value
        if match:
            result.append(key)
    return result


def roster(registry, members, catalog):
    """IDs de origem preservados; conciliação entre cadastros exige chave composta única."""
    resolver, people = CommonResolver(catalog), []
    for source, rows in [('sam', registry), ('irmandade', members)]:
        for row in rows:
            if norm(row.get('status')) in {'INATIVO', 'EXCLUIR'} or not row.get('id'):
                continue
            roles = roles_of(row.get('cargo_ministerio') if source == 'sam' else row.get('cargo_outros'))
            common = resolver.resolve(row.get('codigo_comum') or row.get('comum_congregacao') or row.get('comum'),
                                      row.get('municipio') or row.get('cidade'))
            name = str(row.get('nome_aluno') or row.get('nome') or '').strip()
            if not roles or not common or not name or regional_city(common['cidade']) not in REGIONAL:
                continue
            from .music_events_registry import instrument_family
            families = [instrument_family(row['instrumento'])] if row.get('instrumento') else []
            people.append({'key': f'{source}:{row["id"]}', 'aliases': [f'{source}:{row["id"]}'],
                           'nome': name, 'comum': common['comum'], 'municipio': regional_city(common['cidade']),
                           'roles': roles, 'source': source, 'families': families})
    by_signature = defaultdict(list)
    for person in people:
        by_signature[(norm(person['nome']), code(person['comum']), tuple(sorted(person['roles'])))].append(person)
    result = []
    for group in by_signature.values():
        if len(group) == 2 and {p['source'] for p in group} == {'sam', 'irmandade'}:
            preferred = next(p for p in group if p['source'] == 'irmandade')
            preferred['aliases'] = [alias for p in group for alias in p['aliases']]
            preferred['families'] = sorted({family for p in group for family in p['families']})
            result.append(preferred)
        else:
            result.extend(group)
    return sorted(result, key=lambda p: (norm(p['municipio']), norm(p['nome']), p['key']))


def match_person(row, people):
    aliases = {f'sam:{row["sam_pessoa_id"]}'} if row.get('sam_pessoa_id') else set()
    if row.get('person_key'):
        aliases.add(row['person_key'])
    exact = [p for p in people if aliases.intersection(p['aliases'])]
    if len(exact) == 1:
        return exact
    return [p for p in people if norm(row.get('nome')) in {norm(name) for name in [p['nome'], *p.get('confirmed_names', [])]}
            and code(p['comum']) == code(row.get('comum') or row.get('comum_codigo') or row.get('comum_informada'))]


def person_matcher(people):
    aliases, names = defaultdict(list), defaultdict(list)
    for person in people:
        for alias in person['aliases']:
            aliases[alias].append(person)
        for name in {norm(name) for name in [person['nome'], *person.get('confirmed_names', [])]}:
            names[(name, code(person['comum']))].append(person)
    def match(row):
        keys = [f'sam:{row["sam_pessoa_id"]}'] if row.get('sam_pessoa_id') else []
        if row.get('person_key'):
            keys.append(row['person_key'])
        exact = {p['key']: p for key in keys for p in aliases.get(key, [])}
        if len(exact) == 1:
            return list(exact.values())
        return names.get((norm(row.get('nome')), code(row.get('comum') or row.get('comum_codigo') or row.get('comum_informada'))), [])
    return match


def include_directory(people, directory, confirmed_entries=()):
    people = [dict(p, aliases=list(p['aliases']), confirmed_names=list(p.get('confirmed_names', []))) for p in people]
    known = {alias for person in people for alias in person['aliases']}
    for entry in directory:
        if not entry['roles']:
            continue
        if entry['person_key'] not in known:
            people.append({'key': entry['person_key'], 'aliases': [entry['person_key']], 'nome': entry['nome'],
                           'comum': entry['comum'], 'municipio': regional_city(entry['municipio']),
                           'roles': entry['roles'], 'source': 'arquivo', 'families': [], 'confirmed_names': []})
    indexed = {alias: person for person in people for alias in person['aliases']}
    linked = set()
    for entry in confirmed_entries:
        canonical = entry.get('source', {}).get('canonical_person_key')
        if canonical in indexed:
            person = indexed[canonical]
            if entry['person_key'] not in person['aliases']:
                person['aliases'].append(entry['person_key'])
            if entry['nome'] not in person['confirmed_names']:
                person['confirmed_names'].append(entry['nome'])
            if indexed.get(entry['person_key']) is not person:
                linked.add(entry['person_key'])
    return [p for p in people if p['key'] not in linked]


def parse_meeting(content, catalog):
    if len(content) > 15 * 1024 * 1024:
        raise ValueError('Selecione uma planilha de até 15 MB.')
    from zipfile import ZipFile
    try:
        with ZipFile(BytesIO(content)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 80 * 1024 * 1024:
                raise ValueError('Planilha descompactada excede o limite permitido.')
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=False)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('Não foi possível ler o arquivo Excel.') from exc
    digest, resolver = sha256(content).hexdigest(), CommonResolver(catalog)
    result, selected_sheet, suggested_date = [], None, None
    try:
        for sheet in workbook:
            columns = None
            for index, cells in enumerate(sheet.iter_rows(), 1):
                values = [cell.value for cell in cells]
                labels = {norm(value): col for col, value in enumerate(values) if value is not None}
                if columns is None:
                    for value in values:
                        match = re.search(r'\b(\d{2})/(\d{2})/(\d{4})\b', str(value or ''))
                        if match:
                            try:
                                suggested_date = date(int(match[3]), int(match[2]), int(match[1])).isoformat()
                            except ValueError:
                                pass
                    if {'NOME', 'MINISTERIO/CARGO', 'LOCALIDADE', 'CIDADE', 'PRESENCA'} <= labels.keys():
                        columns, selected_sheet = labels, sheet.title
                    continue
                if index > 20000:
                    raise ValueError('A lista excede 20 mil linhas.')
                if not values[columns['NOME']]:
                    continue
                if any(cell.data_type == 'f' for cell in cells):
                    raise ValueError(f'Linha {index}: fórmulas não são aceitas na lista nominal.')
                name, common, city = [str(values[columns[key]] or '').strip() for key in ['NOME', 'LOCALIDADE', 'CIDADE']]
                canonical = resolver.resolve(common, city)
                roles = roles_of(values[columns['MINISTERIO/CARGO']])
                presence = norm(values[columns['PRESENCA']])
                if presence not in {'SIM', 'NAO', 'PRESENTE', 'AUSENTE'}:
                    raise ValueError(f'Linha {index}: presença inválida.')
                if not roles:
                    raise ValueError(f'Linha {index}: cargo não reconhecido.')
                result.append({'row': index, 'source_key': f'importado:{uuid5(NAMESPACE_URL, digest + ":" + str(index))}',
                               'nome': name, 'comum': canonical['comum'] if canonical else common,
                               'municipio': regional_city(canonical['cidade']) if canonical else regional_city(city),
                               'roles': roles, 'common_resolved': bool(canonical),
                               'situacao': 'PRESENTE' if presence in {'SIM', 'PRESENTE'} else 'SEM_REGISTRO',
                               'original': {'comum': common, 'cidade': city,
                                            'administracao': str(values[columns.get('ADMINISTRACAO', columns['CIDADE'])] or ''),
                                            'entrada': str(values[columns['ENTRADA']] or '') if 'ENTRADA' in columns else '',
                                            'pagina': str(values[columns['PAGINA PDF']] or '') if 'PAGINA PDF' in columns else ''}})
            if columns is not None:
                break
    finally:
        workbook.close()
    if not result:
        raise ValueError('Não foi encontrada uma lista nominal com Nome, Ministério/Cargo, Localidade, Cidade e Presença.')
    names = Counter((norm(r['nome']), code(r['comum'])) for r in result)
    return {'sha256': digest, 'sheet': selected_sheet, 'records': result, 'count': len(result), 'suggested_date': suggested_date,
            'duplicate_rows': [r['row'] for r in result if names[(norm(r['nome']), code(r['comum']))] > 1]}


def attendance_summary(rows):
    """Count places independently of people and repeated event participations."""
    groups = defaultdict(list)
    for person in rows:
        groups[(norm(person['municipio']), code(person['comum']) or norm(person['comum']))].append(person)
    represented = sum(any(p['present'] for p in group) for group in groups.values())
    unresolved = sum(not any(p['present'] for p in group) and
                     (any(p['pending'] for p in group) or not any(p['verified'] for p in group))
                     for group in groups.values())
    return {'commons': len(groups), 'commons_present': represented,
            'commons_pending': unresolved, 'commons_without_presence': len(groups) - represented - unresolved,
            'people': len(rows), 'people_present': sum(p['present'] > 0 for p in rows),
            'present': sum(p['present'] for p in rows), 'pending': sum(p['pending'] for p in rows),
            'without_presence': sum(p['verified'] > 0 and p['present'] == 0 for p in rows)}


def history(people, events, entries, legacy_events, legacy_records, catalog, scope, filters, legacy_reviews=(), legacy_sites=()):
    """Histórico nominal; listas carregadas determinam ausências dos encarregados locais."""
    people = include_directory(people, [], entries)
    known = {alias: p for p in people for alias in p['aliases']}
    for item in [*entries, *legacy_reviews]:
        if item.get('source', {}).get('canonical_person_key'):
            continue
        if item['person_key'] not in known:
            person = {'key': item['person_key'], 'aliases': [item['person_key']], 'nome': item['nome'],
                      'comum': item['comum'], 'municipio': item['municipio'], 'roles': item['roles'], 'source': 'evento'}
            people.append(person)
            known[item['person_key']] = person
    cities = {norm(regional_city(c)) for c in filters.get('municipios', [])}
    commons = set(filters.get('comuns', []))
    visible = [p for p in people if can_access(scope, {'comum': p['comum'], 'cidade': p['municipio']})]
    options = {'cities': sorted({p['municipio'] for p in visible}),
               'commons': [{'key': key, 'name': name, 'city': city} for key, name, city in sorted({
                   (code(p['comum']), p['comum'], p['municipio']) for p in visible if not cities or norm(p['municipio']) in cities})]}
    visible = [p for p in visible if (not cities or norm(p['municipio']) in cities)
               and (not commons or code(p['comum']) in commons)
               and (not filters.get('cargo') or filters['cargo'] in p['roles'])
               and (not filters.get('busca') or norm(filters['busca']) in norm(p['nome'] + ' ' + p['comum']))]
    own_events = {e['id']: e for e in events}
    cells = defaultdict(dict)
    for item in entries:
        if item.get('source', {}).get('canonical_person_key'):
            continue
        if item['event_id'] not in own_events:
            continue
        person = known[item['person_key']]
        event = own_events[item['event_id']]
        cells[person['key']][event['id']] = {**item, 'date': str(event['data_evento']), 'titulo': event['titulo'],
                                         'tipo': event['tipo'], 'local': event['local'], 'modalidade': event['modalidade'],
                                         'editable': True}
    resolver = CommonResolver(catalog)
    legacy_map = {e['id']: e for e in legacy_events if e.get('status') != 'RASCUNHO'}
    loaded = {r['evento_id'] for r in legacy_records if r.get('situacao', 'PRESENTE') == 'PRESENTE'}
    matched = defaultdict(set)
    matched_locations = defaultdict(set)
    sites = {site['id']: site for site in legacy_sites}
    unmatched = 0
    match = person_matcher(people)
    for row in resolver.records(legacy_records):
        event = legacy_map.get(row['evento_id'])
        if not event or row.get('situacao', 'PRESENTE') != 'PRESENTE':
            continue
        matches = match(row)
        if len(matches) == 1:
            matched[matches[0]['key']].add(event['id'])
            site = sites.get(row.get('local_id'))
            if site:
                matched_locations[(matches[0]['key'], event['id'])].add(site['nome'])
        elif (roles_of(row.get('cargo'))
              and (not filters.get('cargo') or filters['cargo'] in roles_of(row.get('cargo')))
              and (not cities or norm(row.get('municipio_informado')) in cities)
              and (not commons or code(row.get('comum_informada')) in commons)
              and (not filters.get('tipo') or event['tipo'] == filters['tipo'])
              and (not filters.get('evento') or filters['evento'] == 'legado:' + event['id'])
              and (not filters.get('situacao') or filters['situacao'] == 'PRESENTE')
              and (not filters.get('busca') or norm(filters['busca']) in norm(str(row.get('nome', '')) + ' ' + str(row.get('comum_informada', ''))))
              and can_access(scope, {'comum': row.get('comum_informada'), 'cidade': row.get('municipio_informado')})):
            unmatched += 1
    review_map = {(r['event_id'], r['person_key']): r for r in legacy_reviews}
    for person in visible:
        for event in legacy_map.values():
            # Presença positiva vale em qualquer local; ausências respeitam o ciclo municipal.
            present = event['id'] in matched[person['key']]
            review = next((review_map[(event['id'], alias)] for alias in person['aliases'] if (event['id'], alias) in review_map), None)
            destinations = regular_destinations(event['data_evento']) if event['tipo'] == 'ENSAIO_REGIONAL' else None
            if not present and not review and destinations and norm(person['municipio']) not in destinations:
                continue
            local_absent = (event['id'] in loaded and 'ENCARREGADO_LOCAL' in person['roles']
                            and person.get('source') != 'arquivo')
            cells[person['key']]['legado:' + event['id']] = {
                'event_id': 'legado:' + event['id'], 'date': str(event['data_evento']), 'titulo': event['titulo'],
                'tipo': event['tipo'], 'local': ' / '.join(sorted(matched_locations[(person['key'], event['id'])])) or 'Local não informado', 'modalidade': 'PRESENCIAL',
                'situacao': 'PRESENTE' if present else review['situacao'] if review else 'SEM_REGISTRO' if local_absent else 'CONFERIR' if event['id'] in loaded else 'SEM_DADOS',
                'observacoes': review['observacoes'] if review else '' if present else 'Não consta na lista de presentes deste encontro.' if local_absent else 'Vínculo e público histórico ainda não conferidos individualmente.',
                'editable': True, 'legacy': True, 'version': review['version'] if review else 0,
                'nominal_present': present, 'person_key': review['person_key'] if review else person['key'],
                'roles': review['roles'] if review else person['roles'],
                'comum': review['comum'] if review else person['comum'], 'municipio': review['municipio'] if review else person['municipio']}
    output = []
    summary_people = []
    event_options = {}
    for person in visible:
        items = [c for c in cells[person['key']].values() if not filters.get('tipo') or c['tipo'] == filters['tipo']]
        items.sort(key=lambda c: (c['date'], c['titulo']))
        for cell in items:
            event_options[cell['event_id']] = {'id': cell['event_id'], 'date': cell['date'], 'titulo': cell['titulo'],
                                             'tipo': cell['tipo'], 'local': own_events.get(cell['event_id'], {}).get('local', '')}
        items = [c for c in items if not filters.get('evento') or c['event_id'] == filters['evento']]
        if filters.get('evento') and not items:
            continue
        states = Counter(c['situacao'] for c in items)
        count = sum(states[state] for state in VERIFIED)
        result = {**person, 'cells': items, 'present': states['PRESENTE'], 'verified': count,
                  'pending': states['CONFERIR'] + states['SEM_DADOS'], 'states': dict(states)}
        summary_people.append(result)
        state = filters.get('situacao')
        if state and not states[state]:
            continue
        # In annual mode, absence means no presence anywhere in the selected period.
        if state == 'SEM_REGISTRO' and not filters.get('evento') and states['PRESENTE']:
            continue
        output.append(result)
    output.sort(key=lambda p: (norm(p['municipio']), norm(p['comum'].split(' - ', 1)[-1]), norm(p['nome']), p['key']))
    return {'rows': output, 'options': options, 'year': filters['ano'], 'unmatched': unmatched,
            'event_options': sorted(event_options.values(), key=lambda e: (e['date'], e['titulo'])),
            'selected_cities': sorted({p['municipio'] for p in output}), 'roles': ROLES, 'kinds': KINDS, 'states': STATES,
            'summary': attendance_summary(summary_people)}


def event_payload(raw, people, records=(), mappings=None):
    day = date.fromisoformat(str(raw.get('data_evento') or '')).isoformat()
    title, kind = str(raw.get('titulo') or '').strip(), raw.get('tipo')
    cities = sorted({regional_city(c) for c in raw.get('municipios', [])})
    roles = sorted(set(raw.get('cargos', [])))
    family = raw.get('familia') or 'GERAL'
    if not title or len(title) > 140 or kind not in KINDS or not cities or not set(cities) <= set(REGIONAL):
        raise ValueError('Confira título, tipo e municípios de abrangência.')
    if not roles or not set(roles) <= ROLES.keys() or family not in {'GERAL', 'CORDAS', 'MADEIRAS', 'METAIS'}:
        raise ValueError('Confira os cargos e a família do público previsto.')
    if raw.get('modalidade') not in {'PRESENCIAL', 'ONLINE', 'HIBRIDO'} or not str(raw.get('local') or '').strip():
        raise ValueError('Informe modalidade e local/plataforma.')
    complete = bool(raw.get('lista_completa')) and bool(records)
    expected = {p['key']: {'person_key': p['key'], 'nome': p['nome'], 'comum': p['comum'],
                           'municipio': p['municipio'], 'roles': p['roles'],
                           'situacao': ('SEM_DADOS' if not records else
                                        'CONFERIR' if p.get('source') == 'arquivo' or family != 'GERAL' and not p.get('families') else
                                        'SEM_REGISTRO' if complete or 'ENCARREGADO_LOCAL' in p['roles'] else 'CONFERIR'),
                           'observacoes': '', 'source': {}}
                for p in people if p['municipio'] in cities and set(roles).intersection(p['roles'])
                and (family == 'GERAL' or not p.get('families') or family in p['families'])}
    choices = {str(m['row']): m.get('key') for m in mappings or []}
    assigned = set()
    for row in records:
        if not row['common_resolved'] or row['municipio'] not in cities:
            raise ValueError(f'Linha {row["row"]}: concilie a comum ou inclua o município no recorte do evento.')
        if not set(row['roles']).intersection(roles):
            raise ValueError(f'Linha {row["row"]}: inclua o cargo no público do evento.')
        matches = match_person(row, people)
        chosen = choices.get(str(row['row']))
        if not chosen or chosen not in {p['key'] for p in matches} | {row['source_key']}:
            raise ValueError(f'Linha {row["row"]}: confirme a identidade individual na prévia.')
        if chosen in assigned:
            raise ValueError('Duas linhas foram vinculadas à mesma pessoa. Confira as duplicidades.')
        assigned.add(chosen)
        person = next((p for p in people if p['key'] == chosen), row)
        expected[chosen] = {'person_key': chosen, 'nome': person['nome'], 'comum': row['comum'],
                            'municipio': row['municipio'], 'roles': row['roles'], 'situacao': row['situacao'],
                            'observacoes': '', 'source': {'row': row['row'], **row['original']}}
    return {'titulo': title, 'tipo': kind, 'data_evento': day, 'municipios': cities, 'cargos': roles,
            'familia': family, 'modalidade': raw['modalidade'], 'local': str(raw['local']).strip()[:120],
            'lista_completa': complete, 'registros': list(expected.values())}
