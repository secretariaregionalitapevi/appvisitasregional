import os
import sys
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','ColorAdmin.settings')
import django
django.setup()
from django.template.loader import render_to_string
from playwright.sync_api import sync_playwright
from ColorAdminApp.tests.tests_darpe import request_for
from ColorAdminApp.tests.tests_darpe_atendimentos_admin import sample
from ColorAdminApp.modules.darpe_atendimentos import SECTORS
from ColorAdminApp.modules.darpe_atendimentos_exports import build_papeleta_pdf, papeleta_print_pages

out=ROOT/'tmp/darpe-modal-qa'
out.mkdir(parents=True,exist_ok=True)
request=request_for('/darpe/atendimentos/')
request.session['user_profile'].update(role_id=1,full_name='Ricardo C. Grangeiro')
record=sample()
record.update(id='00000000-0000-0000-0000-000000000001',data='2026-11-18',local='Cantinho da Esperança',comum='BR-22-0673 - VILA DOUTOR CARDOSO',observacoes='Atendimento realizado com a participação da equipe local.',pedidos_oracao={'familias':'todas','enfermidades':3,'viagens':0})
html=render_to_string('pages/darpe_atendimentos.html',{'scope':{'nivel':'Global','municipio':'ITAPEVI','comum':record['comum']}},request=request)
context={'setores':[{'id':n,'nome':title} for n,title,_ in SECTORS], 'escopo':{'level':'global','municipio':'ITAPEVI','comum':record['comum']},'localidades':[{'municipio':'ITAPEVI','comum':record['comum']}]}
pdf=build_papeleta_pdf(record,'Ricardo C. Grangeiro',datetime.now(ZoneInfo('America/Sao_Paulo')))
(out/'papeleta.pdf').write_bytes(pdf)
print_html=render_to_string('pages/darpe_papeleta_print.html',{'pages':papeleta_print_pages(pdf)})
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 page=browser.new_page(viewport={'width':1440,'height':1050})
 errors=[];exports=[]
 page.on('pageerror',lambda error:errors.append(str(error)))
 def route_handler(route):
  url=urlparse(route.request.url)
  if url.hostname!='darpe-modal.test':route.abort()
  elif url.path=='/darpe/atendimentos/':route.fulfill(content_type='text/html',body=html)
  elif url.path.startswith('/static/'):
   path=(ROOT/url.path.lstrip('/')).resolve()
   if path.is_relative_to(ROOT) and path.is_file():route.fulfill(path=str(path))
   else:route.fulfill(status=404,body='')
  elif '/papeleta/' in url.path:
   exports.append(url.path)
   if url.path.endswith('/imprimir/'):
    route.fulfill(content_type='text/html',body=print_html,headers={'X-Papeleta-Print':'1'})
   else:
    route.fulfill(content_type='application/pdf',body=pdf,headers={'Content-Disposition':"attachment; filename*=UTF-8''Papeleta_DARPE_18_11_2026.pdf"})
  elif 'contexto' in url.path:route.fulfill(json=context)
  elif url.path=='/darpe/atendimentos/api/atendimentos/':route.fulfill(json={'items':[record]})
  else:route.fulfill(json={'pending_count':0})
 page.route('**/*',route_handler)
 page.goto('https://darpe-modal.test/darpe/atendimentos/',wait_until='networkidle')
 view=page.locator('#daa-records button[aria-label^="Visualizar"]')
 view.click()
 modal=page.locator('#da-detail')
 page.wait_for_timeout(450)
 assert modal.is_visible()
 assert not page.locator('#daa-dashboard').get_attribute('hidden')
 assert page.url=='https://darpe-modal.test/darpe/atendimentos/'
 assert page.locator('#da-detail-title').inner_text()==record['local']
 page.screenshot(path=str(out/'modal-desktop.png'))
 with page.expect_download() as result:
  page.locator('#da-detail-pdf').click()
 assert result.value.suggested_filename=='Papeleta_DARPE_18_11_2026.pdf'
 assert len(exports)==1
 page.locator('#app-feedback-layer').wait_for(state='visible')
 page.locator('#app-feedback-layer').evaluate('(node)=>node.remove()')
 page.evaluate('''() => {
  window.__printCount=0;
  const create=document.createElement.bind(document);
  document.createElement=(tag,...args)=>{
   const element=create(tag,...args);
   if(tag==='iframe'){
    Object.defineProperty(element,'contentWindow',{value:{focus(){},print(){window.__printCount++;}}});
    Object.defineProperty(element,'src',{set(){},get(){return 'about:blank';}});
    setTimeout(()=>element.dispatchEvent(new Event('load')),10);
   }
   return element;
  };
 }''')
 page.locator('#da-detail-print').click()
 page.wait_for_function('window.__printCount===1')
 page.locator('#app-feedback-layer').wait_for(state='visible')
 page.locator('#app-feedback-layer').evaluate('(node)=>node.remove()')
 page.keyboard.press('Escape')
 page.wait_for_timeout(450)
 assert not modal.is_visible()
 assert view.evaluate('(node)=>node===document.activeElement'), page.evaluate('document.activeElement.outerHTML')
 assert page.locator('#daa-records .daa-row-actions button').count()==3
 assert page.locator('#daa-records [data-app-export]').count()==0
 assert len(exports)==2
 page.locator('#header-theme-toggle').click()
 page.set_viewport_size({'width':390,'height':844})
 view.click()
 page.wait_for_timeout(450)
 assert modal.evaluate('(node)=>node.getBoundingClientRect().right<=innerWidth')
 page.screenshot(path=str(out/'modal-mobile-dark.png'))
 page.locator('#da-detail-content').evaluate('(node)=>node.scrollTop=node.scrollHeight')
 page.screenshot(path=str(out/'modal-mobile-dark-bottom.png'))
 page.locator('#da-detail-close').click()
 page.wait_for_timeout(450)
 page.locator('#daa-records button[aria-label^="Editar"]').click()
 page.wait_for_timeout(450)
 assert page.locator('#da-editor').is_visible()
 assert page.locator('#da-form [name=local]').input_value()==record['local']
 assert not errors,errors
 browser.close()
print('Tabela com apenas visualizar; ações, PDF, impressão e edição no modal: OK.')
