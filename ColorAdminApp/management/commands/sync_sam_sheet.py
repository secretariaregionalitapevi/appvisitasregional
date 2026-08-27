import json
import os
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from ColorAdminApp.sam_sheet import fetch_sheet_rows, rows_to_export


class Command(BaseCommand):
    help = "Sincroniza os últimos lançamentos coletados pelo scraper SAM e armazenados no Google Sheets."

    def add_arguments(self, parser):
        parser.add_argument("--sheet-id", default=os.getenv("SAM_GOOGLE_SHEET_ID"))
        parser.add_argument("--credentials", type=Path, default=os.getenv("SAM_GOOGLE_CREDENTIALS_FILE"))
        parser.add_argument("--commit", action="store_true", help="Confirma a gravação; o padrão é somente prévia")
        parser.add_argument("--report", type=Path)

    def handle(self, *args, **options):
        sheet_id = options.get("sheet_id")
        credentials = Path(options["credentials"]) if options.get("credentials") else None
        if not sheet_id or not credentials:
            raise CommandError("Informe --sheet-id e --credentials ou configure SAM_GOOGLE_SHEET_ID e SAM_GOOGLE_CREDENTIALS_FILE.")
        if not credentials.is_file():
            raise CommandError(f"Credenciais não encontradas: {credentials}")
        try:
            document = rows_to_export(fetch_sheet_rows(sheet_id, credentials))
        except Exception as exc:
            raise CommandError(f"Falha ao ler a planilha SAM: {exc}") from exc
        self.stdout.write(f"Planilha SAM lida: {len(document['students'])} aluno(s).")
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as temporary:
                json.dump(document, temporary, ensure_ascii=False)
                temporary_path = Path(temporary.name)
            call_command(
                "sync_sam_history", temporary_path,
                commit=options["commit"], report=options.get("report"), stdout=self.stdout, stderr=self.stderr,
            )
        finally:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink()
