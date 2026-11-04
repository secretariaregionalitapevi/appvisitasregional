"""Vigência comprovada, sem transformar a data de captura em data de promoção."""
from collections import defaultdict
from datetime import datetime, time
from zoneinfo import ZoneInfo

FIELDS = {'cargo_ministerio', 'comum_congregacao', 'municipio', 'nivel',
          'data_inicio_gem', 'status', 'instrumento'}
LOCAL = ZoneInfo('America/Sao_Paulo')


def instant(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return result.replace(tzinfo=LOCAL) if result.tzinfo is None else result


def state_at(current, transitions, day):
    cutoff = datetime.combine(instant(str(day)[:10]).date(), time.max, LOCAL)
    result, unknown = dict(current), []
    grouped = defaultdict(list)
    for row in transitions:
        grouped[row['campo']].append(row)
    for field in FIELDS:
        rows = sorted(grouped[field], key=lambda r: (instant(r['effective_at']), str(r.get('id', ''))))
        proven = [r for r in rows if r['date_basis'] in {'sam', 'manual'}]
        # A later source capture of an already documented transition adds no new boundary.
        rows = [r for r in rows if r['date_basis'] != 'detected_at_sync' or not any(
            p['anterior'] == r['anterior'] and p['posterior'] == r['posterior']
            and instant(p['effective_at']) <= instant(r['effective_at'])
            and not any(instant(p['effective_at']) < instant(other['effective_at']) < instant(r['effective_at'])
                        and other['posterior'] != r['posterior'] for other in rows)
            for p in proven)]
        before = [r for r in rows if instant(r['effective_at']) <= cutoff]
        after = [r for r in rows if instant(r['effective_at']) > cutoff]
        if before:
            result[field] = before[-1]['posterior']
        elif after and after[0]['date_basis'] in {'sam', 'manual'}:
            result[field] = after[0]['anterior']
        else:
            # No dated evidence for the old role/location: require a nominal snapshot.
            result[field] = None
            unknown.append(field)
    result['_unknown'] = unknown
    return result


def temporal_roster(registry, members, catalog, transitions):
    from .music_ministry_domain import roster, roles_of
    current = {str(r['id']): r for r in registry}
    grouped = defaultdict(list)
    for row in transitions:
        grouped[str(row['aluno_id'])].append(row)
    people = roster(registry, members, catalog)
    known = {alias for p in people for alias in p['aliases']}
    for identity, changes in grouped.items():
        source = current.get(identity)
        if not source or f'sam:{identity}' in known:
            continue
        prior = next((r['anterior'] for r in changes if r['campo'] == 'cargo_ministerio' and roles_of(r['anterior'])), None)
        if prior:
            people.extend(roster([{**source, 'cargo_ministerio': prior, 'status': 'Ativo'}], [], catalog))
    for person in people:
        ids = [a.split(':', 1)[1] for a in person['aliases'] if a.startswith('sam:')]
        identity = next((i for i in ids if i in current), None)
        person['temporal'] = True
        person['current_state'] = current.get(identity, {})
        person['transitions'] = grouped.get(identity, [])
        person['roles'] = sorted(set(person['roles']) | {
            role for row in person['transitions'] if row['campo'] == 'cargo_ministerio'
            for value in (row['anterior'], row['posterior']) for role in roles_of(value)})
    return people


def event_state(person, day, snapshot=None):
    from .music_ministry_domain import roles_of
    if not person.get('temporal'):
        return {'roles': person['roles'], 'comum': person['comum'], 'municipio': person['municipio'], 'known': True}
    state = state_at(person.get('current_state', {}), person.get('transitions', []), day)
    result = {'roles': roles_of(state.get('cargo_ministerio')), 'comum': state.get('comum_congregacao'),
              'municipio': state.get('municipio'), 'known': 'cargo_ministerio' not in state['_unknown']}
    if snapshot:
        # Event-specific evidence is immutable even after a later transfer/promotion.
        if snapshot.get('roles') is not None:
            result['roles'], result['known'] = snapshot['roles'], True
        for field in ('comum', 'municipio'):
            result[field] = snapshot.get(field) or result[field]
    result['location_known'] = bool(result['comum'] and result['municipio'])
    return result


def transitions_from_audit(event):
    """Only structured old/new fields qualify; generic student-save text does not."""
    raw = event.get('source_payload') or {}
    before, after = raw.get('before'), raw.get('after')
    refs = event.get('parsed_refs') or {}
    source_key = refs.get('student_id') or refs.get('member_id') or raw.get('student_id')
    if not source_key or not isinstance(before, dict) or not isinstance(after, dict):
        return []
    effective = event.get('occurred_at')
    if not effective:
        return []
    return [{'p_source_key': str(source_key), 'p_campo': field,
             'p_anterior': before[field], 'p_posterior': after[field],
             'p_effective_at': instant(effective).isoformat(),
             'p_source_ref': 'sam-log:' + event['source_fingerprint'],
             'p_evidence': event}
            for field in sorted(FIELDS & before.keys() & after.keys()) if before[field] != after[field]]
