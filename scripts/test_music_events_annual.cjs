const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('static/js/music-events-annual.js','utf8');
const render=source.slice(source.indexOf('  function render(){'),source.indexOf('  async function load('));
const elements=new Map();
const $=key=>{if(!elements.has(key))elements.set(key,{value:'',innerHTML:''});return elements.get(key);};
const row=(municipio,dates)=>({municipio,comum:municipio,encarregado_nome:'Nome',cells:dates.map(date=>({date,loaded:false})),loaded_sessions:dates.length});
const data={rows:[row('ITAPEVI',['2026-01-18','2026-05-17','2026-09-20']),row('COTIA',['2026-07-19'])],summary:{},selected_cities:['ITAPEVI','COTIA'],note:''};
vm.runInNewContext(render+';render();',{data,$,esc:String,n:String,date:String});
const html=$('#annual-tables').innerHTML;
assert.equal((html.match(/<table /g)||[]).length,2);
const tables=html.split('<table ').slice(1);
assert.ok(tables[0].includes('2026-01-18'));
assert.ok(!tables[0].includes('2026-07-19'));
assert.ok(tables[1].includes('2026-07-19'));
assert.ok(!tables[1].includes('2026-09-20'));
assert.ok(!html.includes('Outro circuito'));
assert.ok(html.includes('Mar\u00e7o'));
assert.ok(html.includes('annual-leader-zero">Encarregado local: 0/3'));
assert.ok(!html.includes('annual-complete'));
for(const [present,loaded,tone] of [[1,3,'partial'],[3,3,'full'],[0,0,null]]){
  data.rows=[{...row('ITAPEVI',[]),leader_sessions:present,loaded_sessions:loaded}];
  vm.runInNewContext(render+';render();',{data,$,esc:String,n:String,date:String});
  const result=$('#annual-tables').innerHTML;
  if(tone)assert.ok(result.includes(`annual-leader-${tone}">Encarregado local: ${present}/${loaded}`));
  else {
    assert.ok(result.includes('Encarregado local: sem dados carregados'));
    assert.ok(!result.includes('annual-leader-zero'));
  }
}
console.log('Annual tables: cycles, dates and municipalities verified.');
