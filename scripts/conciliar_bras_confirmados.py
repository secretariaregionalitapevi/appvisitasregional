"""Somente os oito pares confirmados pelo usuário; preserva o nome do cadastro."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import json
import re

import requests
from django.conf import settings

from ColorAdminApp.modules.access_control import service_headers
from ColorAdminApp.modules.music_events import _read
from ColorAdminApp.modules.music_events_dashboard import code
from ColorAdminApp.modules.music_events_import import norm
from ColorAdminApp.modules.music_ministry import _rpc

EVENT = '7537d3e7-baac-4bd0-b0ae-acb36fd79c37'
PAIRS = [
    ('Jonathas da Silva Aguiar', 'Jonathas da Silveira Aguiar'),
    ('Leandro de Sousa Moura', 'Leandro Sousa Moura'),
    ('Adalberto Carvalho Teixeira', 'Adalberto Carvalho Teixeira (Beto)'),
    ('Elcio Monteiro dos Reis', 'Elcio Monteiro Reis'),
    ('José Herivan da Silva Albuquerque', 'José Erivan da Silva Albuquerque'),
    ('Joaquim Correa de Andrade dos', 'Joaquim Correa de Andrade dos Santos'),
    ('Flávio Cesar Silvestre', 'Flávio Silvestre'),
    ('Leandro Cunha de Moraes', 'Leandro Cunha de Morais'),
]
ACTOR_ID = 'codex:conciliacao-confirmada'
ACTOR = 'Conciliação de oito identidades confirmada pelo usuário'


def main(confirmar=False):
    def name_key(value):
        return ' '.join(re.sub(r'[^A-Z0-9]+', ' ', norm(value)).split())
    rows = _read('musica_ministerio_participacoes', event_id=f'eq.{EVENT}', order='person_key.asc')
    directory = _read('musica_ministerio_pessoas', order='person_key.asc')
    selected = []
    for original, canonical in PAIRS:
        old = [r for r in rows if r['person_key'].startswith('importado:') and name_key(r['nome']) == name_key(original)]
        target = [r for r in rows if not r['person_key'].startswith('importado:') and name_key(r['nome']) == name_key(canonical)]
        if len(old) != 1 or len(target) != 1 or code(old[0]['comum']) != code(target[0]['comum']):
            raise ValueError(f'O par confirmado não corresponde de forma única à mesma comum: {original}.')
        if target[0]['situacao'] not in {'SEM_REGISTRO', 'PRESENTE'} or old[0]['situacao'] not in {'PRESENTE', 'NAO_APLICA'}:
            raise ValueError('Uma situação foi alterada desde a conferência. Revisar antes de conciliar.')
        selected.append((old[0], target[0]))
    print(json.dumps({'pares_confirmados': len(selected), 'nome_mantido': 'cadastro',
                      'presentes_antes': sum(r['situacao'] == 'PRESENTE' for r in rows)}), flush=True)
    if not confirmar:
        return
    backup = Path('tmp/conciliacao_bras_confirmada')
    backup.mkdir(parents=True, exist_ok=True)
    snapshot = backup / ('antes_' + datetime.now().strftime('%d_%m_%Y_%H_%M_%S') + '.json')
    snapshot.write_text(json.dumps({'participacoes': rows, 'pessoas': directory}, ensure_ascii=False, indent=2), encoding='utf-8')

    def patch(table, params, payload):
        response = requests.patch(f'{settings.SUPABASE_URL}/rest/v1/{table}', headers=service_headers(), params=params, json=payload, timeout=25)
        response.raise_for_status()

    def reconcile(pair):
        old, target = pair
        linked = old['source'].get('canonical_person_key') == target['person_key']
        for row, state in [(target, 'PRESENTE'), (old, 'NAO_APLICA')]:
            if row['situacao'] == state:
                continue
            _rpc('musica_ministerio_conferir', {'p_evento': EVENT, 'p_pessoa': row['person_key'],
                'p_situacao': state, 'p_observacoes': f'Identidade confirmada pelo usuário: {old["nome"]} corresponde a {target["nome"]}. Mantido o nome e vínculo do cadastro: {target["person_key"]}.',
                'p_version': row['version'], 'p_usuario_id': ACTOR_ID, 'p_usuario_nome': ACTOR})
        if not linked:
            source = {**old['source'], 'canonical_person_key': target['person_key'],
                      'canonical_name': target['nome'], 'identity_confirmed_by': 'usuario',
                      'original_name': old['nome']}
            patch('musica_ministerio_participacoes', {'event_id': f'eq.{EVENT}', 'person_key': f'eq.{old["person_key"]}'}, {'source': source})
            response = requests.post(f'{settings.SUPABASE_URL}/rest/v1/musica_ministerio_auditoria', headers=service_headers(),
                json={'event_id': EVENT, 'person_key': old['person_key'], 'operacao': 'CONCILIAR_IDENTIDADE_CONFIRMADA',
                      'anterior': old, 'posterior': {'source': source, 'canonical_person_key': target['person_key'], 'canonical_name': target['nome']},
                      'usuario_id': ACTOR_ID, 'usuario_nome': ACTOR}, timeout=25)
            response.raise_for_status()
        # Mantém o registro e a grafia de origem; retira apenas a identidade duplicada do público ativo.
        patch('musica_ministerio_pessoas', {'person_key': f'eq.{old["person_key"]}'}, {'roles': []})
        return target['person_key']
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(reconcile, selected))
    print(json.dumps({'identidades_conciliadas': len(results)}), flush=True)
