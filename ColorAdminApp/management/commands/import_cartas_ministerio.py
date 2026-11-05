import hashlib
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
import requests
from openpyxl import load_workbook
from ColorAdminApp.modules.access_control import service_headers
from ColorAdminApp.modules.music_letters_domain import ministry_workbook, ROLES

class Command(BaseCommand):
    help = 'Importa a relação de assistência/assinaturas por comum, preservando o cadastro ministerial original.'
    def add_arguments(self, parser):
        parser.add_argument('arquivo')
        parser.add_argument('--commit', action='store_true')
    def handle(self, arquivo, commit=False, **options):
        try:
            with open(arquivo, 'rb') as file:
                fingerprint = hashlib.sha256(file.read()).hexdigest()
            rows = ministry_workbook(load_workbook(arquivo, data_only=True), fingerprint)
            incomplete = [r['comum'] for r in rows if any(not r[k] for k in ROLES)]
            if commit:
                response = requests.post(settings.SUPABASE_URL + '/rest/v1/cartas_ministerio_comuns',
                    params={'on_conflict': 'common_code'}, headers=service_headers('resolution=merge-duplicates,return=minimal'),
                    json=rows, timeout=40)
                response.raise_for_status()
            self.stdout.write(f'{len(rows)} comuns; {len(incomplete)} relações incompletas; ' + ('importação aplicada.' if commit else 'simulação, sem gravação.'))
            for common in incomplete:
                self.stdout.write('Conferir: ' + common)
        except (OSError, ValueError, requests.RequestException) as exc:
            raise CommandError('Não foi possível importar a relação: ' + str(exc))
