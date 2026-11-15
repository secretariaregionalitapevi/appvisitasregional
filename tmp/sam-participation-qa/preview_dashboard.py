"""Isolated component rendering; no application URLs or local server are opened."""
import base64
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path.cwd()
out = root / 'tmp/sam-participation-qa'
groups = [('MUSICO','Músicos',500,250),('ORGANISTA','Organistas',120,32),
          ('CORDAS','Cordas',180,100),('MADEIRAS','Madeiras',170,80),('METAIS','Metais',150,70)]
cities = ['CAUCAIA DO ALTO','COTIA','JANDIRA','SANTANA DE PARNAÍBA','VARGEM GRANDE PAULISTA']
rows = []
for group,label,base,present in groups:
    for i,city in enumerate(cities):
        b=base+i*45;p=present+i*8
        rows.append(dict(event_id='e',event='Ensaio Regional · 15/11/2026',date='2026-11-15',city=city,
                         group=group,label=label,registered=b,present=p,percent=round(p/b*100,2),
                         candidate_base=100,candidate_present=20+i,candidate_percent=20+i))
summaries=[]
for group,label,_,_ in groups:
    values=[r for r in rows if r['group']==group]
    b=sum(r['registered'] for r in values);p=sum(r['present'] for r in values)
    summaries.append(dict(values[0],registered=b,present=p,percent=round(p/b*100,2),candidate_base=500,candidate_present=110,candidate_percent=22))
payload=dict(sam_participation=dict(rows=rows,summaries=summaries,available=True,
    criterion='Cadastro SAM atual. Percentual = presentes ÷ cadastrados × 100.',unresolved_registry=32,undefined_instrument=35))
styles='\n'.join((root/path).read_text(encoding='utf-8') for path in
    ['static/css/vendor.min.css','static/css/default/app.min.css','static/css/music-events.css',
     'static/css/music-events-admin.css','static/css/music-events-participation.css',
     'static/plugins/@fortawesome/fontawesome-free/css/all.css'])
font=base64.b64encode((root/'static/plugins/@fortawesome/fontawesome-free/webfonts/fa-solid-900.woff2').read_bytes()).decode()
styles+=f"\n@font-face{{font-family:'Font Awesome 6 Free';font-weight:900;src:url(data:font/woff2;base64,{font}) format('woff2')}}"
styles+='\nbody{margin:0;background:#e9eef2;padding:24px;font-family:Arial,sans-serif}.events-panel{max-width:1500px;margin:auto} @media(max-width:700px){body{padding:8px}}'
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1500,'height':1050},device_scale_factor=1)
    page.route('**/*',lambda route:route.abort())
    page.set_content('<html><meta charset="utf-8"><style>'+styles+'</style><section id="events-sam-participation" class="events-panel"></section></html>')
    page.evaluate('window.MusicEventsDashboard={download:()=>{}}')
    page.evaluate((root/'static/js/music-events-participation.js').read_text(encoding='utf-8'))
    page.evaluate('(detail)=>document.dispatchEvent(new CustomEvent("music-events-data",{detail}))',payload)
    page.screenshot(path=str(out/'dashboard-desktop.png'),full_page=True)
    page.locator('[data-sam-category="ORGANISTA"]').click()
    assert page.locator('.sam-explore-heading h4').inner_text()=='Indicadores por município'
    assert page.locator('.sam-explore-heading p strong').inner_text()=='Organistas'
    page.locator('[data-sam-mode="candidates"]').click()
    assert page.locator('.sam-city-panel').count()==5
    assert page.locator('.sam-local-kpi').count()==25
    assert page.locator('.sam-insight-card').count()==4
    page.locator('[data-sam-view="table"]').click()
    assert page.locator('.sam-municipal-content table').count()==1
    page.locator('[data-sam-sort]').select_option('rate')
    assert page.locator('.sam-municipal-content tbody tr').first.locator('th').inner_text()=='VARGEM GRANDE PAULISTA'
    page.locator('[data-sam-view="cards"]').click()
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(out/'dashboard-mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'), 'Mobile horizontal overflow'
    assert page.locator('[data-sam-view="cards"]').get_attribute('aria-pressed')=='true'
    page.set_viewport_size({'width':1500,'height':1050})
    page.locator('[data-sam-view="table"]').click()
    assert page.locator('.sam-matrix tbody tr').count()==5
    assert page.locator('.sam-matrix thead th').count()==6
    assert page.locator('.sam-matrix tbody tr').first.locator('td').count()==5
    page.screenshot(path=str(out/'municipal-comparison.png'),full_page=True)
    browser.close()
print('Isolated UI: category, candidate mode, table/cards, sorting and mobile width passed.')
