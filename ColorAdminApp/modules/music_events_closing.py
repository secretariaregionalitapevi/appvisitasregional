"""Público físico por local, independente do recorte das comuns de origem."""
import json
from collections import Counter, defaultdict
from pathlib import Path
from .music_events_identity import normalized_city
from .music_events_calendar import valid_destination


def physical_closings(events, records, sites):
    events = {event['id']: event for event in events}
    sites = {site['id']: site for site in sites if site['evento_id'] in events
             and valid_destination(events[site['evento_id']], site)}
    groups = defaultdict(list)
    for row in records:
        site = sites.get(row.get('local_id'))
        if not site or row['evento_id'] != site['evento_id'] or row.get('situacao', 'PRESENTE') != 'PRESENTE':
            continue
        groups[(str(events[row['evento_id']]['data_evento'])[:10], normalized_city(site.get('municipio') or site['nome']))].append(row)
    result = []
    for (day, city), rows in groups.items():
        counts = Counter(row['categoria'] for row in rows)
        result.append({'date': day, 'city': city, 'musicians': counts['MUSICO'], 'organists': counts['ORGANISTA'],
                       'total': len(rows), 'instruments': dict(Counter(row.get('instrumento') or 'NÃO INFORMADO' for row in rows if row['categoria'] == 'MUSICO')),
                       'roles': dict(Counter(row['cargo'] for row in rows if row.get('cargo'))),
                       'source_label': 'LISTA NOMINAL IMPORTADA - PÚBLICO DO LOCAL, TODAS AS ORIGENS'})
    return result


def closing_for(data):
    if not data.get('allow_original'):
        return None
    dates = {str(e['data_evento'])[:10] for e in data.get('events', [])}
    cities = {normalized_city(city) for city in data.get('filters', {}).get('municipios', [])}
    if len(dates) != 1 or len(cities) != 1:
        return None
    day, city = next(iter(dates)), next(iter(cities))
    nominal = next((row for row in data.get('physical_closings', []) if row['date'] == day and row['city'] == city), None)
    for path in (Path(__file__).parents[2] / 'docs/references/music_events').glob('*_closing.json'):
        declared = json.loads(path.read_text(encoding='utf-8'))
        if declared['date'] == day and declared['city'] == city:
            return {**declared, 'nominal_total': nominal['total'] if nominal else None, 'declared': True}
    return nominal
