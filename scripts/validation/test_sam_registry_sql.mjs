import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {PGlite} from '../../tmp/ministry-sql/node_modules/@electric-sql/pglite/dist/index.js';

const db = new PGlite();
await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
create schema auth;
create function auth.uid() returns uuid language sql as 'select null::uuid';
create table musica_acompanhamento_aluno(
 id uuid primary key default gen_random_uuid(), registro_msa text, nome_aluno text,
 cargo_ministerio text, comum_congregacao text, municipio text, status text,
 nivel text, instrumento text, data_inicio_gem date);
grant select,insert,update on musica_acompanhamento_aluno to service_role;`);
const sql = await fs.readFile('scripts/migrations/037_sam_cadastro_auditoria.sql', 'utf8');
await db.exec(sql);
await db.exec(sql); // Reapplying does not duplicate the trigger.
await db.exec(`set role service_role;
insert into musica_acompanhamento_aluno(registro_msa,nome_aluno,cargo_ministerio,comum_congregacao)
 values ('1','Henrique','Encarregado Local','Suburbano III');
update musica_acompanhamento_aluno set cargo_ministerio='Músico',comum_congregacao='Outra comum';
update musica_acompanhamento_aluno set cargo_ministerio='Músico';`);
const {rows} = await db.query('select * from sam_cadastro_historico');
assert.equal(rows.length, 1);
assert.equal(rows[0].anterior.cargo_ministerio, 'Encarregado Local');
assert.equal(rows[0].posterior.cargo_ministerio, 'Músico');
assert.equal(rows[0].anterior.comum_congregacao, 'Suburbano III');
assert.equal(rows[0].posterior.comum_congregacao, 'Outra comum');
await assert.rejects(() => db.exec('delete from sam_cadastro_historico'));
await db.exec(`begin; update musica_acompanhamento_aluno set cargo_ministerio='Encarregado Local'; rollback;`);
assert.equal((await db.query('select * from sam_cadastro_historico')).rows.length, 1);
await db.exec('reset role');
await db.exec(await fs.readFile('scripts/migrations/012_sam_automatic_sync.sql', 'utf8'));
const temporalSql = await fs.readFile('scripts/migrations/038_sam_transicoes_temporais.sql', 'utf8');
await db.exec(temporalSql);
await db.exec(temporalSql);
await db.exec('set role service_role');
assert.equal((await db.query('select * from sam_cadastro_transicoes')).rows.length, 2);
const params = ['1', 'cargo_ministerio', JSON.stringify('Encarregado Local'), JSON.stringify('Músico'),
                '2026-09-01T12:00:00-03:00', 'sam-log:123', JSON.stringify({source_log_id: 123})];
const register = () => db.query('select sam_registrar_transicao($1,$2,$3::jsonb,$4::jsonb,$5::timestamptz,$6,$7::jsonb)', params);
await register();
await register();
assert.equal((await db.query("select * from sam_cadastro_transicoes where date_basis='sam'")).rows.length, 1);
params[3] = JSON.stringify('Outro');
await assert.rejects(register);
await assert.rejects(() => db.exec('delete from sam_cadastro_transicoes'));
await db.exec("update musica_acompanhamento_aluno set nivel='RJM',data_inicio_gem='2023-02-01'");
assert.equal((await db.query("select * from sam_cadastro_transicoes where campo='nivel'")).rows.length, 1);
assert.equal((await db.query("select * from sam_cadastro_transicoes where campo='data_inicio_gem'")).rows.length, 1);
const cadastroSql = await fs.readFile('scripts/migrations/054_gem_cadastro_temporal.sql', 'utf8');
await db.exec('reset role');
await db.exec(cadastroSql);
await db.exec(cadastroSql);
await db.exec(`alter table musica_acompanhamento_aluno disable trigger musica_acompanhamento_updated_at;
update musica_acompanhamento_aluno set updated_at='2000-01-01T00:00:00Z';
alter table musica_acompanhamento_aluno enable trigger musica_acompanhamento_updated_at;
set role service_role;
update musica_acompanhamento_aluno set nome_aluno='Henrique Atualizado';`);
const timestamp = (await db.query('select updated_at from musica_acompanhamento_aluno')).rows[0].updated_at;
assert.ok(Date.parse(timestamp) > Date.parse('2000-01-01T00:00:00Z'));
const nameTransition = (await db.query(
    "select anterior,posterior from sam_cadastro_transicoes where campo='nome_aluno'")).rows[0];
assert.equal(nameTransition.anterior, 'Henrique');
assert.equal(nameTransition.posterior, 'Henrique Atualizado');
const studentId = (await db.query('select id from musica_acompanhamento_aluno')).rows[0].id;
await db.exec(`set role service_role;
update musica_acompanhamento_aluno set nivel='RJM / CULTO OFICIAL';
insert into sam_level_history(aluno_id,previous_level,new_level,effective_at,date_basis,evidence)
values ('${studentId}','RJM / ENSAIO','RJM / CULTO OFICIAL','2026-11-07T12:00:00Z','manual',
        '{"exam_id":"c2825408-132e-48c5-894c-7382c02ae765"}');`);
const normalizeSql = await fs.readFile('scripts/migrations/055_gem_culto_oficial_levels.sql', 'utf8');
await db.exec('reset role');
await db.exec(normalizeSql);
await db.exec(normalizeSql);
assert.equal((await db.query('select nivel from musica_acompanhamento_aluno')).rows[0].nivel, 'CULTO OFICIAL');
assert.equal((await db.query('select new_level from sam_level_history')).rows[0].new_level, 'CULTO OFICIAL');
const badTransitions = await db.query(
    "select id from sam_cadastro_transicoes where campo='nivel' and (anterior='\"RJM / CULTO OFICIAL\"'::jsonb or posterior='\"RJM / CULTO OFICIAL\"'::jsonb)");
assert.equal(badTransitions.rows.length, 0);
await assert.rejects(() => db.exec(
    "update musica_acompanhamento_aluno set nivel='RJM / CULTO OFICIAL'"));
await db.close();
console.log('SAM audit: timestamps, name history, level normalization, permissions and idempotency passed.');
