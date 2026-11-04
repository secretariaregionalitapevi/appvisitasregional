"""Nomes dos relatórios de presença, baseados no recorte e na data do ensaio."""
import re
from urllib.parse import quote

from .music_events_import import norm
from .music_events_dashboard import REGIONAL, regional_city

def report_scope(cities, *, filename=False):
    cities = sorted({regional_city(city) for city in cities if city})
    if not cities or {norm(city) for city in cities} == {norm(city) for city in REGIONAL}:
        return 'Regional' if filename else 'REGIONAL ITAPEVI'
    if filename:
        return re.sub(r'[^A-Z0-9_-]+', '_', norm(cities[0])).strip('_') if len(cities) == 1 else 'Selecao'
    if len(cities) <= 2:
        short = {'PIRAPORA DO BOM JESUS': 'PIRAPORA', 'VARGEM GRANDE PAULISTA': 'VGP',
                 'SANTANA DE PARNAÍBA': 'SANTANA', 'CAUCAIA DO ALTO': 'CAUCAIA'}
        return ' / '.join(short.get(city, city) for city in cities)
    return f'{len(cities)} MUNICÍPIOS SELECIONADOS'


def presence_filename(cities, dates):
    months = ('JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ')
    days = sorted(set(str(day)[:10] for day in dates))
    labels = list(dict.fromkeys(months[int(day[5:7]) - 1] + day[2:4] for day in days))
    period = labels[0] if len(labels) == 1 else f'{labels[0]}_A_{labels[-1]}' if labels else 'PERIODO'
    places = sorted({re.sub(r'[^A-Z0-9]+', '_', norm(city)).strip('_') for city in cities if city})
    place = '_E_'.join(places) or 'REGIONAL'
    return f'[RELATÓRIO] EnR_{place}_{period}.pdf'


def rehearsal_places(data):
    options = data.get('options', {}).get('locations', [])
    local = data.get('filters', {}).get('local')
    if local:
        return [site['nome'] for site in options if site['id'] == local]
    cities = data.get('filters', {}).get('municipios', [])
    selected = [site['nome'] for site in options if norm(site['nome']) in {norm(city) for city in cities}]
    return selected or [site['nome'] for site in data.get('locations', [])] or [site['nome'] for site in options]


def download_header(filename):
    # Fallback compatível e nome UTF-8 para preservar os acentos no download.
    fallback = filename.replace('RELATÓRIO', 'RELATORIO').replace('PRESENÇA', 'PRESENCA')
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(filename, safe="")}'
