import os,json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
os.environ.setdefault('DJANGO_SETTINGS_MODULE','ColorAdmin.settings')
import django
django.setup()
from ColorAdminApp.modules.music_ministry_reports import build_pdf,event_heading
from pypdf import PdfReader
import pypdfium2 as pdfium
out=Path('tmp/pdfs/ministry-matrix')
data=json.loads((out/'data.json').read_text(encoding='utf-8'))
for event in data['event_options']:
 day='/'.join(str(event['date'])[:10].split('-')[::-1])
 assert event_heading(event).count(day)==1
 assert event_heading(event).endswith(day)
(out/'annual.pdf').write_bytes(build_pdf(data,'Ricardo Grangeiro',datetime.now(ZoneInfo('America/Sao_Paulo'))))
for page in PdfReader(out/'annual.pdf').pages:
 text=page.extract_text()
 assert 'Regional Itapevi - 2026 - Itapevi - SP' in text
 assert 'Impresso por: Ricardo Grangeiro - P\u00e1gina' in text
with pdfium.PdfDocument(str(out/'annual.pdf')) as doc:
 doc[0].render(scale=1.25).to_pil().save(out/'footer-review.png')
print('PDF generated; dates and one-line footer verified on every page')
