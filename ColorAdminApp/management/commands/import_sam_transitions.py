"""Importação idempotente de transições documentadas, sem alterar o SAM."""
import json
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from ColorAdminApp.access_control import service_headers
from ColorAdminApp.modules.sam_temporal import FIELDS, instant


class Command(BaseCommand):
    help = 'Preserva cargo, comum, ingresso e níveis com data e evidência do SAM. Prévia por padrão.'

    def add_arguments(self, parser):
        parser.add_argument('input', type=Path)
        parser.add_argument('--commit', action='store_true')

    def handle(self, *args, **options):
        try:
            rows = json.loads(options['input'].read_text(encoding='utf-8-sig'))
            if not isinstance(rows, list):
                raise ValueError('Informe uma lista de transições.')
            payloads = []
            for row in rows:
                if row['campo'] not in FIELDS or not row.get('evidence') or not row.get('source_ref') or not row.get('source_key'):
                    raise ValueError('Campo, identidade, referência e evidência são obrigatórios.')
                if row['anterior'] == row['posterior']:
                    raise ValueError('Valores anterior e posterior devem ser diferentes.')
                payloads.append({'p_source_key': str(row['source_key']), 'p_campo': row['campo'],
                    'p_anterior': row['anterior'], 'p_posterior': row['posterior'],
                    'p_effective_at': instant(row['effective_at']).isoformat(),
                    'p_source_ref': row['source_ref'], 'p_evidence': row['evidence']})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CommandError(f'Arquivo inválido: {exc}') from exc
        if options['commit']:
            for payload in payloads:
                response = requests.post(f'{settings.SUPABASE_URL}/rest/v1/rpc/sam_registrar_transicao',
                    headers=service_headers(), json=payload, timeout=30)
                response.raise_for_status()
        self.stdout.write(f'{len(payloads)} transição(ões) ' + ('processadas.' if options['commit'] else 'validadas; prévia sem gravação.'))
