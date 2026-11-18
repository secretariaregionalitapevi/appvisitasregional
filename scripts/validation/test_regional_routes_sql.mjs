// Banco PostgreSQL isolado em memoria; nenhuma chamada ao Supabase.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {PGlite} from '../../tmp/ministry-sql/node_modules/@electric-sql/pglite/dist/index.js';
const db=new PGlite();
const id=n=>'00000000-0000-0000-0000-'+String(n).padStart(12,'0');
await db.exec(`create role anon;create role authenticated;create role service_role bypassrls;
create table visitas_equipes(id uuid primary key,nome text,tipo text,municipio text,ativo boolean);
create table visitas_irmandade(id uuid primary key,comum text,endereco text);
create table visitas_agenda(id uuid primary key default gen_random_uuid(),irmandade_id uuid references visitas_irmandade(id),
titulo text,setor text,endereco_visitado text,categoria text,equipe_id uuid,equipe_responsavel text,equipe_tipo text,
data_inicio timestamptz,data_fim timestamptz,status text,observacoes text);
grant all on visitas_equipes,visitas_irmandade,visitas_agenda to service_role;`);
await db.exec(await fs.readFile('scripts/migrations/057_visitas_planejamento_regional.sql','utf8'));
for(let n=1;n<=2;n++){
  await db.query("insert into visitas_equipes values($1,$2,'REGIONAL','ITAPEVI',true)",[id(n),'Grupo '+String.fromCharCode(64+n)]);
  await db.query('insert into visitas_irmandade values($1,$2,$3)',[id(10+n),'COMUM '+n,'Rua '+n+', 10']);
}
await db.query('insert into visitas_irmandade values($1,$2,$3)',[id(13),'COMUM 2','Rua 1, 10']);
await db.exec('set role service_role');
const groups=[1,2].map(n=>({id:id(n),nome:'Grupo '+String.fromCharCode(64+n),confirmado:true,coordenador_nome:n===1?'Joao':'Manoel'}));
async function saveParticipation(day,items=groups){
  const prior=(await db.query('select equipe_id,updated_at::text as updated_at from visitas_participacao_regional where data=$1',[day])).rows;
  const payload=items.map(g=>({...g,expected_updated_at:prior.find(p=>p.equipe_id===g.id)?.updated_at||''}));
  await db.query('select visitas_salvar_participacao_regional($1,$2,$3,$4::jsonb)',[day,'ITAPEVI',id(99),JSON.stringify(payload)]);
}
await saveParticipation('2099-10-17');
await assert.rejects(()=>db.query('select visitas_salvar_participacao_regional($1,$2,$3,$4::jsonb)',
  ['2099-10-17','ITAPEVI',id(99),JSON.stringify(groups)])); // Outra tela nao sobrescreve a versao salva.
await saveParticipation('2099-08-17',[{...groups[0],coordenador_nome:'Outro coordenador'},groups[1]]);
assert.equal((await db.query("select coordenador_nome from visitas_participacao_regional where data='2099-10-17' and equipe_id=$1",[id(1)])).rows[0].coordenador_nome,'Joao');
const version=async()=> (await db.query("select visitas_versao_agenda_regional('2099-10-17') as v")).rows[0].v;
const plan={groups,houses:[1,2].map(n=>({group_id:id(n),visit_ids:[],bairro:'Vila das Chacaras',
  start:'2099-10-17T09:00:00-03:00',end:'2099-10-17T09:15:00-03:00',
  members:[{id:id(10+n),nome:'Familia '+n,comum:'COMUM '+n,endereco:'Rua '+n+', 10'}]}))};
plan.houses[0].members.push({id:id(13),nome:'Outra familia da mesma casa',comum:'COMUM 2',endereco:'Rua 1, 10'});
async function confirm(n,expected,payload=plan){return db.query('select visitas_confirmar_roteiro_regional($1,$2,$3,$4,$5,$6::jsonb) as id',
  [id(n),'2099-10-17','ITAPEVI',id(99),expected,JSON.stringify(payload)]);}
const initial=await version();
await confirm(100,initial);
await confirm(100,initial); // Resposta perdida: nao gravar duas vezes.
assert.equal((await db.query('select count(*)::int as n from visitas_agenda')).rows[0].n,3);
assert.equal((await db.query('select count(distinct data_inicio)::int as n from visitas_agenda where irmandade_id in ($1,$2)',[id(11),id(13)])).rows[0].n,1);
await assert.rejects(()=>confirm(101,initial)); // Previa antiga nao pode duplicar casas.
const before=await version();
const changed=structuredClone(plan);changed.houses[1].members[0].endereco='Endereco alterado';
await assert.rejects(()=>confirm(102,before,changed));
assert.equal((await db.query('select count(*)::int as n from visitas_roteiros_regionais')).rows[0].n,1);
await saveParticipation('2099-10-17',[{...groups[0],confirmado:false},groups[1]]);
const unconfirmedVersion=await version();
await assert.rejects(()=>confirm(103,unconfirmedVersion));
await saveParticipation('2099-10-17');
const existing=(await db.query('select id,irmandade_id from visitas_agenda')).rows;
const redistributed=structuredClone(plan);
redistributed.houses.forEach((h,i)=>{h.visit_ids=existing.filter(v=>h.members.some(m=>m.id===v.irmandade_id)).map(v=>v.id);h.group_id=groups[1-i].id;});
await db.query('insert into visitas_irmandade values($1,$2,$3)',[id(14),'COMUM 1','Rua 2, 10']);
redistributed.houses[1].members.push({id:id(14),nome:'Morador sem vinculo legado',comum:'COMUM 1',endereco:'Rua 2, 10'});
await confirm(104,await version(),redistributed);
assert.equal((await db.query('select count(*)::int as n from visitas_agenda')).rows[0].n,4);
assert.equal((await db.query('select equipe_id from visitas_agenda where irmandade_id=$1',[id(11)])).rows[0].equipe_id,id(2));
assert.ok((await db.query('select substituido_em from visitas_roteiros_regionais where id=$1',[id(100)])).rows[0].substituido_em);
await db.exec('reset role;alter table visitas_equipes add column updated_at timestamptz default now()');
await db.exec(await fs.readFile('scripts/migrations/058_visitas_coordenador_cadastrado.sql','utf8'));
await db.exec('set role service_role');
assert.equal((await db.query('select coordenador_nome from visitas_equipes where id=$1',[id(1)])).rows[0].coordenador_nome,'Joao');
const canonicalChange=[{...groups[0],coordenador_nome:'Sergio',atualizar_cadastro:true,expected_coordenador_cadastrado:'Joao'},groups[1]];
await saveParticipation('2099-11-17',canonicalChange);
assert.equal((await db.query('select coordenador_nome from visitas_equipes where id=$1',[id(1)])).rows[0].coordenador_nome,'Sergio');
assert.equal((await db.query('select plano from visitas_roteiros_regionais where id=$1',[id(100)])).rows[0].plano.groups[0].coordenador_nome,'Joao');
// Desmarcar uma data antiga nao restaura o antigo coordenador no cadastro.
await saveParticipation('2099-08-17',[{...groups[0],confirmado:false},groups[1]]);
assert.equal((await db.query('select coordenador_nome from visitas_equipes where id=$1',[id(1)])).rows[0].coordenador_nome,'Sergio');
await assert.rejects(()=>saveParticipation('2099-12-17',canonicalChange));
assert.equal((await db.query("select count(*)::int as n from visitas_participacao_regional where data='2099-12-17'")).rows[0].n,0);
await saveParticipation('2099-12-17',[{...groups[0],confirmado:false,coordenador_nome:'',atualizar_cadastro:true,expected_coordenador_cadastrado:'Sergio'},groups[1]]);
assert.equal((await db.query('select coordenador_nome from visitas_equipes where id=$1',[id(1)])).rows[0].coordenador_nome,'');
await db.exec('reset role');
await db.exec(await fs.readFile('scripts/migrations/059_visitas_excluir_agendamentos_roteiro.sql','utf8'));
await db.exec('set role service_role');
// Um agendamento local da mesma data nunca pertence a exclusao do roteiro.
await db.query("insert into visitas_agenda(irmandade_id,titulo,status,data_inicio) values($1,'Visita local','Marcada','2099-10-17T11:00:00-03:00')",[id(11)]);
const deletionStats=async n=>(await db.query('select visitas_previa_exclusao_roteiro_regional($1,$2,$3) as stats',[id(n),'2099-10-17','ITAPEVI'])).rows[0].stats;
const removePlan=(n,version,city='ITAPEVI')=>db.query('select visitas_excluir_agendamentos_roteiro_regional($1,$2,$3,$4,$5) as removed',[id(n),'2099-10-17',city,id(99),version]);
const initialDeletion=await deletionStats(104);
assert.equal(initialDeletion.agendamentos,4);
await db.query("update visitas_agenda set status='Realizada' where id=(select id from visitas_agenda where roteiro_regional_id=$1 limit 1)",[id(104)]);
assert.equal((await deletionStats(104)).protegidos,1);
await assert.rejects(()=>removePlan(104,initialDeletion.version));
assert.equal((await db.query('select count(*)::int as n from visitas_agenda')).rows[0].n,5);
await db.query("update visitas_agenda set status='Marcada',titulo='Alterado apos previa' where roteiro_regional_id=$1",[id(104)]);
await assert.rejects(()=>removePlan(104,initialDeletion.version));
const readyDeletion=await deletionStats(104);
await assert.rejects(()=>removePlan(104,readyDeletion.version,'JANDIRA'));
assert.equal((await removePlan(104,readyDeletion.version)).rows[0].removed,4);
assert.equal((await removePlan(104,readyDeletion.version)).rows[0].removed,0);
assert.equal((await db.query('select count(*)::int as n from visitas_agenda')).rows[0].n,1);
assert.ok((await db.query('select plano from visitas_roteiros_regionais where id=$1',[id(104)])).rows[0].plano.deleted_at);
// Historico sem agendas tambem pode sair da lista, preservando sua auditoria.
assert.equal((await removePlan(100,(await deletionStats(100)).version)).rows[0].removed,0);
await db.exec('reset role;set role anon');
await assert.rejects(()=>db.query("select visitas_versao_agenda_regional('2099-10-17')"));
await assert.rejects(()=>deletionStats(104));
await assert.rejects(()=>removePlan(104,readyDeletion.version));
await db.close();
console.log('Roteiros regionais: transacao, idempotencia, coordenador por data, previa obsoleta e permissoes OK.');
