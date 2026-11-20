// PostgreSQL isolado, sem dados ou conexão de produção.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {PGlite} from '../../tmp/ministry-sql/node_modules/@electric-sql/pglite/dist/index.js';
const db = new PGlite();
await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
create table musica_eventos(id uuid primary key,tipo text,data_evento date,familia text);
create table musica_ministerio_eventos(id uuid primary key,tipo text,data_evento date,familia text);
grant select on musica_eventos,musica_ministerio_eventos to service_role;`);
const sql = await fs.readFile('scripts/migrations/062_musica_justificativas_publicas.sql','utf8');
await db.exec(sql);
await db.exec(sql); // Reaplicação segura.
const day = (await db.query("select (now() at time zone 'America/Sao_Paulo')::date::text as day")).rows[0].day;
const id = '00000000-0000-0000-0000-000000000001';
await db.query('insert into musica_eventos values($1,$2,$3,$4)',[id,'ENSAIO_REGIONAL',day,'GERAL']);
const wrong = '00000000-0000-0000-0000-000000000002';
await db.query('insert into musica_eventos values($1,$2,$3,$4)',[wrong,'REUNIAO_TECNICA',day,'CORDAS']);
const insert = async (agenda='a'.repeat(24), person='b'.repeat(64), date=day) => (await db.query(`insert into musica_justificativas_publicas
(agenda_id,evento_titulo,data_evento,tipo,familia,municipios,comum_codigo,comum,municipio,person_key,pessoa_identidade,nome,motivo)
values($1,'Ensaio regional',$2,'ENSAIO_REGIONAL','GERAL','["COTIA"]','BR-22-1','Central','COTIA','sam:1',$3,'Pessoa teste','Compromisso de trabalho') returning id`,[agenda,date,person])).rows[0].id;
await db.exec('set role service_role');
const justification = await insert();
await assert.rejects(() => insert(), /duplicate key/);
await assert.rejects(() => insert('c'.repeat(24),'d'.repeat(64),'2000-01-01'), /Prazo/);
await assert.rejects(() => db.query('update musica_justificativas_publicas set motivo=$1 where id=$2',['Outro motivo',justification]), /imutável/);
await assert.rejects(() => db.query('update musica_justificativas_publicas set evento_id=$1 where id=$2',[id,justification]), /responsável/);
await assert.rejects(() => db.query("update musica_justificativas_publicas set evento_id=$1,vinculado_por_id='operador',vinculado_por_nome='Operador' where id=$2",[wrong,justification]), /incompatível/);
await db.query(`update musica_justificativas_publicas set evento_id=$1,vinculado_por_id='operador',vinculado_por_nome='Operador' where id=$2`,[id,justification]);
assert.equal((await db.query('select count(*)::int as n from musica_justificativas_vinculos_auditoria')).rows[0].n,1);
await db.exec('reset role; set role anon');
await assert.rejects(() => db.query('select * from musica_justificativas_publicas'), /permission denied/);
await assert.rejects(() => insert('e'.repeat(24),'f'.repeat(64)), /permission denied/);
await db.exec('reset role; set role authenticated');
await assert.rejects(() => db.query('select * from musica_justificativas_publicas'), /permission denied/);
await db.close();
console.log('SQL: prazo, duplicidade, imutabilidade, autoria, auditoria, RLS e reaplicação validados.');
