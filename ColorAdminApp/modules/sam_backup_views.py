"""Rotas pessoais de Backup SAM, sem restauração e sem cliente de escrita remota."""
from functools import wraps
from datetime import datetime
from zoneinfo import ZoneInfo
import logging
import json
import sqlite3

import requests
from django.conf import settings
from django.core.cache import cache
from django.http import FileResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods

from . import sam_backup
from . import sam_rehearsal

logger = logging.getLogger(__name__)


def owner_only(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        profile = request.session.get("user_profile") or {}
        if not request.session.get("authenticated") or str(profile.get("role_id")) != "1":
            return JsonResponse({"error": "Backup SAM é restrito ao perfil Master."}, status=403)
        try:
            response = view(request, *args, **kwargs)
            response["Cache-Control"] = "no-store, private"
            return response
        except (sam_backup.BackupError, requests.RequestException, OSError, ValueError, sqlite3.Error) as exc:
            logger.warning("Backup SAM: %s", type(exc).__name__)
            message = str(exc) if isinstance(exc, sam_backup.BackupError) else "Não foi possível concluir a leitura ou preservar a cópia. Nenhum dado foi enviado ao SAM."
            return JsonResponse({"error": message}, status=503)
    return wrapped


def _document(request):
    backup_id = request.GET.get("backup")
    if backup_id:
        return sam_backup.load(backup_id)
    # A captura persistida não utiliza este cache de consulta.
    document = cache.get("sam-backup:inventory:v1")
    if document is None:
        document = sam_backup.capture()
        cache.set("sam-backup:inventory:v1", document, 60)
    return document


@owner_only
@require_GET
@ensure_csrf_cookie
def page(request):
    return render(request, "pages/sam_backup.html")


@owner_only
@require_GET
def options(request):
    document = _document(request)
    locations, _, pending = sam_backup.locations(document["tables"], include_pending=True)
    return JsonResponse({"locations": locations, "pending_locations": pending, "captured_at": document["finished_at"],
                         "backup_id": document["id"] if document.get("sha256") else None})


@owner_only
@require_GET
def data(request):
    if not request.GET.get("comum"):
        return JsonResponse({"error": "Selecione uma comum."}, status=400)
    return JsonResponse(sam_backup.inventory(_document(request), request.GET["comum"]))


@owner_only
@require_http_methods(["GET", "POST"])
def archives(request):
    if request.method == "GET":
        return JsonResponse({"backups": sam_backup.list_archives(), "sam_write_enabled": False})
    document = sam_backup.capture()
    document["created_by"] = str(request.session.get("user_id") or "Master")
    saved = sam_backup.save(document)
    cache.delete("sam-backup:inventory:v1")
    return JsonResponse({"id": saved["id"], "sha256": saved["sha256"],
                         "finished_at": saved["finished_at"],
                         "counts": {table: len(rows) for table, rows in saved["tables"].items()},
                         "sam_write_enabled": False}, status=201)


@owner_only
@require_GET
def download(request, backup_id):
    # Verifica o conteúdo antes de permitir o download. Arquivos ficam fora de static/media.
    document = sam_backup.load(backup_id)
    stamp = datetime.fromisoformat(document["finished_at"]).astimezone(
        ZoneInfo(settings.TIME_ZONE)
    ).strftime("%d-%m-%Y_%H-%M")
    response = FileResponse(sam_backup._archive_path(backup_id).open("rb"), as_attachment=True,
                            filename=f"Backup_SAM_{stamp}_{backup_id}.json.gz", content_type="application/gzip")
    response["X-Backup-SHA256"] = document["sha256"]
    return response


@owner_only
@require_http_methods(["GET", "POST"])
def rehearsals(request):
    if request.method == "GET":
        return JsonResponse({"runs": sam_rehearsal.list_runs(), "sam_write_enabled": False})
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Informe os dados do ensaio em JSON."}, status=400)
    if not isinstance(payload, dict) or not payload.get("backup_id") or not payload.get("group_id"):
        return JsonResponse({"error": "Selecione uma cópia preservada e uma turma."}, status=400)
    if payload.get("comum") != sam_rehearsal.COMMON:
        return JsonResponse({"error": "Este ensaio é exclusivo de Vila das Chácaras, Itapevi."}, status=400)
    # Exige arquivo preservado/verificado. Não utiliza espelho atual ou rede.
    document = sam_backup.load(payload["backup_id"])
    result = sam_rehearsal.create(document, str(payload["group_id"]), request.session.get("user_id") or "Master")
    return JsonResponse(result, status=200 if result["reused"] else 201)


@owner_only
@require_GET
def rehearsal_detail(request, run_id):
    return JsonResponse(sam_rehearsal.read(run_id))
