"""Autoriza pastas funcionais sem confundir permissao com escopo territorial."""
import unicodedata
import requests
from django.conf import settings
from django.core.cache import cache

MODULE_VISITAS = "visitas"
MODULE_MUSICALIZACAO = "musicalizacao"
VALID_MODULES = {MODULE_VISITAS, MODULE_MUSICALIZACAO}

def _norm(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).strip().lower()

def is_global(profile):
    try:
        if int(profile.get("role_id") or 99) == 1:
            return True
    except (TypeError, ValueError):
        pass
    return _norm(profile.get("role")) in {"master", "global"}

def primary_module(profile):
    sector = _norm(profile.get("sector") or profile.get("setor") or profile.get("cadastro_origem_setor_sugerido"))
    if sector == "musicalizacao":
        return MODULE_MUSICALIZACAO
    if sector == "visitas":
        return MODULE_VISITAS
    return None

def explicit_modules(user_id):
    if not user_id:
        return set()
    key = f"user-module-access:{user_id}"
    cached = cache.get(key)
    if cached is not None:
        return set(cached)
    try:
        response = requests.get(
            f"{settings.SUPABASE_URL}/rest/v1/user_module_access",
            headers={"apikey": settings.SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}"},
            params={"user_id": f"eq.{user_id}", "active": "eq.true", "select": "module"}, timeout=5,
        )
        response.raise_for_status()
        modules = {row.get("module") for row in response.json()} & VALID_MODULES
        cache.set(key, sorted(modules), 60)
        return modules
    except (requests.RequestException, ValueError):
        return set()  # Falha fechada: nunca concede uma pasta adicional.

def invalidate_module_access(user_id):
    cache.delete(f"user-module-access:{user_id}")

def allowed_modules(request):
    profile = request.session.get("user_profile") or {}
    if is_global(profile):
        return set(VALID_MODULES)
    primary = primary_module(profile)
    user_id = request.session.get("user_id") or profile.get("user_id")
    return ({primary} if primary else set()) | explicit_modules(user_id)

def can_access_module(request, module):
    return module in VALID_MODULES and module in allowed_modules(request)
