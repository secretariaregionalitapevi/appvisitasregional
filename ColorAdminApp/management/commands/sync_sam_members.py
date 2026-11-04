import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from ColorAdminApp.sam_live_session import SamLiveSession


class Command(BaseCommand):
    help = 'Espelha todos os Membros e Alunos do SAM; músicos, organistas e ministério. Prévia por padrão.'

    def add_arguments(self, parser):
        parser.add_argument('--scraper-dir', type=Path, default=os.getenv('SAM_SCRAPER_DIR'))
        parser.add_argument('--commit', action='store_true')
        parser.add_argument('--report', type=Path)
        parser.add_argument('--output', type=Path, help='Preservar o catálogo integral capturado para conferência.')

    def handle(self, *args, **options):
        directory = options.get('scraper_dir')
        if not directory:
            candidates = [p for p in Path(settings.BASE_DIR).parent.glob('PROJETO_SAM*') if (p / 'web_scraper.py').is_file()]
            directory = candidates[0] if len(candidates) == 1 else None
        if not directory:
            raise CommandError('Configure SAM_SCRAPER_DIR para ler o SAM original.')
        session = SamLiveSession(directory)
        try:
            if not session.scraper.login():
                raise CommandError('Login SAM indisponível.')
            catalog = session.catalog()
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        finally:
            session.close()
        self.stdout.write('Cobertura validada: ' + json.dumps(catalog['coverage'], ensure_ascii=False))
        with TemporaryDirectory(prefix='sam-members-') as temp:
            path = options.get('output') or Path(temp) / 'catalog.json'
            path.write_text(json.dumps(catalog, ensure_ascii=False), encoding='utf-8')
            call_command('sync_sam_catalog', path, commit=options['commit'], report=options.get('report'),
                         stdout=self.stdout, stderr=self.stderr)
