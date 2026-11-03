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
    days = sorted(set(str(day)[:10] for day in dates))
    labels = [day[8:10] + '_' + day[5:7] + '_' + day[:4] for day in days]
    period = labels[0] if len(labels) == 1 else f'{labels[0]}_a_{labels[-1]}' if labels else 'Periodo'
    return f'Presencas_{report_scope(cities, filename=True)}_{period}.pdf'


def download_header(filename):
    # Fallback compatível e nome UTF-8 para preservar os acentos no download.
    fallback = filename.replace('RELATÓRIO', 'RELATORIO').replace('PRESENÇA', 'PRESENCA')
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(filename, safe="")}'
