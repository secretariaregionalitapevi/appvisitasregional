from .report_identity import workbook_identity
import json
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from . import congregation_distribution

import requests
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .access_control import common_catalog
from .module_access import VALID_MODULES, invalidate_module_access
from .views import log_audit

logger = logging.getLogger(__name__)


ROLE_NAMES = {1: "Master", 2: "Admin", 3: "Coordenador", 4: "Instrutor"}
class ProfileUpdateConfigurationError(requests.RequestException):
    """Indica que a ponte RPC segura ainda n�o foi instalada no banco."""

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


def _is_administrator(request):
    profile = request.session.get("user_profile") or {}
    try:
        return int(profile.get("role_id") or 99) in {1, 2}
    except (TypeError, ValueError):
        return str(profile.get("role") or "").strip().upper() in {"MASTER", "GLOBAL", "ADMIN"}


def administrative_only(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not _is_administrator(request):
            if "/api/" in request.path:
                return JsonResponse({"error": "Acesso exclusivo para administradores."}, status=403)
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


def _update_profile_direct(user_id, changes):
    """Compatibilidade no backend usando apenas os privilegios do service_role."""
    response = requests.patch(
        f"{settings.SUPABASE_URL}/rest/v1/profiles",
        headers=_headers("return=representation"),
        params={"user_id": f"eq.{user_id}"},
        json=changes,
        timeout=15,
    )
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list) or len(rows) != 1 or str(rows[0].get("user_id")) != str(user_id):
        raise requests.RequestException("O banco nao confirmou a atualizacao do perfil solicitado.")
    return rows[0]


def _update_profile_via_rpc(user_id, changes):
    """Usa a RPC, com compatibilidade para a migracao ausente ou claims antigas."""
    if not user_id or not isinstance(changes, dict) or not changes:
        raise ValueError("Informe o usuario e as alteracoes.")
    if set(changes) - (ALLOWED_PROFILE_FIELDS | {"role"}):
        raise ValueError("Campos de perfil nao permitidos.")
    if "status" in changes and changes["status"] not in {"pending", "approved", "rejected"}:
        raise ValueError("Status invalido.")
    changes = {key: (value.strip() or None) if isinstance(value, str) else value
               for key, value in changes.items()}
    response = requests.post(
        f"{settings.SUPABASE_URL}/rest/v1/rpc/admin_update_user_profile",
        headers=_headers(),
        json={"p_user_id": str(user_id), "p_changes": changes},
        timeout=15,
    )
    if response.status_code >= 400:
        try:
            error = response.json()
        except ValueError:
            error = {}
        if not isinstance(error, dict):
            error = {}
        missing_rpc = response.status_code == 404 and error.get("code") == "PGRST202"
        legacy_claims = (response.status_code == 403 and error.get("code") == "42501"
                         and error.get("message") == "Service role required")
        if missing_rpc or legacy_claims:
            # Nao concede privilegios: o banco continua exigindo a chave de
            # servico do backend e aplicando suas permissoes e triggers.
            logger.warning("RPC administrativa indisponivel; usando acesso service_role do backend.")
            return _update_profile_direct(user_id, changes)
    response.raise_for_status()
    updated = response.json()
    if not isinstance(updated, dict) or str(updated.get("user_id")) != str(user_id):
        raise requests.RequestException("A rotina administrativa nao retornou o perfil solicitado.")
    return updated

@global_only
def audit_center(request):
    profile = request.session.get("user_profile") or {}
    return render(request, "pages/auditoria.html", {"report_user": profile.get("full_name") or profile.get("username") or "Usuário"})


def audit_center_generic(request):
    """Dashboard centralizado de auditoria para todos os módulos."""
    profile = request.session.get("user_profile") or {}
    from .access_control import user_scope
    scope = user_scope(request)
    return render(request, "pages/auditoria_modulos.html", {
        "report_user": profile.get("full_name") or profile.get("username") or "Usuário",
        "scope": scope,
    })


@require_http_methods(["GET"])
def audit_generic_api(request):
    """API genérica para auditoria de múltiplos módulos."""
    from .audit_generic import api_audit_generic

    module = str(request.GET.get('module', '')).lower().strip()
    return api_audit_generic(request, module)


@global_only
@require_http_methods(["GET"])
def administration_data(request):
    try:
        queries = {
            "profiles": ("profiles", {"select": "*", "order": "created_at.desc"}),
            "logs": ("audit_logs", {"select": "*", "order": "created_at.desc", "limit": "1000"}),
            "sessions": ("audit_access_sessions", {"select": "*", "order": "started_at.desc", "limit": "500"}),
            "levels": ("access_levels", {"select": "*", "order": "level_order.asc"}),
            "modules": ("user_module_access", {"select": "user_id,module,active,granted_by,granted_at,revoked_at"}),
        }
        # Consultas independentes: a latencia de rede nao precisa ser somada.
        with ThreadPoolExecutor(max_workers=5) as executor:
            pending = {key: executor.submit(_get_table, table, params)
                       for key, (table, params) in queries.items()}
            profile_rows = pending["profiles"].result()
            profiles = list({str(row.get("user_id")): row for row in profile_rows if row.get("user_id")}.values())
            logs = pending["logs"].result()
            sessions = pending["sessions"].result()
            levels = pending["levels"].result()
            try:
                module_access = pending["modules"].result()
            except requests.RequestException:
                module_access = []
        return JsonResponse({"profiles": profiles, "logs": logs, "sessions": sessions, "access_levels": levels, "module_access": module_access})
    except requests.RequestException as exc:
        logger.exception("Falha ao consultar dados administrativos: %s", exc)
        return JsonResponse({"error": "Falha ao consultar os dados administrativos."}, status=502)


@global_only
@require_http_methods(["GET"])
def export_audit_excel(request):
    logs = _get_table("audit_logs", {"select": "*", "order": "created_at.desc", "limit": "1000"})
    profiles = _get_table("profiles", {"select": "user_id,full_name,username,sector,comum,municipio,cidade"})
    profile_map = {str(row.get("user_id")): row for row in profiles if row.get("user_id")}
    module_filter = str(request.GET.get("module") or "").strip()
    action_filter = str(request.GET.get("action") or "").strip()
    date_from = str(request.GET.get("date_from") or request.GET.get("date") or "").strip()
    date_to = str(request.GET.get("date_to") or request.GET.get("date") or "").strip()
    event_id = str(request.GET.get("event_id") or "").strip()
    search = str(request.GET.get("search") or "").strip().casefold()
    action_labels = {
        "USER_APPROVAL_APPROVED": "Aprovação de acesso", "USER_APPROVAL_REJECTED": "Rejeição de acesso",
        "UPDATE_USER_ACCESS": "Permissões do usuário", "UPDATE_USER_MODULE_ACCESS": "Pastas autorizadas",
        "VIEW_PAGE": "Navegação", "LOGIN": "Login", "LOGOUT": "Logout",
    }
    module_labels = {"ADMIN": "Usuários e acessos", "NAVIGATION": "Navegação", "AUTH": "Autenticação", "AUDITORIA": "Auditoria", "MUSICALIZACAO": "Musicalização"}

    def target(log):
        details = log.get("details") or {}
        snapshot = details.get("target") or {}
        target_id = snapshot.get("user_id") or details.get("target_user_id") or details.get("reviewed_user_id")
        target_profile = profile_map.get(str(target_id), {})
        return target_id, snapshot, target_profile

    def actor_name(log):
        details = log.get("details") or {}
        actor = details.get("actor") or {}
        profile = profile_map.get(str(log.get("user_id")), {})
        return profile.get("full_name") or actor.get("name") or log.get("user_id") or "Sistema"

    def summary(log):
        action = str(log.get("action") or "").upper()
        target_id, snapshot, target_profile = target(log)
        target_name = snapshot.get("name") or target_profile.get("full_name") or target_profile.get("username") or target_id
        if action == "USER_APPROVAL_APPROVED":
            return f"Aprovou o acesso de {target_name or 'usuário não identificado'}."
        if action == "USER_APPROVAL_REJECTED":
            return f"Rejeitou o acesso de {target_name or 'usuário não identificado'}."
        return action_labels.get(action, action.replace("_", " ").title())

    filtered = []
    for log in logs:
        if event_id and str(log.get("id")) != event_id:
            continue
        if module_filter and log.get("module") != module_filter:
            continue
        if action_filter and log.get("action") != action_filter:
            continue
        log_date = str(log.get("created_at") or "")[:10]
        if date_from and log_date < date_from:
            continue
        if date_to and log_date > date_to:
            continue
        haystack = " ".join([str(log.get("action") or ""), str(log.get("module") or ""), actor_name(log), summary(log), json.dumps(log.get("details") or {}, ensure_ascii=False)]).casefold()
        if search and search not in haystack:
            continue
        filtered.append(log)

    profile = request.session.get("user_profile") or {}
    report_user = profile.get("full_name") or profile.get("username") or "Usuário"
    now = datetime.now()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "AUDITORIA"
    headers = ["Data e hora", "Responsável", "Operação", "Módulo", "Usuário analisado", "Decisão", "Setor", "Comum", "IP de origem", "Resumo"]
    last_column = get_column_letter(len(headers))
    navy, pale, thin = "1E4B7A", "EAF2F8", Side(style="thin", color="CCD5DD")
    for row, text, size, color, fill in [
        (1, "CONGREGAÇÃO CRISTÃ NO BRASIL", 15, "FFFFFF", navy),
        (2, "Regional Itapevi - São Paulo", 10, "FFFFFF", navy),
        (3, "ADMINISTRAÇÃO · AUDITORIA E CONTROLE DE ACESSO", 12, navy, pale),
    ]:
        sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=len(headers))
        cell = sheet.cell(row, 1, text); cell.font = Font(size=size, bold=row != 2, color=color); cell.fill = PatternFill("solid", fgColor=fill); cell.alignment = Alignment(horizontal="center")
    sheet.merge_cells("A4:E4"); sheet["A4"] = f"{'Evento individual' if event_id else 'Relatório de auditoria'} · {len(filtered)} evento(s) · Recorte: {module_filter or 'Todos os módulos'}"
    sheet.merge_cells(f"F4:{last_column}4"); sheet["F4"] = f"Emissão: {now:%d/%m/%Y %H:%M} · Responsável: {report_user}"; sheet["F4"].alignment = Alignment(horizontal="right")
    for cell in sheet[4]: cell.font = Font(size=9, bold=True, color="536A7D")
    for column, label in enumerate(headers, 1):
        cell = sheet.cell(6, column, label); cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor=navy); cell.alignment = Alignment(horizontal="center", vertical="center"); cell.border = Border(bottom=thin)
    status_names = {"approved": "Aprovado", "rejected": "Rejeitado", "pending": "Pendente"}
    for row_index, log in enumerate(filtered, 7):
        target_id, snapshot, target_profile = target(log)
        action = str(log.get("action") or "").upper()
        decision = snapshot.get("status_after") or ("approved" if action == "USER_APPROVAL_APPROVED" else "rejected" if action == "USER_APPROVAL_REJECTED" else "")
        created = str(log.get("created_at") or "")
        try: created = datetime.fromisoformat(created.replace("Z", "+00:00")).astimezone().strftime("%d/%m/%Y %H:%M")
        except ValueError: pass
        target_name = snapshot.get("name") or target_profile.get("full_name") or target_profile.get("username") or target_id or "—"
        values = [created, actor_name(log), action_labels.get(action, action.replace("_", " ").title()), module_labels.get(log.get("module"), str(log.get("module") or "Global").replace("_", " ").title()), target_name, status_names.get(decision, decision or "—"), str(snapshot.get("sector") or target_profile.get("sector") or "—").upper(), snapshot.get("common") or target_profile.get("comum") or "—", log.get("ip_address") or "—", summary(log)]
        for column, value in enumerate(values, 1):
            cell = sheet.cell(row_index, column, value); cell.border = Border(bottom=thin); cell.alignment = Alignment(vertical="top", wrap_text=column == 10)
            if row_index % 2 == 0: cell.fill = PatternFill("solid", fgColor="F4F6F8")
    for index, width in enumerate([20, 28, 26, 23, 32, 16, 18, 42, 18, 48], 1): sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A7"; sheet.auto_filter.ref = f"A6:{last_column}{max(6, sheet.max_row)}"; sheet.sheet_view.showGridLines = False
    sheet.page_setup.orientation = "landscape"; sheet.page_setup.fitToWidth = 1; sheet.page_setup.fitToHeight = 0; sheet.sheet_properties.pageSetUpPr.fitToPage = True; sheet.print_title_rows = "1:6"
    stream = io.BytesIO(); workbook_identity(workbook, report_user);workbook.save(stream)
    log_audit(request, "EXPORT", "AUDITORIA", {"format": "xlsx", "row_count": len(filtered), "event_id": event_id or None, "filters": {"module": module_filter or None, "action": action_filter or None, "date_from": date_from or None, "date_to": date_to or None, "search": search or None}, "outcome": "success"})
    response = HttpResponse(stream.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="Relatorio_Auditoria_{now:%d-%m-%Y_%H-%M}.xlsx"'
    return response


@global_only
@require_http_methods(["GET"])
def pending_access_count(request):
    """Retorna somente a quantidade necessária pelo alerta global do cabeçalho."""
    try:
        rows = _get_table("profiles", {"select": "user_id", "status": "eq.pending"})
        unique_user_ids = {str(row.get("user_id")) for row in rows if row.get("user_id")}
        return JsonResponse({"pending_count": len(unique_user_ids)})
    except requests.RequestException as exc:
        logger.exception("Falha ao consultar acessos pendentes: %s", exc)
        return JsonResponse({"error": "Falha ao consultar acessos pendentes."}, status=502)


def _auth_user_email(user_id):
    response = requests.get(
        f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}",
        headers=_headers(), timeout=10,
    )
    response.raise_for_status()
    return response.json().get("email")


def _audit_author(event):
    if not event:
        return None
    details = event.get("details") or {}
    actor = details.get("actor") or {}
    actor_id = actor.get("user_id") or details.get("actor_user_id") or event.get("user_id")
    name = actor.get("name") or details.get("actor_name")
    if not name and actor_id:
        rows = _get_table("profiles", {"select": "full_name,username", "user_id": f"eq.{actor_id}", "limit": "1"})
        if rows:
            name = rows[0].get("full_name") or rows[0].get("username")
    return {"name": name, "user_id": actor_id, "at": event.get("created_at")}


@global_only
@require_http_methods(["GET"])
def administration_user_metadata(request, user_id):
    target = str(user_id)
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            email_job = executor.submit(_auth_user_email, target)
            registration_job = executor.submit(_get_table, "audit_logs", {
                "select": "user_id,created_at,details", "action": "eq.REGISTER",
                "or": f"(details->>user_id.eq.{target},details->>target_user_id.eq.{target})", "order": "created_at.asc", "limit": "1",
            })
            update_job = executor.submit(_get_table, "audit_logs", {
                "select": "user_id,created_at,details",
                "action": "in.(UPDATE_USER_ACCESS,UPDATE_USER_MODULE_ACCESS,USER_APPROVAL_APPROVED,USER_APPROVAL_REJECTED)",
                "or": f"(details->>target_user_id.eq.{target},details->>reviewed_user_id.eq.{target})",
                "order": "created_at.desc", "limit": "1",
            })
            email = email_job.result()
            registrations, updates = registration_job.result(), update_job.result()
        if not registrations and email:
            # Eventos legados identificavam o alvo pelo email. Exige proximidade
            # do horario de criacao e um unico evento, evitando recriacoes ambiguas.
            profiles = _get_table("profiles", {"select": "created_at", "user_id": f"eq.{target}", "limit": "1"})
            if profiles and profiles[0].get("created_at"):
                created = datetime.fromisoformat(profiles[0]["created_at"].replace("Z", "+00:00"))
                legacy = _get_table("audit_logs", {
                    "select": "user_id,created_at,details", "action": "eq.REGISTER",
                    "details->>email": f"eq.{email}",
                    "and": f"(created_at.gte.{(created - timedelta(minutes=5)).isoformat()},created_at.lte.{(created + timedelta(minutes=5)).isoformat()})",
                    "order": "created_at.asc", "limit": "2",
                })
                if len(legacy) == 1:
                    registrations = legacy
        return JsonResponse({
            "email": email,
            "registration": _audit_author(registrations[0]) if registrations else None,
            "last_update": _audit_author(updates[0]) if updates else None,
        })
    except requests.RequestException:
        logger.warning("Falha ao consultar metadados administrativos do usuario %s", target)
        return JsonResponse({"error": "Nao foi possivel consultar email e autoria. Feche e abra o cadastro para tentar novamente."}, status=502)


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
            _update_profile_via_rpc(user_id, {"status": "rejected"})
            auth_response = requests.delete(
                f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}",
                headers=_headers(), timeout=15,
            )
            if auth_response.status_code not in {200, 204}:
                logger.error("Auth user deletion failed with HTTP %s", auth_response.status_code)
                return JsonResponse({"error": "Não foi possível excluir a conta de autenticação."}, status=502)
            # Mantém compatibilidade com bancos onde o perfil não usa CASCADE.
            profile_response = requests.delete(
                f"{settings.SUPABASE_URL}/rest/v1/profiles",
                headers=_headers(), params={"user_id": f"eq.{user_id}"}, timeout=15,
            )
            if profile_response.status_code not in {200, 204}:
                logger.error("Residual profile deletion failed with HTTP %s", profile_response.status_code)
                return JsonResponse({"error": "A conta foi removida, mas o perfil residual não pôde ser apagado."}, status=502)
            log_audit(request, "DELETE_USER", "ADMIN", {
                "target_user_id": str(user_id), "deleted_profile": before[0],
            })
            return JsonResponse({"status": "deleted", "message": "Usuário excluído com sucesso."})
        except requests.RequestException as exc:
            logger.exception("Falha ao excluir usuário %s: %s", user_id, exc)
            return JsonResponse({"error": "Falha ao excluir o usuário."}, status=502)

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
        if changes["role_id"] == 1:
            changes["sector"] = "Global"
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
        previous = before[0]
        updated = _update_profile_via_rpc(user_id, changes)
        previous_status = previous.get("status")
        current_status = updated.get("status") or changes.get("status") or previous_status
        if previous_status == "pending" and current_status == "approved":
            audit_action = "USER_APPROVAL_APPROVED"
        elif previous_status == "pending" and current_status == "rejected":
            audit_action = "USER_APPROVAL_REJECTED"
        else:
            audit_action = "UPDATE_USER_ACCESS"
        changed_fields = {
            key: {"before": previous.get(key), "after": updated.get(key, value)}
            for key, value in changes.items()
            if previous.get(key) != updated.get(key, value)
        }
        log_audit(request, audit_action, "ADMIN", {
            "target_user_id": str(user_id),
            "target": {
                "user_id": str(user_id),
                "name": updated.get("full_name") or updated.get("username") or previous.get("full_name") or previous.get("username"),
                "username": updated.get("username") or previous.get("username"),
                "status_before": previous_status,
                "status_after": current_status,
                "role_id": updated.get("role_id", previous.get("role_id")),
                "role": updated.get("role", previous.get("role")),
                "sector": updated.get("sector", previous.get("sector")),
                "municipality": updated.get("municipio", previous.get("municipio")),
                "common": updated.get("comum", previous.get("comum")),
            },
            "decision": current_status if audit_action.startswith("USER_APPROVAL_") else None,
            "changed_fields": changed_fields,
            "outcome": "success",
        })
        return JsonResponse(updated)
    except ProfileUpdateConfigurationError as exc:
        logger.error("Ponte RPC de atualiza��o ausente para o usu�rio %s: %s", user_id, exc)
        return JsonResponse({"error": str(exc)}, status=503)
    except requests.RequestException as exc:
        logger.exception("Falha ao atualizar usu�rio %s: %s", user_id, exc)
        return JsonResponse({"error": "Falha de comunica��o ao atualizar o usu�rio. Tente novamente em instantes."}, status=502)
OPERATIONAL_CONFIG = {
    "ministerio": {
        "table": "ministerio_regional",
        "required": {"nome", "ministerio", "comum", "municipio"},
        "fields": {"nome", "data_apresentacao", "data_ordenacao", "ministerio", "comum", "municipio", "administracao", "rrm", "aprovador_rrm", "cadastro_completo", "status", "possui_foto", "sexo", "observacoes"},
        "order": "nome.asc",
        "module": "MINISTERIO_REGIONAL",
    },
    "santa-ceia": {
        "table": "santa_ceia_eventos",
        "required": {"data_evento", "municipio", "comum"},
        "fields": {"data_evento", "municipio", "comum", "atendimento", "hora", "palavra", "oracao_pao", "oracao_calice", "diaconos", "ano_anterior"},
        "order": "data_evento.desc",
        "module": "SANTA_CEIA",
    },
}


def _request_json(request):
    try:
        value = json.loads(request.body or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("JSON invalido.") from exc
    if not isinstance(value, dict):
        raise ValueError("O corpo da requisicao deve ser um objeto.")
    return value


def _audit_changes(before, after, fields):
    return {
        key: {"anterior": (before or {}).get(key), "novo": (after or {}).get(key)}
        for key in fields if (before or {}).get(key) != (after or {}).get(key)
    }


@administrative_only
def administration(request):
    return redirect("/administracao/congregacoes/")


@administrative_only
def operational_page(request, section):
    if section not in {"congregacoes", "ministerio", "santa-ceia"}:
        return redirect("/administracao/congregacoes/")
    labels = {"congregacoes": "Congrega\u00e7\u00f5es", "ministerio": "Minist\u00e9rio", "santa-ceia": "Santa Ceia"}
    return render(request, "pages/administracao_operacional.html", {"section": section, "section_title": labels[section]})


def _catalog_norm(value):
    import unicodedata
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).upper().split())


def _common_code(value):
    import re
    match = re.search(r"\bBR-\d{2}-\d{4}\b", str(value or ""), re.IGNORECASE)
    return match.group(0).upper() if match else ""


def _common_name(value):
    import re
    value = str(value or "").strip()
    return re.sub(r"^BR-\d{2}-\d{4}\s*-\s*", "", value, flags=re.IGNORECASE).strip()


def _person_matches_congregation(person, common_name, common_code, municipality=""):
    person_common = str(person.get("comum") or "").strip()
    person_code = _common_code(person_common)
    if common_code and person_code:
        return common_code == person_code
    expected_name = _catalog_norm(_common_name(common_name))
    actual_name = _catalog_norm(_common_name(person_common))
    if not expected_name or expected_name != actual_name:
        return False
    person_municipality = _catalog_norm(person.get("municipio") or person.get("cidade"))
    expected_municipality = _catalog_norm(municipality)
    return not (person_municipality and expected_municipality) or person_municipality == expected_municipality


MINISTRY_HIERARCHY = (
    ("ANCIAO",),
    ("DIACONO",),
    ("COOPERADOR DO OFICIO", "COOPERADOR OFICIO MINISTERIAL", "COOPERADOR OFICIAL"),
    ("COOPERADOR DE JOVENS", "COOPERADOR DE JOVENS E MENORES"),
    ("ENCARREGADO REGIONAL",),
    ("ENCARREGADO LOCAL",),
    ("EXAMINADORA", "EXAMINADORA DE ORGANISTA", "EXAMINADORA DE ORGANISTAS"),
    ("SECRETARIO DA MUSICA", "SECRETARIO DE MUSICA", "SECRETARIO (A) DA MUSICA", "SECRETARIO(A) DA MUSICA"),
    ("SECRETARIA DA MUSICA", "SECRETARIA DE MUSICA"),
    ("SECRETARIO DO GEM", "SECRETARIO GEM", "SECRETARIA DO GEM", "SECRETARIA GEM"),
)


def _ministry_rank(value):
    normalized = _catalog_norm(value).replace("_", " ")
    for rank, aliases in enumerate(MINISTRY_HIERARCHY):
        if normalized in aliases:
            return rank
    return len(MINISTRY_HIERARCHY)


def _sort_ministry_rows(rows, catalog=None):
    if catalog is not None:
        by_code = {_common_code(common.get("comum")): common for common in catalog}
        resolved_rows = []
        for row in rows:
            common = by_code.get(_common_code(row.get("comum")), {})
            municipality = common.get("cidade") or common.get("municipio")
            resolved_rows.append({**row, "municipio": municipality} if municipality else dict(row))
        rows = resolved_rows
    return sorted(
        rows,
        key=lambda row: (
            _catalog_norm(row.get("municipio")),
            _catalog_norm(row.get("comum")),
            _ministry_rank(row.get("ministerio")),
            _catalog_norm(row.get("ministerio")),
            _catalog_norm(row.get("nome")),
        ),
    )


CONGREGATION_ASSIGNMENT_FIELDS = (
    "encarregados_regionais",
    "examinadoras",
    "secretarios_musica",
    "encarregados_locais",
    "secretarios_gem",
)


def _congregation_assignment_category(role):
    normalized = _catalog_norm(role).replace("_", " ")
    if "ENCARREGADO REGIONAL" in normalized:
        return "encarregados_regionais"
    if "EXAMINADORA" in normalized:
        return "examinadoras"
    if ("SECRETARIO" in normalized or "SECRETARIA" in normalized) and "MUSICA" in normalized:
        return "secretarios_musica"
    if "ENCARREGADO LOCAL" in normalized:
        return "encarregados_locais"
    if ("SECRETARIO" in normalized or "SECRETARIA" in normalized) and "GEM" in normalized:
        return "secretarios_gem"
    return ""


def _congregation_people(sam_registry, catalog, ministry=()):
    """Ministério para os quatro ofícios; SAM para os cargos da Música."""
    import re
    from .sam_catalog import match_local_common

    by_code = {_common_code(row.get("comum")): row for row in catalog}
    people, seen = [], set()
    sources = [("ministerio", {
        "id": row.get("id"), "nome_aluno": row.get("nome"),
        "comum_congregacao": row.get("comum"), "municipio": row.get("municipio"),
        "cargo_ministerio": row.get("ministerio"), "status": row.get("status"),
    }) for row in ministry]
    sources.extend(("sam", row) for row in sam_registry)
    for source, row in sources:
        name = str(row.get("nome_aluno") or "").strip()
        common = congregation_distribution.corrected_common(str(row.get("comum_congregacao") or "").strip())
        code = _common_code(common)
        if not row.get("id") or not name:
            continue
        # Um código desconhecido nunca é substituído por outra comum de mesmo nome.
        resolved = by_code.get(code) if code else match_local_common({
            "common_name": common,
            "city": row.get("municipio"),
        }, catalog)
        if not resolved:
            continue
        canonical_common = resolved["comum"]
        roles = re.split(r"[,;/|]+", str(row.get("cargo_ministerio") or ""))
        for role in roles:
            role = role.strip().replace("_", " ")
            # O SAM usa um cargo genérico para ambos. A indicação de organista
            # é explícita no cadastro; nunca inferir pelo primeiro nome.
            generic_secretary = _catalog_norm(role) in {
                "SECRETARIO (A) DA MUSICA", "SECRETARIO(A) DA MUSICA",
            }
            if generic_secretary:
                organist = (
                    bool(re.search(r"\(\s*ORGANISTA\s*\)", _catalog_norm(name)))
                    or _catalog_norm(row.get("instrumento")) in {"ORGAO", "ORGAN", "ORGANISTA"}
                    or "ORGANISTA" in _catalog_norm(row.get("nivel"))
                )
                role = "Secretária da Música" if organist else "Secretário da Música"
            rank = _ministry_rank(role)
            if rank == len(MINISTRY_HIERARCHY) or (source == "ministerio" and rank > 3):
                continue
            identity_name = _catalog_norm(re.sub(r"\(\s*ORGANISTA\s*\)", "", name, flags=re.IGNORECASE))
            identity = (identity_name, _common_code(canonical_common), rank)
            if identity in seen:
                continue
            seen.add(identity)
            people.append({
                "id": f"{source}:{row['id']}:{rank}",
                "person_key": f"{_common_code(canonical_common)}:{identity_name}",
                "source_id": str(row["id"]),
                "source": source,
                "nome": congregation_distribution.person_display_name(name),
                "ministerio": role,
                "comum": canonical_common,
                "municipio": resolved.get("cidade") or resolved.get("municipio") or "",
                "status": str(row.get("status") or "").strip(),
                "categoria": _congregation_assignment_category(role) or "ministerio",
            })
    return _sort_ministry_rows(people)


def _sam_congregation_registry():
    # PostgREST limita cada resposta: percorrer todas as páginas evita omissões.
    rows = []
    while True:
        batch = _get_table("musica_acompanhamento_aluno", {
            "select": "id,nome_aluno,cargo_ministerio,status,comum_congregacao,municipio,instrumento,nivel",
            "or": "(cargo_ministerio.ilike.*encarregado*,cargo_ministerio.ilike.*examinadora*,cargo_ministerio.ilike.*secret*)",
            "order": "id.asc", "offset": str(len(rows)), "limit": "1000",
        })
        rows.extend(batch)
        if len(batch) < 1000:
            return rows


def _fetch_congregation_people():
    with ThreadPoolExecutor(max_workers=2) as executor:
        registry = executor.submit(_sam_congregation_registry)
        ministry = executor.submit(_get_table, "ministerio_regional", {
            "select": "id,nome,ministerio,comum,municipio,status", "order": "id.asc", "limit": "3000",
        })
        return _congregation_people(registry.result(), congregation_distribution.corrected_catalog(common_catalog()), ministry.result())


def _congregation_data(include_archived=False, include_people=False):
    with ThreadPoolExecutor(max_workers=5) as executor:
        catalog_future = executor.submit(common_catalog)
        distribution_future = executor.submit(congregation_distribution.load_overrides, _get_table)
        registry_future = executor.submit(_sam_congregation_registry)
        ministry_future = executor.submit(_get_table, "ministerio_regional", {
            "select": "id,nome,ministerio,comum,municipio,status", "order": "id.asc", "limit": "3000",
        })
        settings_future = executor.submit(_get_table, "administrative_congregation_settings", {
            "select": "*", "limit": "3000",
        })
        # O catálogo pode trazer mais de uma descrição para o mesmo código BR.
        catalog = list({
            _common_code(row.get("comum")) or _catalog_norm(row.get("comum")): row
            for row in congregation_distribution.corrected_catalog(catalog_future.result())
        }.values())
        people = _congregation_people(registry_future.result(), catalog, ministry_future.result())
        congregation_settings_rows = settings_future.result()
    settings_by_code = {
        str(row.get("congregation_code") or "").upper(): row
        for row in congregation_settings_rows if row.get("congregation_code")
    }
    by_code = {}
    for person in people:
        by_code.setdefault(_common_code(person["comum"]), []).append(person)
    rows = []
    for common in catalog:
        full_name = str(common.get("comum") or common.get("nome") or "").strip()
        code = _common_code(full_name)
        congregation_settings = settings_by_code.get(code, {})
        archived = bool(congregation_settings.get("archived_at"))
        if archived and not include_archived:
            continue
        servants = by_code.get(code, [])
        rows.append({
            "id": common.get("id") or code or full_name,
            "codigo": code,
            "nome": congregation_settings.get("nome") or full_name,
            "nome_comum": _common_name(congregation_settings.get("nome") or full_name),
            "municipio": congregation_settings.get("municipio") or common.get("cidade") or common.get("municipio") or "",
            "administracao": congregation_settings.get("administracao") or "",
            "arquivada": archived,
            "responsaveis_sistema": [p for p in servants if p["categoria"] in CONGREGATION_ASSIGNMENT_FIELDS],
            # Seleções antigas não podem reintroduzir pessoas de outra fonte.
            "distribuicao": {
                field: [p["id"] for p in servants if p["categoria"] == field]
                for field in CONGREGATION_ASSIGNMENT_FIELDS
            },
            "quantidade_servos": len({p["person_key"] for p in servants}),
            "servos": servants,
        })
    rows = sorted(rows, key=lambda row: (_catalog_norm(row["municipio"]), _catalog_norm(row["nome"])))
    overrides, editable = distribution_future.result()
    congregation_distribution.apply(rows, people, overrides, editable)
    for row in rows:
        row["servos"] = _sort_ministry_rows(row["servos"])
    return rows, people if include_people else []


def _congregation_rows(include_archived=False):
    return _congregation_data(include_archived=include_archived)[0]


def _congregation_settings_missing(exc):
    response = getattr(exc, "response", None)
    if response is None:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    return payload.get("code") in {"PGRST205", "PGRST204", "42P01"} and (
        "administrative_congregation_settings" in str(payload)
    )


def _normalize_ministry_dates(row):
    """Move legacy dates to the ordination field without replacing existing dates."""
    row = dict(row)
    if _catalog_norm(row.get("ministerio")) in {"ANCIAO", "DIACONO"}:
        if not row.get("data_ordenacao") and row.get("data_apresentacao"):
            row["data_ordenacao"] = row["data_apresentacao"]
            row["data_apresentacao"] = None
    return row


@administrative_only
@require_http_methods(["GET"])
def operational_data(request, section):
    try:
        if section == "congregacoes":
            rows, people = _congregation_data(include_archived=True, include_people=True)
            catalog = congregation_distribution.corrected_catalog(common_catalog())
            persons = congregation_distribution.directory(people, [{"assignments": [item for row in rows for item in row.get("assignments", [])]}])
            administration_by_code = {_common_code(c["comum"]): congregation_distribution.administration(c.get("cidade") or c.get("municipio")) for c in catalog}
            for row in rows:
                row["administration_id"] = administration_by_code.get(row["codigo"], "")
            return JsonResponse({
                "rows": rows,
                "people": people,
                "assignment_people": list(congregation_distribution.scoped_directory(persons, catalog).values()),
            })
        config = OPERATIONAL_CONFIG.get(section)
        if not config:
            return JsonResponse({"error": "Secao administrativa invalida."}, status=404)
        rows = _get_table(config["table"], {"select": "*", "order": config["order"], "limit": "2000"})
        if section == "ministerio":
            rows = _sort_ministry_rows([_normalize_ministry_dates(row) for row in rows], common_catalog())
        payload = {"rows": rows}
        if section == "santa-ceia":
            payload["counts"] = _get_table("santa_ceia_contagem", {"select": "*", "order": "created_at.desc", "limit": "2000"})
        return JsonResponse(payload)
    except requests.RequestException as exc:
        logger.exception("Falha ao consultar %s: %s", section, exc)
        if section == "congregacoes" and _congregation_settings_missing(exc):
            return JsonResponse({
                "error": "A configuração de Congregações ainda não foi criada no Supabase.",
                "migration": "scripts/migrations/052_administrative_congregation_settings.sql",
            }, status=503)
        return JsonResponse({"error": "Nao foi possivel consultar os dados administrativos."}, status=502)


@administrative_only
@require_http_methods(["POST", "PATCH", "DELETE"])
def operational_record(request, section, record_id=None):
    config = OPERATIONAL_CONFIG.get(section)
    if not config:
        return JsonResponse({"error": "Secao administrativa invalida."}, status=404)
    try:
        before = []
        if record_id:
            before = _get_table(config["table"], {"select": "*", "id": f"eq.{record_id}", "limit": "1"})
            if not before:
                return JsonResponse({"error": "Registro nao encontrado."}, status=404)
        if request.method == "DELETE":
            response = requests.delete(f"{settings.SUPABASE_URL}/rest/v1/{config['table']}", headers=_headers(), params={"id": f"eq.{record_id}"}, timeout=15)
            response.raise_for_status()
            log_audit(request, "DELETE", config["module"], {"entity": config["table"], "entity_id": str(record_id), "before": before[0], "outcome": "success"})
            return JsonResponse({"status": "deleted"})
        body = _request_json(request)
        changes = {key: body.get(key) for key in config["fields"] if key in body}
        if not changes:
            return JsonResponse({"error": "Nenhum campo permitido foi enviado."}, status=400)
        candidate = {**(before[0] if before else {}), **changes}
        missing = [field for field in config.get("required", set()) if not str(candidate.get(field) or "").strip()]
        if missing:
            return JsonResponse({"error": "Preencha os campos obrigatorios: " + ", ".join(sorted(missing)) + "."}, status=400)
        for field in {"data_apresentacao", "data_ordenacao", "data_evento"} & changes.keys():
            value = changes[field]
            if value is None or (isinstance(value, str) and not value.strip()):
                changes[field] = None
            else:
                try:
                    changes[field] = date.fromisoformat(str(value).strip()).isoformat()
                except ValueError:
                    raise ValueError(f"Data invalida no campo {field}. Use AAAA-MM-DD.")
        if "ano_anterior" in changes:
            value = changes["ano_anterior"]
            try:
                changes["ano_anterior"] = None if value is None or str(value).strip() == "" else int(str(value).strip())
            except ValueError:
                raise ValueError("Informe um numero inteiro no campo ano_anterior.")
        for boolean_field in {"cadastro_completo", "possui_foto"} & changes.keys():
            changes[boolean_field] = str(changes[boolean_field]).lower() in {"1", "true", "on", "sim"}
        if section == "ministerio":
            candidate = {**(before[0] if before else {}), **changes}
            normalized = _normalize_ministry_dates(candidate)
            for field in ("data_apresentacao", "data_ordenacao"):
                if normalized.get(field) != candidate.get(field):
                    changes[field] = normalized.get(field)
        actor_id = request.session.get("user_id")
        if section == "ministerio":
            changes["updated_by"] = actor_id
            if request.method == "POST":
                changes["created_by"] = actor_id
        elif section == "santa-ceia":
            changes["user_id"] = actor_id
        url = f"{settings.SUPABASE_URL}/rest/v1/{config['table']}"
        if request.method == "POST":
            response = requests.post(url, headers=_headers("return=representation"), json=changes, timeout=15)
        else:
            response = requests.patch(url, headers=_headers("return=representation"), params={"id": f"eq.{record_id}"}, json=changes, timeout=15)
        response.raise_for_status()
        result = response.json()[0]
        event = "CREATE" if request.method == "POST" else "UPDATE"
        log_audit(request, event, config["module"], {
            "entity": config["table"], "entity_id": str(result.get("id") or record_id),
            "before": before[0] if before else None, "after": result,
            "changes": _audit_changes(before[0] if before else {}, result, config["fields"]), "outcome": "success",
        })
        return JsonResponse(result, status=201 if request.method == "POST" else 200)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except requests.RequestException as exc:
        logger.exception("Falha ao alterar %s: %s", section, exc)
        log_audit(request, "MUTATION_FAILED", config["module"], {"entity": config["table"], "entity_id": str(record_id or ""), "outcome": "failure", "error_type": type(exc).__name__})
        return JsonResponse({"error": "Nao foi possivel concluir a operacao."}, status=502)


@administrative_only
@require_http_methods(["PATCH", "DELETE"])
def congregation_record(request, record_id):
    code = _common_code(record_id)
    if not code or code != str(record_id).upper():
        return JsonResponse({"error": "Código da congregação inválido."}, status=400)

    table = "administrative_congregation_settings"
    try:
        common = next(
            (
                row for row in congregation_distribution.corrected_catalog(common_catalog())
                if _common_code(row.get("comum") or row.get("nome")) == code
            ),
            None,
        )
        if not common:
            return JsonResponse({"error": "Congregação não encontrada no catálogo."}, status=404)
        existing_rows = _get_table(
            table,
            {"select": "*", "congregation_code": f"eq.{code}", "limit": "1"},
        )
        before = existing_rows[0] if existing_rows else {}
        source_name = str(common.get("comum") or common.get("nome") or "").strip()
        source_municipality = str(common.get("cidade") or common.get("municipio") or "").strip()

        if request.method == "DELETE":
            changes = {}
            archived_at = datetime.now(timezone.utc).isoformat()
            event = "ARCHIVE"
        else:
            body = _request_json(request)
            allowed = {"nome", "municipio", "administracao", "arquivada", *CONGREGATION_ASSIGNMENT_FIELDS}
            unknown = set(body) - allowed
            if unknown:
                return JsonResponse({"error": "A solicitação contém campos não permitidos."}, status=400)
            changes = {key: body[key] for key in {"nome", "municipio", "administracao"} if key in body}
            selected_people = {}
            for field in CONGREGATION_ASSIGNMENT_FIELDS:
                if field not in body:
                    continue
                value = body[field]
                if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                    return JsonResponse({"error": f"A lista de pessoas em {field} é inválida."}, status=400)
                if len(value) != len(set(value)):
                    return JsonResponse({"error": f"A lista de pessoas em {field} contém duplicatas."}, status=400)
                changes[field] = value
                selected_people.update({item: field for item in value})
            if selected_people:
                available_people = {person["id"]: person for person in _fetch_congregation_people()}
                for person_id, field in selected_people.items():
                    person = available_people.get(person_id)
                    if (
                        not person
                        or person["categoria"] != field
                        or not _person_matches_congregation(
                            person, source_name, code, source_municipality
                        )
                    ):
                        return JsonResponse({
                            "error": "Uma ou mais pessoas selecionadas não correspondem ao cargo ou à comum."
                        }, status=400)
            if not changes and "arquivada" not in body:
                return JsonResponse({"error": "Nenhum campo permitido foi enviado."}, status=400)

            if "arquivada" in body:
                if not isinstance(body["arquivada"], bool):
                    return JsonResponse({"error": "O estado de arquivamento deve ser verdadeiro ou falso."}, status=400)
                archived_at = datetime.now(timezone.utc).isoformat() if body["arquivada"] else None
                event = "ARCHIVE" if body["arquivada"] else "RESTORE"
            else:
                archived_at = before.get("archived_at")
                event = "UPDATE" if before else "CREATE"

        candidate = {
            "nome": before.get("nome") or source_name,
            "municipio": before.get("municipio") or source_municipality,
            "administracao": before.get("administracao") or "",
            **{field: before.get(field) or [] for field in CONGREGATION_ASSIGNMENT_FIELDS},
            **changes,
        }
        for field in ("nome", "municipio"):
            candidate[field] = str(candidate.get(field) or "").strip()
            if not candidate[field]:
                return JsonResponse({"error": "Nome e município são obrigatórios."}, status=400)
        candidate["administracao"] = str(candidate.get("administracao") or "").strip()

        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "congregation_code": code,
            **candidate,
            "archived_at": archived_at,
            "updated_by": str(request.session.get("user_id") or ""),
            "updated_at": now,
        }
        response = requests.post(
            f"{settings.SUPABASE_URL}/rest/v1/{table}",
            headers=_headers("resolution=merge-duplicates,return=representation"),
            params={"on_conflict": "congregation_code"},
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        result_rows = response.json()
        if not isinstance(result_rows, list) or len(result_rows) != 1:
            raise requests.RequestException("O banco não confirmou a alteração da congregação.")
        result = result_rows[0]
        log_audit(request, event, "ADMINISTRACAO_CONGREGACOES", {
            "entity": table,
            "entity_id": code,
            "before": before or None,
            "after": result,
            "changes": _audit_changes(
                before, result,
                {"nome", "municipio", "administracao", "archived_at", *CONGREGATION_ASSIGNMENT_FIELDS},
            ),
            "outcome": "success",
        })
        return JsonResponse(result)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except requests.RequestException as exc:
        logger.exception("Falha ao atualizar a congregação %s: %s", code, exc)
        log_audit(request, "MUTATION_FAILED", "ADMINISTRACAO_CONGREGACOES", {
            "entity": table, "entity_id": code, "outcome": "failure", "error_type": type(exc).__name__,
        })
        if _congregation_settings_missing(exc):
            return JsonResponse({
                "error": "A configuração de Congregações ainda não foi criada no Supabase.",
                "migration": "scripts/migrations/052_administrative_congregation_settings.sql",
            }, status=503)
        return JsonResponse({"error": "Não foi possível concluir a operação da congregação."}, status=502)


@administrative_only
@require_http_methods(["PATCH"])
def congregation_distribution_record(request, record_id):
    """Substitui só os atendimentos desta comum, com controle de concorrência."""
    try:
        catalog = congregation_distribution.corrected_catalog(common_catalog())
        if record_id not in {_common_code(c["comum"]) for c in catalog}:
            return JsonResponse({"error": "Congregação não encontrada."}, status=404)
        body = _request_json(request)
        revision = body.get("revision")
        if type(revision) is not int or revision < 0:
            raise ValueError("Versão da distribuição inválida. Atualize a página.")
        overrides, editable = congregation_distribution.load_overrides(_get_table)
        if not editable:
            return JsonResponse({"error": "A edição de assistências ainda precisa ser habilitada na configuração do sistema."}, status=503)
        persons = congregation_distribution.directory(_fetch_congregation_people(), overrides)
        assignments = congregation_distribution.validate_assignments(body.get("assignments"), persons, catalog, record_id)
        before = next((r for r in overrides if r["congregation_code"] == record_id), None)
        if (before["revision"] if before else 0) != revision:
            return JsonResponse({"error": "Outra pessoa alterou esta distribuição. Atualize antes de salvar."}, status=409)
        actor = str(request.session.get("user_id") or "")
        payload = {"congregation_code": record_id, "assignments": assignments,
                   "revision": revision + 1, "updated_by": actor,
                   "updated_at": datetime.now(timezone.utc).isoformat()}
        url = f"{settings.SUPABASE_URL}/rest/v1/{congregation_distribution.TABLE}"
        if revision == 0:
            response = requests.post(url, headers=_headers("return=representation"), json=payload, timeout=15)
        else:
            response = requests.patch(url, headers=_headers("return=representation"),
                                      params={"congregation_code": f"eq.{record_id}", "revision": f"eq.{revision}"},
                                      json=payload, timeout=15)
        if response.status_code == 409:
            return JsonResponse({"error": "A distribuição foi alterada. Atualize antes de salvar."}, status=409)
        response.raise_for_status()
        confirmed = response.json()
        if not confirmed:
            return JsonResponse({"error": "A distribuição foi alterada. Atualize antes de salvar."}, status=409)
        log_audit(request, "UPDATE", "ADMINISTRACAO_CONGREGACOES", {
            "entity": congregation_distribution.TABLE, "entity_id": record_id,
            "before": before or {"assignments": [a for a in congregation_distribution.seed()["assignments"] if a["congregation_code"] == record_id]},
            "after": confirmed[0], "outcome": "success",
        })
        return JsonResponse(confirmed[0])
    except congregation_distribution.ResidenceConflict as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except requests.RequestException:
        logger.exception("Falha ao salvar distribuição da comum %s", record_id)
        return JsonResponse({"error": "Não foi possível salvar a distribuição."}, status=502)


@administrative_only
@require_http_methods(["GET"])
def export_congregations_excel(request):
    import io
    from datetime import datetime
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    rows = _congregation_rows()
    municipality = str(request.GET.get("municipio") or "").strip()
    search = _catalog_norm(request.GET.get("q"))
    if municipality:
        rows = [row for row in rows if str(row.get("municipio") or "") == municipality]
    if search:
        rows = [row for row in rows if search in _catalog_norm(" ".join(str(row.get(key) or "") for key in ("codigo", "nome", "municipio", "administracao")))]
    profile = request.session.get("user_profile") or {}
    actor = profile.get("full_name") or profile.get("username") or "Usuario do Sistema"
    now = datetime.now()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "CONGREGACOES"
    headers = ["C\u00f3digo", "Congrega\u00e7\u00e3o", "Munic\u00edpio", "Administra\u00e7\u00e3o", "Servos vinculados", "Situacao"]
    last_column = get_column_letter(len(headers))
    navy, pale, stripe = "1E4B7A", "EAF2F8", "F4F6F8"
    for row_number, text, size, color, fill in [
        (1, "CONGREGA\u00c7\u00c3O CRIST\u00c3 NO BRASIL", 15, "FFFFFF", navy),
        (2, "Regional Itapevi - S\u00e3o Paulo", 10, "FFFFFF", navy),
        (3, "ADMINISTRA\u00c7\u00c3O - CONGREGA\u00c7\u00d5ES", 12, navy, pale),
    ]:
        sheet.merge_cells(start_row=row_number, start_column=1, end_row=row_number, end_column=len(headers))
        cell = sheet.cell(row_number, 1, text)
        cell.font = Font(size=size, bold=row_number != 2, color=color)
        cell.fill = PatternFill("solid", fgColor=fill)
        cell.alignment = Alignment(horizontal="center")
    sheet.merge_cells("A4:C4"); sheet["A4"] = f"Recorte: {municipality or 'Todos os munic\u00edpios'} - {len(rows)} comuns"
    sheet.merge_cells("D4:F4"); sheet["D4"] = f"Emissao: {now:%d/%m/%Y %H:%M} - Responsavel: {actor}"
    sheet["D4"].alignment = Alignment(horizontal="right")
    for cell in sheet[4]: cell.font = Font(size=9, bold=True, color="536A7D")
    thin = Side(style="thin", color="C8D1DA")
    for column, label in enumerate(headers, 1):
        cell = sheet.cell(6, column, label)
        cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor=navy)
        cell.alignment = Alignment(horizontal="center", vertical="center"); cell.border = Border(bottom=thin)
    for index, row in enumerate(rows, 7):
        values = [row.get("codigo"), row.get("nome_comum"), row.get("municipio"), row.get("administracao"), row.get("quantidade_servos"), "Com minist\u00e9rio" if row.get("quantidade_servos") else "Sem minist\u00e9rio"]
        for column, value in enumerate(values, 1):
            cell = sheet.cell(index, column, value if value is not None else "")
            cell.border = Border(bottom=thin); cell.alignment = Alignment(vertical="center")
            if index % 2 == 0: cell.fill = PatternFill("solid", fgColor=stripe)
        sheet.cell(index, 5).alignment = Alignment(horizontal="center")
    for index, width in enumerate([17, 44, 26, 30, 18, 20], 1): sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A7"; sheet.auto_filter.ref = f"A6:F{max(6, sheet.max_row)}"; sheet.sheet_view.showGridLines = False
    sheet.page_setup.orientation = "landscape"; sheet.page_setup.fitToWidth = 1; sheet.page_setup.fitToHeight = 0; sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_title_rows = "1:6"; sheet.oddFooter.center.text = "Administra\u00e7\u00e3o - Congrega\u00e7\u00f5es - Regional Itapevi"; sheet.oddFooter.right.text = "Pagina &P de &N"
    stream = io.BytesIO(); workbook_identity(workbook, actor);workbook.save(stream)
    log_audit(request, "EXPORT", "ADMINISTRACAO_CONGREGACOES", {"format": "xlsx", "row_count": len(rows), "municipality": municipality or None, "outcome": "success"})
    response = HttpResponse(stream.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="Congregacoes_{now:%d-%m-%Y_%H-%M}.xlsx"'
    return response


@administrative_only
@require_http_methods(["GET"])
def export_ministerio_excel(request):
    """Exportação institucional do recorte exibido no painel de Ministério."""
    import io
    from datetime import datetime
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    rows = _sort_ministry_rows(
        _get_table("ministerio_regional", {"select": "*", "order": "nome.asc", "limit": "3000"}),
        common_catalog(),
    )
    municipality = str(request.GET.get("municipio") or "").strip()
    query = _catalog_norm(request.GET.get("q"))
    if municipality:
        rows = [row for row in rows if _catalog_norm(row.get("municipio")) == _catalog_norm(municipality)]
    if query:
        rows = [row for row in rows if query in _catalog_norm(" ".join(str(row.get(key) or "") for key in ("nome", "ministerio", "comum", "municipio", "administracao", "rrm")))]
    profile = request.session.get("user_profile") or {}
    actor = profile.get("full_name") or profile.get("username") or "Usuário do Sistema"
    now = datetime.now()
    workbook = Workbook(); sheet = workbook.active; sheet.title = "MINISTERIO"
    headers = ["Nome", "Ministério", "Comum", "Município", "Administração", "RRM", "Status", "Apresentação"]
    navy, pale, stripe = "1E4B7A", "EAF2F8", "F4F6F8"
    for row_number, text, size, color, fill in [
        (1, "CONGREGAÇÃO CRISTÃ NO BRASIL", 15, "FFFFFF", navy),
        (2, "Regional Itapevi - São Paulo", 10, "FFFFFF", navy),
        (3, "ADMINISTRAÇÃO - MINISTÉRIO", 12, navy, pale),
    ]:
        sheet.merge_cells(start_row=row_number, start_column=1, end_row=row_number, end_column=len(headers))
        cell = sheet.cell(row_number, 1, text); cell.font = Font(size=size, bold=row_number != 2, color=color); cell.fill = PatternFill("solid", fgColor=fill); cell.alignment = Alignment(horizontal="center")
    sheet.merge_cells("A4:D4"); sheet["A4"] = f"Recorte: {municipality or 'Todos os municípios'} - {len(rows)} registros"
    sheet.merge_cells("E4:H4"); sheet["E4"] = f"Emissão: {now:%d/%m/%Y %H:%M} - Responsável: {actor}"; sheet["E4"].alignment = Alignment(horizontal="right")
    for cell in sheet[4]: cell.font = Font(size=9, bold=True, color="536A7D")
    thin = Side(style="thin", color="C8D1DA")
    for column, label in enumerate(headers, 1):
        cell = sheet.cell(6, column, label); cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor=navy); cell.alignment = Alignment(horizontal="center", vertical="center"); cell.border = Border(bottom=thin)
    for index, row in enumerate(rows, 7):
        values = [row.get("nome"), row.get("ministerio"), row.get("comum"), row.get("municipio"), row.get("administracao"), row.get("rrm"), row.get("status"), row.get("data_apresentacao")]
        for column, value in enumerate(values, 1):
            cell = sheet.cell(index, column, value if value is not None else ""); cell.border = Border(bottom=thin); cell.alignment = Alignment(vertical="center")
            if index % 2 == 0: cell.fill = PatternFill("solid", fgColor=stripe)
    for index, width in enumerate([33, 31, 40, 20, 22, 18, 14, 16], 1): sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A7"; sheet.auto_filter.ref = f"A6:H{max(6, sheet.max_row)}"; sheet.sheet_view.showGridLines = False
    sheet.page_setup.orientation = "landscape"; sheet.page_setup.fitToWidth = 1; sheet.page_setup.fitToHeight = 0; sheet.sheet_properties.pageSetUpPr.fitToPage = True; sheet.print_title_rows = "1:6"
    sheet.oddFooter.center.text = "Administração - Ministério - Regional Itapevi"; sheet.oddFooter.right.text = "Página &P de &N"
    stream = io.BytesIO(); workbook_identity(workbook, actor);workbook.save(stream)
    log_audit(request, "EXPORT", "MINISTERIO_REGIONAL", {"format": "xlsx", "row_count": len(rows), "municipality": municipality or None, "outcome": "success"})
    response = HttpResponse(stream.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="Ministerio_{now:%d-%m-%Y_%H-%M}.xlsx"'
    return response
