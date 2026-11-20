const {test} = require('node:test');
const assert = require('node:assert/strict');
const {JSDOM} = require('jsdom');
const {readFileSync} = require('node:fs');
const {resolve} = require('node:path');
const tick = () => new Promise(resolve=>setImmediate(resolve));
const html = readFileSync(resolve(__dirname,'../templates/pages/music_justifications.html'),'utf8').replace(/{%[\s\S]*?%}/g,'');
const source = readFileSync(resolve(__dirname,'../../static/js/music-justifications-panel.js'),'utf8');
test('Exportação usa os filtros, bloqueia repetição e mostra progresso somente no botão',async()=>{
  const dom = new JSDOM(html,{runScripts:'outside-only',url:'https://regional.example/musica/justificativas/'});
  const {window} = dom, calls = [], notices = [];
  let complete;
  window.AppFeedback={show:options=>notices.push(options)};
  window.URL.createObjectURL=()=> 'blob:test'; window.URL.revokeObjectURL=()=>{};
  window.HTMLAnchorElement.prototype.click=function(){};
  window.setTimeout=fn=>{queueMicrotask(fn);return 1;};
  const data={items:[],metrics:{total:0,ENSAIO_REGIONAL:0,REUNIAO_TECNICA:0,REUNIAO_MINISTERIO:0,pendentes:0},
    options:{cities:['COTIA'],commons:[{id:'Central',titulo:'Central',municipio:'COTIA'}],events:[{id:'legado:ensaio',titulo:'Ensaio regional 15/11'}]},can_manage:false};
  window.fetch=async url=>{
    calls.push(url);
    if(url.includes('exportar-'))return new Promise(resolve=>{complete=resolve;});
    return {ok:true,json:async()=>data};
  };
  try{
    window.eval(source);await tick();
    const $=id=>window.document.getElementById(id);
    assert.equal($('jp-name'),null);assert.equal($('jp-start'),null);assert.equal($('jp-end'),null);
    assert.ok(window.document.querySelector('.management-hero .management-event'));
    assert.ok(window.document.querySelector('.management-controls .management-actions'));
    assert.equal(window.document.querySelectorAll('.management-metric').length,4);
    $('jp-city').value='COTIA';$('jp-event').value='legado:ensaio';
    $('jp-pdf').click();$('jp-pdf').click();$('jp-excel').click();
    assert.equal(calls.filter(url=>url.includes('exportar-')).length,1);
    assert.match(calls.at(-1),/municipio=COTIA/);assert.match(calls.at(-1),/evento=legado%3Aensaio/);
    assert.equal($('jp-pdf').disabled,true);assert.equal($('jp-excel').disabled,true);
    assert.match($('jp-pdf').innerHTML,/fa-spinner/);assert.equal(notices.length,0);
    complete({ok:true,redirected:false,headers:{get:key=>key==='Content-Type'?'application/pdf':"attachment; filename*=UTF-8''justificativas.pdf"},blob:async()=>new window.Blob(['pdf'])});
    await tick();assert.equal($('jp-pdf').disabled,false);assert.equal($('jp-pdf').textContent,'PDF');
    assert.equal(notices.length,0);
  }finally{window.close();}
});

test('Registros agrupam evento e municípios e retiram o nome repetido do motivo',async()=>{
  const dom = new JSDOM(html,{runScripts:'outside-only',url:'https://regional.example/musica/justificativas/'});
  const {window} = dom;
  const base={event_key:'legado:ensaio',agenda_id:'legado:ensaio',evento_titulo:'Ensaio Regional · 15/11/2026',
    data_evento:'2026-11-15',familia:'GERAL',hora:'',local:'',destino:'ensaio',destino_url:'/musica/ensaios-regionais/?evento=ensaio',
    created_at:'2026-11-16T19:47:30Z',candidates:[],cargo:'Encarregado Local'};
  const data={items:[
    {...base,nome:'ROBERTO DA SILVA',comum:'BR-22-1 - CENTRAL',municipio:'COTIA',motivo:'ROBERTO DA SILVA: Trabalho'},
    {...base,nome:'JORGE AMÂNCIO',comum:'BR-22-2 - JARDIM ISAURA',municipio:'SANTANA DE PARNAÍBA',motivo:'Enfermidade'}
  ],metrics:{total:2,ENSAIO_REGIONAL:2,REUNIAO_TECNICA:0,REUNIAO_MINISTERIO:0,pendentes:0},
  options:{cities:['COTIA','SANTANA DE PARNAÍBA'],commons:[],events:[{id:'legado:ensaio',titulo:'Ensaio Regional · 15/11/2026'}]},can_manage:false};
  const notices=[];window.AppFeedback={show:options=>notices.push(options)};
  window.fetch=async()=>({ok:true,json:async()=>data});
  try{
    window.eval(source);await tick();
    const records=window.document.getElementById('jp-rows');
    assert.equal(notices.length,0);
    assert.equal(records.querySelectorAll('.jp-record-event').length,1);
    assert.equal(records.querySelector('h3').textContent,'Ensaio Regional');
    assert.equal(records.querySelectorAll('.jp-record-city').length,2);
    assert.equal(records.querySelectorAll('tbody tr').length,2);
    assert.equal(records.querySelectorAll('.jp-event-actions a').length,1);
    assert.equal(records.querySelector('.jp-reason-tag.work').textContent,'Trabalho');
    assert.equal(records.querySelector('.jp-reason-tag.health').textContent,'Enfermidade');
    assert.equal(records.textContent.includes('ROBERTO DA SILVA:'),false);
    assert.equal(records.textContent.includes('16:47:30'),false);
    assert.equal(records.querySelector('.jp-person-name').textContent,'Roberto da Silva');
    assert.equal(records.querySelector('.jp-person-role').textContent,'Encarregado Local');
    assert.equal(records.querySelector('.jp-record-table thead tr').children.length,4);
    assert.equal(data.items[0].motivo,'ROBERTO DA SILVA: Trabalho');
  }finally{window.close();}
});

test('Excluir exige confirmação e recarrega os totais após a exclusão',async()=>{
  const dom=new JSDOM(html,{runScripts:'outside-only',url:'https://regional.example/musica/justificativas/'});
  const {window}=dom,calls=[],notices=[];let confirmed=false,removed=false;
  const csrf=window.document.createElement('input');csrf.name='csrfmiddlewaretoken';csrf.value='test';window.document.body.append(csrf);
  const row={id:'j1',delete_token:'signed-selection',nome:'Ricardo',cargo:'Secretário da Música',comum:'BR-22-0673 - Vila Doutor Cardoso',municipio:'ITAPEVI',data_evento:'2026-11-28',evento_titulo:'Reunião Geral da Música',tipo:'REUNIAO_MINISTERIO',familia:'GERAL',created_at:'2026-11-20T17:47:00Z',motivo:'Trabalho'};
  window.AppFeedback={confirm:async()=>confirmed,show:options=>notices.push(options)};
  window.fetch=async(url,options={})=>{
    calls.push({url,options});
    if(options.method==='POST'){removed=true;return {ok:true,json:async()=>({deleted:true})};}
    return {ok:true,json:async()=>({items:removed?[]:[row],can_delete:true,metrics:{total:removed?0:1,ENSAIO_REGIONAL:0,REUNIAO_TECNICA:0,REUNIAO_MINISTERIO:1,pendentes:1},groups:[],options:{cities:[],commons:[],events:[]}})};
  };
  try{
    window.eval(source);await tick();
    window.document.querySelector('.jp-delete').click();await tick();
    assert.equal(calls.filter(c=>c.options.method==='POST').length,0);
    confirmed=true;window.document.querySelector('.jp-delete').click();await tick();await tick();
    const post=calls.find(c=>c.options.method==='POST');assert.deepEqual(JSON.parse(post.options.body),{action:'delete',token:'signed-selection'});
    assert.equal(window.document.querySelector('.jp-delete'),null);
    assert.match(window.document.getElementById('jp-records-count').textContent,/0 registros/);
    assert.equal(notices.at(-1).title,'Justificativa Excluída');
  }finally{window.close();}
});
