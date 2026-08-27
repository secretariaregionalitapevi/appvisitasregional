import json
from collections import Counter, defaultdict
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ColorAdminApp.access_control import service_headers
from ColorAdminApp.sam_history_sync import SOURCE_CONFIG, event_payload, event_signature, match_student


class Command(BaseCommand):
    help = "Concilia e importa o histórico completo exportado do SAM. O padrão é somente prévia."

    def add_arguments(self, parser):
        parser.add_argument("input", type=Path, help="Arquivo JSON exportado do SAM")
        parser.add_argument("--commit", action="store_true", help="Confirma gravação; sem esta opção nada é alterado")
        parser.add_argument("--report", type=Path, help="Grava relatório detalhado da conciliação")

    def _fetch_all(self, table, select="*"):
        rows, limit = [], 1000
        url = f"{settings.SUPABASE_URL}/rest/v1/{table}"
        for offset in range(0, 100000, limit):
            response = requests.get(url, headers=service_headers(), params={"select": select, "offset": offset, "limit": limit}, timeout=30)
            response.raise_for_status()
            batch = response.json()
            rows.extend(batch)
            if len(batch) < limit:
                break
        return rows

    def _insert_batches(self, table, rows):
        for start in range(0, len(rows), 200):
            response = requests.post(
                f"{settings.SUPABASE_URL}/rest/v1/{table}",
                headers=service_headers("return=minimal"), json=rows[start:start + 200], timeout=45,
            )
            if not response.ok:
                raise requests.HTTPError(
                    f"{response.status_code} em {table}: {response.text[:800]}", response=response,
                )
            response.raise_for_status()

    def handle(self, *args, **options):
        path = options["input"]
        if not path.is_file():
            raise CommandError(f"Arquivo não encontrado: {path}")
        try:
            document = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"JSON inválido: {exc}") from exc
        students = document.get("students")
        if not isinstance(students, list):
            raise CommandError("O arquivo precisa conter uma lista 'students'.")

        try:
            targets = self._fetch_all("musica_acompanhamento_aluno", "id,nome_aluno,comum_congregacao,municipio,instrumento")
            existing = {}
            for source_name, (table, _) in SOURCE_CONFIG.items():
                existing[source_name] = {event_signature(source_name, row) for row in self._fetch_all(table)}
        except requests.RequestException as exc:
            raise CommandError(f"Falha ao consultar o GEM: {exc}") from exc

        stats = Counter()
        unresolved = []
        inserts = defaultdict(list)
        for source_student in students:
            target, status = match_student(source_student, targets)
            stats[status] += 1
            if not target:
                unresolved.append({
                    "source_id": source_student.get("source_id"),
                    "nome": source_student.get("nome") or source_student.get("nome_aluno"),
                    "comum": source_student.get("comum") or source_student.get("comum_congregacao"),
                    "reason": status,
                })
                continue
            history = source_student.get("history") or source_student.get("historico") or {}
            for source_name in SOURCE_CONFIG:
                for event in history.get(source_name, []):
                    payload = event_payload(source_name, event, target)
                    signature = event_signature(source_name, payload)
                    if signature in existing[source_name]:
                        stats["existing_events"] += 1
                        continue
                    existing[source_name].add(signature)
                    inserts[source_name].append(payload)
                    stats["new_events"] += 1

        report = {
            "mode": "commit" if options["commit"] else "preview",
            "statistics": dict(stats),
            "new_events_by_source": {name: len(rows) for name, rows in inserts.items()},
            "unresolved": unresolved,
        }
        if options.get("report"):
            options["report"].write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(json.dumps(report["statistics"], ensure_ascii=False, indent=2))
        self.stdout.write(f"Eventos novos por fonte: {report['new_events_by_source']}")
        if unresolved:
            self.stdout.write(self.style.WARNING(f"{len(unresolved)} aluno(s) não foram vinculados; nenhum evento deles será gravado."))
        if not options["commit"]:
            self.stdout.write(self.style.WARNING("PRÉVIA concluída. Nenhum dado foi alterado. Use --commit somente após revisar o relatório."))
            return
        try:
            for source_name, rows in inserts.items():
                if rows:
                    self._insert_batches(SOURCE_CONFIG[source_name][0], rows)
        except requests.RequestException as exc:
            raise CommandError(f"A importação foi interrompida: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Sincronização concluída: {stats['new_events']} evento(s) importado(s)."))
