"""Render the actual print document on A4 and A5, checking image bounds and pagination."""
import os
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from io import BytesIO

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','ColorAdmin.settings')
import django
django.setup()
import pymupdf
from django.template.loader import render_to_string
from playwright.sync_api import sync_playwright
from pypdf import PdfReader
from ColorAdminApp.modules.darpe_atendimentos_exports import build_papeleta_pdf,papeleta_print_pages
from ColorAdminApp.tests.tests_darpe_atendimentos_admin import sample

out=ROOT/'tmp/darpe-modal-qa'
out.mkdir(parents=True,exist_ok=True)
record=sample()
record.update(local='Cantinho da Esperança',municipio='Itapevi',comum='BR-22-0673 - VILA DOUTOR CARDOSO')
source=build_papeleta_pdf(record,'Ricardo C. Grangeiro',datetime.now(ZoneInfo('America/Sao_Paulo')))
text=''.join(page.extract_text() for page in PdfReader(BytesIO(source)).pages)
assert 'CONGREGAÇÃO CRISTÃ NO BRASIL' in text
assert 'Secretária Regional do DARPE' in text
assert 'Ricardo C. Grangeiro' in text
images=papeleta_print_pages(source)
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 page=browser.new_page()
 for count in (1,2):
  html=render_to_string('pages/darpe_papeleta_print.html',{'pages':images*count})
  page.set_content(html,wait_until='load')
  page.wait_for_function('[...document.images].every(image=>image.complete&&image.naturalWidth>0)')
  for size,expected in [('A4',(595.28,841.89)),('A5',(419.53,595.28))]:
   output=page.pdf(format=size,print_background=True,prefer_css_page_size=False,display_header_footer=False)
   document=pymupdf.open(stream=output,filetype='pdf')
   assert len(document)==count,(size,count,len(document))
   for printed in document:
    assert abs(printed.rect.width-expected[0])<2
    assert abs(printed.rect.height-expected[1])<2
    rects=[rect for image in printed.get_images() for rect in printed.get_image_rects(image[0])]
    assert rects
    for rect in rects:
     assert rect.x0>=15 and rect.y0>=15,(size,rect)
     assert rect.x1<=printed.rect.width-15 and rect.y1<=printed.rect.height-15,(size,rect,printed.rect)
   if count==1:
    (out/f'impressao-{size}.pdf').write_bytes(output)
    document[0].get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).save(str(out/f'impressao-{size}.png'))
   print(size,':',count,'página(s), conteúdo inteiro dentro da área útil.')
 browser.close()
