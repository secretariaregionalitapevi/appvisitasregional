"""Resolve concordant identities before using the older membership directory."""
from collections import defaultdict
from .music_events_import import norm


def current_members(registry, members):
    """SAM wins for a unique name in the same city; homonyms stay unresolved."""
    by_name = defaultdict(list)
    for row in registry:
        by_name[norm(row.get('nome_aluno'))].append(row)
    for member in members:
        matches = by_name.get(norm(member.get('nome')), [])
        if len(matches) == 1 and norm(matches[0].get('municipio')) == norm(member.get('cidade')):
            sam = matches[0]
            yield {**member, 'cargo_outros': sam.get('cargo_ministerio'),
                   'comum': sam.get('comum_congregacao'), 'codigo_comum': None,
                   'cidade': sam.get('municipio'), 'status': sam.get('status')}
        else:
            yield member
