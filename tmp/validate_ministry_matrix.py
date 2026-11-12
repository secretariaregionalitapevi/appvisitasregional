import os,sys,json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','ColorAdmin.settings')
import django
django.setup()
from django.test import RequestFactory
from ColorAdminApp.modules import music_ministry as api
from ColorAdminApp.modules.music_ministry_reports import build_pdf,build_excel,matrix_events
from unittest.mock import patch
request=RequestFactory().get('/',{'ano':'2026','municipio':['ITAPEVI'],'cargo':'ENCARREGADO_LOCAL'})
request.session={}
with patch.object(api,'user_scope',return_value={'level':'global'}):
 data=api.dashboard_data(request)
out=Path('tmp/pdfs/ministry-matrix');out.mkdir(parents=True,exist_ok=True)
(out/'data.json').write_text(json.dumps(data,ensure_ascii=False,default=str),encoding='utf-8')
now=datetime.now(ZoneInfo('America/Sao_Paulo'))
(out/'annual.pdf').write_bytes(build_pdf(data,'Validacao',now))
(out/'annual.xlsx').write_bytes(build_excel(data,'Validacao',now))
from pypdf import PdfReader
pdf=PdfReader(out/'annual.pdf');print('people',len(data['rows']),'events',len(matrix_events(data)),'pages',len(pdf.pages))
from openpyxl import load_workbook
book=load_workbook(out/'annual.xlsx');assert book.active.max_row==len(data['rows'])+7
text='\n'.join(p.extract_text() for p in pdf.pages)
assert 'Hist?rico por pessoa e evento' not in text
import pypdfium2 as pdfium
render=pdfium.PdfDocument(str(out/'annual.pdf'))
for index in {0,len(render)-1}:render[index].render(scale=1.25).to_pil().save(out/f'page-{index+1}.png')
print('files generated and verified')
