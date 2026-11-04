"""Busca por todas as palavras, sem exigir sobrenomes consecutivos."""
from .access_control import _norm

FIELDS = ('nome_aluno', 'comum_congregacao', 'municipio', 'instrumento', 'nivel')


def terms(query):
    clean = ''.join(c if c.isalnum() or c == '-' else ' ' for c in str(query or ''))[:80]
    return list(dict.fromkeys(clean.split()))


def variants(term):
    if _norm(term) in {'SOUSA', 'SOUZA'}:
        return ('SOUSA', 'SOUZA')
    return (term,)


def database_filter(query):
    return '(' + ','.join('or(' + ','.join(
        f'{field}.ilike.*{value}*' for field in FIELDS for value in variants(term)) + ')'
        for term in terms(query)) + ')'


def matches(row, query):
    text = _norm(' '.join(str(row.get(field) or '') for field in FIELDS))
    return all(any(_norm(value) in text for value in variants(term)) for term in terms(query))
