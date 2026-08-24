"""Reclassifica a agenda RF/RE somente com confirmação explícita."""
import argparse
import os
import sys

import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Confirma as alterações em massa.')
    args = parser.parse_args()
    if not args.apply:
        print('Modo de prévia: nada foi alterado. Use --apply para confirmar.')
        return 0

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ColorAdmin.settings')
    import django
    django.setup()
    from django.conf import settings

    base = f"{settings.SUPABASE_URL}/rest/v1"
    headers = {
        'apikey': settings.SUPABASE_SERVICE_ROLE_KEY,
        'Authorization': f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        'Content-Type': 'application/json', 'Prefer': 'return=representation',
    }
    teams_url = f"{base}/{settings.SUPABASE_TABLE_VISITAS_EQUIPES}"
    agenda_url = f"{base}/{settings.SUPABASE_TABLE_VISITAS_AGENDA}"

    def ensure_group(name):
        response = requests.get(teams_url, headers=headers, params={'nome': f'eq.{name}', 'select': '*'}, timeout=20)
        response.raise_for_status()
        rows = response.json()
        if rows:
            requests.patch(
                teams_url, headers=headers, params={'id': f"eq.{rows[0]['id']}"},
                json={'nome': name, 'tipo': 'LOCAL', 'comum': 'TODAS'}, timeout=20,
            ).raise_for_status()
            return rows[0]
        response = requests.post(teams_url, headers=headers, json={
            'nome': name, 'tipo': 'LOCAL', 'municipio': 'ITAPEVI', 'comum': 'TODAS', 'ativo': True,
        }, timeout=20)
        response.raise_for_status()
        return response.json()[0]

    groups = {name: ensure_group(name) for name in ('Grupo RF', 'Grupo RE')}
    print('GRUPOS', {name: row.get('id') for name, row in groups.items()})
    for category, name in (('RF', 'Grupo RF'), ('RE', 'Grupo RE')):
        group = groups[name]
        response = requests.patch(
            agenda_url, headers=headers, params={'categoria': f'eq.{category}'},
            json={'equipe_responsavel': name, 'equipe_tipo': 'LOCAL', 'equipe_id': group.get('id')}, timeout=30,
        )
        response.raise_for_status()
        print(category, 'ATUALIZADOS', len(response.json()) if response.text else 0)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
