const {test} = require('node:test');
const assert = require('node:assert/strict');
const {JSDOM} = require('jsdom');
const {readFileSync} = require('node:fs');
const {resolve} = require('node:path');
const html = readFileSync(resolve(__dirname,'../templates/pages/music_justification_public.html'),'utf8').replace(/{%[\s\S]*?%}/g,'');
const source = readFileSync(resolve(__dirname,'../../static/js/music-justification-public.js'),'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
async function setup() {
  const dom = new JSDOM(html, {runScripts:'outside-only',url:'https://regional.example/justificativas/'});
  const {window} = dom, calls = [], notices = [];
  const nativeTimeout = window.setTimeout.bind(window), nativeClear = window.clearTimeout.bind(window);
  window.setTimeout = (fn, delay) => {if (delay >= 1000) return nativeTimeout(fn, delay); queueMicrotask(fn); return -1;};
  window.clearTimeout = id => {if (id !== -1) nativeClear(id);};
  window.AppFeedback = {show:options => notices.push(options)};
  const csrf = window.document.createElement('input'); csrf.name = 'csrfmiddlewaretoken'; csrf.value = 'csrf'; window.document.body.append(csrf);
  const catalog = {commons:[{codigo:'BR-22-1',nome:'BR-22-1 - CENTRAL',municipio:'COTIA'},
      {codigo:'BR-22-2',nome:'BR-22-2 - VILA',municipio:'ITAPEVI'}],
    events:[{id:'first',titulo:'Ensaio regional Cotia',data_evento:'2099-11-15',hora:'09:00',municipios:['COTIA'],local:'Central de Cotia'},
      {id:'second',titulo:'Reunião musical Cotia',data_evento:'2099-12-01',municipios:['COTIA'],local:'Central de Cotia'}]};
  let saveResolve, searchOverride;
  window.fetch = async (url, options = {}) => {
    calls.push({url,options});
    if (options.method === 'POST') return new Promise(resolve => {saveResolve = resolve;});
    if (url.includes('?')) return searchOverride ? searchOverride(url) : {ok:true,json:async()=>({people:[{nome:'JOSÉ SILVA',cargo:'Encarregado Local',token:'signed-person'}]})};
    return {ok:true,json:async()=>catalog};
  };
  window.eval(source);
  await tick();
  const $ = id => window.document.getElementById(id);
  const change = (id,value,type='change') => {$(id).value = value; $(id).dispatchEvent(new window.Event(type,{bubbles:true}));};
  async function selectPerson() {
    change('ram-city','COTIA'); change('ram-church','BR-22-1 - CENTRAL','input');
    change('ram-person','José','input'); await tick();
    $('ram-people-list').querySelector('button').click();
  }
  return {window,$,change,selectPerson,calls,notices,catalog,close:()=>window.close(),
    finishSave: response => saveResolve(response), overrideSearch:fn => {searchOverride=fn;}};
}

test('Município → comum → evento mais próximo → encarregado, preservando o evento escolhido', async () => {
  const s = await setup();
  try {
    s.change('ram-city','COTIA');
    assert.ok(s.window.document.querySelector('.ram-steps li:first-child .fa-check'));
    assert.equal(s.window.document.querySelector('.ram-steps li:nth-child(2)').getAttribute('aria-current'),'step');
    assert.equal(s.$('ram-event-select').value,'first');
    assert.equal(s.$('ram-event-date').textContent,'15/11/2099 · 09:00');
    assert.equal(s.$('ram-church').disabled,false);
    assert.equal(s.$('ram-person').disabled,true);
    s.change('ram-church','BR-22-1 - CENTRAL','input');
    assert.ok(s.window.document.querySelector('.ram-steps li:nth-child(2) .fa-check'));
    assert.ok(s.window.document.querySelector('.ram-steps li:nth-child(3) .fa-check'));
    assert.equal(s.$('ram-person').disabled,false);
    s.change('ram-event-select','second');
    s.change('ram-person','José','input'); await tick();
    const personOption = s.$('ram-people-list').querySelector('button');
    assert.equal(personOption.querySelector('.ram-avatar').textContent,'J');
    assert.equal(personOption.querySelector('strong').textContent,'José Silva');
    assert.equal(personOption.querySelector('small').textContent,'Encarregado Local');
    s.$('ram-person').dispatchEvent(new s.window.KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true}));
    assert.equal(s.window.document.activeElement.tagName,'BUTTON');
    s.window.document.activeElement.click();
    assert.ok(s.window.document.querySelector('.ram-steps li:nth-child(4) .fa-check'));
    assert.equal(s.$('ram-reason-details').hidden,true);
    s.change('ram-reason-type','Outros');
    assert.equal(s.$('ram-reason-details').hidden,false);
    assert.equal(s.$('ram-reason').required,true);
    assert.equal(s.$('ram-submit').disabled,true);
    s.change('ram-reason','Compromisso familiar','input');
    assert.equal(s.$('ram-submit').disabled,false);
    s.change('ram-reason-type','Trabalho');
    assert.equal(s.$('ram-reason-details').hidden,true);
    assert.equal(s.$('ram-reason').value,'');
    assert.equal(s.$('ram-submit').disabled,false);
    s.$('ram-form').dispatchEvent(new s.window.Event('submit',{cancelable:true}));
    s.$('ram-form').dispatchEvent(new s.window.Event('submit',{cancelable:true}));
    assert.equal(s.calls.filter(c=>c.options.method==='POST').length,1);
    const post = s.calls.find(c=>c.options.method==='POST');
    assert.deepEqual(JSON.parse(post.options.body),{evento:'second',evento_municipio:'COTIA',comum:'BR-22-1',pessoa:'signed-person',motivo:'Trabalho'});
    assert.equal(post.options.headers['X-CSRFToken'],'csrf');
    assert.equal(s.$('ram-fields').disabled,true);
    assert.equal(s.notices.length,0);
    s.finishSave({ok:true,json:async()=>({evento:'Reunião musical Cotia',data:'2099-12-01'})}); await tick();
    assert.equal(s.notices.length,0);
    assert.equal(s.$('ram-form').hidden,true);
    assert.equal(s.$('ram-success').hidden,false);
    assert.equal(s.$('ram-receipt-name').textContent,'José Silva');
    assert.match(s.$('ram-receipt-event').textContent,/01\/12\/2099/);
    assert.equal(s.$('ram-receipt-common').textContent,'Central');
    assert.equal(s.$('ram-receipt-city').textContent,'Cotia');
    s.$('ram-another').click();
    assert.equal(s.$('ram-success').hidden,true);
    assert.equal(s.$('ram-form').hidden,false);
    assert.equal(s.$('ram-person').value,'');
    assert.equal(s.$('ram-submit').disabled,true);
  } finally {s.close();}
});

test('Dropdown de comuns fica no campo e lista somente o município selecionado', async () => {
  const s = await setup();
  try {
    const trigger = s.$('ram-city-trigger'), menu = s.$('ram-city-options');
    trigger.click();
    assert.equal(menu.hidden,false);
    assert.equal(menu.querySelectorAll('.fa-location-dot').length,2);
    [...menu.children].find(item => item.textContent === 'Cotia').click();
    assert.equal(s.$('ram-city').value,'COTIA');
    assert.equal(s.$('ram-city-label').textContent,'Cotia');
    assert.equal(menu.hidden,true);
    trigger.click();
    assert.equal(menu.querySelector('[aria-selected=true] .fa-check').hidden,false);
    trigger.dispatchEvent(new s.window.KeyboardEvent('keydown',{key:'End',bubbles:true}));
    trigger.dispatchEvent(new s.window.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
    assert.equal(s.$('ram-city').value,'ITAPEVI');
    assert.equal(menu.hidden,true);
    s.change('ram-city','COTIA');
    s.$('ram-church').focus();
    assert.equal(s.$('ram-church').hasAttribute('list'),false);
    assert.equal(s.$('ram-commons').hidden,false);
    const buttons = [...s.$('ram-commons').querySelectorAll('button')];
    assert.equal(buttons.length,1);
    assert.equal(buttons[0].querySelector('strong').textContent,'BR-22-1 - CENTRAL');
    assert.equal(buttons[0].querySelector('small').textContent,'COTIA');
    s.change('ram-church','inexistente','input');
    assert.equal(s.$('ram-commons').querySelectorAll('button').length,0);
    s.change('ram-church','central','input');
    s.$('ram-commons').querySelector('button').click();
    assert.equal(s.$('ram-church').value,'BR-22-1 - CENTRAL');
    assert.equal(s.$('ram-commons').hidden,true);
    assert.equal(s.$('ram-person').disabled,false);
    s.change('ram-city','ITAPEVI'); s.$('ram-church').focus(); s.$('ram-church').click();
    assert.equal(s.$('ram-commons').querySelector('small').textContent,'ITAPEVI');
    assert.equal(s.$('ram-commons').textContent.includes('CENTRAL'),false);
  } finally {s.close();}
});

test('Trocar município limpa comum e pessoa e bloqueia município sem evento futuro', async () => {
  const s = await setup();
  try {
    await s.selectPerson(); s.change('ram-reason-type','Trabalho');
    assert.equal(s.$('ram-submit').disabled,false);
    s.change('ram-city','ITAPEVI');
    assert.equal(s.window.document.querySelector('.ram-steps li:nth-child(2) span').textContent,'2');
    assert.equal(s.window.document.querySelector('.ram-steps li:nth-child(3) span').textContent,'3');
    assert.equal(s.window.document.querySelector('.ram-steps li:nth-child(4) span').textContent,'4');
    assert.equal(s.$('ram-church').value,'');
    assert.equal(s.$('ram-person').value,'');
    assert.equal(s.$('ram-person').disabled,true);
    assert.equal(s.$('ram-event-select').value,'');
    assert.equal(s.$('ram-submit').disabled,true);
  } finally {s.close();}
});

test('Busca atrasada não exibe encarregado de outra comum', async () => {
  const s = await setup();
  try {
    let finish;
    s.overrideSearch(() => new Promise(resolve=>{finish=resolve;}));
    s.change('ram-city','COTIA'); s.change('ram-church','BR-22-1 - CENTRAL','input');
    s.change('ram-person','José','input'); await tick();
    s.change('ram-city','ITAPEVI');
    finish({ok:true,json:async()=>({people:[{nome:'Pessoa antiga',token:'old'}]})}); await tick();
    assert.equal(s.$('ram-results').hidden,true);
    assert.equal(s.$('ram-person').value,'');
  } finally {s.close();}
});

test('Cargo de Secretaria aparece na sugestão e pode ser selecionado para justificar', async () => {
  const s = await setup();
  try {
    s.overrideSearch(async()=>({ok:true,json:async()=>({people:[{nome:'RICARDO DA SILVA',cargo:'Secretário da Música',token:'secretary-token'}]})}));
    s.change('ram-city','COTIA'); s.change('ram-church','BR-22-1 - CENTRAL','input');
    s.change('ram-person','Ricardo','input'); await tick();
    const candidate=s.$('ram-people-list').querySelector('button');
    assert.equal(candidate.querySelector('small').textContent,'Secretário da Música');
    candidate.click();
    assert.equal(s.$('ram-name-help').textContent,'Secretário da Música');
    assert.equal(s.window.document.activeElement,s.$('ram-reason-type'));
    s.change('ram-reason-type','Viagem');
    assert.equal(s.$('ram-submit').disabled,false);
  } finally {s.close();}
});

test('Repetir a busca reutiliza o resultado e trocar a comum consulta novamente', async () => {
  const s = await setup();
  try {
    await s.selectPerson();
    const requests = () => s.calls.filter(c=>c.url.includes('?comum='));
    assert.equal(requests().length,1);
    s.change('ram-person','José','input'); await tick();
    assert.equal(requests().length,1);
    assert.equal(s.$('ram-results').hidden,false);
    s.change('ram-city','ITAPEVI'); s.change('ram-church','BR-22-2 - VILA','input');
    s.change('ram-person','José','input'); await tick();
    assert.equal(requests().length,2);
    assert.match(requests()[1].url,/comum=BR-22-2/);
  } finally {s.close();}
});

test('Nao oferece cadastro manual e preserva a comum ao selecionar o nome',async()=>{
 const app=await setup();
 try{
  assert.equal(app.$('ram-manual'),null);
  await app.selectPerson();
  assert.equal(app.$('ram-church').value,'BR-22-1 - CENTRAL');
  assert.equal(app.$('ram-city').value,'COTIA');
 }finally{app.close();}
});

test('Eventos mostram apenas os dois proximos e um terceiro desabilitado',async()=>{
 const app=await setup();
 try{
  app.catalog.events.push({id:'third',titulo:'Terceiro',data_evento:'2099-12-02',municipios:['COTIA']},{id:'fourth',titulo:'Quarto',data_evento:'2099-12-03',municipios:['COTIA']});
  app.change('ram-city','COTIA');
  const options=[...app.$('ram-event-select').options];
  assert.equal(options.length,3);
  assert.deepEqual(options.map(o=>o.value),['first','second','third']);
  assert.deepEqual(options.map(o=>o.disabled),[false,false,true]);
  assert.match(options[2].textContent,/Em breve/);
 }finally{app.close();}
});

