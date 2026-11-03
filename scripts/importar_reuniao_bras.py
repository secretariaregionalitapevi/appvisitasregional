"""Importação assistida da lista enviada, pela mesma transação utilizada na página.

Executar pelo shell Django. Sem --confirmar, apenas apresenta a conferência.
"""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from pathlib import Path

from django.core.cache import cache

from ColorAdminApp.modules.music_events_dashboard import REGIONAL
from ColorAdminApp.modules.music_ministry import _sources, _rpc
from ColorAdminApp.modules.music_ministry_domain import (parse_meeting, roster, include_directory,
                                                       match_person, event_payload)


def prepare(path):
    sources = _sources(2026, True)
    if not sources['available']:
        raise ValueError('A migração 036 precisa estar aplicada.')
    parsed = parse_meeting(Path(path).read_bytes(), sources['catalog'])
    if parsed['suggested_date'] != '2026-10-06':
        raise ValueError('A lista deve identificar o encontro de 06/10/2026.')
    if parsed['count'] != 113 or any(r['situacao'] != 'PRESENTE' for r in parsed['records']):
        raise ValueError('A lista diverge dos 113 presentes conferidos no arquivo enviado.')
    if parsed['duplicate_rows'] or any(not r['common_resolved'] for r in parsed['records']):
        raise ValueError('Confira duplicidades e comuns antes de gravar.')
    people = include_directory(roster(sources['registry'], sources['members'], sources['catalog']), sources['directory'])
    mappings, matches = [], Counter()
    for row in parsed['records']:
        candidates = match_person(row, people)
        matches[len(candidates)] += 1
        if len(candidates) > 1:
            raise ValueError(f'Linha {row["row"]}: identidade ambígua; exige conferência individual.')
        mappings.append({'row': row['row'], 'key': candidates[0]['key'] if candidates else row['source_key']})
    raw = {'titulo': 'Reunião do Ministério da Música - Brás', 'tipo': 'REUNIAO_MINISTERIO',
           'data_evento': '2026-10-06', 'modalidade': 'PRESENCIAL', 'local': 'Brás', 'familia': 'GERAL',
           'municipios': list(REGIONAL), 'cargos': sorted({role for r in parsed['records'] for role in r['roles']}),
           'lista_completa': False}
    payload = event_payload(raw, people, parsed['records'], mappings)
    summary = {'data': '06/10/2026', 'presentes': parsed['count'],
               'vinculos_existentes': matches[1], 'identidades_proprias': matches[0],
               'por_cargo': dict(Counter(role for r in parsed['records'] for role in r['roles'])),
               'situacoes': dict(Counter(r['situacao'] for r in payload['registros'])),
               'ausencias_automaticas': sum(r['situacao'] == 'SEM_REGISTRO' for r in payload['registros'])}
    return parsed, payload, summary


def apply_local_absences(event_id):
    """Aplica a regra confirmada pelo usuário aos vínculos individuais já importados."""
    from ColorAdminApp.modules.music_events import _read
    entries = _read('musica_ministerio_participacoes', event_id=f'eq.{event_id}', order='person_key.asc')
    source = _sources(2026, True)
    people = roster(source['registry'], source['members'], source['catalog'])
    registered = {alias for p in people if 'ENCARREGADO_LOCAL' in p['roles'] for alias in p['aliases']}
    missing = [r for r in entries if r['person_key'] in registered and 'ENCARREGADO_LOCAL' in r['roles']
               and r['situacao'] == 'CONFERIR']
    print(json.dumps({'encarregados_ausentes_a_conferir': len(missing)}), flush=True)
    def update(row):
        return _rpc('musica_ministerio_conferir', {'p_evento': event_id, 'p_pessoa': row['person_key'],
            'p_situacao': 'SEM_REGISTRO',
            'p_observacoes': 'Não consta na lista nominal de presentes de 06/10/2026. Regra de ausência confirmada pelo usuário para encarregados locais cadastrados.',
            'p_version': row['version'], 'p_usuario_id': 'codex:importacao-assistida',
            'p_usuario_nome': 'Importação assistida solicitada pelo usuário'})
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(update, missing))
    cache.delete('music-ministry:sources:v2:2026')
    print(json.dumps({'ausencias_confirmadas': len(results)}), flush=True)
    return len(results)


def main(arguments=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('arquivo')
    parser.add_argument('--confirmar', action='store_true')
    args = parser.parse_args(arguments)
    parsed, payload, summary = prepare(args.arquivo)
    print(json.dumps(summary, ensure_ascii=True), flush=True)
    if args.confirmar:
        result = _rpc('musica_ministerio_salvar', {'p_evento': payload, 'p_hash': parsed['sha256'],
            'p_arquivo': Path(args.arquivo).name,
            'p_usuario_id': 'codex:importacao-assistida',
            'p_usuario_nome': 'Importação assistida solicitada pelo usuário'})
        cache.delete('music-ministry:sources:v2:2026')
        print(json.dumps(result, ensure_ascii=True), flush=True)
        return result


if __name__ == '__main__':
    main()
