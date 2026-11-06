"""Consulta documental atual do GEM, informativa e sem bloquear cartas."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import uuid
import requests
from django.conf import settings
from django.utils import timezone
from .access_control import service_headers
from .sam_program import assess_program

LABELS = {'eligible': 'Documentado', 'pending': 'Requisitos pendentes',
          'review': 'Validação pendente', 'unavailable': 'Consulta indisponível',
          'no_data': 'Sem histórico no GEM', 'unlinked': 'Sem vínculo com o GEM'}
TABLES = {'msa': 'musica_acompanhamento_msa', 'metodo': 'musica_acompanhamento_metodo',
          'hinario': 'musica_acompanhamento_hinario'}

def applicable(row):
    return row.get('tipo') == 'musico' and row.get('modalidade') in {'culto', 'oficializacao'}

def fetch_rows(table, ids, field):
    result = []
    for start in range(0, len(ids), 100):
        batch = ids[start:start + 100]
        offset = 0
        while True:
            response = requests.get(settings.SUPABASE_URL + '/rest/v1/' + table, headers=service_headers(),
                params={'select': '*', field: 'in.(' + ','.join(batch) + ')', 'order': 'id.asc',
                        'limit': 500, 'offset': offset}, timeout=15)
            response.raise_for_status()
            rows = response.json()
            result.extend(rows)
            if len(rows) < 500:
                break
            offset += len(rows)
    return result

def assess_letters(rows):
    output = [dict(row) for row in rows]
    ids = set()
    for row in output:
        if applicable(row):
            try:
                ids.add(str(uuid.UUID(str((row.get('payload') or {}).get('pessoa_id')))))
            except (ValueError, TypeError):
                pass
    students, datasets, failed = {}, {}, False
    if ids:
        try:
            ids = sorted(ids)
            sources = [('students', 'musica_acompanhamento_aluno', 'id')] + [(area, table, 'aluno_id') for area, table in TABLES.items()]
            def fetch(source):
                area, table, field = source
                return area, fetch_rows(table, ids, field)
            with ThreadPoolExecutor(max_workers=4) as executor:
                fetched = dict(executor.map(fetch, sources))
            students = {r['id']: r for r in fetched.pop('students')}
            for area, records in fetched.items():
                grouped = defaultdict(list)
                for record in records:
                    grouped[record['aluno_id']].append(record)
                datasets[area] = grouped
        except (requests.RequestException, ValueError, KeyError):
            failed = True
    checked = timezone.localtime().strftime('%d/%m/%Y %H:%M')
    for row in output:
        row['program_assessment'] = None
        if not applicable(row):
            continue
        identifier = str((row.get('payload') or {}).get('pessoa_id') or '')
        status = 'unavailable' if failed else 'unlinked' if identifier not in students else None
        if status:
            assessment = {'status': status, 'requirements': [], 'summary': LABELS[status]}
        else:
            records = {area: grouped.get(identifier, []) for area, grouped in datasets.items()}
            assessment = assess_program(students[identifier], records, target=row['modalidade'])
            if not any(records.values()):
                assessment.update(status='no_data', summary=LABELS['no_data'])
        assessment.update(label=LABELS[assessment['status']], checked_at=checked,
                          basis='Consulta atual ao GEM; emissão permitida')
        row['program_assessment'] = assessment
    return output

def program_summary(rows):
    # Cada aluno/etapa conta uma vez, mesmo com mais de uma carta/exame.
    unique = {}
    for row in rows:
        assessment = row.get('program_assessment')
        if assessment:
            key = ((row.get('payload') or {}).get('pessoa_id') or row.get('id'), row.get('modalidade'))
            unique[key] = assessment
    counts = {status: sum(a['status'] == status for a in unique.values()) for status in LABELS}
    assessed = sum(counts[k] for k in ('eligible', 'pending', 'review'))
    return {'total': len(unique), 'assessed': assessed, 'counts': counts,
            'pending_percent': round(counts['pending'] * 100 / assessed, 1) if assessed else None,
            'unconfirmed_percent': round((counts['pending'] + counts['review']) * 100 / assessed, 1) if assessed else None}
