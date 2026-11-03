// Requer PGlite instalado somente em tmp/ministry-sql para validar sem banco de produção.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {PGlite} from '../../tmp/ministry-sql/node_modules/@electric-sql/pglite/dist/index.js';

const db=new PGlite();
await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
create table public.musica_eventos(id uuid primary key);`);
await db.exec(await fs.readFile('scripts/migrations/036_musica_ministerio_acompanhamento.sql','utf8'));
const legacy='00000000-0000-0000-0000-000000000001';
await db.query('insert into musica_eventos values ($1)',[legacy]);
await db.exec('set role service_role');
const row={person_key:'sam:teste',nome:'Pessoa de teste',comum:'BR-22-1 - Central',municipio:'ITAPEVI',
  roles:['ENCARREGADO_LOCAL'],situacao:'PRESENTE',observacoes:'',source:{row:5}};
const event={titulo:'Reunião de teste',tipo:'REUNIAO_MINISTERIO',data_evento:'2026-10-06',modalidade:'PRESENCIAL',
  local:'Brás',familia:'GERAL',municipios:['ITAPEVI'],cargos:['ENCARREGADO_LOCAL'],lista_completa:true,registros:[row]};
async function save(payload,hash){
  const result=await db.query('select public.musica_ministerio_salvar($1::jsonb,$2,$3,$4,$5) as value',
    [JSON.stringify(payload),hash,'teste.xlsx','operador','Operador de teste']);
  return result.rows[0].value;
}
const created=await save(event,'a'.repeat(64));
assert.equal(created.existing,false);
const repeated=await save(event,'a'.repeat(64));
assert.equal(repeated.id,created.id);assert.equal(repeated.existing,true);
assert.equal((await db.query('select count(*)::int as n from musica_ministerio_participacoes')).rows[0].n,1);
await assert.rejects(()=>save({...event,titulo:'Outro'},'b'.repeat(64)).then(async()=>{
  // A primeira gravação é válida; a segunda deve violar a unicidade do encontro.
  await save({...event,titulo:'Outro'},'c'.repeat(64));
}));
await db.query('select public.musica_ministerio_conferir($1,$2,$3,$4,$5,$6,$7)',
  [created.id,row.person_key,'JUSTIFICOU','Justificativa registrada',1,'operador','Operador']);
await assert.rejects(()=>db.query('select public.musica_ministerio_conferir($1,$2,$3,$4,$5,$6,$7)',
  [created.id,row.person_key,'PRESENTE','',1,'operador','Operador']));
const review=await db.query('select public.musica_ministerio_conferir_legado($1,$2::jsonb,$3,$4,$5) as value',
  [legacy,JSON.stringify({...row,situacao:'SEM_REGISTRO'}),0,'operador','Operador']);
assert.equal(review.rows[0].value.version,1);
await assert.rejects(()=>db.query('select public.musica_ministerio_conferir_legado($1,$2::jsonb,$3,$4,$5)',
  [legacy,JSON.stringify(row),0,'operador','Operador']));
const pending=await save({...event,titulo:'Reunião online',modalidade:'ONLINE',lista_completa:false,
  registros:[{...row,situacao:'SEM_DADOS'}]},null);
await save({...event,event_id:pending.id,titulo:'Reunião online',modalidade:'ONLINE'},'d'.repeat(64));
assert.equal((await db.query('select count(*)::int as n from musica_ministerio_eventos where id=$1',[pending.id])).rows[0].n,1);
assert.equal((await db.query('select situacao from musica_ministerio_participacoes where event_id=$1',[pending.id])).rows[0].situacao,'PRESENTE');
await assert.rejects(()=>save({...event,titulo:'Importação inválida',registros:[{...row,situacao:'JUSTIFICOU',observacoes:''}]},'f'.repeat(64)));
assert.equal((await db.query('select count(*)::int as n from musica_ministerio_eventos where titulo=$1',['Importação inválida'])).rows[0].n,0);
await db.exec('reset role; set role anon');
await assert.rejects(()=>db.query('select * from musica_ministerio_participacoes'));
await assert.rejects(()=>db.query('select public.musica_ministerio_salvar($1::jsonb,$2,$3,$4,$5)',
  [JSON.stringify(event),'e'.repeat(64),'arquivo.xlsx','operador','Operador']));
await db.exec('reset role');
await db.close();
console.log('SQL validated: migration, atomic import, idempotency, later upload, reviews, version conflicts and permissions.');
