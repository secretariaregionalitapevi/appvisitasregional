import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ColorAdmin.settings')
import django
django.setup()
from django.template.loader import render_to_string
from django.test import RequestFactory
from playwright.sync_api import sync_playwright
from urllib.parse import urlparse
from ColorAdminApp.modules.account_views import account_context

profile = {'full_name': 'Ricardo Grangeiro', 'email': 'ricardo@example.test',
           'role_id': 1, 'cargo': 'Secretário da Música', 'sector': 'Global',
           'celular': '(11) 94355-7933',
           'municipio': 'ITAPEVI', 'comum': 'BR-22-0673 - VILA DOUTOR CARDOSO'}
out = ROOT / 'tmp' / 'account-qa'
out.mkdir(parents=True, exist_ok=True)
pages = {}
for path, template in [('/extra/profile', 'extra-profile'), ('/extra/settings', 'extra-settings')]:
    request = RequestFactory().get(path)
    request.session = {'authenticated': True, 'user_id': 'test-user', 'user_profile': profile}
    pages[path] = render_to_string('pages/' + template + '.html', account_context(request), request=request)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1920, 'height': 1200})
    writes = []
    errors = []
    cep_calls = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    def respond(route):
        url = urlparse(route.request.url)
        if url.hostname == 'account-ui.test' and url.path == '/extra/profile/cep':
            cep_calls.append(url.path)
            route.fulfill(json={'cep': '06700-241', 'logradouro': 'Rua Coapa', 'bairro': 'Jardim Leonor', 'localidade': 'Cotia', 'uf': 'SP'})
        elif url.hostname != 'account-ui.test':
            route.abort()
        elif route.request.method == 'POST':
            writes.append(route.request.post_data)
            route.fulfill(json={'saved': True, 'full_name': 'Ricardo C. Grangeiro'})
        elif url.path in pages:
            route.fulfill(content_type='text/html', body=pages[url.path])
        elif url.path.startswith('/static/'):
            target = (ROOT / url.path.lstrip('/')).resolve()
            if target.is_relative_to(ROOT) and target.is_file():
                route.fulfill(path=str(target))
            else:
                route.fulfill(status=404, body='')
        else:
            route.fulfill(json={'pending_count': 0})
    page.route('**/*', respond)
    page.goto('https://account-ui.test/extra/profile', wait_until='networkidle')
    page.locator('#account-cep').fill('0670024')
    assert not cep_calls
    page.locator('#account-cep').fill('06700241')
    page.wait_for_function("document.querySelector('#account-street').value === 'Rua Coapa'")
    assert page.locator('#account-cep').input_value() == '06700-241'
    assert page.locator('#account-neighborhood').input_value() == 'Jardim Leonor'
    assert page.locator('#account-number').evaluate('(node) => node === document.activeElement')
    page.locator('#account-number').fill('123')
    page.locator('#account-name').fill('Ricardo C. Grangeiro')
    assert page.locator('#account-name-preview').inner_text() == 'Ricardo C. Grangeiro'
    page.locator('[type=reset]').click()
    page.wait_for_timeout(50)
    assert page.locator('#account-name').input_value() == 'Ricardo Grangeiro'
    page.locator('#account-name').fill('Ricardo C. Grangeiro')
    page.locator('#account-profile-form [type=submit]').click()
    page.locator('#app-feedback-layer').wait_for(state='visible')
    assert len(writes) == 1
    assert page.locator('.navbar-user .fw-bold').inner_text() == 'Ricardo C. Grangeiro'
    assert page.locator('.menu-profile-info .flex-grow-1').inner_text() == 'Ricardo C. Grangeiro'
    page.locator('#app-feedback-layer').evaluate('(node) => node.remove()')
    page.evaluate('scrollTo(0,0)')
    page.wait_for_timeout(150)
    page.screenshot(path=str(out / 'profile-desktop.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.evaluate('scrollTo(0,0)')
    page.wait_for_timeout(150)
    page.screenshot(path=str(out / 'profile-mobile.png'), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#account-remove-avatar').click()
    assert page.locator('#account-remove-avatar-value').input_value() == '1'
    page.locator('[type=reset]').click()
    page.wait_for_timeout(50)
    assert page.locator('#account-remove-avatar-value').input_value() == '0'
    page.goto('https://account-ui.test/extra/settings', wait_until='networkidle')
    before = page.locator('html').get_attribute('data-bs-theme')
    page.locator('[data-account-theme="dark"]').click()
    page.wait_for_timeout(100)
    assert before != page.locator('html').get_attribute('data-bs-theme')
    page.evaluate('scrollTo(0,0)')
    page.wait_for_timeout(150)
    page.screenshot(path=str(out / 'settings-mobile-dark.png'), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), page.evaluate('[...document.querySelectorAll("body *")].filter(n=>n.getBoundingClientRect().right>innerWidth+1).map(n=>n.className).slice(0,20)')
    page.set_viewport_size({'width': 1920, 'height': 1200})
    page.locator('[data-account-theme="light"]').click()
    page.locator('#account-general').scroll_into_view_if_needed()
    page.evaluate('scrollTo(0,0)')
    page.screenshot(path=str(out / 'settings-desktop.png'), full_page=True)
    page.reload(wait_until='networkidle')
    assert page.locator('[data-account-theme="light"]').get_attribute('aria-pressed') == 'true'
    for width in (768, 1024, 1440):
        page.set_viewport_size({'width': width, 'height': 1000})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
    assert not errors, errors
    browser.close()
print('Perfil: salvar, cancelar, nome no menu, prévia; configurações: tema; desktop/mobile sem overflow.')
