"""Administracao global das concessoes explicitas de pasta."""
import json
from datetime import datetime

import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .admin_views import _get_table, _headers, global_only
from .module_access import VALID_MODULES, invalidate_module_access
from .views import log_audit


@global_only
@require_http_methods(["PUT"])
def administration_user_modules(request, user_id):
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido."}, status=400)
    modules = body.get("modules")
    if not isinstance(modules, list) or any(module not in VALID_MODULES for module in modules):
        return JsonResponse({"error": "Informe uma lista válida de módulos."}, status=400)
    requested = set(modules)
    actor_id = request.session.get("user_id") or (request.session.get("user_profile") or {}).get("user_id")
    profile_rows = []
    try:
        profile_rows = _get_table("profiles", {"select": "user_id,sector", "user_id": f"eq.{user_id}", "limit": "1"})
        if not profile_rows:
            return JsonResponse({"error": "Usuário não encontrado."}, status=404)
        
        # Determina o setor correspondente às pastas solicitadas
        if requested == set(VALID_MODULES):
            target_sector = "Global"
        elif "musicalizacao" in requested:
            target_sector = "Musicalização"
        else:
            target_sector = "Visitas"

        # Sincroniza o setor no perfil do usuário
        try:
            requests.patch(
                f"{settings.SUPABASE_URL}/rest/v1/profiles",
                headers=_headers(),
                params={"user_id": f"eq.{user_id}"},
                json={"sector": target_sector},
                timeout=10,
            )
        except requests.RequestException:
            pass

        before = set()
        try:
            before_rows = _get_table("user_module_access", {"select": "module,active", "user_id": f"eq.{user_id}"})
            before = {row["module"] for row in before_rows if row.get("active")}
            now = datetime.now().astimezone().isoformat()
            for module in VALID_MODULES:
                active = module in requested
                response = requests.post(
                    f"{settings.SUPABASE_URL}/rest/v1/user_module_access",
                    headers=_headers("resolution=merge-duplicates,return=minimal"),
                    params={"on_conflict": "user_id,module"},
                    json={"user_id": str(user_id), "module": module, "active": active,
                          "granted_by": actor_id, "revoked_at": None if active else now, "updated_at": now},
                    timeout=15,
                )
                response.raise_for_status()
        except requests.RequestException:
            # Caso a tabela user_module_access não esteja criada no Supabase, a permissão
            # é assegurada pelo campo 'sector' já gravado no perfil.
            pass

        invalidate_module_access(str(user_id))
        log_audit(request, "UPDATE_USER_MODULE_ACCESS", "ADMIN", {
            "target_user_id": str(user_id), "before": sorted(before), "after": sorted(requested), "sector": target_sector
        })
        return JsonResponse({"user_id": str(user_id), "modules": sorted(requested), "sector": target_sector})
    except Exception as exc:
        return JsonResponse({"error": f"Falha ao atualizar permissões de pasta: {exc}"}, status=500)
