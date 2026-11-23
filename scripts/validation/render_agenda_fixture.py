"""Renderização offline do template real para testes de interface (sem rede)."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ColorAdmin.settings')
import django
django.setup()
from django.template.loader import render_to_string
from django.test import RequestFactory

output = ROOT / 'tmp' / 'agenda-validation'
output.mkdir(parents=True, exist_ok=True)
html = render_to_string('pages/regional_agenda.html', {'agenda_master': True, 'csrf_token': 'test-csrf'})
(output / 'page.html').write_text(html, encoding='utf-8')
request = RequestFactory().get('/musica/agenda-regional/')
request.session = {'authenticated': True, 'user_id': '00000000-0000-0000-0000-000000000001',
                   'user_profile': {'role_id': 1, 'full_name': 'Prévia da Agenda', 'cargo': 'Secretaria Regional',
                                    'sector': 'Administrativo'}}
(output / 'preview.html').write_text(render_to_string('pages/regional_agenda.html',
    {'agenda_master': True}, request=request), encoding='utf-8')
print('Template renderizado para teste offline.')
