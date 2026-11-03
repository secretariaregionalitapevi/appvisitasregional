const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('static/js/music-ministry.js','utf8');
const elements=new Map();
function $(selector){
  if(!elements.has(selector))elements.set(selector,{value:'',innerHTML:'',textContent:'',disabled:false,open:false,
    options:[],selectedOptions:[{textContent:'Encarregado local'}],querySelectorAll:()=>[],
    addEventListener(){},setAttribute(){},close(){this.open=false;},add(){}});
  return elements.get(selector);
}
$('#ministry-year').value='2026';
$('#ministry-role').value='ENCARREGADO_LOCAL';
const result={summary:{people:1,present:1,without_presence:0,pending:0},available:true,can_manage:true,unmatched:0,year:2026,
  filters:{situacao:''},options:{cities:['ITAPEVI'],commons:[]},events:[],
  event_options:[{id:'bras',date:'2026-10-06',titulo:'Reunião do Ministério da Música',tipo:'REUNIAO_MINISTERIO'}],
  states:{PRESENTE:'Presente'},roles:{ENCARREGADO_LOCAL:'Encarregado local'},kinds:{REUNIAO_MINISTERIO:'Reunião do Ministério da Música'},
  rows:[{nome:'Pessoa de teste',municipio:'ITAPEVI',comum:'BR-22-1 - Central',roles:['ENCARREGADO_LOCAL'],
    cells:[{event_id:'bras',date:'2026-10-06',situacao:'PRESENTE',tipo:'REUNIAO_MINISTERIO',local:'Brás'}]}]};
let finish,requestCount=0;
const sandbox={document:{querySelector:$,querySelectorAll:()=>[]},
  window:{MusicMultiSelect:{setupAll(){},values:()=>[],setOptions(){},setValues(){},refresh(){},labels:()=> 'Toda a Regional'}},
  fetch:async()=>{requestCount++;await new Promise(resolve=>{finish=resolve;});return {ok:true,redirected:false,json:async()=>result};},
  AbortController,URLSearchParams,setTimeout,clearTimeout,Option:function(){}};
vm.createContext(sandbox);
vm.runInContext(source,sandbox);
(async()=>{
  assert.equal(requestCount,1,'A página precisa iniciar a consulta ao abrir.');
  assert.ok($('#ministry-body').innerHTML.includes('Carregando'));
  finish();await new Promise(resolve=>setTimeout(resolve,20));
  assert.ok($('#ministry-body').innerHTML.includes('Pessoa de teste'));
  assert.ok($('#ministry-body').innerHTML.includes('ministry-status PRESENTE'));
  assert.ok($('#ministry-head').innerHTML.includes('06/10/2026'));
  assert.ok($('#ministry-head').innerHTML.includes('Reunião do Ministério da Música'));
  assert.equal($('#ministry-pdf').disabled,false);
  assert.ok(!$('#ministry-body').innerHTML.includes('Carregando'));
  sandbox.fetch=async()=>{throw Error('Falha de conexão');};
  await $('#ministry-refresh').onclick();
  assert.ok($('#ministry-body').innerHTML.includes('Não foi possível carregar'));
  assert.ok($('#ministry-feedback').innerHTML.includes('Falha de conexão'));
  assert.equal($('#ministry-pdf').disabled,true);
  console.log('Ministry loading: full startup, event columns, successful rendering and failure recovery verified.');
})().catch(error=>{console.error(error);process.exitCode=1;});
