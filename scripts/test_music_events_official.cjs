const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let render;
const target={hidden:true,innerHTML:'',querySelectorAll:()=>[]};
const note={textContent:''};
const context={document:{addEventListener:(name,handler)=>{render=handler;},
  getElementById:id=>id==='events-attendance-overview'?target:note},window:{}};
vm.createContext(context);
vm.runInContext(fs.readFileSync('static/js/music-events-attendance.js','utf8'),context);
const original=JSON.parse(fs.readFileSync('docs/references/music_events/2026-05-17_itapevi_closing.json','utf8'));
render({detail:{attendance_overview:{totals:{total:2165,MUSICO:1019,ORGANISTA:326},
  display_totals:{total:2440,MUSICO:1201,ORGANISTA:320,APOIO:28,IRMANDADE:830},
  has_official:true,origin_context:{regional:1083},closings:[{date:'2026-05-17',city:'ITAPEVI',
    total:2165,musicians:1019,organists:326,declared_total:2440,difference:275,official:original}]},registry:{}}});
assert.match(target.innerHTML,/2\.440/);
assert.match(target.innerHTML,/1\.201/);
assert.match(target.innerHTML,/320/);
assert.match(target.innerHTML,/830/);
assert.match(target.innerHTML,/Relatório oficial/);
assert.doesNotMatch(target.innerHTML,/2\.165|1\.019|Conciliação pendente|PIRAPORA/);
console.log('Fechamento oficial: fonte e valores corretos no quadro geral.');
