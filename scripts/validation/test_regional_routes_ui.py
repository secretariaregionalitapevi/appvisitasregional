"""QA offline do planejador e da impressao. Nao abre localhost nem consulta dados reais."""
import json
import os
import re
import sys
from copy import deepcopy
from unittest.mock import patch
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ColorAdmin.settings')
import django
django.setup()
from django.template.loader import render_to_string
from django.test import RequestFactory
from playwright.sync_api import sync_playwright
from pypdf import PdfReader

from ColorAdminApp.tests.tests_regional_routes import members, teams, COMMONS, DAY
from ColorAdminApp.modules.regional_routes import build_plan, finalize_plan

out = ROOT / 'relatorios' / 'qa-roteiro-regional'
out.mkdir(parents=True, exist_ok=True)
request = RequestFactory().get('/')
request.session = {'authenticated':True, 'user_profile':{'full_name':'Operador de teste','role_id':1}}
catalog = [{'comum':c, 'cidade':'ITAPEVI'} for c in COMMONS]
catalog.append({'comum':'COMUM C','cidade':'ITAPEVI'})
catalog.append({'comum':'COMUM DE JANDIRA','cidade':'JANDIRA'})
html = render_to_string('pages/visitas-roteiro-regional.html', {
    'comuns':catalog, 'municipios':['ITAPEVI','JANDIRA'], 'municipio_padrao':'ITAPEVI',
    'appHeaderHide':True,'appSidebarHide':True,
}, request=request)
# Guardar tambem a pagina com os scripts reais, sem inicializacao artificial.
full_html=html
# As respostas continuam interceptadas; nao ha consultas de producao.
html = re.sub(r'<script\b[^>]*src=[^>]+>\s*</script>', '', html)
plan = finalize_plan(build_plan(members(), [], teams(), DAY, 'ITAPEVI', COMMONS))
state = {'groups':[dict(g,coordenador_cadastrado=g['coordenador_nome'],coordenador_cadastro_valor=g['coordenador_nome'],cadastro_disponivel=True,participacao_salva=False) for g in teams()], 'confirm_calls':0}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True,args=['--log-file='+str(out/'browser-debug.log')])
    page = browser.new_page(viewport={'width':1365,'height':1000})
    def route_handler(route):
        url = urlparse(route.request.url)
        if url.hostname != 'regional-planner.test':
            route.abort()
        elif url.path.startswith('/static/'):
            path = (ROOT / url.path.lstrip('/')).resolve()
            if path.is_relative_to(ROOT) and path.is_file():
                route.fulfill(path=str(path))
            else:
                route.fulfill(status=404,body='')
        elif url.path == '/visitas/api/roteiro-regional/':
            if route.request.method == 'GET':
                if state.pop('fail_next_load',False):
                    route.fulfill(status=503,json={'error':'Falha de conexão de teste. Tente novamente.'})
                    return
                state['last_city']=parse_qs(url.query).get('municipio',[''])[0]
                state['loads']=state.get('loads',0)+1
                result = {'groups':state['groups'],'plans':([{'print_url':'/visitas/roteiro-regional/00000000-0000-0000-0000-000000000001/','created_at':'2026-11-17T12:00:00-03:00'}] if state.get('legacy_plan') else []),'agenda_summary':{'families':0,'groups':0}}
            else:
                payload = route.request.post_data_json
                if payload['action'] == 'participation':
                    prior={g['id']:g for g in state['groups']}
                    state['groups']=[dict(g,ativo=True,nome='Grupo '+chr(65+int(g['id'])),participacao_salva=True,
                        coordenador_cadastrado=g['coordenador_nome'] if g.get('atualizar_cadastro') else prior[g['id']]['coordenador_cadastrado'],
                        coordenador_cadastro_valor=g['coordenador_nome'] if g.get('atualizar_cadastro') else prior[g['id']]['coordenador_cadastro_valor']) for g in payload['groups']]
                    result={'groups':state['groups'],'saved':True}
                elif payload['action'] == 'preview':
                    assert 'capacidade' not in payload
                    if state.get('full_distribution'):
                        assert len(payload['comuns'])==3 and len(payload['grupos'])==4
                        people=members(100)
                        selected_commons=COMMONS+['COMUM C']
                        for index,person in enumerate(people):person['comum']=selected_commons[index%3]
                        current_plan=finalize_plan(build_plan(people,[],teams(4),DAY,'ITAPEVI',selected_commons))
                    else:
                        assert len(payload['comuns']) == 2
                        assert len(payload['grupos']) == 7
                        current_plan=plan
                    for group in current_plan['groups']:
                        group['coordenador_nome']=next(g['coordenador_nome'] for g in state['groups'] if g['id']==group['id'])
                    result={'plan':current_plan,'token':'offline-test-token'}
                elif payload['action']=='remove_commons':
                    assert payload['token']=='offline-delete-token'
                    state['delete_calls']=state.get('delete_calls',0)+1
                    state['last_removal']=payload
                    existing=state.get('remaining_commons',COMMONS+(['COMUM C'] if state.get('full_distribution') else []))
                    remaining=[c for c in existing if c not in payload['comuns']]
                    state['remaining_commons']=remaining
                    state['legacy_plan']=bool(remaining)
                    result={'deleted':len(payload['agenda_comuns']),'removed_commons':payload['comuns'],'remaining_commons':remaining}
                else:
                    assert payload['action'] == 'confirm'
                    assert len(payload['assignments']) == (100 if state.get('full_distribution') else 7)
                    if state.get('edited_key'):assert payload['assignments'][state['edited_key']]==state['edited_group']
                    state['confirm_calls'] += 1
                    result={'saved':True,'agenda_summary':{'families':7,'groups':7},'print_url':'/visitas/roteiro-regional/00000000-0000-0000-0000-000000000001/'}
            route.fulfill(json=result)
        elif url.path.startswith('/visitas/roteiro-regional/'):
            if parse_qs(url.query).get('formato')==['pdf']:
                route.fulfill(content_type='application/pdf',body=b'%PDF-1.4\n% offline download fixture',headers={'Content-Disposition':"attachment; filename*=UTF-8''ROTEIRO_VISITAS_JARDIM_RUTH_GRUPO_A.pdf"})
                return
            base=url.path
            result={'id':'00000000-0000-0000-0000-000000000001','deletion':{'available':not state.get('delete_protected'),'count':100,'token':'offline-delete-token','reason':'Visitas já encerradas.' if state.get('delete_protected') else ''},
                'removal':{'available':not state.get('delete_protected'),'commons':[{'common':c,'scheduled':1} for c in state.get('remaining_commons',COMMONS+(['COMUM C'] if state.get('full_distribution') else []))],
                           'token':'offline-delete-token','reason':'Exclusão indisponível.' if state.get('delete_protected') else ''},
                'coverage':[{'common':c,'records':10,'included_records':10,'families':10} for c in COMMONS],
                'commons':COMMONS+(['COMUM C'] if state.get('full_distribution') else []),'requires_route_refresh':bool(state.get('legacy_plan')),'groups':[{'id':g['id'],'name':g['nome'],'coordinator':g['coordenador_nome'],'families':1,'commons':COMMONS,
                'print_url':base+'?grupo='+g['id'],'pdf_url':base+'?grupo='+g['id']+'&formato=pdf'} for g in state['groups'] if g['confirmado']],
                'zip_url':base+'?formato=zip','excel_url':base+'?formato=excel'}
            route.fulfill(json=result)
        elif url.path == '/visitas/api/equipes/':
            if parse_qs(url.query).get('modo')==['catalogo']:
                result=[dict(g,tipo='REGIONAL',municipio='ITAPEVI',comum=None,coordenador_nome=g['coordenador_cadastrado']) for g in state['groups']]
            else:
                result=[{'id':'source','nome':'Coordenador 0','grupo_regional_id':'0','equipe_id':None,
                         'comum':COMMONS[0],'municipio':'ITAPEVI','status':'Ativo','cargo_outros':'Coordenador'}]
            route.fulfill(json=result)
        else:
            route.fulfill(content_type='text/html',body=state.get('page_html',html))
    page.route('**/*', route_handler)
    page.goto('https://regional-planner.test/')
    page.evaluate('window.AppFeedback={show:options=>{window.lastFeedback=options;}}')
    page.add_script_tag(path=str(ROOT/'static/plugins/jquery/dist/jquery.min.js'))
    page.add_script_tag(path=str(ROOT/'static/plugins/select2/dist/js/select2.min.js'))
    page.add_script_tag(path=str(ROOT/'static/js/app-export.js'))
    page.add_script_tag(content=(ROOT/'static/js/visitas/roteiro-regional.js').read_text(encoding='utf-8'))
    page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")
    page.locator('#regional-date').fill(DAY)
    assert page.locator('#regional-capacity').count()==0
    page.locator('#regional-load').click()
    page.wait_for_selector('[data-group]',state='attached')
    assert page.locator('[data-group] [type=checkbox]:checked').count()==7
    assert page.locator('#regional-metric-groups').inner_text()=='7'
    assert page.locator('#regional-metric-scheduled').inner_text()=='0'
    assert page.locator('[data-group]').first.locator('input:not([type=checkbox])').input_value()=='Coordenador 0'
    assert page.locator('#regional-preview').is_disabled()
    assert page.get_by_role('button',name='Usar cadastrado').count()==0
    for query,label in [('RUTH','JARDIM RUTH'),('CHACARAS','VILA DAS CHACARAS')]:
        page.locator('#regional-commons + .select2 .select2-selection').click()
        page.locator('.select2-search__field').fill(query)
        page.locator('.select2-results').get_by_role('option',name=label,exact=True).click()
        assert page.locator('.select2-search__field').input_value()==''
        assert page.locator('.select2-container--open').count()==0
    page.keyboard.press('Escape')
    # Sem clicar em salvar nem em restaurar nomes: calcular salva os padroes.
    page.locator('#regional-preview').click()
    page.wait_for_selector('[data-house]',state='attached')
    assert all(g['participacao_salva'] for g in state['groups'])
    assert not page.locator('#regional-team-panel').evaluate('(panel)=>panel.open')
    page.locator('#regional-team-panel > summary').click()
    page.locator('[data-remove-coordinator="0"]').click()
    first_row=page.locator('[data-group]').first
    assert not first_row.locator('[type=checkbox]').is_checked()
    assert first_row.locator('input:not([type=checkbox])').input_value()==''
    first_row.locator('[type=checkbox]').check()
    assert first_row.locator('input:not([type=checkbox])').input_value()=='Coordenador 0'
    page.locator('[data-group]').first.locator('input:not([type=checkbox])').fill('Manoel')
    page.locator('[data-group]').last.locator('[type=checkbox]').uncheck()
    page.locator('#regional-save').click()
    page.wait_for_function("window.lastFeedback?.type==='success'")
    assert not state['groups'][-1]['confirmado']
    assert not page.locator('#regional-team-panel').evaluate('(panel)=>panel.open')
    page.locator('#regional-team-panel > summary').click()
    page.locator('[data-group]').last.locator('[type=checkbox]').check()
    page.locator('#regional-save').click()
    page.wait_for_function("!document.getElementById('regional-preview').disabled")
    assert state['groups'][0]['coordenador_nome']=='Manoel'
    assert page.locator('#regional-commons').evaluate('(select)=>select.selectedOptions.length')==2
    page.locator('#regional-preview').click()
    page.wait_for_selector('[data-house]',state='attached')
    assert page.locator('[data-house]').count() == 7
    assert page.locator('#regional-metric-families').inner_text()=='7'
    assert page.locator('#regional-metric-distribution').inner_text()=='1'
    assert page.locator('#regional-houses').text_content().count('JARDIM RUTH') == 4
    assert not page.locator('#regional-families-panel').evaluate('(p)=>p.open')
    page.screenshot(path=str(out/'planner-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(out/'planner-mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    page.locator('#regional-families-panel > summary').click()
    page.locator('[data-house]').first.select_option('1')
    page.locator('#regional-confirm').click()
    page.wait_for_selector('#regional-export-groups [data-app-export]')
    assert page.locator('#regional-export-groups [data-app-export]').count()==7
    assert 'formato=zip' in page.locator('#regional-export-pdf').get_attribute('href')
    assert state['confirm_calls'] == 1
    assert page.locator('[data-house]:enabled').count() == 0
    assert page.locator('#regional-metric-scheduled').inner_text()=='7'
    with page.expect_download() as download:
        page.locator('#regional-export-groups [data-app-export]').first.click()
    assert download.value.suggested_filename=='ROTEIRO_VISITAS_JARDIM_RUTH_GRUPO_A.pdf'
    assert page.locator('#regional-export-groups [data-app-export]').first.get_attribute('aria-busy') is None
    page.screenshot(path=str(out/'export-panel-mobile.png'),full_page=True)

    # Regra solicitada: todas as 100 familias de 3 comuns entram, 25 por grupo.
    page.locator('#regional-team-panel > summary').click()
    for row in page.locator('[data-group]').all()[4:]:row.locator('[type=checkbox]').uncheck()
    page.locator('#regional-save').click()
    page.wait_for_function("!document.getElementById('regional-preview').disabled")
    if not page.locator('#regional-common-panel').evaluate('(p)=>p.open'):page.locator('#regional-common-panel > summary').click()
    page.locator('#regional-commons + .select2 .select2-selection').click()
    page.locator('.select2-search__field').fill('COMUM C')
    page.locator('.select2-results').get_by_role('option',name='COMUM C',exact=True).click()
    page.keyboard.press('Escape')
    state['full_distribution']=True
    page.locator('#regional-preview').click()
    page.wait_for_function("document.querySelectorAll('[data-house]').length===10")
    summary=page.locator('#regional-summary').inner_text()
    for group_id in range(4):assert page.locator(f'[data-group-summary="{group_id}"] .rr-group-value').inner_text()=='25'
    assert '100 famílias · 4 grupos' in summary
    assert page.locator('#regional-metric-families').inner_text()=='100'
    assert page.locator('#regional-metric-distribution').inner_text()=='25'
    assert 'aguardando capacidade' not in summary
    page.locator('#regional-summary').screenshot(path=str(out/'distribution-100-families-4-groups.png'))
    assert not page.locator('#regional-families-panel').evaluate('(p)=>p.open')
    page.set_viewport_size({'width':1365,'height':1000})
    page.screenshot(path=str(out/'planner-compact-desktop.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollHeight')<1400
    assert page.locator('#regional-exports').is_hidden()
    page.locator('#regional-families-panel > summary').click()
    page.locator('#regional-family-next').click()
    edited=page.locator('[data-house]').first
    state['edited_key']=edited.get_attribute('data-house')
    state['edited_group']='1' if edited.input_value()!='1' else '0'
    edited.select_option(state['edited_group'])
    page.locator('#regional-family-search').fill('Familia 99')
    assert page.locator('[data-house]').count()==1
    page.locator('#regional-family-search').fill('')
    page.locator('#regional-family-next').click()
    assert page.locator(f'[data-house="{state["edited_key"]}"]').input_value()==state['edited_group']
    page.locator('[data-group-summary="1"]').click()
    assert page.locator('#regional-family-group').input_value()=='1'
    assert page.locator('[data-house]').count()<=10
    page.locator('#regional-confirm').click()
    page.wait_for_selector('#regional-export-groups [data-app-export]')
    assert state['confirm_calls']==2
    assert page.locator('#regional-preview-panel').is_hidden()
    assert page.locator('#regional-export-groups .fa-file-pdf.text-danger').count()==4
    assert page.locator('#regional-export-pdf .fa-file-pdf.text-danger').count()==1

    state['groups'][-1]['confirmado']=False
    team_request=RequestFactory().get('/',{'data':DAY,'municipio':'ITAPEVI'})
    team_request.session=request.session
    directory_html=render_to_string('pages/visitas-equipes.html',{
        'comuns':catalog,'municipios':['ITAPEVI'],'municipio_padrao':'ITAPEVI',
        'can_plan_regional':True,'appHeaderHide':True,'appSidebarHide':True,
    },request=team_request)
    state['page_html']=re.sub(r'<script\b[^>]*src=[^>]+>\s*</script>','',directory_html)
    page.goto('https://regional-planner.test/equipes-offline/')
    page.add_script_tag(path=str(ROOT/'static/plugins/jquery/dist/jquery.min.js'))
    page.add_script_tag(path=str(ROOT/'static/plugins/select2/dist/js/select2.min.js'))
    page.evaluate('window.bootstrap={Modal:class{show(){}hide(){}}};window.AppFeedback={show:()=>({close(){}})};')
    page.add_script_tag(content=(ROOT/'static/js/visitas/equipes.js').read_text(encoding='utf-8'))
    page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")
    page.wait_for_selector('#teams-list .team-section')
    first=page.locator('#teams-list .team-section').first
    assert 'Manoel' in first.inner_text()
    assert 'Substituição registrada para esta data' not in first.inner_text()
    assert 'Manoel' in first.locator('.team-coordinator').inner_text()
    assert 'Coordenador cadastrado' in first.inner_text()
    assert 'Desabilitado nesta data' in page.locator('#teams-list .team-section').last.inner_text()
    assert 'data='+DAY in first.get_by_role('link',name='Ajustar nesta data').get_attribute('href')
    page.screenshot(path=str(out/'teams-daily-mobile.png'),full_page=True)

    people=members(8)
    # Duas familias por casa, de comuns distintas: validar origem na impressao.
    for m in deepcopy(people):
        m['id']='other-'+m['id'];m['nome']='Outra familia '+m['id'];m['comum']=COMMONS[1]
        people.append(m)
    report=finalize_plan(build_plan(people,[],teams(1),DAY,'ITAPEVI',COMMONS))
    report['issued_at']='17/11/2026 12:00'
    group=report['groups'][0]
    group['houses']=sorted(report['houses'],key=lambda h:h['number'])
    from ColorAdminApp.modules.regional_route_reports import prepare_navigation,decorate_groups,build_group_pdf,original_route_context
    group['origins']={COMMONS[0]:[-23.54,-46.981]}
    prepare_navigation([group],report['city'],request)
    decorate_groups([group])
    from ColorAdminApp.tests.regional_route_fixtures import offline_map_data
    with patch('ColorAdminApp.modules.regional_route_map.google_route_map',side_effect=offline_map_data):
        (out/'ROTEIRO_VISITAS_MODELO_RESTAURADO_GRUPO_A.pdf').write_bytes(build_group_pdf(report,group,request))
    print_html=render_to_string('pages/visitas-roteiro-regional-impresso.html',{
        'plan':report,'groups':[group],'visit_date':'17/10/2099','file_date':'17_10_2099',
    },request=request)
    page.set_viewport_size({'width':1100,'height':1000})
    page.set_content(print_html)
    page.emulate_media(media='print')
    page.pdf(path=str(out/'roteiro-validacao.pdf'),prefer_css_page_size=True,print_background=True)

    # A visualizacao individual reutiliza o template original, incluindo mapa.
    legacy=original_route_context(report,group,request)
    legacy.update({'appHeaderHide':True,'appSidebarHide':True})
    legacy_html=render_to_string('pages/visitas-roteiro-impresso.html',legacy,request=request)
    page.set_content(legacy_html)
    assert page.locator('.visit-card').count()==8
    assert 'da congregação' in page.locator('.visit-card').first.inner_text()
    assert 'do último ponto' in page.locator('.visit-card').nth(1).inner_text()
    page.pdf(path=str(out/'roteiro-template-original.pdf'),prefer_css_page_size=True,print_background=True)

    # Pagina completa: vendor, app, feedback e o planner reais. Sem disparar DOMContentLoaded.
    state['page_html']=full_html
    page.emulate_media(media='screen')
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('https://regional-planner.test/full-page/')
    page.wait_for_selector('[data-group]',state='attached')
    assert not page.locator('#regional-load').is_disabled()
    page.locator('#regional-city').select_option('JANDIRA')
    page.wait_for_function("document.getElementById('regional-metric-groups').textContent!=='—'")
    assert state['last_city']=='JANDIRA'
    assert page.locator('#regional-commons option').count()==1
    page.locator('#regional-city').select_option('ITAPEVI')
    page.wait_for_function("document.getElementById('regional-metric-groups').textContent!=='—'")
    assert state['last_city']=='ITAPEVI'
    assert page.locator('#regional-load-error').is_hidden()
    assert not errors,errors
    state['fail_next_load']=True
    page.locator('#regional-load').click()
    page.wait_for_selector('#regional-load-error')
    assert 'Falha de conexão' in page.locator('#regional-load-error').inner_text()
    page.locator('.app-feedback-close').click()
    page.locator('#regional-load').click()
    page.wait_for_function("document.getElementById('regional-metric-groups').textContent!=='—'")
    assert page.locator('#regional-load-error').is_hidden()
    page.screenshot(path=str(out/'planner-real-scripts.png'),full_page=True)
    state['legacy_plan']=True
    page.locator('#regional-load').click()
    page.wait_for_selector('#regional-export-groups [aria-disabled=true]')
    assert page.locator('#regional-export-pdf').get_attribute('href') is None
    page.locator('#regional-refresh-route').click()
    page.wait_for_function("document.querySelectorAll('[data-house]').length===10")
    assert page.locator('#regional-commons').evaluate('(s)=>s.selectedOptions.length')==3
    state['delete_protected']=True
    page.locator('#regional-load').click()
    page.wait_for_selector('#regional-delete-note')
    assert page.locator('#regional-delete-plan').is_disabled()
    state['delete_protected']=False
    page.locator('#regional-load').click()
    page.wait_for_function("!document.getElementById('regional-delete-plan').disabled")
    coverage=page.locator('#regional-export-coverage').bounding_box()
    export_groups=page.locator('#regional-export-groups').bounding_box()
    assert export_groups['y']-(coverage['y']+coverage['height'])>=16
    page.screenshot(path=str(out/'export-delete-and-spacing.png'),full_page=True)
    page.locator('#regional-delete-plan').click()
    page.locator('#regional-remove-modal').wait_for(state='visible')
    assert page.locator('#regional-remove-submit').is_disabled()
    assert page.locator('[data-remove-agenda="0"]').is_disabled()
    page.locator('#regional-remove-modal .app-btn-cancel').click()
    page.locator('#regional-remove-modal').wait_for(state='hidden')
    assert state.get('delete_calls',0)==0
    page.locator('#regional-delete-plan').click()
    page.locator('[data-remove-common="0"]').check()
    page.locator('[data-remove-agenda="0"]').check()
    assert page.locator('[data-remove-common="1"]').is_checked() is False
    assert page.locator('[data-remove-agenda="1"]').is_disabled()
    for checkbox in page.locator('#regional-remove-modal input[type=checkbox]').all():
        cell=checkbox.locator('xpath=../..').bounding_box()
        box=checkbox.bounding_box()
        assert abs((box['x']+box['width']/2)-(cell['x']+cell['width']/2))<2
    page.locator('#regional-remove-modal .modal-content').screenshot(path=str(out/'remove-commons-modal-desktop.png'))
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#regional-remove-modal .modal-content').screenshot(path=str(out/'remove-commons-modal-mobile.png'))
    assert page.locator('#regional-remove-modal .modal-content').bounding_box()['width']<=390
    page.set_viewport_size({'width':1365,'height':1000})
    page.screenshot(path=str(out/'remove-selected-common-and-calendar.png'),full_page=True)
    page.locator('#regional-remove-submit').click()
    page.locator('#app-feedback-layer [data-result=true]').click()
    page.wait_for_selector('#app-feedback-layer .app-feedback-card.success')
    assert state['delete_calls']==1
    assert state['last_removal']['comuns']==[COMMONS[0]]
    assert state['last_removal']['agenda_comuns']==[COMMONS[0]]
    assert COMMONS[1] in state['remaining_commons']
    page.locator('.app-feedback-close').click()
    page.locator('#regional-delete-plan').click()
    page.locator('#regional-remove-modal').wait_for(state='visible')
    for checkbox in page.locator('[data-remove-common]').all():checkbox.check()
    assert page.locator('[data-remove-agenda]:checked').count()==0
    page.locator('#regional-remove-submit').click()
    page.locator('#app-feedback-layer [data-result=true]').click()
    page.wait_for_selector('#app-feedback-layer .app-feedback-card.success')
    assert state['delete_calls']==2
    assert state['last_removal']['agenda_comuns']==[]
    assert page.locator('#regional-exports').is_hidden()
    browser.close()

reader=PdfReader(out/'ROTEIRO_VISITAS_MODELO_RESTAURADO_GRUPO_A.pdf')
for index,pdf_page in enumerate(reader.pages):
    text=pdf_page.extract_text()
    assert 'CONGREGAÇÃO CRISTÃ NO BRASIL' in text, f'Cabecalho ausente na pagina {index+1}'
    assert 'Impresso por:' in text
    assert 'JARDIM RUTH' in text or 'VILA DAS CHACARAS' in text
print(f'UI desktop/mobile, ajuste manual, confirmacao unica e PDF com {len(reader.pages)} paginas: OK.')
