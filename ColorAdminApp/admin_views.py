import json
from functools import wraps

import requests
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .access_control import common_catalog
from .views import log_audit


ROLE_NAMES = {1: "Master", 2: "Admin", 3: "Coordenador", 4: "Instrutor"}
ALLOWED_PROFILE_FIELDS = {
    "full_name", "username", "status", "role_id", "sector", "cargo", "comum",
    "municipio", "cidade", "cadastro_origem", "cadastro_origem_label",
    "cadastro_origem_rota", "cadastro_origem_setor_sugerido",
}


def _is_global(request):
    profile = request.session.get("user_profile") or {}
    try:
        if int(profile.get("role_id") or 99) == 1:
            return True
    except (TypeError, ValueError):
        pass
    return str(profile.get("role") or "").strip().upper() in {"MASTER", "GLOBAL"}


def global_only(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not _is_global(request):
            if request.path.startswith("/administracao/api/"):
                return JsonResponse({"error": "Acesso exclusivo para administradores globais."}, status=403)
            return redirect("/dashboard/v3")
        return view(request, *args, **kwargs)
    return wrapped


def _headers(prefer=None):
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _get_table(table, params):
    response = requests.get(
        f"{settings.SUPABASE_URL}/rest/v1/{table}", headers=_headers(), params=params, timeout=15
    )
    response.raise_for_status()
    return response.json()


@global_only
def administration(request):
    log_audit(request, "VIEW_ADMINISTRATION", "ADMIN", {"section": "user_management"})
    return render(request, "pages/administracao.html")


@global_only
@require_http_methods(["GET"])
def administration_data(request):
    try:
        profiles = _get_table("profiles", {"select": "*", "order": "created_at.desc"})
        logs = _get_table("audit_logs", {"select": "*", "order": "created_at.desc", "limit": "500"})
        sessions = _get_table("audit_access_sessions", {"select": "*", "order": "started_at.desc", "limit": "500"})
        levels = _get_table("access_levels", {"select": "*", "order": "level_order.asc"})
        return JsonResponse({"profiles": profiles, "logs": logs, "sessions": sessions, "access_levels": levels})
    except requests.RequestException as exc:
        return JsonResponse({"error": "Falha ao consultar os dados administrativos.", "details": str(exc)}, status=502)


@global_only
@require_http_methods(["PATCH", "DELETE"])
def administration_user(request, user_id):
    if request.method == "DELETE":
        current_user_id = str(
            request.session.get("user_id")
            or (request.session.get("user_profile") or {}).get("user_id")
            or ""
        )
        if current_user_id == str(user_id):
            return JsonResponse({"error": "Você não pode excluir a própria conta enquanto está conectado."}, status=400)
        try:
            before = _get_table("profiles", {"select": "*", "user_id": f"eq.{user_id}", "limit": "1"})
            if not before:
                return JsonResponse({"error": "Usuário não encontrado."}, status=404)
            revoke_response = requests.patch(
                f"{settings.SUPABASE_URL}/rest/v1/profiles",
                headers=_headers(), params={"user_id": f"eq.{user_id}"},
                json={"status": "rejected"}, timeout=15,
            )
            if revoke_response.status_code not in {200, 204}:
                return JsonResponse({
                    "error": "Não foi possível revogar o acesso antes da exclusão.",
                    "details": revoke_response.text,
                }, status=502)
            auth_response = requests.delete(
                f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}",
                headers=_headers(), timeout=15,
            )
            if auth_response.status_code not in {200, 204}:
                return JsonResponse({
                    "error": "Não foi possível excluir a conta de autenticação.",
                    "details": auth_response.text,
                }, status=502)
            # Mantém compatibilidade com bancos onde o perfil não usa CASCADE.
            profile_response = requests.delete(
                f"{settings.SUPABASE_URL}/rest/v1/profiles",
                headers=_headers(), params={"user_id": f"eq.{user_id}"}, timeout=15,
            )
            if profile_response.status_code not in {200, 204}:
                return JsonResponse({
                    "error": "A conta foi removida, mas o perfil residual não pôde ser apagado.",
                    "details": profile_response.text,
                }, status=502)
            log_audit(request, "DELETE_USER", "ADMIN", {
                "target_user_id": str(user_id), "deleted_profile": before[0],
            })
            return JsonResponse({"status": "deleted", "message": "Usuário excluído com sucesso."})
        except requests.RequestException as exc:
            return JsonResponse({"error": "Falha ao excluir o usuário.", "details": str(exc)}, status=502)

    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido."}, status=400)
    changes = {key: value for key, value in body.items() if key in ALLOWED_PROFILE_FIELDS}
    if not changes:
        return JsonResponse({"error": "Nenhuma alteração permitida foi enviada."}, status=400)
    if "role_id" in changes:
        try:
            changes["role_id"] = int(changes["role_id"])
        except (TypeError, ValueError):
            return JsonResponse({"error": "Nível de acesso inválido."}, status=400)
        if changes["role_id"] not in ROLE_NAMES:
            return JsonResponse({"error": "Nível de acesso fora do padrão deste projeto."}, status=400)
        changes["role"] = ROLE_NAMES[changes["role_id"]]
        changes["sector"] = "Global" if changes["role_id"] == 1 else "Visitas"
    if "status" in changes and changes["status"] not in {"pending", "approved", "rejected"}:
        return JsonResponse({"error": "Status inválido."}, status=400)
    try:
        before = _get_table("profiles", {"select": "*", "user_id": f"eq.{user_id}", "limit": "1"})
        if not before:
            return JsonResponse({"error": "Usuário não encontrado."}, status=404)
        candidate = {**before[0], **changes}
        candidate_role = int(candidate.get("role_id") or 4)
        if candidate_role == 4:
            candidate_common = str(candidate.get("comum") or "").strip()
            common_row = next(
                (item for item in common_catalog() if str(item.get("comum") or "").strip() == candidate_common),
                None,
            )
            if not common_row:
                return JsonResponse({
                    "error": "Para aprovar um acesso local, selecione uma comum válida."
                }, status=400)
            municipality = str(common_row.get("cidade") or "").strip()
            changes.update({"comum": candidate_common, "municipio": municipality, "cidade": municipality})
        response = requests.patch(
            f"{settings.SUPABASE_URL}/rest/v1/profiles", headers=_headers("return=representation"),
            params={"user_id": f"eq.{user_id}"}, json=changes, timeout=15,
        )
        response.raise_for_status()
        updated = response.json()[0]
        log_audit(request, "UPDATE_USER_ACCESS", "ADMIN", {
            "target_user_id": user_id, "before": before[0], "changes": changes,
        })
        return JsonResponse(updated)
    except requests.RequestException as exc:
        return JsonResponse({"error": "Falha ao atualizar o usuário.", "details": str(exc)}, status=502)
