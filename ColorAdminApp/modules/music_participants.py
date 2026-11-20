"""Diretório musical compartilhado; mantém secretarias e instrução além do cargo SAM."""
from django.conf import settings
from django.core.cache import cache


def member_directory():
    key = 'music:participant-directory:v1'
    rows = cache.get(key)
    if rows is None:
        from .music_events import _read
        rows = _read(settings.SUPABASE_TABLE_VISITAS_IRMANDADE,
                     select='id,nome,cargo_outros,codigo_comum,comum,cidade,status',
                     **{'or': '(cargo_outros.ilike.*encarregado*,cargo_outros.ilike.*examinad*,cargo_outros.ilike.*secret*,cargo_outros.ilike.*instrut*,cargo_outros.ilike.*ancião*,cargo_outros.ilike.*anciao*,cargo_outros.ilike.*cooperador*)'},
                     order='id.asc')
        cache.set(key, rows, 120)
    return rows
