"""Administracao global das concessoes explicitas de pasta."""
import json
from datetime import datetime

import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .admin_views import _get_table, _headers, _update_profile_via_rpc, global_only
from .module_access import VALID_MODULES, invalidate_module_access, primary_module
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

        if not requested:
            return JsonResponse({'error': 'Selecione ao menos uma pasta autorizada.'}, status=400)
        names = {
            'musicalizacao': 'Musicaliza\u00e7\u00e3o',
            'musica': 'M\u00fasica',
            'darpe': 'D.A.R.P.E',
            'visitas': 'Visitas',
            'gem': 'G.E.M',
        }
        primary = primary_module(profile_rows[0])
        target_sector = ('Global' if requested == set(VALID_MODULES) else
                         names[primary] if primary in requested else
                         next(names[key] for key in names if key in requested))

        before = set()
        try:
            before_rows = _get_table("user_module_access", {"select": "module,active", "user_id": f"eq.{user_id}"})
            before = {row["module"] for row in before_rows if row.get("active")}
            now = datetime.now().astimezone().isoformat()
            grants = [{"user_id": str(user_id), "module": module, "active": module in requested,
                       "granted_by": actor_id, "revoked_at": None if module in requested else now,
                       "updated_at": now} for module in sorted(requested | before)]
            # Um único comando SQL no PostgREST: ou grava todas as pastas ou nenhuma.
            response = requests.post(
                    f"{settings.SUPABASE_URL}/rest/v1/user_module_access",
                    headers=_headers("resolution=merge-duplicates,return=minimal"),
                    params={"on_conflict": "user_id,module"},
                    json=grants,
                    timeout=15,
                )
            response.raise_for_status()
        except requests.RequestException as exc:
            # Não confirmar sucesso quando as concessões explícitas falharem.
            invalidate_module_access(str(user_id))
            failed_response = getattr(exc, 'response', None)
            if failed_response is not None:
                try:
                    error = failed_response.json()
                except ValueError:
                    error = {}
                if error.get('code') == '23514' and 'user_module_access_module_check' in str(error.get('message', '')):
                    return JsonResponse({"error": "O banco ainda não aceita uma das pastas selecionadas. Aplique scripts/migrations/050_gem_module_access.sql no Supabase e tente salvar novamente. Nenhuma pasta foi alterada nesta tentativa."}, status=503)
            return JsonResponse({"error": "Não foi possível salvar todas as pastas. Aplique as migrações de controle de acesso e revise as permissões do usuário antes de confirmar a liberação."}, status=503)

        _update_profile_via_rpc(user_id, {"sector": target_sector})
        invalidate_module_access(str(user_id))
        log_audit(request, "UPDATE_USER_MODULE_ACCESS", "ADMIN", {
            "target_user_id": str(user_id), "before": sorted(before), "after": sorted(requested), "sector": target_sector
        })
        return JsonResponse({"user_id": str(user_id), "modules": sorted(requested), "sector": target_sector})
    except Exception as exc:
        return JsonResponse({"error": f"Falha ao atualizar permissões de pasta: {exc}"}, status=500)
