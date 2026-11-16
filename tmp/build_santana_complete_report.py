import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
import pymupdf
from django.test import RequestFactory
from ColorAdminApp.modules.music_events import annual_dashboard_data
from ColorAdminApp.modules.music_events_annual_reports import session_report, build_model_pdf
from ColorAdminApp.modules.music_events_closing import closing_for

request=RequestFactory().get('/', {'ano':'2026','atualizar':'1',
    'municipio':['SANTANA DE PARNAÍBA','PIRAPORA DO BOM JESUS']})
request.session={}
with patch('ColorAdminApp.modules.music_events.user_scope',return_value={'level':'global'}):
    annual=annual_dashboard_data(request)
session=next(row for row in annual['sessions'] if row['date']=='2026-11-15')
report=session_report(annual,session)
closing=closing_for(report)
assert (closing['musicians'],closing['organists'],closing['total'])==(201,59,406)
current=report['comparison']['current']
assert sum(row['MUSICO'] for row in report['rows'])==current['musicians']
assert sum(row['musicos_orquestra'] for row in report['rows'])==current['musicians']
assert sum(row['organistas_orquestra'] for row in report['rows'])==current['organists']
assert len(current['by_municipality'])==2
assert current['commons']>=40
output=Path('output/pdf/relatorio_completo_santana_pirapora_15_11_2026.pdf')
output.parent.mkdir(parents=True,exist_ok=True)
output.write_bytes(build_model_pdf(report,'Ricardo Grangeiro',datetime.now(ZoneInfo('America/Sao_Paulo'))))
pdf=pymupdf.open(output)
images=Path('tmp/pdfs');images.mkdir(parents=True,exist_ok=True)
text='\n'.join(page.get_text() for page in pdf)
for required in ['201','59','406','PARTICIPAÇÃO POR MUNICÍPIO DE ORIGEM','MÚSICOS NO MUNICÍPIO','FECHAMENTO OFICIAL']:
    assert required in text,required
for i,page in enumerate(pdf):
    contents=page.get_text()
    if any(key in contents for key in ['PAINEL DE PARTICIPAÇÃO','PARTICIPAÇÃO POR MUNICÍPIO DE ORIGEM','FECHAMENTO DO ENSAIO REGIONAL']):
        page.get_pixmap(matrix=pymupdf.Matrix(1.3,1.3)).save(images/f'santana-completo-{i+1}.png')
    assert all(block[0]>=0 and block[1]>=0 and block[2]<=page.rect.width+1 and block[3]<=page.rect.height+1
               for block in page.get_text('blocks'))
Path('tmp/santana-report-reconciliation.json').write_text(json.dumps({'official':closing,'origin':current,
    'pages':len(pdf),'output':str(output)},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'official':[201,59,406],'nominal_local':[closing.get('nominal_musicians'),closing.get('nominal_organists'),closing.get('nominal_total')],
                  'origin':current,'pages':len(pdf),'output':str(output)},ensure_ascii=True))
