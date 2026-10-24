"""Nomes dos relatórios de presença, baseados no recorte e na data do ensaio."""
import re
from urllib.parse import quote

from .music_events_import import norm

MONTHS = ('JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ')


def presence_filename(cities, dates):
    city = '_'.join(re.sub(r'[^A-Z0-9_-]+', '_', norm(value)).strip('_') for value in sorted(set(cities))) or 'REGIONAL'
    periods = list(dict.fromkeys(MONTHS[int(day[5:7]) - 1] + day[2:4] for day in sorted(set(str(d)[:10] for d in dates))))
    period = '-'.join(periods) or 'PERIODO_SELECIONADO'
    return f'[RELATÓRIO] PRESENÇA_EnR_{city}_{period}.pdf'


def download_header(filename):
    # Fallback compatível e nome UTF-8 para preservar os acentos no download.
    fallback = filename.replace('RELATÓRIO', 'RELATORIO').replace('PRESENÇA', 'PRESENCA')
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(filename, safe="")}'
