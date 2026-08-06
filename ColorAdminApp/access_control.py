"""Escopo regional para as APIs de Visitas.

O servidor usa service_role para falar com o Supabase; por isso toda autorizacao
precisa ocorrer antes de devolver ou alterar qualquer linha.
"""
import unicodedata
from functools import lru_cache

import requests
from django.conf import settings


def _norm(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).upper().split())


def service_headers(prefer=None):
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


@lru_cache(maxsize=1)
def common_catalog():
    response = requests.get(
        f"{settings.SUPABASE_URL}/rest/v1/visitas_comuns",
        headers=service_headers(),
        params={"select": "comum,cidade", "order": "comum.asc"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def user_scope(request):
    profile = request.session.get("user_profile") or {}
    role_id = int(profile.get("role_id") or 99)
    explicit = _norm(profile.get("access_level") or profile.get("nivel_acesso")).lower()
    level = explicit if explicit in {"local", "municipal", "regional", "global"} else (
        "global" if role_id == 1 else "regional" if role_id == 2 else "municipal" if role_id == 3 else "local"
    )
    comum = str(profile.get("comum") or "").strip()
    municipio = str(profile.get("municipio") or profile.get("cidade") or "").strip()
    if level in {"local", "municipal"} and not municipio and comum:
        match = next((x for x in common_catalog() if _norm(x.get("comum")) == _norm(comum)), None)
        municipio = str((match or {}).get("cidade") or "").strip()
    return {"level": level, "comum": comum, "municipio": municipio, "profile": profile}


def row_location(row):
    comum = str(row.get("comum") or "").strip()
    municipio = str(row.get("municipio") or row.get("cidade") or "").strip()
    if not municipio and comum:
        match = next((x for x in common_catalog() if _norm(x.get("comum")) == _norm(comum)), None)
        municipio = str((match or {}).get("cidade") or "").strip()
    return municipio, comum


def can_access(scope, row):
    if scope["level"] in {"global", "regional"}:
        return True
    municipio, comum = row_location(row)
    if scope["level"] == "municipal":
        return bool(scope["municipio"] and _norm(municipio) == _norm(scope["municipio"]))
    return bool(scope["comum"] and _norm(comum) == _norm(scope["comum"]))


def filter_rows(scope, rows):
    return [row for row in rows if can_access(scope, row)]


def visible_commons(scope):
    return filter_rows(scope, common_catalog())


def scope_details(scope):
    return {"nivel": scope["level"], "municipio": scope["municipio"], "comum": scope["comum"]}
