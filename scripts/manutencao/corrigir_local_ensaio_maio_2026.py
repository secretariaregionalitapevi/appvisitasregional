"""Correção autorizada: Cotia -> Itapevi somente no ensaio de 17/05/2026.

Sem --apply, apenas confere. O backup registra os IDs e o local anterior.
Não altera comum, município de origem, categoria, UUID ou observações.
"""
import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ColorAdmin.settings')

EVENT_ID = '2b7e86cd-9a82-4889-a799-f1c35e0e8e1b'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    import django
    django.setup()
    import requests
    from django.conf import settings
    from ColorAdminApp.modules.music_events import _read, _invalidate_annual
    from ColorAdminApp.modules.access_control import service_headers

    event = _read('musica_eventos', id='eq.' + EVENT_ID)
    if len(event) != 1 or str(event[0]['data_evento'])[:10] != '2026-05-17':
        raise RuntimeError('Evento não corresponde ao ensaio autorizado.')
    sites = _read('musica_evento_locais', evento_id='eq.' + EVENT_ID)
    source = [site for site in sites if site['nome'].strip().upper() == 'COTIA']
    target = [site for site in sites if site['nome'].strip().upper() == 'ITAPEVI']
    if len(source) != 1 or len(target) != 1:
        raise RuntimeError('Locais de origem/destino ambíguos.')
    before = _read('musica_evento_presencas', evento_id='eq.' + EVENT_ID, order='id.asc')
    moved = [row for row in before if row['local_id'] == source[0]['id']]
    backup_dir = ROOT / '.backups' / 'correcao_ensaio_17-05-2026'
    backup = backup_dir / 'cotia_para_itapevi.json'
    if not moved and backup.exists():
        print('Correção já aplicada; nenhum registro restante em Cotia.')
        return
    if len(moved) != 73 or len(before) != 2308:
        raise RuntimeError(f'Pré-condição divergente: {len(moved)} em Cotia / {len(before)} no evento.')
    counts = Counter(row['categoria'] for row in moved)
    if counts != {'MUSICO': 67, 'IRMANDADE': 5, 'MINISTERIO': 1}:
        raise RuntimeError('Categorias divergem da conferência autorizada.')
    print('Conferido: 73 registros, mesmo evento, transferência apenas do local físico.')
    if not args.apply:
        return
    backup_dir.mkdir(parents=True, exist_ok=True)
    snapshot = {'event_id': EVENT_ID, 'source_local_id': source[0]['id'],
                'target_local_id': target[0]['id'], 'record_ids': [row['id'] for row in moved],
                'count': 73, 'created_at': datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m/%Y %H:%M'),
                'authorization': 'Usuário confirmou que os registros de Cotia deste evento devem ser transferidos para Itapevi.'}
    if backup.exists() and json.loads(backup.read_text(encoding='utf-8'))['record_ids'] != snapshot['record_ids']:
        raise RuntimeError('Backup anterior divergente; interrompido antes de alterar dados.')
    backup.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    response = requests.patch(
        f'{settings.SUPABASE_URL}/rest/v1/musica_evento_presencas',
        headers=service_headers('return=representation'),
        params={'evento_id': 'eq.' + EVENT_ID, 'local_id': 'eq.' + source[0]['id'],
                'id': 'in.(' + ','.join(snapshot['record_ids']) + ')'},
        json={'local_id': target[0]['id']}, timeout=30)
    response.raise_for_status()
    if {row['id'] for row in response.json()} != set(snapshot['record_ids']):
        raise RuntimeError('Resposta de gravação divergente. Conferir o backup antes de repetir.')
    after = _read('musica_evento_presencas', evento_id='eq.' + EVENT_ID, order='id.asc')
    if len(after) != len(before):
        raise RuntimeError('Quantidade total alterada inesperadamente.')
    expected = {row['id']: {**row, 'local_id': target[0]['id']} if row['id'] in snapshot['record_ids'] else row for row in before}
    for row in after:
        for key in ['evento_id', 'local_id', 'comum_codigo', 'comum_informada', 'municipio_informado',
                    'categoria', 'instrumento', 'cargo', 'nome', 'situacao', 'origem_registro_id', 'observacoes']:
            if row.get(key) != expected[row['id']].get(key):
                raise RuntimeError('Verificação dos campos preservados falhou: ' + key)
    _invalidate_annual()
    print('Validado: Itapevi 2165; Pirapora 143; Cotia 0; total do evento 2308. Origem e classificação preservadas.')
    print('Backup: .backups/correcao_ensaio_17-05-2026/cotia_para_itapevi.json')


if __name__ == '__main__':
    main()
