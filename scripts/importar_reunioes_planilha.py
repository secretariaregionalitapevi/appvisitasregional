"""Importa reunioes familiares/evangelizacoes de uma planilha para a agenda.

Uso: python scripts/importar_reunioes_planilha.py arquivo.xlsx [--apply]
Sem --apply, apenas exibe a previa da carga.
"""
import argparse
import calendar
import difflib
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import openpyxl
import requests
from dateutil import parser as date_parser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ColorAdmin.settings')

import django  # noqa: E402
django.setup()
from django.conf import settings  # noqa: E402

COMUM = 'BR-22-0673 - VILA DOUTOR CARDOSO'
TEAM_BY_ATTENDANT = {
    'ALCIDES SOUSA': 2, 'JOSE DE ALENCAR': 2,
    'ADERBAL BAZANTE': 3, 'JAIR JOAO': 3, 'ROGER OLIVEIRA': 3,
    'THIAGO PASSOS': 1, 'REINALDO FAUSTINO': 1, 'MINISTERIO': 1,
}


def norm(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c)).upper().split())


def host_name(value):
    value = ' '.join(str(value or '').split())
    value = re.sub(r'^REUNIÃO\s+EVANGELIZAÇÃO\s+', '', value, flags=re.IGNORECASE)
    return re.sub(r'^IRMÃO?\s+', '', value, flags=re.IGNORECASE).title()


def sector_from_address(address):
    normalized = norm(address)
    names = ('CIDADE DA SAUDE', 'VILA DR. CARDOSO', 'VILA DOUTOR CARDOSO',
             'VILA SANTO ANTONIO', 'VILA SAO FRANCISCO', 'JARDIM VITAPOLIS',
             'JARDIM DONA ELVIRA', 'JARDIM NOVA ITAPEVI')
    found = next((name for name in names if name in normalized), 'Não Definido')
    return found.title().replace('Dr.', 'Doutor')


def local_minute(value):
    parsed = date_parser.parse(str(value))
    if parsed.tzinfo:
        parsed = parsed.astimezone(ZoneInfo('America/Sao_Paulo'))
    return parsed.strftime('%Y-%m-%dT%H:%M')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('arquivo')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--target-month', help='Projeta a mesma ordem semanal em outro mês (AAAA-MM).')
    args = parser.parse_args()
    headers = {
        'apikey': settings.SUPABASE_SERVICE_ROLE_KEY,
        'Authorization': f'Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}',
        'Content-Type': 'application/json', 'Prefer': 'return=representation',
    }
    base = f'{settings.SUPABASE_URL}/rest/v1/'
    member_url = base + settings.SUPABASE_TABLE_VISITAS_IRMANDADE
    agenda_url = base + settings.SUPABASE_TABLE_VISITAS_AGENDA
    teams = requests.get(base + settings.SUPABASE_TABLE_VISITAS_EQUIPES, headers=headers,
                         params={'select': '*', 'comum': f'eq.{COMUM}'}, timeout=30).json()
    team_by_number = {int(re.search(r'\d+', t['nome']).group()): t for t in teams}
    members = requests.get(member_url, headers=headers, params={
        'select': 'id,nome,comum,endereco,setor', 'comum': f'eq.{COMUM}'}, timeout=30).json()
    target_year, target_month = (map(int, args.target_month.split('-'))
                                 if args.target_month else (2026, 8))
    target_start = f'{target_year:04d}-{target_month:02d}-01T00:00:00-03:00'
    next_year, next_month = (target_year + 1, 1) if target_month == 12 else (target_year, target_month + 1)
    target_end = f'{next_year:04d}-{next_month:02d}-01T00:00:00-03:00'
    existing = requests.get(agenda_url, headers=headers, params=[
        ('select', '*'), ('data_inicio', f'gte.{target_start}'), ('data_inicio', f'lt.{target_end}')
    ], timeout=30).json()

    rows = []
    for values in openpyxl.load_workbook(args.arquivo, data_only=True).active.iter_rows(values_only=True):
        if not re.fullmatch(r'\d{2}/\d{2}', str(values[0] or '')):
            continue
        source_date_time = datetime.strptime(f'{values[0]}/2026 {values[2]}', '%d/%m/%Y %H:%M')
        date_time = source_date_time
        if args.target_month:
            weekday = source_date_time.weekday()
            ordinal = ((source_date_time.day - 1) // 7) + 1
            matching_days = [day for day in range(1, calendar.monthrange(target_year, target_month)[1] + 1)
                             if datetime(target_year, target_month, day).weekday() == weekday]
            if len(matching_days) < ordinal:
                continue
            date_time = source_date_time.replace(
                year=target_year, month=target_month, day=matching_days[ordinal - 1])
        category = 'RE' if 'EVANGELIZACAO' in norm(values[3]) else 'RF'
        record = (date_time, category, host_name(values[3]), str(values[4]).strip(),
                  ' '.join(str(values[5]).split()).title())
        if record not in rows:
            rows.append(record)

    created = updated = 0
    for start, category, title, address, attendant in rows:
        number = (re.search(r'\b(?:N|NO|NUMERO)?\s*(\d+)\b', norm(address)) or [None, None])[1]
        first_name = norm(title).split()[0]
        candidates = [m for m in members if difflib.SequenceMatcher(
            None, norm(m['nome']).split()[0], first_name).ratio() >= 0.8]
        address_matches = [m for m in candidates if number and re.search(rf'\b{number}\b', norm(m.get('endereco')))]
        member = (address_matches or candidates[:1] or [None])[0]
        if not member and args.apply:
            response = requests.post(member_url, headers=headers, json={
                'nome': title, 'comum': COMUM, 'endereco': address,
                'setor': sector_from_address(address), 'status': 'Ativo'}, timeout=30)
            response.raise_for_status()
            member = response.json()[0]
            members.append(member)
        team = team_by_number[TEAM_BY_ATTENDANT[norm(attendant)]]
        iso_start = start.strftime('%Y-%m-%dT%H:%M:00-03:00')
        payload = {
            'irmandade_id': member['id'] if member else None, 'titulo': title,
            'data_inicio': iso_start,
            'data_fim': (start + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:00-03:00'),
            'equipe_responsavel': team['nome'], 'equipe_id': team['id'], 'equipe_tipo': 'LOCAL',
            'categoria': category, 'status': 'Marcada', 'setor': sector_from_address(address),
            'endereco_visitado': address,
            'observacoes': f'[[responsavel_atendimento:{attendant.title()}]]',
        }
        match = next((item for item in existing if local_minute(item.get('data_inicio')) == iso_start[:16]
                      and item.get('categoria') == category
                      and (str(item.get('irmandade_id') or '') == str((member or {}).get('id') or '')
                           or norm(item.get('titulo')) == norm(title))), None)
        action = 'ATUALIZAR' if match else 'CRIAR'
        print(f'{action}: {start:%d/%m %H:%M} {category} - {title} - {attendant.title()} ({team["nome"]})')
        if not args.apply:
            continue
        response = requests.patch(agenda_url, headers=headers, params={'id': f'eq.{match["id"]}'},
                                  json=payload, timeout=30) if match else requests.post(
                                      agenda_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        updated += bool(match)
        created += not bool(match)
    print(f'Total: {len(rows)} | criados: {created} | atualizados: {updated} | modo: {"aplicado" if args.apply else "prévia"}')


if __name__ == '__main__':
    main()
