"""Preserva o espelho local, sem abrir ou alterar o SAM original."""
from django.core.management.base import BaseCommand, CommandError
from ColorAdminApp import sam_backup


class Command(BaseCommand):
    help = "Cria uma nova cópia verificada do acervo local SAM; não escreve no SAM."

    def handle(self, *args, **options):
        try:
            document = sam_backup.capture(progress=lambda table, count: self.stdout.write(f"Lido: {table}: {count} registro(s)"))
            document["created_by"] = "comando local backup_sam"
            saved = sam_backup.save(document)
        except Exception as exc:
            # Não imprimir URLs/credenciais de exceções do cliente HTTP.
            detail = str(exc) if isinstance(exc, sam_backup.BackupError) else type(exc).__name__
            raise CommandError(f"Backup não concluído: {detail}") from None
        self.stdout.write(self.style.SUCCESS(f"Backup verificado: {saved['id']}"))
        for table, rows in saved["tables"].items():
            self.stdout.write(f"{table}: {len(rows)} registro(s)")
        self.stdout.write(f"SHA-256: {saved['sha256']}")
