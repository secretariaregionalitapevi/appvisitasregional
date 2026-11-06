"""Situação operacional do SAM e pendência interna, separadas do resultado do exame."""
import uuid
import requests
from django.conf import settings
from django.utils import timezone
from .access_control import service_headers

def pending_activity(activity):
    return bool(activity and activity.get('pending'))

def current_activity(source):
    days = source.get('inactive_days')
    exclude = bool(source.get('requires_review')) or (days is not None and days > 365)
    pending = exclude or source.get('operational_status') == 'INATIVO' or (days is not None and days > 180)
    return {'status': 'EXCLUIR' if exclude else 'INATIVO' if pending else source.get('operational_status'),
            'pending': pending, 'requires_review': exclude, 'inactive_days': days,
            'last_activity_at': source.get('last_activity_at'), 'source': 'GEM/SAM',
            'checked_at': timezone.now().isoformat(), 'basis': 'Consulta atual; sem situação registrada na emissão'}

def fetch_current(ids):
    result = {}
    for start in range(0, len(ids), 100):
        offset = 0
        while True:
            response = requests.get(settings.SUPABASE_URL + '/rest/v1/sam_mirror_student_status', headers=service_headers(),
                params={'select': 'sync_state_id,aluno_id,operational_status,requires_review,inactive_days,last_activity_at',
                        'aluno_id': 'in.(' + ','.join(ids[start:start + 100]) + ')',
                        'order': 'sync_state_id.asc', 'limit': 500, 'offset': offset}, timeout=15)
            response.raise_for_status()
            batch = response.json()
            result.update({r['aluno_id']: current_activity(r) for r in batch})
            if len(batch) < 500:
                break
            offset += len(batch)
    return result

def annotate_activity(rows):
    output = [dict(r) for r in rows]
    ids = set()
    for row in output:
        payload = row.get('payload') or {}
        if row.get('tipo') == 'musico' and not payload.get('student_activity'):
            try:
                ids.add(str(uuid.UUID(str(payload.get('pessoa_id')))))
            except (ValueError, TypeError):
                pass
    try:
        current = fetch_current(sorted(ids)) if ids else {}
    except (requests.RequestException, ValueError):
        current = {}
    for row in output:
        payload = row.get('payload') or {}
        row['student_activity'] = None
        row['activity_review'] = None
        if row.get('tipo') != 'musico':
            continue
        activity = payload.get('student_activity') or current.get(str(payload.get('pessoa_id')))
        row['student_activity'] = activity
        review = payload.get('activity_review')
        if not review and pending_activity(activity):
            review = {'status': 'pending', 'channel': 'internal', 'basis': activity.get('basis'),
                      'recipients': [{'label': 'Ancião da música'},
                          {'label': 'Encarregado regional que atende', 'name': ((row.get('ministry_snapshot') or {}).get('regional') or {}).get('nome')},
                          {'label': 'Secretário da regional'}]}
        row['activity_review'] = review
    return output

def activity_report_note(row):
    payload = row.get('payload') or {}
    activity = row.get('student_activity') or payload.get('student_activity')
    review = row.get('activity_review') or payload.get('activity_review')
    if not activity:
        return ''
    status = str(activity.get('status') or 'Não informado')
    if not activity.get('pending'):
        return ''
    basis = activity.get('basis') or 'Situação registrada na emissão'
    notification = 'Alerta interno: ancião da música, encarregado regional e secretário da regional'
    pending = 'PENDENTE DE ANÁLISE REGIONAL' if not review or review.get('status') == 'pending' else str(review.get('status'))
    last = str(activity.get('last_activity_at') or '')[:10]
    last = '/'.join(reversed(last.split('-'))) if len(last) == 10 else 'Não informado'
    return f'{pending} · GEM/SAM: {status} · Último lançamento: {last} · {basis} · {notification}'
