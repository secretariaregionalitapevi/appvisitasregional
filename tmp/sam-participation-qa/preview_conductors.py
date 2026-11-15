"""Render a standalone fixture; no local application URLs are opened."""
import base64
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path.cwd();out=root/'tmp/sam-participation-qa'
styles='\n'.join((root/path).read_text(encoding='utf-8') for path in ['static/css/vendor.min.css',
    'static/css/default/app.min.css','static/css/music-events.css','static/css/music-events-admin.css',
    'static/plugins/@fortawesome/fontawesome-free/css/all.css'])
font=base64.b64encode((root/'static/plugins/@fortawesome/fontawesome-free/webfonts/fa-solid-900.woff2').read_bytes()).decode()
styles+=f"\n@font-face{{font-family:'Font Awesome 6 Free';font-weight:900;src:url(data:font/woff2;base64,{font}) format('woff2')}}"
styles+='body{padding:20px;background:#e9eef2;font-family:Arial,sans-serif} .events-panel{padding-bottom:16px} @media(max-width:600px){body{padding:8px}}'
statuses=['PRESENTE','JUSTIFICOU','NAO_JUSTIFICOU','NAO_INFORMADO','SEM_ENCARREGADO','ENFERMO']
rows=[dict(evento='Ensaio Regional',data='2026-11-15',evento_id='e',municipio=city,
           comum='Comum de validação',comum_chave=city,presenca_situacao=status,
           presenca_lista_label=status,observacoes='')
      for city in ['JANDIRA','COTIA'] for status in statuses for _ in range(2 if status=='PRESENTE' else 1)]
markup='''<section class="events-panel"><div class="events-heading"><h2>Presença dos Encarregados Locais</h2></div>
<div id="conductor-summary" class="conductor-summary"></div><div id="conductor-review-progress" class="px-3"></div><div id="conductor-city-summary" class="px-3"></div>
<div id="conductor-notice" class="px-3 small text-muted"></div><div hidden>
<select id="conductor-city-filter"></select><select id="conductor-filter"></select><button id="conductor-add"></button>
<button id="conductor-excel"></button><button id="conductor-pdf"></button><table><tbody id="conductor-body"></tbody></table>
</div><details id="conductor-details"><summary>Conferir registros</summary></details></section>'''
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1500,'height':700})
    page.route('**/*',lambda route:route.abort())
    page.set_content('<html><meta charset="utf-8"><style>'+styles+'</style>'+markup+'</html>')
    page.evaluate("window.MusicEventsDashboard={esc:v=>String(v??''),request:()=>{},feedback:()=>{}}")
    page.evaluate((root/'static/js/music-events-conductors.js').read_text(encoding='utf-8'))
    page.evaluate('(detail)=>document.dispatchEvent(new CustomEvent("music-events-data",{detail}))',
                  dict(events=[dict(id='e',titulo='Ensaio Regional')],conductors=dict(rows=rows,sites=[],catalog=[],available=True)))
    for card in page.locator('.conductor-kpi').all():
        label=card.locator('.conductor-status').bounding_box();num=card.locator('strong').bounding_box()
        assert abs(label['x']+label['width']/2-num['x']-num['width']/2)<1
    headers=page.locator('.conductor-city-table thead th').all()[1:]
    cells=page.locator('.conductor-city-table tbody tr').first.locator('td').all()
    for h,c in zip(headers,cells):
        a=h.locator('span').bounding_box();b=c.locator('span').bounding_box()
        assert abs(a['x']+a['width']/2-b['x']-b['width']/2)<1
    assert page.locator('.conductor-city-table td .PRESENTE').first.evaluate('(e)=>getComputedStyle(e).color')=='rgb(33, 133, 74)'
    assert page.locator('.conductor-city-table td .NAO_JUSTIFICOU').first.evaluate('(e)=>getComputedStyle(e).color')=='rgb(189, 41, 72)'
    assert page.locator('.conductor-kpi.JUSTIFICOU strong').evaluate('(e)=>getComputedStyle(e).color')=='rgb(33, 101, 173)'
    assert page.locator('.conductor-kpi').count()==5
    assert page.locator('.conductor-kpi.NAO_INFORMADO').count()==0
    assert '12 de 14 registros classificados' in page.locator('#conductor-review-progress').inner_text()
    assert page.locator('.conductor-city-table thead th').count()==6
    page.screenshot(path=str(out/'conductors-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(out/'conductors-mobile.png'),full_page=True)
    page.locator('#conductor-review-pending').click()
    assert page.locator('#conductor-filter').input_value()=='NAO_INFORMADO'
    assert page.locator('#conductor-body tr').count()==2
    assert 'PENDENTE DE CONFERÊNCIA' in page.locator('#conductor-body').inner_text()
    assert page.locator('#conductor-details').evaluate('(e)=>e.open')
    browser.close()
print('Conductor cards and table: centers aligned, green/red badges correct, mobile width passed.')
