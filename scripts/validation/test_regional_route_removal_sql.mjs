// PostgreSQL isolado em memoria; nao altera o Supabase nem a agenda real.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {PGlite} from '../../tmp/ministry-sql/node_modules/@electric-sql/pglite/dist/index.js';
process.on('uncaughtException',error=>{console.error(error.message,error.where||'',error.position||'');process.exit(1);});
const db=new PGlite();
const id=n=>'00000000-0000-0000-0000-'+String(n).padStart(12,'0');
await db.exec(`create role anon;create role authenticated;create role service_role bypassrls;
create table visitas_roteiros_regionais(id uuid primary key,data date,municipio text,plano jsonb);
create table visitas_agenda(id uuid primary key,roteiro_regional_id uuid,irmandade_id uuid,status text,data_inicio timestamptz);
grant all on visitas_roteiros_regionais,visitas_agenda to service_role;`);
await db.exec(await fs.readFile('scripts/migrations/060_visitas_exclusao_seletiva_comuns.sql','utf8'));
await db.exec('set role service_role');
const A='BR-22-3062 - JARDIM ALABAMA', B='BR-21-1542 - VILA BELMIRA';
const plan={commons:[A,B],groups:[{id:id(9),nome:'Grupo A'}],coverage:[{common:A},{common:B}],houses:[
  {key:'shared',group_id:id(9),number:1,visit_ids:[id(21),id(22)],members:[{id:id(11),comum:'BR-22-3062 - Jardim Alabama'},{id:id(12),comum:B}]},
  {key:'only-a',group_id:id(9),number:2,visit_ids:[id(23)],members:[{id:id(13),comum:A}]}
]};
const day='2099-10-17';
await db.query('insert into visitas_roteiros_regionais values($1,$2,$3,$4)',[id(1),day,'ITAPEVI',plan]);
for(const [number,route,member,status,date] of [
  [21,1,11,'Marcada',day+'T00:00:00-03:00'],[22,1,12,'Marcada',day+'T23:59:00-03:00'],
  [23,1,13,'Realizada',day+'T10:00:00-03:00'],[24,1,11,'Marcada','2099-10-18T09:00:00-03:00'],
  [25,2,11,'Marcada',day+'T10:00:00-03:00'],[26,null,11,'Marcada',day+'T10:00:00-03:00']]) {
  await db.query('insert into visitas_agenda values($1,$2,$3,$4,$5)',[id(number),route?id(route):null,id(member),status,date]);
}
const preview=async()=> (await db.query('select visitas_previa_remocao_comuns_roteiro($1,$2,$3) as value',[id(1),day,'ITAPEVI'])).rows[0].value;
const remove=(version,commons,agenda,city='ITAPEVI')=>db.query('select visitas_remover_comuns_roteiro($1,$2,$3,$4,$5,$6,$7) as value',
  [id(1),day,city,id(99),version,commons,agenda]);
const first=await preview();
assert.deepEqual(first.commons,[{common:A,scheduled:1},{common:B,scheduled:1}]);
await assert.rejects(()=>remove(first.version,['OUTRA COMUM'],[]));
await assert.rejects(()=>remove(first.version,[A],[B]));
await assert.rejects(()=>remove(first.version,[A],[A],'OUTRO MUNICIPIO'));
// Alterar somente o snapshot tambem invalida a confirmacao antiga.
await db.query("update visitas_roteiros_regionais set plano=plano||'{\"changed\":true}' where id=$1",[id(1)]);
await assert.rejects(()=>remove(first.version,[A],[A]));
assert.equal((await db.query('select count(*)::int as n from visitas_agenda')).rows[0].n,6);
const current=await preview();
const deleted=(await remove(current.version,[A],[A])).rows[0].value;
assert.equal(deleted.deleted,1);
const agenda=(await db.query('select id from visitas_agenda order by id')).rows.map(r=>r.id);
assert.deepEqual(agenda,[22,23,24,25,26].map(id)); // B, realizadas, outra data, outro roteiro e avulsa intactos.
const remaining=(await db.query('select plano from visitas_roteiros_regionais where id=$1',[id(1)])).rows[0].plano;
assert.deepEqual(remaining.commons,[B]);
assert.equal(remaining.houses.length,1);
assert.deepEqual(remaining.houses[0].members,[{id:id(12),comum:B}]);
assert.deepEqual(remaining.houses[0].visit_ids,[id(22)]);
assert.equal(remaining.records_in_plan,1);
assert.deepEqual(remaining.coverage,[{common:B}]);
assert.equal(remaining.deleted_at,undefined);
assert.deepEqual(remaining.removals[0].agenda_commons,[A]);
// Remover B somente do roteiro preserva sua visita na agenda/calendario.
const next=await preview();
assert.equal((await remove(next.version,[B],[])).rows[0].value.deleted,0);
assert.equal((await db.query('select count(*)::int as n from visitas_agenda')).rows[0].n,5);
const final=(await db.query('select plano from visitas_roteiros_regionais where id=$1',[id(1)])).rows[0].plano;
assert.ok(final.deleted_at);
assert.deepEqual(final.commons,[]);
assert.deepEqual(final.houses,[]);
assert.deepEqual(final.groups,[]);
await db.exec('reset role;set role anon');
await assert.rejects(()=>preview());
await db.close();
console.log('OK: exclusao parcial, agenda opcional, casa compartilhada, data, status, escopo, concorrencia e permissoes.');
