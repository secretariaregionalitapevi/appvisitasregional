import json
import os
import tempfile
import time
import ctypes
import threading
from datetime import datetime, timezone
from pathlib import Path

import requests
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from ColorAdminApp.access_control import service_headers
from ColorAdminApp.sam_live_session import SamLiveSession
from ColorAdminApp.sam_portal_history import portal_report_to_export

DEFAULT_IDLE_INTERVAL_SECONDS = 120
MIN_IDLE_INTERVAL_SECONDS = 60


class Command(BaseCommand):
    help = "Executa a sincronização SAM em processo separado, com ciclos periódicos e atualização de históricos."

    def add_arguments(self, parser):
        parser.add_argument("--scraper-dir", type=Path, default=os.getenv("SAM_SCRAPER_DIR"))
        parser.add_argument(
            "--interval",
            type=int,
            default=int(os.getenv("SAM_SYNC_INTERVAL_SECONDS", str(DEFAULT_IDLE_INTERVAL_SECONDS))),
            help="Intervalo ocioso entre consultas do catálogo; padrão: 120 segundos.",
        )
        parser.add_argument("--history-limit", type=int, default=int(os.getenv("SAM_SYNC_HISTORY_LIMIT", "100")))
        parser.add_argument("--visible", action="store_true", help="Exibe o navegador somente para diagnóstico")
        parser.add_argument("--once", action="store_true")

    def _pending(self, limit):
        response = requests.get(
            f"{settings.SUPABASE_URL}/rest/v1/sam_student_sync_state",
            headers=service_headers(), params={
                "select": "id,source_key,source_name,aluno_id", "sync_status": "in.(pending,failed)",
                "aluno_id": "not.is.null", "missing_since": "is.null",
                "order": "sync_status.desc,updated_at.asc", "limit": limit,
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
        url = f"{settings.SUPABASE_URL}/rest/v1/sam_sync_control"
        payload = {"heartbeat_at": now, "worker_id": str(os.getpid()), "updated_at": now, **values}
        response = requests.patch(
            url,
            headers=service_headers("return=minimal"), params={"id": "eq.1"},
            json=payload, timeout=20,
        )
        if response.status_code == 400:
            # Compatibilidade com instalações que ainda não aplicaram a migration 014.
            for optional in ("worker_status", "last_error", "cycle_started_at"):
                payload.pop(optional, None)
            response = requests.patch(
                url, headers=service_headers("return=minimal"), params={"id": "eq.1"},
                json=payload, timeout=20,
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

    @staticmethod
    def _validate_history(report, document, import_report=None):
        tabs = report.get("tabs") if isinstance(report, dict) else None
        if not isinstance(tabs, dict):
            raise RuntimeError("O SAM não devolveu as abas do histórico do aluno.")
        expected_tabs = ("MSA", "Método", "Hinário", "Provas", "Escalas")
        missing = [name for name in expected_tabs if name not in tabs]
        failed = [name for name in expected_tabs if isinstance(tabs.get(name), dict) and tabs[name].get("error")]
        if missing or failed:
            details = []
            if missing:
                details.append("ausentes: " + ", ".join(missing))
            if failed:
                details.append("com falha: " + ", ".join(failed))
            raise RuntimeError("Extração incompleta do histórico (" + "; ".join(details) + ").")
        if not any(isinstance(tabs[name].get("tables"), list) and tabs[name]["tables"] for name in expected_tabs):
            raise RuntimeError("O SAM não devolveu nenhuma tabela de histórico; o aluno permanecerá na fila.")

        students = document.get("students") if isinstance(document, dict) else None
        if not isinstance(students, list) or len(students) != 1:
            raise RuntimeError("A conversão do histórico não produziu exatamente um aluno.")
        history = students[0].get("history")
        if not isinstance(history, dict):
            raise RuntimeError("A conversão do histórico não produziu eventos válidos.")
        extracted_events = sum(len(history.get(source) or []) for source in (
            "msa", "metodo", "hinario", "provas", "escalas", "atividades"
        ))
        if import_report is None:
            return extracted_events

        statistics = import_report.get("statistics") or {}
        if statistics.get("linked") != 1:
            raise RuntimeError("A importação não confirmou o vínculo permanente do aluno.")
        reconciled_events = sum(int(statistics.get(key) or 0) for key in (
            "new_events", "updated_events", "existing_events"
        ))
        if reconciled_events != extracted_events:
            raise RuntimeError(
                f"Validação da importação falhou: {extracted_events} evento(s) extraído(s), "
                f"mas {reconciled_events} conciliado(s)."
            )
        return extracted_events

    def _cycle(self, session, history_limit, refresh_catalog=True):
        with tempfile.TemporaryDirectory(prefix="sam-sync-") as temporary_name:
            temporary = Path(temporary_name)
            if refresh_catalog:
                catalog = temporary / "catalog.json"
                report = temporary / "catalog-report.json"
                catalog.write_text(json.dumps(session.catalog(), ensure_ascii=False), encoding="utf-8")
                call_command("sync_sam_catalog", catalog, commit=True, report=report, stdout=self.stdout, stderr=self.stderr)

            pending = self._pending(history_limit)
            count_response = requests.get(
                f"{settings.SUPABASE_URL}/rest/v1/sam_student_sync_state",
                headers=service_headers("count=exact"),
                params={"select": "id", "missing_since": "is.null", "limit": 1}, timeout=20,
            )
            count_response.raise_for_status()
            try:
                total_students = int(count_response.headers.get("Content-Range", "0/0").rsplit("/", 1)[-1])
            except ValueError:
                total_students = len(pending)
            self._heartbeat(total_students=total_students, last_message="Catálogo conciliado; processando históricos")
            self.stdout.write(f"Históricos pendentes selecionados neste ciclo: {len(pending)}")
            consecutive_failures = 0
            for index, state in enumerate(pending, 1):
                if self._control().get("desired_state") != "running":
                    self._heartbeat(current_student=None, worker_status="paused", last_message="Sincronização pausada por solicitação administrativa")
                    return index - 1
                name = state["source_name"]
                converted = temporary / f"history-{index}-converted.json"
                import_report_path = temporary / f"history-{index}-import-report.json"
                try:
                    self._heartbeat(current_student=name, processed_students=index - 1, worker_status="running",
                                    last_message=f"Processando {index} de {len(pending)} neste lote; a fila continuará automaticamente")
                    self.stdout.write(f"[{index}/{len(pending)}] Atualizando histórico de {name}")
                    student_started = time.monotonic()
                    raw_report = session.history(name, state.get("source_key"))
                    portal_seconds = time.monotonic() - student_started
                    document = portal_report_to_export(raw_report)
                    self._validate_history(raw_report, document)
                    converted.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
                    database_started = time.monotonic()
                    call_command(
                        "sync_sam_history", converted, student_id=state["aluno_id"], commit=True,
                        report=import_report_path,
                        stdout=self.stdout, stderr=self.stderr,
                    )
                    database_seconds = time.monotonic() - database_started
                    import_report = json.loads(import_report_path.read_text(encoding="utf-8"))
                    event_count = self._validate_history(raw_report, document, import_report)
                    self._mark(state["id"], "synced")
                    consecutive_failures = 0
                    total_seconds = time.monotonic() - student_started
                    timing = f"SAM {portal_seconds:.1f}s · banco {database_seconds:.1f}s · total {total_seconds:.1f}s"
                    self.stdout.write(f"[TEMPO] {name}: {timing}")
                    self._heartbeat(current_student=name, processed_students=index, worker_status="running",
                                    last_message=f"Histórico de {name} validado ({event_count} eventos) · {timing}")
                except Exception as exc:
                    self._mark(state["id"], "failed", str(exc)[:1000])
                    self.stderr.write(self.style.ERROR(f"Histórico de {name} falhou: {exc}"))
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        raise RuntimeError(
                            "A sessão do SAM falhou em 3 alunos consecutivos; "
                            "o navegador será reiniciado antes de retomar a fila."
                        ) from exc

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
        interval = max(MIN_IDLE_INTERVAL_SECONDS, options["interval"])
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
        refresh_catalog = True
        heartbeat_stop = threading.Event()
        def pulse():
            while not heartbeat_stop.wait(10):
                try:
                    self._heartbeat()
                except requests.RequestException:
                    pass
        heartbeat_thread = threading.Thread(target=pulse, name="sam-heartbeat", daemon=True)
        heartbeat_thread.start()
        try:
            while True:
                try:
                    control = self._control()
                except requests.RequestException as exc:
                    raise CommandError("Aplique a migração 013 do controle SAM antes de iniciar o worker: " + str(exc)) from exc
                if control.get("desired_state") != "running":
                    self._heartbeat(current_student=None, worker_status="paused", last_error=None,
                                    last_message="Serviço online e pausado; aguardando comando Start")
                    if options["once"]:
                        break
                    time.sleep(10)
                    continue
                if session is None:
                    self._heartbeat(worker_status="starting", last_error=None,
                                    cycle_started_at=datetime.now(timezone.utc).isoformat(),
                                    last_message="Iniciando sessão segura no SAM")
                    session = SamLiveSession(scraper_dir, headless=not options["visible"])
                    session.start()
                started = time.monotonic()
                processed = 0
                try:
                    self._heartbeat(worker_status="running", last_error=None, last_message="Sincronização em andamento")
                    processed = self._cycle(session, max(1, options["history_limit"]), refresh_catalog=refresh_catalog)
                except Exception as exc:
                    self._heartbeat(worker_status="error", last_error=str(exc)[:1000], current_student=None,
                                    last_message="A execução encontrou uma falha e será tentada novamente")
                    self.stderr.write(self.style.ERROR(f"Ciclo SAM falhou: {exc}"))
                    if options["once"]:
                        raise CommandError(str(exc)) from exc
                    if session:
                        try:
                            session.close()
                        except Exception:
                            pass
                    session = None
                    refresh_catalog = False
                    time.sleep(10)
                    continue
                if options["once"]:
                    break
                if processed >= max(1, options["history_limit"]):
                    self.stdout.write("Há mais históricos pendentes; continuando na mesma sessão SAM.")
                    refresh_catalog = False
                    continue
                refresh_catalog = True
                wait = max(1, interval - int(time.monotonic() - started))
                self.stdout.write(f"Próximo ciclo SAM em {wait} segundos.")
                remaining = wait
                while remaining > 0:
                    self._heartbeat(current_student=None, worker_status="idle",
                                    last_message=f"Serviço online; próximo ciclo em até {remaining} segundos")
                    if self._control().get("desired_state") != "running":
                        if session:
                            session.close()
                            session = None
                        break
                    step = min(10, remaining)
                    time.sleep(step)
                    remaining -= step
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=2)
            if session:
                session.close()
            try:
                self._heartbeat(worker_status="offline", current_student=None, last_message="Serviço encerrado")
            except requests.RequestException:
                pass
            lock_path.unlink(missing_ok=True)
