import json
import os
import tempfile
import time
import ctypes
from datetime import datetime, timezone
from pathlib import Path

import requests
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from ColorAdminApp.access_control import service_headers
from ColorAdminApp.sam_live_session import SamLiveSession
from ColorAdminApp.sam_portal_history import portal_report_to_export


class Command(BaseCommand):
    help = "Executa a sincronização SAM em processo separado, com ciclos periódicos e atualização de históricos."

    def add_arguments(self, parser):
        parser.add_argument("--scraper-dir", type=Path, default=os.getenv("SAM_SCRAPER_DIR"))
        parser.add_argument("--interval", type=int, default=int(os.getenv("SAM_SYNC_INTERVAL_SECONDS", "1800")))
        parser.add_argument("--history-limit", type=int, default=int(os.getenv("SAM_SYNC_HISTORY_LIMIT", "100")))
        parser.add_argument("--visible", action="store_true", help="Exibe o navegador somente para diagnóstico")
        parser.add_argument("--once", action="store_true")

    def _pending(self, limit):
        response = requests.get(
            f"{settings.SUPABASE_URL}/rest/v1/sam_student_sync_state",
            headers=service_headers(), params={
                "select": "id,source_key,source_name,aluno_id", "sync_status": "in.(pending,failed)",
                "aluno_id": "not.is.null", "order": "updated_at.asc", "limit": limit,
            }, timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def _control(self):
        response = requests.get(
            f"{settings.SUPABASE_URL}/rest/v1/sam_sync_control", headers=service_headers(),
            params={"select": "*", "id": "eq.1", "limit": 1}, timeout=20,
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else {"desired_state": "paused"}

    def _heartbeat(self, **values):
        now = datetime.now(timezone.utc).isoformat()
        response = requests.patch(
            f"{settings.SUPABASE_URL}/rest/v1/sam_sync_control",
            headers=service_headers("return=minimal"), params={"id": "eq.1"},
            json={"heartbeat_at": now, "worker_id": str(os.getpid()), "updated_at": now, **values}, timeout=20,
        )
        response.raise_for_status()

    def _mark(self, state_id, status, error=None):
        payload = {"sync_status": status, "last_error": error, "updated_at": datetime.now(timezone.utc).isoformat()}
        if status == "synced":
            payload["last_history_sync_at"] = datetime.now(timezone.utc).isoformat()
        response = requests.patch(
            f"{settings.SUPABASE_URL}/rest/v1/sam_student_sync_state",
            headers=service_headers("return=minimal"), params={"id": f"eq.{state_id}"},
            json=payload, timeout=30,
        )
        response.raise_for_status()

    def _cycle(self, session, history_limit):
        with tempfile.TemporaryDirectory(prefix="sam-sync-") as temporary_name:
            temporary = Path(temporary_name)
            catalog = temporary / "catalog.json"
            report = temporary / "catalog-report.json"
            catalog.write_text(json.dumps(session.catalog(), ensure_ascii=False), encoding="utf-8")
            call_command("sync_sam_catalog", catalog, commit=True, report=report, stdout=self.stdout, stderr=self.stderr)

            pending = self._pending(history_limit)
            count_response = requests.get(
                f"{settings.SUPABASE_URL}/rest/v1/sam_student_sync_state",
                headers=service_headers("count=exact"), params={"select": "id", "limit": 1}, timeout=20,
            )
            count_response.raise_for_status()
            try:
                total_students = int(count_response.headers.get("Content-Range", "0/0").rsplit("/", 1)[-1])
            except ValueError:
                total_students = len(pending)
            self._heartbeat(total_students=total_students, last_message="Catálogo conciliado; processando históricos")
            self.stdout.write(f"Históricos pendentes selecionados neste ciclo: {len(pending)}")
            for index, state in enumerate(pending, 1):
                if self._control().get("desired_state") != "running":
                    self._heartbeat(current_student=None, last_message="Sincronização pausada por solicitação administrativa")
                    return index - 1
                name = state["source_name"]
                converted = temporary / f"history-{index}-converted.json"
                try:
                    self._heartbeat(current_student=name, processed_students=index - 1,
                                    last_message=f"Processando {index} de {len(pending)} neste lote")
                    self.stdout.write(f"[{index}/{len(pending)}] Atualizando histórico de {name}")
                    document = portal_report_to_export(session.history(name))
                    converted.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
                    call_command(
                        "sync_sam_history", converted, student_id=state["aluno_id"], commit=True,
                        stdout=self.stdout, stderr=self.stderr,
                    )
                    self._mark(state["id"], "synced")
                    self._heartbeat(current_student=name, processed_students=index,
                                    last_message=f"Histórico de {name} sincronizado")
                except Exception as exc:
                    self._mark(state["id"], "failed", str(exc)[:1000])
                    self.stderr.write(self.style.ERROR(f"Histórico de {name} falhou: {exc}"))

            return len(pending)

    @staticmethod
    def _process_alive(pid):
        if not pid:
            return False
        if os.name == "nt":
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        try:
            os.kill(int(pid), 0)
            return True
        except (OSError, ValueError):
            return False

    def handle(self, *args, **options):
        scraper_dir = Path(options["scraper_dir"]).resolve() if options.get("scraper_dir") else None
        if not scraper_dir or not (scraper_dir / "web_scraper.py").is_file():
            raise CommandError("Configure SAM_SCRAPER_DIR ou informe --scraper-dir.")
        interval = max(300, options["interval"])
        lock_path = Path(tempfile.gettempdir()) / "app_visitas_sam_sync.lock"
        if lock_path.exists():
            try:
                lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                lock_data = {}
            if not self._process_alive(lock_data.get("pid")):
                lock_path.unlink(missing_ok=True)
        try:
            descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, json.dumps({"pid": os.getpid(), "started_at": time.time()}).encode())
            os.close(descriptor)
        except FileExistsError as exc:
            raise CommandError("Já existe outro worker SAM em execução.") from exc
        session = None
        try:
            while True:
                try:
                    control = self._control()
                except requests.RequestException as exc:
                    raise CommandError("Aplique a migração 013 do controle SAM antes de iniciar o worker: " + str(exc)) from exc
                if control.get("desired_state") != "running":
                    self._heartbeat(current_student=None, last_message="Worker online, aguardando Start")
                    if options["once"]:
                        break
                    time.sleep(10)
                    continue
                if session is None:
                    self._heartbeat(last_message="Iniciando sessão única e invisível no SAM")
                    session = SamLiveSession(scraper_dir, headless=not options["visible"])
                    session.start()
                started = time.monotonic()
                processed = 0
                try:
                    processed = self._cycle(session, max(1, options["history_limit"]))
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f"Ciclo SAM falhou: {exc}"))
                    if options["once"]:
                        raise CommandError(str(exc)) from exc
                if options["once"]:
                    break
                if processed >= max(1, options["history_limit"]):
                    self.stdout.write("Há mais históricos pendentes; continuando na mesma sessão SAM.")
                    continue
                wait = max(1, interval - int(time.monotonic() - started))
                self.stdout.write(f"Próximo ciclo SAM em {wait} segundos.")
                remaining = wait
                while remaining > 0:
                    self._heartbeat(current_student=None, last_message=f"Próximo ciclo em até {remaining} segundos")
                    if self._control().get("desired_state") != "running":
                        if session:
                            session.close()
                            session = None
                        break
                    step = min(10, remaining)
                    time.sleep(step)
                    remaining -= step
        finally:
            if session:
                session.close()
            lock_path.unlink(missing_ok=True)
