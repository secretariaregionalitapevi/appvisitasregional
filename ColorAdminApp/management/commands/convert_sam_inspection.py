import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ColorAdminApp.sam_portal_history import portal_report_to_export


class Command(BaseCommand):
    help = "Converte a leitura direta do portal SAM para o formato seguro de sincronização."

    def add_arguments(self, parser):
        parser.add_argument("input", type=Path)
        parser.add_argument("output", type=Path)

    def handle(self, *args, **options):
        try:
            report = json.loads(options["input"].read_text(encoding="utf-8-sig"))
            document = portal_report_to_export(report)
            options["output"].write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        counts = {key: len(rows) for key, rows in document["students"][0]["history"].items()}
        self.stdout.write(self.style.SUCCESS(f"Histórico convertido: {counts}"))
