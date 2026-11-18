import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {PGlite} from '../../tmp/ministry-sql/node_modules/@electric-sql/pglite/dist/index.js';
process.on('uncaughtException',e=>{console.error(e.message,e.where||'');process.exit(1);});
const db=new PGlite();
const id=n=>'00000000-0000-0000-0000-'+String(n).padStart(12,'0');
await db.exec(`create role anon;create role authenticated;create role service_role bypassrls;
create table visitas_equipes(id uuid primary key default gen_random_uuid(),nome text,tipo text,municipio text,ativo boolean,coordenador_nome text);
create table visitas_participacao_regional(data date,municipio text,equipe_id uuid,confirmado boolean,coordenador_nome text,
updated_by uuid,updated_at timestamptz default clock_timestamp(),primary key(data,municipio,equipe_id));
grant all on visitas_equipes,visitas_participacao_regional to service_role;`);
const sql=await fs.readFile('scripts/migrations/061_visitas_composicao_regional.sql','utf8');
await db.exec(sql);
// Simula execucao por instrucoes, com commit entre elas: nenhuma tabela
// temporaria/sessao anterior pode ser necessaria para o bloco de importacao.
assert.ok(!/create\s+temporary\s+table/i.test(sql));
const statements=sql.match(/(?:[^;'$]|'(?:''|[^'])*'|\$\$[\s\S]*?\$\$)+;/g);
assert.ok(statements?.length>10);
for(const statement of statements){
  const command=statement.replace(/--[^\n]*/g,'').trim();
  if(/^(begin|commit);$/i.test(command))continue;
  await db.exec(statement);
}
await db.exec('set role service_role');
const count=async table=>(await db.query(`select count(*)::int as n from ${table}`)).rows[0].n;
assert.equal(await count('visitas_integrantes_regionais'),20);
assert.equal(await count('visitas_funcoes_regionais'),23);
assert.equal(await count('visitas_equipes'),15);
assert.equal(await count('visitas_participacao_regional'),0); // Nenhuma cor virou presenca.
assert.equal((await db.query("select count(*)::int as n from visitas_equipes where exige_confirmacao_data")).rows[0].n,15);
const team=(await db.query("select id,coordenador_nome from visitas_equipes where nome='Grupo A'")).rows[0];
const secretary=(await db.query("select id from visitas_integrantes_regionais where nome='Sidney de Aguiar Fogaça'")).rows[0];
const day='2099-11-17';
const assign=(person,version=null,group=team.id)=>db.query('select visitas_atribuir_integrante_por_data($1,$2,$3,$4,$5,$6,$7)',
  ['ITAPEVI',day,group,person,id(99),true,version]);
await assign(secretary.id);
const saved=(await db.query('select coordenador_integrante_id,coordenador_nome,updated_at from visitas_participacao_regional')).rows[0];
assert.equal(saved.coordenador_integrante_id,secretary.id);
assert.equal(saved.coordenador_nome,'Sidney de Aguiar Fogaça');
assert.equal((await db.query('select coordenador_nome from visitas_equipes where id=$1',[team.id])).rows[0].coordenador_nome,'Emerson Nunes Moraes');
await assert.rejects(()=>assign(secretary.id)); // versao obsoleta
const b=(await db.query("select id from visitas_equipes where nome='Grupo B'")).rows[0];
await assert.rejects(()=>assign(secretary.id,null,b.id)); // mesmo integrante, dois grupos no mesmo dia
const outsider=(await db.query("insert into visitas_integrantes_regionais(municipio,nome) values('JANDIRA','Outro integrante') returning id")).rows[0];
await assert.rejects(()=>assign(outsider.id));
await assert.rejects(()=>db.query("insert into visitas_funcoes_regionais(municipio,integrante_id,funcao,equipe_id) values('ITAPEVI',$1,'PARTICIPANTE',$2)",[outsider.id,team.id]));
assert.equal(await count('visitas_atribuicoes_regionais_auditoria'),1);
await db.exec('reset role;set role anon');
await assert.rejects(()=>db.query('select * from visitas_integrantes_regionais'));
await assert.rejects(()=>assign(secretary.id));
await db.close();
console.log('OK: 20 integrantes, 23 funcoes, A-O, idempotencia, nenhuma presenca, substituicao por data, isolamento municipal e permissoes.');
