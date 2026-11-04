"""Indicador DARPE no GEM, sem expor os dados pessoais do cadastro DARPE."""
from collections import Counter

import requests
from django.core.cache import cache
from .access_control import _norm, common_catalog
from .music_events_identity import CommonResolver

CACHE_KEY = 'gem:darpe-membership:v1'


def read_members():
    from .darpe import RESOURCES, _read_all_rows
    rows = cache.get(CACHE_KEY)
    if rows is None:
        base = 'id,nome_completo,comum_congregacao,cidade,status,darpe_musico_organista'
        try:
            rows = _read_all_rows(RESOURCES['cadastros'], select=base + ',darpe_musico,darpe_organista')
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 400 or not any(
                field in exc.response.text for field in ('darpe_musico', 'darpe_organista')):
                raise
            rows = _read_all_rows(RESOURCES['cadastros'], select=base)
        cache.set(CACHE_KEY, rows, 60)
    return rows


def attach_membership(students, members, catalog):
    from .darpe import _resolve_import_common
    from .darpe_sam import CONFIRMED_NAMES
    resolver = CommonResolver(catalog)

    def key(name, common, city, darpe=False):
        canonical = _resolve_import_common(resolver, common, city)
        if not canonical:
            return None
        identity = (_norm(name).strip(' *'), canonical['comum'].split(' - ', 1)[0])
        return (CONFIRMED_NAMES.get(identity, identity[0]), identity[1]) if darpe else identity

    matches = Counter()
    for row in members:
        if _norm(row.get('status')) != 'ATIVO' or not any(row.get(f) is True for f in (
                'darpe_musico', 'darpe_organista', 'darpe_musico_organista')):
            continue
        identity = key(row.get('nome_completo'), row.get('comum_congregacao'), row.get('cidade'), True)
        if identity:
            matches[identity] += 1
    keys = [key(r.get('nome_aluno'), r.get('comum_congregacao'), r.get('municipio')) for r in students]
    counts = Counter(k for k in keys if k)
    for row, identity in zip(students, keys):
        row['darpe_cadastrado'] = bool(identity and matches[identity] == 1 and counts[identity] == 1)
    return students


def enrich(students):
    if not students:
        return True
    try:
        attach_membership(students, read_members(), common_catalog())
        return True
    except requests.RequestException:
        for row in students:
            row['darpe_cadastrado'] = None
        return False
