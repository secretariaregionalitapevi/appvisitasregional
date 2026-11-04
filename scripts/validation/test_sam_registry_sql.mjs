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
await db.close();
console.log('SAM audit: before/after, no-op, permissions, rollback and idempotency passed.');
