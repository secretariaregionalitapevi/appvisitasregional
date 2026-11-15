const {test} = require('node:test');
const assert = require('node:assert/strict');
const {JSDOM} = require('jsdom');
const {readFileSync} = require('node:fs');
const {resolve} = require('node:path');

const source = readFileSync(resolve(__dirname, '../../static/js/music-events-justifications.js'), 'utf8');
const event = {id: 'cotia', titulo: 'Ensaio Cotia', data_evento: '2026-11-15', status: 'ABERTO'};
const tick = () => new Promise(resolve => setImmediate(resolve));

function setup() {
  const dom = new JSDOM('<div class="music-events"><select id="events-event"><option value="">Todos</option><option value="cotia">Cotia</option></select><div data-view-panel="conductors"></div><input name="csrfmiddlewaretoken" value="csrf"></div>', {runScripts: 'outside-only', url: 'https://events.example/'});
  const {window} = dom, calls = [], notices = [];
  let resolveEvents, listedItems = [];
  const initial = new Promise(resolve => resolveEvents = resolve);
  window.bootstrap = {Modal: {getOrCreateInstance: () => ({show() {}, hide() {}})}};
  window.AppFeedback = {show: value => {notices.push(value); return {close() {}}}, confirm: async () => true};
  window.MusicEventsDashboard = {
    esc: value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;'),
    refresh: async () => {},
    request: async (url, options) => {
      calls.push({url, options});
      if (url === '/musica/eventos/api/eventos/') return initial;
      if (url.endsWith('/listar/')) return {items: listedItems, evento: event};
      if (url.endsWith('/cadastro/')) return {comuns: [{id:'BR-22-1', comum:'Jardim Cotia', municipio:'COTIA', encarregados:['Encarregado cadastrado']}]};
      if (url.endsWith('/registrar/')) return {item:{id:'saved'}};
      if (url.endsWith('/previa/')) return {token:'preview', rows:[
        {nome:'Encarregado cadastrado', cargo:'Encarregado Local', comum:'Jardim Cotia', municipio:'COTIA', encarregado:'Encarregado cadastrado', encarregados_identificados:['Encarregado cadastrado'], problema:''},
        {nome:'Segundo encarregado', cargo:'Encarregado Local', comum:'Jardim Cotia', municipio:'COTIA', encarregado:'Segundo encarregado', encarregados_identificados:['Segundo encarregado'], problema:''}
      ], ignorados:64};
      throw Error(`Unexpected request ${url}`);
    }
  };
  window.eval(source);
  const $ = id => window.document.querySelector('#just-' + id);
  function dashboardReady() {
    window.document.querySelector('#events-event').value = event.id;
    window.document.dispatchEvent(new window.CustomEvent('music-events-data', {detail:{filters:{evento:event.id}, events:[event]}}));
  }
  function chooseFile() {
    const file = new window.File(['pdf'], 'JUSTIFICATIVA 15-11-2026.pdf', {type:'application/pdf'});
    Object.defineProperty($('file'), 'files', {value:[file], configurable:true});
    $('file').dispatchEvent(new window.Event('change'));
  }
  return {window, $, calls, notices, dashboardReady, chooseFile, setSavedItems: items => listedItems = items, eventsReady: () => resolveEvents({can_manage:true, items:[event]}), close: () => window.close()};
}

for (const order of ['events-first', 'dashboard-first']) {
  test(`event initialization and file preview: ${order}`, async t => {
    const app = setup(); t.after(app.close);
    assert.equal(app.$('preview').disabled, true);
    if (order === 'events-first') {app.eventsReady(); await tick(); app.dashboardReady();}
    else {app.dashboardReady(); app.eventsReady();}
    await tick();
    assert.equal(app.$('event').value, 'cotia');
    app.chooseFile();
    assert.equal(app.$('preview').disabled, false);
    assert.equal(app.$('filename').textContent, 'JUSTIFICATIVA 15-11-2026.pdf');
    app.$('preview').click(); await tick(); await tick();
    const call = app.calls.find(c => c.url.endsWith('/previa/'));
    assert.ok(call.url.includes('/eventos/cotia/'));
    assert.equal(call.options.body.get('arquivo').name, 'JUSTIFICATIVA 15-11-2026.pdf');
    assert.equal(app.$('preview-wrap').hidden, false);
    assert.match(app.$('rows').textContent, /Encarregado cadastrado/);
    assert.match(app.$('rows').textContent, /Segundo encarregado/);
    assert.equal(app.$('rows').querySelectorAll('tr').length, 2);
    assert.equal(app.notices.some(n => n.type === 'error'), false);
  });
}

test('manual justification is created inside the selected event', async t => {
  const app = setup(); t.after(app.close);
  app.dashboardReady(); app.eventsReady(); await tick();
  app.$('register').click(); await tick();
  const doc = app.window.document, common = doc.querySelector('#just-new-common');
  common.value = 'BR-22-1'; common.dispatchEvent(new app.window.Event('change'));
  assert.equal(doc.querySelector('#just-new-person').value, 'Encarregado cadastrado');
  doc.querySelector('#just-new-reason').value = 'Viagem';
  doc.querySelector('#just-new-save').closest('form').dispatchEvent(new app.window.Event('submit', {cancelable:true}));
  await tick(); await tick();
  const call = app.calls.find(c => c.url.endsWith('/registrar/'));
  assert.ok(call.url.includes('/eventos/cotia/'));
  assert.deepEqual(JSON.parse(call.options.body), {comum_chave:'BR-22-1', nome:'Encarregado cadastrado', motivo:'Viagem'});
  assert.equal(doc.querySelector('#just-sync'), null);
  assert.equal(doc.querySelector('#just-link'), null);
});

test('saved justification opens useful detail cards without exposing the batch identifier', async t => {
  const app = setup(); t.after(app.close);
  app.setSavedItems([{
    id:'saved-1', nome:'Michel Frank Bomfim Chaves', comum_nome:'Jardim Cotia', municipio:'COTIA',
    motivo:'Viagem de serviço', origem:'JUSTIFICATIVAS.pdf', bloco:'15/11/2026',
    lote:'raw-batch-identifier', created_by_name:'Secretaria', updated_by_name:'Secretaria'
  }]);
  app.eventsReady(); await tick();
  app.$('event').value = event.id;
  app.$('event').dispatchEvent(new app.window.Event('change'));
  await tick();
  app.window.document.querySelector('#just-saved [data-view="saved-1"]').click();
  const modal = app.window.document.querySelector('.justification-record-modal');
  assert.match(modal.textContent, /Ensaio Cotia/);
  assert.match(modal.textContent, /Michel Frank Bomfim Chaves/);
  assert.match(modal.textContent, /Jardim Cotia/);
  assert.match(modal.textContent, /COTIA/);
  assert.match(modal.textContent, /JUSTIFICATIVAS\.pdf/);
  assert.doesNotMatch(modal.textContent, /raw-batch-identifier/);
  assert.ok(modal.querySelector('.justification-detail-grid'));
  assert.equal(modal.querySelector('#just-edit-person').hidden, true);
  assert.equal(modal.querySelector('#just-edit-reason').readOnly, true);
});

test('newly imported events become selectable without reloading the page', async t => {
  const app = setup(); t.after(app.close);
  app.eventsReady(); await tick();
  const next = {...event, id:'new-cotia', titulo:'Novo ensaio Cotia'};
  app.window.document.querySelector('#events-event').add(new app.window.Option(next.titulo, next.id));
  app.window.document.querySelector('#events-event').value = next.id;
  app.window.document.dispatchEvent(new app.window.CustomEvent('music-events-data', {detail:{filters:{evento:next.id}, events:[next]}}));
  await tick();
  assert.equal(app.$('event').value, next.id);
  app.chooseFile(); app.$('preview').click(); await tick();
  assert.ok(app.calls.find(c => c.url.includes('/eventos/new-cotia/justificativas/previa/')));
});
