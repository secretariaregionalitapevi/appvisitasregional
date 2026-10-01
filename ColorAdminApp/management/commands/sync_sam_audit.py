import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ColorAdminApp.access_control import service_headers
from ColorAdminApp.sam_audit_parser import parse_log_row
from ColorAdminApp.sam_audit_mirror import mirror_referenced_classes
from ColorAdminApp.sam_audit_source import fetch_audit_logs
from ColorAdminApp.sam_live_session import SamLiveSession


class Command(BaseCommand):
    help = "Espelha a trilha operacional do SAM em arquivo permanente e idempotente."

    def add_arguments(self, parser):
        parser.add_argument("--scraper-dir", type=Path, default=os.getenv("SAM_SCRAPER_DIR"))
        parser.add_argument("--limit", type=int, default=int(os.getenv("SAM_AUDIT_SYNC_LIMIT", "2000")))
        parser.add_argument("--full", action="store_true")
        parser.add_argument("--visible", action="store_true")

    @staticmethod
    def _upsert(table, rows, conflict, ignore=True):
        if not rows:
            return []
        resolution = "ignore-duplicates" if ignore else "merge-duplicates"
        response = requests.post(
            f"{settings.SUPABASE_URL}/rest/v1/{table}",
            headers=service_headers(f"resolution={resolution},return=representation"),
            params={"on_conflict": conflict}, json=rows, timeout=60,
        )
        if not response.ok:
            raise CommandError(f"Falha ao gravar {table}: HTTP {response.status_code} - {response.text[:800]}")
        return response.json()

    def handle(self, *args, **options):
        scraper_dir = Path(options["scraper_dir"]).resolve() if options.get("scraper_dir") else None
        if not scraper_dir or not (scraper_dir / "web_scraper.py").is_file():
            candidates = [p for p in Path(settings.BASE_DIR).resolve().parent.glob("PROJETO_SAM*") if (p / "web_scraper.py").is_file()]
            scraper_dir = candidates[0] if len(candidates) == 1 else None
        if not scraper_dir:
            raise CommandError("Configure SAM_SCRAPER_DIR para sincronizar os logs do SAM.")

        limit, start, imported, newest = max(1, options["limit"]), 0, 0, None
        session = SamLiveSession(scraper_dir, headless=not options["visible"])
        try:
            session.start()
            while start < limit:
                page = fetch_audit_logs(session, start=start, length=min(1000, limit - start),
                                        lookback_days=36500 if options["full"] else int(os.getenv("SAM_AUDIT_LOOKBACK_DAYS", "7")))
                headers, events = page.get("headers") or [], []
                for raw in page.get("rows") or []:
                    if isinstance(raw, list) and headers:
                        raw = {headers[i]: value for i, value in enumerate(raw) if i < len(headers)}
                    event = parse_log_row(raw)
                    if event:
                        events.append(event)
                        newest = max(filter(None, (newest, event["occurred_at"])))
                events = list({event["source_fingerprint"]: event for event in events}.values())
                mirrored = mirror_referenced_classes(session, events)
                if mirrored["classes"]:
                    self.stdout.write(f"Aulas citadas nos logs: {mirrored['classes']} aula(s), "
                                      f"{mirrored['attendance']} chamada(s) vinculada(s).")
                for index in range(0, len(events), 500):
                    imported += len(self._upsert("sam_audit_events", events[index:index + 500], "source_fingerprint", ignore=False))
                received = len(page.get("rows") or [])
                start += received
                if not received or start >= int(page.get("total") or 0):
                    break
        finally:
            session.close()

        now = datetime.now(timezone.utc).isoformat()
        cursor = {"source": "sam_system_logs", "last_occurred_at": newest,
                  "last_incremental_sync_at": now, "imported_count": imported,
                  "last_error": None, "updated_at": now}
        if options["full"]:
            cursor["last_full_sync_at"] = now
        self._upsert("sam_audit_sync_cursor", [cursor], "source", ignore=False)
        self.stdout.write(self.style.SUCCESS(f"Historico SAM sincronizado: {imported} novo(s) evento(s)."))
