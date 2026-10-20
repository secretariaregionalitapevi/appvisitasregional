"""Grava a sequência sugerida do roteiro sem repetir uma escrita incerta."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from django.conf import settings

from .routing import route_address_key
from .supabase_http import supabase_get


def sao_paulo_datetime(value):
    dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return dt.replace(tzinfo=ZoneInfo('America/Sao_Paulo')) if dt.tzinfo is None else dt.astimezone(ZoneInfo('America/Sao_Paulo'))


def persist_suggested_schedule(ordered, original_visits, changes):
    url = f'{settings.SUPABASE_URL}/rest/v1/{settings.SUPABASE_TABLE_VISITAS_AGENDA}'
    headers = {'apikey': settings.SUPABASE_SERVICE_ROLE_KEY,
               'Authorization': f'Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}',
               'Prefer': 'return=representation'}
    for house in ordered:
        start = sao_paulo_datetime(house['data_inicio'])
        end = sao_paulo_datetime(house['data_fim']) if house.get('data_fim') else start + timedelta(minutes=15)
        payload = {'data_inicio': start.isoformat(), 'data_fim': end.isoformat()}
        for original in original_visits:
            if route_address_key(original) != route_address_key(house):
                continue
            if original.get('status') != 'Marcada' or not original.get('id'):
                raise ValueError('Somente visitas marcadas podem ter os horários sugeridos reorganizados.')
            if (sao_paulo_datetime(original['data_inicio']) == start and original.get('data_fim')
                    and sao_paulo_datetime(original['data_fim']) == end):
                continue
            params = {'id': f"eq.{original['id']}", 'status': 'eq.Marcada',
                      'data_inicio': f"eq.{original['data_inicio']}",
                      'data_fim': f"eq.{original['data_fim']}" if original.get('data_fim') else 'is.null'}
            try:
                response = requests.patch(url, headers=headers, params=params, json=payload, timeout=15)
                response.raise_for_status()
                rows = response.json()
                if len(rows) != 1:
                    raise ValueError('A agenda foi alterada durante a otimização. Atualize o roteiro.')
            except requests.RequestException:
                # A escrita pode ter ocorrido antes da queda. Consultar, nunca reenviar.
                response = supabase_get(url, headers=headers, params={'id': f"eq.{original['id']}", 'select': 'id,status,data_inicio,data_fim'})
                response.raise_for_status()
                rows = response.json()
            if (len(rows) != 1 or rows[0].get('status') != 'Marcada'
                    or sao_paulo_datetime(rows[0]['data_inicio']) != start
                    or sao_paulo_datetime(rows[0]['data_fim']) != end):
                raise ValueError('Não foi possível confirmar a nova sequência na agenda. Atualize o roteiro.')
            changes.append({'id': original['id'],
                            'anterior': {key: original.get(key) for key in payload}, 'novo': payload})
