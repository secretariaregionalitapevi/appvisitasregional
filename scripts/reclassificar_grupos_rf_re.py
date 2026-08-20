"""Cria os grupos regionais RF/RE e reclassifica a agenda existente."""
import os
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ColorAdmin.settings')
import django
django.setup()
from django.conf import settings

BASE = f"{settings.SUPABASE_URL}/rest/v1"
HEADERS = {
    'apikey': settings.SUPABASE_SERVICE_ROLE_KEY,
    'Authorization': f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    'Content-Type': 'application/json',
    'Prefer': 'return=representation',
}
teams_url = f"{BASE}/{settings.SUPABASE_TABLE_VISITAS_EQUIPES}"
agenda_url = f"{BASE}/{settings.SUPABASE_TABLE_VISITAS_AGENDA}"

def ensure_group(name, old_name):
    response = requests.get(teams_url, headers=HEADERS, params=[('nome', f'eq.{name}'), ('select', '*')], timeout=20)
    response.raise_for_status()
    rows = response.json()
    if not rows:
        legacy = requests.get(teams_url, headers=HEADERS, params=[('nome', f'eq.{old_name}'), ('select', '*')], timeout=20).json()
        if not legacy:
            legacy = requests.get(teams_url, headers=HEADERS, params=[('nome', f'eq.{old_name} - histórico'), ('select', '*')], timeout=20).json()
        if legacy:
            rows = legacy
            requests.patch(f"{teams_url}?id=eq.{rows[0]['id']}", headers=HEADERS, json={'nome': name, 'tipo': 'LOCAL', 'comum': 'TODAS'}, timeout=20).raise_for_status()
    if rows:
        requests.patch(f"{teams_url}?id=eq.{rows[0]['id']}", headers=HEADERS, json={'nome': name, 'tipo': 'LOCAL', 'comum': 'TODAS'}, timeout=20).raise_for_status()
        rows[0].update({'tipo': 'LOCAL', 'comum': 'TODAS'})
        return rows[0]
    response = requests.post(teams_url, headers=HEADERS, json={
        'nome': name, 'tipo': 'LOCAL', 'municipio': 'ITAPEVI', 'comum': 'TODAS', 'ativo': True,
    }, timeout=20)
    response.raise_for_status()
    return response.json()[0]

groups = {name: ensure_group(name, name) for name in ('Grupo RF', 'Grupo RE')}
print('GRUPOS', {name: row.get('id') for name, row in groups.items()})

for category, name in (('RF', 'Grupo RF'), ('RE', 'Grupo RE')):
    group = groups[name]
    response = requests.patch(
        agenda_url,
        headers=HEADERS,
        params=[('categoria', f'eq.{category}')],
        json={'equipe_responsavel': name, 'equipe_tipo': 'LOCAL', 'equipe_id': group.get('id')},
        timeout=30,
    )
    response.raise_for_status()
    print(category, 'ATUALIZADOS', len(response.json()) if response.text else 0)

for name, group in groups.items():
    # A tabela de equipes não possui necessariamente coluna de membros; a
    # ausência de linhas vinculadas é verificada pelo campo equipe_id da irmandade.
    members_url = f"{BASE}/{settings.SUPABASE_TABLE_VISITAS_IRMANDADE}"
    members = requests.get(members_url, headers=HEADERS, params=[('equipe_id', f'eq.{group.get("id")}'), ('select', 'id')], timeout=20)
    members.raise_for_status()
    print(name, 'MEMBROS', len(members.json()))
