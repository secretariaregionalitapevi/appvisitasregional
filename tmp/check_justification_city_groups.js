const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('static/js/music-events-justifications.js','utf8');
const start=source.indexOf('  const visibleRows =');
const end=source.indexOf('  async function loadSaved()',start);
const nodes=new Map();
const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',innerHTML:''});return nodes.get(id)};
const row=(id,city,name,common,lot='a')=>({id,municipio:city,nome:name,comum_nome:common,lote:lot,motivo:'Enfermidade',motivo_resumido:'Enfermidade',origem:'Mensagem'});
const context={
  $:node,esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
  saved:[row('jorge','SANTANA DE PARNAÍBA','JORGE','BR-22-1252 - JARDIM ISAURA'),
         row('otoniel','SANTANA DE PARNAÍBA','OTONIEL','BR-22-1252 - JARDIM ISAURA'),
         row('cotia','COTIA','ELCIO','BR-22-3789 - PAISAGEM CASA GRANDE','b')],
  expandedMunicipalities:new Set(),selected:new Set(),eventItems:[],busy:false
};
vm.createContext(context);vm.runInContext(source.slice(start,end),context);
context.renderSaved();
let html=node('saved').innerHTML;
assert.equal((html.match(/<details /g)||[]).length,2);
assert(!/<details[^>]*\sopen\b/.test(html));
assert(html.indexOf('data-just-city="COTIA"')<html.indexOf('data-just-city="SANTANA'));
assert(html.includes('2 justificativas')&&html.includes('1 justificativa'));
assert(html.includes('data-pick="jorge"')&&html.includes('data-pick="otoniel"'));
context.expandedMunicipalities.add('SANTANA DE PARNAÍBA');
context.selected.add('jorge');context.renderSaved();
html=node('saved').innerHTML;
assert(/data-just-city="SANTANA DE PARNAÍBA" open/.test(html));
assert(html.includes('data-pick="jorge" checked'));
assert(node('select-all').indeterminate);
node('lot').value='b';context.renderSaved();
assert(node('saved').innerHTML.includes('data-just-city="COTIA"'));
assert(!node('saved').innerHTML.includes('data-pick="jorge"'));
node('lot').value='';context.saved.push(row('unsafe','<script>','<img>','BR-22-0 - <b>'));
context.renderSaved();
assert(!node('saved').innerHTML.includes('<script>'));
assert(!node('saved').innerHTML.includes('<img>'));
context.saved=[];context.renderSaved();assert(node('saved').innerHTML.includes('Nenhuma justificativa'));
console.log('Grupos recolhidos, contagens, ordem, estado aberto, seleção, filtro de lote e escape de HTML validados.');
