import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import local

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

from ColorAdminApp.access_control import service_headers
from ColorAdminApp.sam_history_sync import (
    SOURCE_CONFIG, event_match_signature, event_payload, event_signature, match_student, program_minimum_progress,
)


_HTTP_STATE = local()


def _http():
    session = getattr(_HTTP_STATE, "session", None)
    if session is None:
        session = requests.Session()
        session.mount("https://", requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=4))
        _HTTP_STATE.session = session
    return session


class Command(BaseCommand):
    help = "Concilia e importa o histórico completo exportado do SAM. O padrão é somente prévia."

    def add_arguments(self, parser):
        parser.add_argument("input", type=Path, help="Arquivo JSON exportado do SAM")
        parser.add_argument("--student-id", help="Vínculo já confirmado pelo ID permanente do estado SAM")
        parser.add_argument("--commit", action="store_true", help="Confirma gravação; sem esta opção nada é alterado")
        parser.add_argument("--report", type=Path, help="Grava relatório detalhado da conciliação")

    def _fetch_all(self, table, select="*", filters=None):
        rows, limit = [], 1000
        url = f"{settings.SUPABASE_URL}/rest/v1/{table}"
        for offset in range(0, 100000, limit):
            params = {"select": select, "offset": offset, "limit": limit, **(filters or {})}
            response = _http().get(url, headers=service_headers(), params=params, timeout=30)
            response.raise_for_status()
            batch = response.json()
            rows.extend(batch)
            if len(batch) < limit:
                break
        return rows

    def _insert_batches(self, table, rows):
        for start in range(0, len(rows), 200):
            response = _http().post(
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

        stats = Counter()
        unresolved = []
        inserts = defaultdict(list)
        updates = defaultdict(list)
        matched_students = []
        existing_rows = {}
        try:
            targets = []
            if options.get("student_id"):
                if len(students) != 1:
                    raise CommandError("--student-id exige um arquivo com exatamente um aluno.")
                targets = self._fetch_all(
                    "musica_acompanhamento_aluno", "id,nome_aluno,comum_congregacao,municipio,instrumento",
                    {"id": f"eq.{options['student_id']}"},
                )
                if len(targets) != 1:
                    raise CommandError("O aluno vinculado ao ID informado não existe mais na base GEM.")
            else:
                names = {str(row.get("nome") or row.get("nome_aluno") or "").strip() for row in students}
                for name in filter(None, names):
                    targets.extend(self._fetch_all(
                        "musica_acompanhamento_aluno", "id,nome_aluno,comum_congregacao,municipio,instrumento",
                        {"nome_aluno": f"eq.{name}"},
                    ))
        except requests.RequestException as exc:
            raise CommandError(f"Falha ao consultar os alunos do GEM: {exc}") from exc
        for source_student in students:
            target, status = (targets[0], "linked") if options.get("student_id") else match_student(source_student, targets)
            stats[status] += 1
            if not target:
                unresolved.append({
                    "source_id": source_student.get("source_id"),
                    "nome": source_student.get("nome") or source_student.get("nome_aluno"),
                    "comum": source_student.get("comum") or source_student.get("comum_congregacao"),
                    "reason": status,
                })
                continue
            matched_students.append((source_student, target))
        target_ids = [str(target["id"]) for _, target in matched_students]
        try:
            existing = {}
            filters = {"aluno_id": f"in.({','.join(target_ids)})"} if target_ids else {"limit": 0}
            def load_source(item):
                source_name, (table, _) = item
                return source_name, self._fetch_all(table, filters=filters)

            with ThreadPoolExecutor(max_workers=len(SOURCE_CONFIG), thread_name_prefix="sam-history-read") as executor:
                source_results = list(executor.map(load_source, SOURCE_CONFIG.items()))
            for source_name, source_rows in source_results:
                existing_rows[source_name] = source_rows
                existing[source_name] = {event_signature(source_name, row) for row in source_rows}
                existing[f"{source_name}:matches"] = {
                    event_match_signature(source_name, row): row for row in source_rows
                }
        except requests.RequestException as exc:
            raise CommandError(f"Falha ao consultar os históricos vinculados: {exc}") from exc

        for source_student, target in matched_students:
            history = source_student.get("history") or source_student.get("historico") or {}
            for source_name in SOURCE_CONFIG:
                for event in history.get(source_name, []):
                    payload = event_payload(source_name, event, target)
                    signature = event_signature(source_name, payload)
                    if signature in existing[source_name]:
                        stats["existing_events"] += 1
                        continue
                    matched = existing[f"{source_name}:matches"].get(event_match_signature(source_name, payload))
                    if matched and matched.get("id"):
                        _, fields = SOURCE_CONFIG[source_name]
                        changed = {field: payload.get(field) for field in fields if matched.get(field) != payload.get(field)}
                        if changed:
                            updates[source_name].append((matched["id"], changed))
                            matched.update(changed)
                            stats["updated_events"] += 1
                        else:
                            stats["existing_events"] += 1
                        existing[source_name].add(signature)
                        continue
                    existing[source_name].add(signature)
                    existing[f"{source_name}:matches"][event_match_signature(source_name, payload)] = payload
                    inserts[source_name].append(payload)
                    stats["new_events"] += 1

        report = {
            "mode": "commit" if options["commit"] else "preview",
            "statistics": dict(stats),
            "new_events_by_source": {name: len(rows) for name, rows in inserts.items()},
            "updated_events_by_source": {name: len(rows) for name, rows in updates.items()},
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
            insert_jobs = [(SOURCE_CONFIG[source_name][0], rows) for source_name, rows in inserts.items() if rows]
            with ThreadPoolExecutor(max_workers=min(len(insert_jobs), len(SOURCE_CONFIG)) or 1, thread_name_prefix="sam-history-write") as executor:
                list(executor.map(lambda job: self._insert_batches(*job), insert_jobs))
            for source_name, rows in updates.items():
                table = SOURCE_CONFIG[source_name][0]
                for record_id, values in rows:
                    response = _http().patch(
                        f"{settings.SUPABASE_URL}/rest/v1/{table}", headers=service_headers("return=minimal"),
                        params={"id": f"eq.{record_id}"}, json=values, timeout=30,
                    )
                    response.raise_for_status()
            msa_rows = existing_rows.get("msa", []) + inserts.get("msa", [])
            for _, target in matched_students:
                student_msa = [row for row in msa_rows if str(row.get("aluno_id")) == str(target["id"])]
                response = _http().patch(
                    f"{settings.SUPABASE_URL}/rest/v1/musica_acompanhamento_aluno",
                    headers=service_headers("return=minimal"), params={"id": f"eq.{target['id']}"},
                    json={"programa_minimo_percentual": program_minimum_progress(student_msa)}, timeout=30,
                )
                response.raise_for_status()
            cache.delete("gem:students:v5")
        except requests.RequestException as exc:
            raise CommandError(f"A importação foi interrompida: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Sincronização concluída: {stats['new_events']} evento(s) importado(s)."))
