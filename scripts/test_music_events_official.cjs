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
const september=JSON.parse(fs.readFileSync('docs/references/music_events/2026-09-20_itapevi_closing.json','utf8'));
render({detail:{attendance_overview:{totals:{total:846,MUSICO:428,ORGANISTA:104},
  display_totals:{total:842,MUSICO:436,ORGANISTA:95,APOIO:26,IRMANDADE:258},
  has_official:true,origin_context:{regional:643,visitantes:203},closings:[{
    date:'2026-09-20',city:'ITAPEVI',total:846,musicians:443,organists:105,official:september,
    nominal_reconciliation:{total:846,musicians:428,organists:104,candidate_musicians:15,candidate_organists:1}
  }]},registry:{}}});
const cards=target.innerHTML.split('attendance-origin-summary')[0];
for(const value of ['842','436','95','531'])assert.match(cards,new RegExp('>'+value+'<'));
assert.doesNotMatch(cards,/>846<|>428<|>104</);
assert.match(target.innerHTML,/Conciliação com a lista nominal/);
assert.match(target.innerHTML,/Candidatos músicos na lista nominal: 15. Candidatas organistas: 1./);
console.log('Setembro: totais oficiais nos cards e divergencias nominais identificadas.');
