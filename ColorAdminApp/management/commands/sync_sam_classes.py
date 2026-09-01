import os
import re
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ColorAdminApp.access_control import service_headers
from ColorAdminApp.sam_class_mirror import (
    BASE_URL, fetch_class_page, fetch_text, fingerprint, norm, parse_attendance, parse_class_detail, parse_class_row,
)
from ColorAdminApp.sam_live_session import SamLiveSession


class Command(BaseCommand):
    help = "Sincroniza aulas e frequências do SAM por delta, sem reabrir o histórico de cada aluno."

    def add_arguments(self, parser):
        parser.add_argument("--scraper-dir", type=Path, default=os.getenv("SAM_SCRAPER_DIR"))
        parser.add_argument("--full", action="store_true", help="Varre todas as aulas na carga inicial.")
        parser.add_argument("--lookback-days", type=int, default=45)

    def _get_all(self, table, select="*", **filters):
        rows = []
        for offset in range(0, 100000, 1000):
            response = requests.get(
                f"{settings.SUPABASE_URL}/rest/v1/{table}", headers=service_headers(),
                params={"select": select, "offset": offset, "limit": 1000, **filters}, timeout=30,
            )
            response.raise_for_status()
            batch = response.json()
            rows.extend(batch)
            if len(batch) < 1000:
                break
        return rows

    def _upsert(self, table, rows, conflict):
        if not rows:
            return []
        response = requests.post(
            f"{settings.SUPABASE_URL}/rest/v1/{table}",
            headers=service_headers("resolution=merge-duplicates,return=representation"),
            params={"on_conflict": conflict}, json=rows, timeout=60,
        )
        if not response.ok:
            raise CommandError(f"Falha ao gravar {table}: HTTP {response.status_code} - {response.text[:1000]}")
        return response.json()

    def handle(self, *args, **options):
        scraper_dir = Path(options["scraper_dir"]).resolve() if options.get("scraper_dir") else None
        if not scraper_dir or not (scraper_dir / "web_scraper.py").is_file():
            project_parent = Path(settings.BASE_DIR).resolve().parent
            candidates = [
                path for path in project_parent.glob("PROJETO_SAM*")
                if path.is_dir() and (path / "web_scraper.py").is_file()
            ]
            if len(candidates) == 1:
                scraper_dir = candidates[0].resolve()
        if not scraper_dir or not (scraper_dir / "web_scraper.py").is_file():
            raise CommandError(
                "Não foi possível localizar automaticamente o scraper SAM. "
                "Configure SAM_SCRAPER_DIR ou informe --scraper-dir."
            )
        self.stdout.write(f"Scraper SAM: {scraper_dir}")
        try:
            existing_rows = self._get_all("sam_gem_classes", "id,source_id,source_hash,data_aula")
        except requests.RequestException as exc:
            raise CommandError("Aplique a migration 018_sam_gem_classes_attendance.sql antes da sincronização.") from exc
        existing = {str(row["source_id"]): row for row in existing_rows}
        full = options["full"] or not existing
        cutoff = date.today() - timedelta(days=max(7, options["lookback_days"]))
        session = SamLiveSession(scraper_dir, headless=True)
        processed = changed_classes = changed_attendance = 0
        try:
            if not session.scraper.login():
                raise CommandError("Não foi possível autenticar no SAM.")
            page = session.scraper.page
            page.goto(f"{BASE_URL}/aulas_abertas", wait_until="domcontentloaded", timeout=60000)
            start, length, candidates = 0, 2000, []
            while True:
                payload = fetch_class_page(page, start, length)
                batch = [parse_class_row(row) for row in payload.get("data") or []]
                candidates.extend(batch)
                start += len(batch)
                if not full or not batch or start >= int(payload.get("recordsFiltered") or 0):
                    break
            if full:
                buckets = defaultdict(deque)
                for candidate in sorted(candidates, key=lambda row: row.get("data_aula") or "", reverse=True):
                    buckets[(norm(candidate.get("curso")), norm(candidate.get("congregacao")))].append(candidate)
                diversified = []
                active_keys = deque(sorted(buckets))
                while active_keys:
                    key = active_keys.popleft()
                    diversified.append(buckets[key].popleft())
                    if buckets[key]:
                        active_keys.append(key)
                candidates = diversified
            completed_class_ids = {
                str(row.get("aula_id")) for row in self._get_all("sam_gem_attendance", "aula_id")
            }
            student_states = self._get_all("sam_student_sync_state", "source_key,source_name,aluno_id", aluno_id="not.is.null")
            by_key = {str(row.get("source_key")): row.get("aluno_id") for row in student_states}
            by_name = {}
            for row in student_states:
                by_name.setdefault(norm(row.get("source_name")), []).append(row.get("aluno_id"))
            for item in candidates:
                previous_row = existing.get(item["source_id"])
                if full and previous_row and str(previous_row.get("id")) in completed_class_ids:
                    continue
                event_date = date.fromisoformat(item["data_aula"]) if item.get("data_aula") else None
                if not full and item["source_id"] in existing and (not event_date or event_date < cutoff):
                    continue
                if not item.get("turma_source_id"):
                    continue
                detail = parse_class_detail(fetch_text(page, f"{BASE_URL}/aulas_abertas/visualizar_aula/{item['source_id']}"))
                class_payload = {**item, **detail, "source_payload": {**item, **detail}, "last_seen_at": datetime.now(timezone.utc).isoformat(), "synced_at": datetime.now(timezone.utc).isoformat()}
                class_payload["source_hash"] = fingerprint({key: value for key, value in class_payload.items() if key not in {"last_seen_at", "synced_at", "source_hash"}})
                previous = existing.get(item["source_id"])
                saved = self._upsert("sam_gem_classes", [class_payload], "source_id")[0]
                if not previous or previous.get("source_hash") != class_payload["source_hash"]:
                    changed_classes += 1
                attendance = parse_attendance(fetch_text(page, f"{BASE_URL}/aulas_abertas/visualizar_frequencias/{item['source_id']}/{item['turma_source_id']}"))
                old_attendance = self._get_all("sam_gem_attendance", "source_member_id,source_hash", aula_id=f"eq.{saved['id']}")
                old_hashes = {str(row["source_member_id"]): row.get("source_hash") for row in old_attendance}
                updates = []
                for record in attendance:
                    member_match = re.search(r"\d+", str(record.get("source_member_id") or ""))
                    frequency_match = re.search(r"\d+", str(record.get("source_frequency_id") or ""))
                    if not member_match:
                        self.stderr.write(f"Aula {item['source_id']}: presença ignorada por não possuir id_membro numérico.")
                        continue
                    member_id = member_match.group(0)
                    named = by_name.get(norm(record["nome_aluno"])) or []
                    record.update({
                        "source_member_id": int(member_id),
                        "source_frequency_id": int(frequency_match.group(0)) if frequency_match else None,
                        "aula_id": saved["id"],
                        "aluno_id": by_key.get(member_id) or (named[0] if len(named) == 1 else None),
                        "last_seen_at": datetime.now(timezone.utc).isoformat(),
                        "synced_at": datetime.now(timezone.utc).isoformat(),
                    })
                    if old_hashes.get(member_id) != record["source_hash"]:
                        updates.append(record)
                self._upsert("sam_gem_attendance", updates, "aula_id,source_member_id")
                changed_attendance += len(updates)
                processed += 1
                self.stdout.write(f"Aula {item['source_id']}: {len(attendance)} chamada(s), {len(updates)} alteração(ões).")
            now = datetime.now(timezone.utc).isoformat()
            self._upsert("sam_gem_sync_cursor", [{
                "source": "aulas_abertas", "last_source_id": max((int(row["source_id"]) for row in candidates), default=None),
                "last_event_at": max((row.get("data_aula") or "" for row in candidates), default=None) or None,
                **({"last_full_sync_at": now} if full else {}), "last_incremental_sync_at": now,
                "last_error": None, "updated_at": now,
            }], "source")
        finally:
            session.close()
        self.stdout.write(self.style.SUCCESS(
            f"Sincronização {'inicial' if full else 'incremental'}: {processed} aula(s), "
            f"{changed_classes} aula(s) alterada(s), {changed_attendance} presença(s) alterada(s)."
        ))
