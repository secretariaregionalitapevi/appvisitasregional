import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pymupdf
from django.test import RequestFactory
from ColorAdminApp.modules.music_events import dashboard_data
from ColorAdminApp.modules.music_events_reports import build_pdf, build_excel
from ColorAdminApp.modules.music_conductor_identity import active_conductor, common_name_key
from openpyxl import load_workbook
from io import BytesIO

request = RequestFactory().get('/', {'evento': '0c00b334-0ab6-4175-b759-028aef44161f'})
request.session = {}
with patch('ColorAdminApp.modules.music_events.user_scope', return_value={'level': 'global'}):
    data = dashboard_data(request, include_history=False)
rows = data['conductors']['rows']
justified = [row for row in rows if row.get('justificativa_registrada') or row['situacao']=='JUSTIFICOU']
assert len(justified)==5, [(row['encarregado_nome'],row['situacao']) for row in justified]
individual_cities = data['conductors']['individual_municipalities']
assert next(row for row in individual_cities if row['municipio']=='COTIA')['JUSTIFICOU']==3
assert next(row for row in individual_cities if row['municipio']=='CAUCAIA DO ALTO')['JUSTIFICOU']==2
print(json.dumps({'justified':[(row['encarregado_nome'],row['municipio'],row['situacao']) for row in justified]},ensure_ascii=True))
assert all(active_conductor(row['encarregado_nome']) for row in rows)
oseia = [row for row in rows if row['comum_chave'] == 'BR-22-2934']
assert len(oseia) == 1 and oseia[0]['encarregado_nome'] == 'OSÉIA DE SOUZA'
elcio = [row for row in rows if row['comum_chave'] == 'BR-22-3789']
assert len(elcio) == 1 and elcio[0]['situacao'] == 'JUSTIFICOU'
for city in {row['municipio'] for row in rows}:
    names = [common_name_key(row['comum']) for row in rows if row['municipio'] == city]
    assert names == sorted(names), city
expected = {'BR-22-0432': 'MARIO AFONSO SANCHES', 'BR-22-1668': 'VALDIR BUENO',
            'BR-22-1902': 'EDSON VICENTE DA SILVA'}
for key, name in expected.items():
    assert any(row['comum_chave'] == key and row['encarregado_nome'] == name for row in rows), key
unidentified = [row for row in rows if not row.get('encarregado_nome')]
mapped_unidentified = [row for row in unidentified if row.get('encarregado_nomes')]
assert not mapped_unidentified, mapped_unidentified
data['report'] = 'encarregados'
now = datetime.now(ZoneInfo('America/Sao_Paulo'))
output = Path('output/pdf/presenca_encarregados_identificados_15_11_2026.pdf')
output.parent.mkdir(parents=True, exist_ok=True)
output.write_bytes(build_pdf(data, 'Ricardo Grangeiro', now))
book = load_workbook(BytesIO(build_excel(data, 'Ricardo Grangeiro', now)))
excel_text = '\n'.join(str(cell.value or '') for row in book['Encarregados por comum'] for cell in row)
pdf = pymupdf.open(output)
text = '\n'.join(page.get_text() for page in pdf)
for name in ['GETÚLIO SANTIAGO COSTA', 'JOSE RICARDO BARDELI', 'SILAS AGUIAR ROCHA', 'OSÉIAS DE SOUZA']:
    assert name not in text and name not in excel_text, name
assert 'OSÉIA DE SOUZA' in text
for index, page in enumerate(pdf):
    if 'OSÉIA DE SOUZA' in page.get_text():
        page.get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4)).save(Path('tmp/pdfs/encarregados-oseia.png'))
        break
for name in expected.values():
    assert name in text and name in excel_text, name
images = Path('tmp/pdfs')
images.mkdir(parents=True, exist_ok=True)
pdf[0].get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4)).save(images / 'encarregados-identificados-1.png')
pdf[-1].get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4)).save(images / 'encarregados-resumo-comuns.png')
assert 'Total de comuns' in text
municipalities = data['conductors']['municipalities']
itapevi = next(row for row in municipalities if row['municipio'] == 'ITAPEVI')
vgp = next(row for row in municipalities if row['municipio'] == 'VARGEM GRANDE PAULISTA')
assert itapevi['total'] == 51 and itapevi['PRESENTE'] == 7
assert vgp['total'] == 10 and vgp['PRESENTE'] == 10 and vgp['NAO_JUSTIFICOU'] == 0
rafael = next(row for row in rows if row['encarregado_nome'] == 'RAFAEL DE BARROS RODRIGUES')
assert rafael['participacao'] == 'NO MUNICÍPIO'
print(json.dumps({'examples': [(r['comum_chave'], r['encarregado_nome'], r['situacao'])
                              for r in rows if r['comum_chave'] in expected],
                  'total_rows': len(rows), 'unidentified': len(unidentified),
                  'unidentified_commons': [(r['comum_chave'], r['comum']) for r in unidentified],
                  'pages': len(pdf)}, ensure_ascii=True))
