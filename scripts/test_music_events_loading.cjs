const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/js/music-events-dashboard.js', 'utf8');
const loadSource = source.slice(source.indexOf('  async function load(preloaded)'), source.indexOf('  async function initialize'));
const elements = new Map();
const element = selector => {
  if (!elements.has(selector)) {
    const classes = new Set();
    elements.set(selector, {innerHTML:'old data', textContent:'old event', hidden:false,
      classList:{add:name=>classes.add(name),remove:name=>classes.delete(name),contains:name=>classes.has(name)},
      setAttribute(){},add(){}});
  }
  return elements.get(selector);
};
let finish;
const sandbox = {state:{data:{old:true},version:0}, dashboardController:null,historyController:null,
  $:element,AbortController,query:()=>new URLSearchParams(),
  request:()=>new Promise(resolve=>{finish=resolve;}),
  multi:{setOptions(){},values:()=>[],normalizedValues:()=>[],setValues(){},refresh(){}},
  options(){},render:data=>{sandbox.state.data=data;},feedback(){},loadHistory(){},Option:function(){}};
vm.createContext(sandbox);
vm.runInContext(loadSource+'\nthis.load=load;',sandbox);
(async()=>{
  const pending=sandbox.load();
  assert.equal(sandbox.state.data,null);
  assert.equal(element('#events-metrics').innerHTML,'');
  assert.equal(element('#events-attendance-overview').hidden,true);
  assert.equal(element('.music-events').classList.contains('events-data-pending'),true);
  finish({totals:{},options:{cities:[],commons:[],locations:[]}});
  await pending;
  assert.equal(element('.music-events').classList.contains('events-data-pending'),false);
  sandbox.request=async()=>{throw Error('Offline');};
  await sandbox.load();
  assert.equal(sandbox.state.data,null);
  assert.equal(element('.music-events').classList.contains('events-data-pending'),true);
  assert.match(element('#events-scope-reading').textContent,/indisponivel/);
  console.log('Troca de evento: resultados antigos ocultos durante consulta e falha.');
})().catch(error=>{console.error(error);process.exitCode=1;});
