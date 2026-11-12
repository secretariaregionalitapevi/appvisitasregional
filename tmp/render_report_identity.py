import os,sys,json
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','ColorAdmin.settings')
import django
django.setup()
from ColorAdminApp.tests.tests_music_events_annual import fixture
from ColorAdminApp.modules.music_events_annual import annual_data
from ColorAdminApp.modules.music_events_annual_reports import build_annual_pdf
from ColorAdminApp.modules.music_ministry_reports import build_pdf,build_excel
from ColorAdminApp.modules.darpe_sam_exports import build_pdf as darpe_pdf
from ColorAdminApp.tests.tests_darpe_sam_exports import example_rows
from django.template.loader import get_template
from pypdf import PdfReader
import pypdfium2 as pdfium
out=Path('tmp/report-identity');out.mkdir(exist_ok=True)
e,r,s,registry,catalog=fixture()
data=annual_data(e,r,s,registry,catalog,[],[],[],2026,{'level':'regional'},['ITAPEVI'])
now=datetime(2026,11,12,14,30)
(out/'ensaios.pdf').write_bytes(build_annual_pdf(data,'Operador Teste',now,'2026-09-20'))
source=json.loads(Path('tmp/pdfs/ministry-matrix/data.json').read_text(encoding='utf-8'))
(out/'acompanhamento.pdf').write_bytes(build_pdf(source,'Operador Teste',now))
(out/'acompanhamento.xlsx').write_bytes(build_excel(source,'Operador Teste',now))
(out/'darpe.pdf').write_bytes(darpe_pdf(example_rows(3),'ITAPEVI','Operador Teste',now))
for name in ['ensaios','acompanhamento','darpe','browser']:
 path=out/(name+'.pdf')
 pages=PdfReader(path).pages
 for page in pages:
  text=page.extract_text()
  assert 'Respons\u00e1vel:' in text,(name,text[:300])
  assert 'Secretaria Regional da M\u00fasica' in text,name
  assert 'Impresso por:' in text,name
  assert 'Operador Teste' in text,name
 with pdfium.PdfDocument(str(path)) as doc:
  for index in {0,len(doc)-1}:doc[index].render(scale=1.1).to_pil().save(out/(name+'-'+str(index+1)+'.png'))
 print(name,len(pages),'pages verified')
get_template('base.html')
print('Report samples and base template verified')
