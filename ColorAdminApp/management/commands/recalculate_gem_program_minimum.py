from collections import Counter, defaultdict

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

from ColorAdminApp.access_control import service_headers
from ColorAdminApp.sam_history_sync import program_minimum_progress


class Command(BaseCommand):
    help = "Recalcula o Programa Mínimo de todos os alunos usando o histórico MSA já importado."

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true", help="Grava os percentuais; sem esta opção exibe somente a prévia")

    def _fetch_all(self, table, select):
        rows = []
        for offset in range(0, 100000, 1000):
            response = requests.get(
                f"{settings.SUPABASE_URL}/rest/v1/{table}", headers=service_headers(),
                params={"select": select, "offset": offset, "limit": 1000}, timeout=30,
            )
            response.raise_for_status()
            batch = response.json()
            rows.extend(batch)
            if len(batch) < 1000:
                break
        return rows

    def handle(self, *args, **options):
        try:
            students = self._fetch_all("musica_acompanhamento_aluno", "id,programa_minimo_percentual")
            msa_rows = self._fetch_all("musica_acompanhamento_msa", "aluno_id,fase")
        except requests.RequestException as exc:
            raise CommandError(f"Falha ao consultar os históricos MSA: {exc}") from exc

        by_student = defaultdict(list)
        for row in msa_rows:
            by_student[str(row.get("aluno_id"))].append(row)
        changes = defaultdict(list)
        for student in students:
            progress = program_minimum_progress(by_student[str(student["id"])])
            try:
                current = int(round(float(student.get("programa_minimo_percentual") or 0)))
            except (TypeError, ValueError):
                current = 0
            if current != progress or student.get("programa_minimo_percentual") is None:
                changes[progress].append(str(student["id"]))

        summary = Counter({percent: len(ids) for percent, ids in changes.items()})
        self.stdout.write(f"Alunos: {len(students)}; históricos MSA: {len(msa_rows)}; alterações: {sum(summary.values())}")
        self.stdout.write(f"Percentuais a gravar: {dict(sorted(summary.items()))}")
        if not options["commit"]:
            self.stdout.write(self.style.WARNING("PRÉVIA concluída. Use --commit para gravar."))
            return
        try:
            for progress, student_ids in changes.items():
                for start in range(0, len(student_ids), 100):
                    ids = ",".join(student_ids[start:start + 100])
                    response = requests.patch(
                        f"{settings.SUPABASE_URL}/rest/v1/musica_acompanhamento_aluno",
                        headers=service_headers("return=minimal"), params={"id": f"in.({ids})"},
                        json={"programa_minimo_percentual": progress}, timeout=45,
                    )
                    response.raise_for_status()
        except requests.RequestException as exc:
            raise CommandError(f"Falha ao gravar o Programa Mínimo: {exc}") from exc
        cache.delete("gem:students:v5")
        self.stdout.write(self.style.SUCCESS(f"Programa Mínimo atualizado em {sum(summary.values())} aluno(s)."))
