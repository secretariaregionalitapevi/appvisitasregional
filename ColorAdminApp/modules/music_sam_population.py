"""Canonical musical population from the current SAM source catalog."""
from .music_events_import import norm
from .music_events_dashboard import REGIONAL, code, regional_city
from .music_events_identity import CommonResolver


def musical_category(role, instrument=''):
    value=norm(role)
    if value.startswith(('ORGANISTA','INSTRUTORA','EXAMINADORA DE ORGANISTAS')):
        return 'ORGANISTA'
    if value.startswith(('MUSICO','MUSICISTA','INSTRUTOR','ENCARREGADO LOCAL','ENCARREGADO REGIONAL','SECRETARIO DO GEM')):
        return 'MUSICO'
    # Compatibility for earlier datasets without ministry, never for an explicit administrative role.
    if not value:
        instrument=norm(instrument)
        return 'ORGANISTA' if instrument=='ORGAO' else 'MUSICO' if instrument not in {'','A DEFINIR'} else None
    return None


def current_sam_people(states, registry, catalog):
    """Use SAM membership, not local pedagogical activity or historical mirror rows."""
    local={str(row.get('id')):row for row in registry}
    resolver=CommonResolver(catalog)
    result=[];seen=set()
    for state in states:
        key=str(state.get('source_key') or '')
        if not key or key in seen or state.get('missing_since'):
            continue
        seen.add(key)
        payload=state.get('source_payload') or {}
        linked=local.get(str(state.get('aluno_id')), {})
        common=payload.get('resolved_common') or state.get('source_common') or ''
        city=payload.get('city') or payload.get('source_city') or linked.get('municipio') or ''
        canonical=resolver.resolve(common,city)
        if not canonical and not city:
            matches={code(match['comum']):match for candidate in REGIONAL
                     if (match:=resolver.resolve(common,candidate))}
            if len(matches)==1:
                canonical=next(iter(matches.values()))
            else:
                named=[candidate for candidate in REGIONAL if norm(candidate) in norm(common)]
                if len(named)==1:city=named[0]
        if canonical:
            common,city=canonical['comum'],canonical['cidade']
        result.append(dict(id='sam:'+key,local_student_id=state.get('aluno_id'),
                           comum_congregacao=common,municipio=regional_city(city),
                           instrumento=state.get('source_instrument') or payload.get('instrument') or '',
                           nivel=state.get('source_level') or payload.get('level') or '',
                           cargo_ministerio=payload.get('ministry') or linked.get('cargo_ministerio') or '',
                           status='SAM_ATUAL',updated_at=state.get('last_seen_at')))
    return result
