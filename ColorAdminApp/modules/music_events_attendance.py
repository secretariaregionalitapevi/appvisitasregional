"""Público do evento separado da participação por origem."""
import json
from collections import Counter
from pathlib import Path

from .music_events_dashboard import aggregate
from .music_events_closing import physical_closings
from .music_events_identity import normalized_city


def attendance_overview(events, records, locations, filters, catalog):
    # Neste quadro, município seleciona a sede física. A origem da pessoa
    # continua sendo detalhada separadamente, inclusive para visitantes.
    general_filters = {**filters, 'origem': 'todos', 'municipios': [], 'comuns': []}
    cities = {normalized_city(city) for city in filters.get('municipios', [])}
    scoped_sites = [site for site in locations
        if (not cities or normalized_city(site.get('municipio') or site['nome']) in cities)
        and (not filters.get('local') or site['id'] == filters['local'])]
    site_ids = {site['id'] for site in scoped_sites}
    scoped_records = [row for row in records if row.get('local_id') in site_ids]
    event_days = {event['id']:str(event['data_evento'])[:10] for event in events}
    site_cities = {site['id']:normalized_city(site.get('municipio') or site['nome']) for site in scoped_sites}
    general = aggregate(events, scoped_records, scoped_sites, [], general_filters, catalog)
    closings = physical_closings(general['events'], scoped_records, scoped_sites)
    declared = {}
    for path in (Path(__file__).parents[2] / 'docs/references/music_events').glob('*_closing.json'):
        row = json.loads(path.read_text(encoding='utf-8'))
        declared[(row['date'], row['city'])] = row
    for row in closings:
        original = declared.get((row['date'], row['city']))
        row['declared_total'] = original['total'] if original else None
        row['difference'] = original['total'] - row['total'] if original else None
        row['declared_source'] = original['source_label'] if original else None
        row['official'] = original if original and original.get('use_as_official_closing') else None
    official = [row['official'] for row in closings if row.get('official')]
    # Não atribuir o saldo sem nomes a municípios de origem. Nos recortes
    # mistos, cada local mantém identificada a própria fonte de fechamento.
    official_only = bool(closings) and len(official) == len(closings)
    display_totals = dict(general['totals'])
    for closing in closings:
        original = closing.get('official')
        if not original:
            continue
        nominal_rows = [row for row in scoped_records if event_days.get(row['evento_id'])==closing['date']
            and site_cities.get(row['local_id'])==closing['city']
            and row.get('situacao','PRESENTE')=='PRESENTE']
        counts = Counter(row['categoria'] for row in nominal_rows)
        replacements = {'total': original['total'], 'MUSICO': original['musicians'],
            'ORGANISTA': original['organists'], 'IRMANDADE': original.get('support',{}).get('IRMANDADE',0),
            'APOIO': sum(value for key,value in original.get('support',{}).items() if key!='IRMANDADE')}
        for key,value in replacements.items():
            display_totals[key] = display_totals.get(key,0) + value - (len(nominal_rows) if key=='total' else counts[key])
    general_filters['municipios_locais'] = list(filters.get('municipios', []))
    return {'totals': general['totals'], 'municipalities': general['municipalities'],
            'locations': general['locations'], 'origin_context': general['origin_context'],
            'closings': closings, 'filters': general_filters, 'official_only': official_only,
            'display_totals': display_totals, 'has_official': bool(official)}


def general_report(data):
    """Reutiliza a composição institucional, sem aplicar filtros de origem."""
    overview = data['attendance_overview']
    report_filters = {**overview['filters'], 'municipios': overview['filters'].get('municipios_locais',[])}
    return {**data, 'totals': overview['display_totals'], 'municipalities': overview['municipalities'],
            'locations': overview['locations'], 'filters': report_filters, 'report': 'geral'}
