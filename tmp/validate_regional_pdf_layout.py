import os
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ColorAdmin.settings')
import django
django.setup()

import pymupdf
from django.test import RequestFactory
from ColorAdminApp.tests.tests_regional_routes import members, teams, DAY, COMMONS
from ColorAdminApp.modules.regional_routes import build_plan, finalize_plan
from ColorAdminApp.modules.regional_route_reports import build_group_pdf, prepare_navigation

people = members(14)
for index, person in enumerate(people):
    person['preferencia_periodo_visita'] = 'Tarde' if index < 3 else 'Manhã'
    if index % 2:
        person['apontamentos_restritos'] = 'Do 12:00 hrs às 14:00 hrs por motivo de reunião na Central'
plan = finalize_plan(build_plan(people, [], teams(1), DAY, 'ITAPEVI', COMMONS))
plan['issued_at'] = '17/11/2026 14:20'
group = plan['groups'][0]
group['houses'] = plan['houses']
request = RequestFactory().get('/')
request.session = {'user_profile': {'full_name': 'Operador de teste'}}
prepare_navigation([group], 'ITAPEVI', request)
output = Path('output/pdf')
output.mkdir(parents=True, exist_ok=True)
pdf = build_group_pdf(plan, group, request, include_map=False)
(output / 'roteiro-regional-validacao.pdf').write_bytes(pdf)
document = pymupdf.open(stream=pdf, filetype='pdf')
for index, page in enumerate(document):
    assert 'Grupo de Visitas Regional' in page.get_text()
    assert 'Secretaria Regional' not in page.get_text()
    page.get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4)).save(str(output / f'roteiro-regional-validacao-{index + 1}.png'))
print('Pages validated:', len(document))
