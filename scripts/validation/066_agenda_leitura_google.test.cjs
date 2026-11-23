const {test,before,after}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const {resolve}=require('node:path');
const {randomUUID}=require('node:crypto');
const {PGlite}=require('../../tmp/agenda-validation/node_modules/@electric-sql/pglite');
let db;
const run=async(sql,args=[])=>(await db.query(sql,args)).rows;
const op=async(action,data={})=>(await run('select agenda_google_operar($1,$2::jsonb) v',[action,JSON.stringify(data)]))[0].v;
const range={inicio:'2099-12-01T00:00:00-03:00',fim:'2100-01-01T00:00:00-03:00'};
const event=(id='g1')=>({id:randomUUID(),google_event_id:id,titulo:'Evento Google',local:'Central',inicio:'2099-12-05T19:00:00-03:00',fim:'2099-12-05T21:00:00-03:00',dia_inteiro:false,disponivel:false});
const finish=(j,eventos)=>op('resultado',{id:j.id,lease_token:j.lease_token,resultado:'ok',eventos});
async function reset(){await db.exec('truncate agenda_google_eventos,agenda_google_leituras;');}
async function requeue(j){await run("update agenda_google_leituras set status='PENDENTE',lease_token=null,lease_ate=null,solicitado_em=now()-interval '1 hour' where id=$1",[j.id]);return (await op('buscar')).job;}
before(async()=>{
 db=new PGlite();await db.exec('create role anon;create role authenticated;create role service_role;');
 for(const name of ['064_agenda_regional.sql','065_agenda_calendarios_municipais.sql','066_agenda_leitura_google.sql'])await db.exec(readFileSync(resolve(__dirname,'../migrations/'+name),'utf8'));
 await run("update agenda_calendarios set calendar_id=id||'@example.com'");
});
after(async()=>{if(db)await db.close();});
test('request queues seven independent reads and is idempotent',async()=>{
 await reset();await op('solicitar',range);await op('solicitar',range);
 assert.equal((await run('select count(*)::int n from agenda_google_leituras'))[0].n,7);
});
test('snapshot displays existing Google events without creating reservations',async()=>{
 await reset();await op('solicitar',range);const j=(await op('buscar')).job;await finish(j,[event()]);
 const rows=await run('select * from agenda_google_visiveis');assert.equal(rows.length,1);assert.equal(rows[0].agenda_id,j.agenda_id);
 assert.equal((await run('select count(*)::int n from agenda_eventos'))[0].n,0);
});
test('failed read preserves the previous snapshot',async()=>{
 await reset();await op('solicitar',range);let j=(await op('buscar')).job;await finish(j,[event()]);j=await requeue(j);
 await op('resultado',{id:j.id,lease_token:j.lease_token,resultado:'erro',mensagem:'Permission denied'});
 assert.equal((await run('select count(*)::int n from agenda_google_visiveis'))[0].n,1);
 assert.equal((await run('select status from agenda_google_leituras where id=$1',[j.id]))[0].status,'ERRO');
});
test('complete empty snapshot removes deleted Google events',async()=>{
 await reset();await op('solicitar',range);let j=(await op('buscar')).job;await finish(j,[event()]);j=await requeue(j);await finish(j,[]);
 assert.equal((await run('select count(*)::int n from agenda_google_visiveis'))[0].n,0);
});
test('stale or forged lease cannot replace a snapshot',async()=>{
 await reset();await op('solicitar',range);const j=(await op('buscar')).job;
 await assert.rejects(op('resultado',{id:j.id,lease_token:randomUUID(),resultado:'ok',eventos:[]}),/substituída/);
});
test('same Google ID in different calendars remains distinct',async()=>{
 await reset();await op('solicitar',range);let j=(await op('buscar')).job;await finish(j,[event('same')]);
 j=(await op('buscar')).job;await finish(j,[event('same')]);
 assert.equal((await run('select count(*)::int n from agenda_google_visiveis'))[0].n,2);
});
test('source calendar change invalidates the old callback',async()=>{
 await reset();await op('solicitar',range);const j=(await op('buscar')).job;
 await run('update agenda_calendarios set calendar_id=$1 where id=$2',['new@example.com',j.agenda_id]);
 await assert.rejects(finish(j,[]),/agenda mudou/);
 await run('update agenda_calendarios set calendar_id=$1 where id=$2',[j.calendar_id,j.agenda_id]);
});
test('browser roles cannot read the mirror or execute synchronization RPC',async()=>{
 await db.exec('set role authenticated');try{
   await assert.rejects(run('select * from agenda_google_visiveis'),/permission denied/);
   await assert.rejects(run("select agenda_google_operar('buscar')"),/permission denied/);
 }finally{await db.exec('reset role');}
});
test('existing local Google event is not duplicated by its mirror',async()=>{
 await reset();await op('solicitar',range);const j=(await op('buscar')).job, row=event();await finish(j,[row]);
 const c=(await run('select * from agenda_calendarios where id=$1',[j.agenda_id]))[0];const user=randomUUID(),id=randomUUID();
 await run(`insert into agenda_eventos(id,administracao_id,agenda_id,municipio,titulo,categoria,local,inicio,fim,criado_por,criado_por_nome,status,google_calendar_id,google_event_id)
 values($1,$2,$3,$4,'Evento local','Reunião','Central',$5,$6,$7,'Responsável','CONFIRMADO',$8,$9)`,[id,c.administracao_id,c.id,c.municipio,row.inicio,row.fim,user,j.calendar_id,row.google_event_id]);
 assert.equal((await run('select count(*)::int n from agenda_google_visiveis'))[0].n,0);
 await run('delete from agenda_eventos where id=$1',[id]);
});
test('malformed snapshot does not erase cache',async()=>{
 await reset();await op('solicitar',range);let j=(await op('buscar')).job;await finish(j,[event()]);j=await requeue(j);
 await assert.rejects(op('resultado',{id:j.id,lease_token:j.lease_token,resultado:'ok'}),/inválida/);
 assert.equal((await run('select count(*)::int n from agenda_google_visiveis'))[0].n,1);
});
