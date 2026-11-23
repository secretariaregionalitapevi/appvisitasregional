/* PostgreSQL isolado em memória. Instale PGlite em tmp/agenda-validation. */
const {test,before,after}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const {resolve}=require('node:path');
const {randomUUID}=require('node:crypto');
const {PGlite}=require(process.env.AGENDA_PGLITE_MODULE||'../../tmp/agenda-validation/node_modules/@electric-sql/pglite');
let db, migrationSnapshot;
const ids={master:randomUUID(),itapevi:randomUUID(),cotia:randomUUID(),regional:randomUUID(),other:randomUUID()};
const run=async(sql,args=[])=> (await db.query(sql,args)).rows;
const op=async(action,data,user='master',level='global',city='')=> (await run('select public.agenda_operar($1,$2::jsonb,$3::uuid,$4,$5,$6,$7) value',
  [action,JSON.stringify(data),ids[user],user,level,city,user==='master']))[0].value;
const worker=async(action,data={})=>(await run('select public.agenda_trabalho($1,$2::jsonb) value',[action,JSON.stringify({protocol_version:2,...data})]))[0].value;
function payload(admin='itapevi',hour=19,day=1){return {id:randomUUID(),administracao_id:admin,municipio:{itapevi:'Itapevi',cotia:'Cotia',jandira:'Jandira',santana:'Santana de Parnaíba'}[admin],titulo:'Reunião',categoria:'Técnica',local:'Central',inicio:`2099-12-${String(day).padStart(2,'0')}T${hour}:00:00-03:00`,fim:`2099-12-${String(day).padStart(2,'0')}T${hour+2}:00:00-03:00`};}
async function decide(event,user,adm,decision='APROVAR'){return op('parecer',{id:event.id,versao:event.versao,administracao_id:adm,decisao:decision,justificativa:'Análise dos responsáveis'},user,'municipal',adm==='cotia'?'Cotia':'Itapevi');}
async function reset(){await db.exec('truncate agenda_notificacoes,agenda_historico,agenda_pareceres,agenda_eventos restart identity;');}
before(async()=>{
  db=new PGlite();
  await db.exec(`create role anon; create role authenticated; create role service_role;
    create table public.profiles(user_id uuid primary key,full_name text,status text,whatsapp text,celular text,telefone text);`);
  for(const [name,id] of Object.entries(ids)) await run("insert into profiles(user_id,full_name,status) values($1,$2,'approved')",[id,name]);
  await db.exec(readFileSync(resolve(__dirname,'../migrations/064_agenda_regional.sql'),'utf8'));
  for(const adm of ['itapevi','cotia','jandira','santana']) await op('configurar',{tipo:'agenda',administracao_id:adm,calendar_id:adm+'@group.calendar.google.com',prazo_horas:48});
  for(const name of ['itapevi','cotia']) await op('configurar',{tipo:'responsavel',user_id:ids[name],papel:'ENCARREGADO',administracao_id:name});
  await op('configurar',{tipo:'responsavel',user_id:ids.regional,papel:'REGIONAL'});
  const oldRequest=await op('criar',{...payload('cotia',19,15),municipio:'Caucaia do Alto'});
  const oldJob=(await worker('buscar')).job;
  await worker('resultado',{id:oldJob.id,lease_token:oldJob.lease_token,resultado:'confirmado',google_event_id:oldJob.google_id});
  await db.exec(readFileSync(resolve(__dirname,'../migrations/065_agenda_calendarios_municipais.sql'),'utf8'));
  migrationSnapshot={calendars:await run('select * from agenda_calendarios'),event:(await run('select * from agenda_eventos where id=$1',[oldRequest.id]))[0],roles:await run('select * from agenda_responsaveis')};
  for(const c of migrationSnapshot.calendars)if(!c.calendar_id)await op('configurar',{tipo:'agenda',agenda_id:c.id,calendar_id:c.id+'-municipal@group.calendar.google.com'});

});
after(async()=>{if(db)await db.close();});

test('SQL: same administration blocks and adjacent intervals are allowed',async()=>{
  await reset(); await op('criar',payload());
  await assert.rejects(op('criar',payload()),/mesma administração/);
  assert.equal((await op('criar',payload('itapevi',21))).status,'PRONTO');
});
test('SQL: client cannot create outside municipal scope',async()=>{
  await reset();await assert.rejects(op('criar',payload('cotia'),'other','municipal','Itapevi'),/escopo/);
  await assert.rejects(op('criar',payload(),'other','local','Itapevi'),/escopo/);
  assert.equal((await op('criar',payload(),'other','municipal','Itapevi')).status,'PRONTO');
});
test('SQL: retry of the same request does not duplicate or accept changed data',async()=>{
  await reset();const p=payload();await op('criar',p);await op('criar',p);
  assert.equal((await run('select count(*)::int n from agenda_eventos'))[0].n,1);
  await assert.rejects(op('criar',{...p,titulo:'Alterado'}),/outros dados/);
});
test('SQL: cross-administration requires both delegated opinions',async()=>{
  await reset();await op('criar',payload());let e=await op('criar',payload('cotia'));
  assert.equal(e.status,'PENDENTE_ADM');
  await assert.rejects(decide(e,'other','itapevi'),/designado/);
  e=await decide(e,'itapevi','itapevi');assert.equal(e.status,'PENDENTE_ADM');
  await assert.rejects(decide(e,'itapevi','itapevi'),/duplicate/);
  e=await decide(e,'cotia','cotia');assert.equal(e.status,'PRONTO');
});
test('SQL: impediment escalates and only designated Regional gives final decision',async()=>{
  await reset();await op('criar',payload());let e=await op('criar',payload('cotia'));
  e=await decide(e,'itapevi','itapevi','IMPEDIMENTO');assert.equal(e.status,'PENDENTE_REGIONAL');
  await assert.rejects(decide(e,'master',null),/Regional designada/);
  e=await decide(e,'regional',null);assert.equal(e.status,'PRONTO');
});
test('SQL: Regional can refuse and release the requested interval',async()=>{
  await reset();await op('criar',payload());let e=await op('criar',payload('cotia'));
  e=await decide(e,'itapevi','itapevi','IMPEDIMENTO');e=await decide(e,'regional',null,'RECUSAR');assert.equal(e.status,'RECUSADO');
  assert.equal((await op('criar',payload('cotia'))).status,'PENDENTE_ADM');
});
test('SQL: no response by deadline escalates but never confirms',async()=>{
  await reset();await op('criar',payload());const e=await op('criar',payload('cotia'));
  await run("update agenda_eventos set prazo_em=now()-interval '1 hour' where id=$1",[e.id]);await worker('buscar');
  assert.equal((await run('select status from agenda_eventos where id=$1',[e.id]))[0].status,'PENDENTE_REGIONAL');
});
test('SQL: reminder is enqueued once at half the deadline',async()=>{
  await reset();await op('criar',payload());const e=await op('criar',payload('cotia'));
  await run("update agenda_eventos set criado_em=now()-interval '30 hours',prazo_em=now()+interval '10 hours' where id=$1",[e.id]);
  await worker('buscar');await worker('buscar');
  const rows=await run("select count(*)::int n,count(distinct destinatario)::int recipients from agenda_notificacoes where evento_id=$1 and tipo='LEMBRETE_PARECER'",[e.id]);
  assert.ok(rows[0].n>0);assert.equal(rows[0].n,rows[0].recipients);
});
test('SQL: new request does not revoke older reservation',async()=>{
  await reset();const older=await op('criar',payload());await op('criar',payload('cotia'));
  const {job}=await worker('buscar');assert.equal(job.id,older.id);assert.equal(job.status,'INTEGRANDO');
});
test('SQL: stale lease callback cannot confirm; lease recovery uses same Google ID',async()=>{
  await reset();await op('criar',payload());const first=(await worker('buscar')).job;
  assert.equal((await worker('buscar')).job,null);
  await run("update agenda_eventos set lease_ate=now()-interval '1 minute' where id=$1",[first.id]);
  const second=(await worker('buscar')).job;assert.equal(second.google_id,first.google_id);assert.notEqual(second.lease_token,first.lease_token);
  await assert.rejects(worker('resultado',{id:first.id,lease_token:first.lease_token,resultado:'confirmado',google_event_id:first.google_id}),/substituída/);
  const data={id:second.id,lease_token:second.lease_token,resultado:'confirmado',google_event_id:second.google_id};
  assert.equal((await worker('resultado',data)).status,'CONFIRMADO');
  await worker('resultado',data);
  assert.equal((await run("select count(*)::int n from agenda_historico where evento_id=$1 and acao='INTEGRACAO'",[second.id]))[0].n,1);
});
test('SQL: ambiguous Google result preserves reservation until reconciliation',async()=>{
  await reset();await op('criar',payload());const {job}=await worker('buscar');
  let e=await worker('resultado',{id:job.id,lease_token:job.lease_token,resultado:'erro',mensagem:'Timeout'});
  assert.equal(e.status,'ERRO_INTEGRACAO');
  await assert.rejects(op('criar',payload()),/mesma administração/);
  await assert.rejects(op('cancelar',{id:e.id,justificativa:'Cancelar teste'}),/verificação/);
  e=await op('reenviar',{id:e.id},'regional');assert.equal(e.status,'PRONTO');
});
test('SQL: cancellation only frees a confirmed event after Google deletion',async()=>{
  await reset();await op('criar',payload());const {job}=await worker('buscar');
  await worker('resultado',{id:job.id,lease_token:job.lease_token,resultado:'confirmado',google_event_id:job.google_id});
  await assert.rejects(op('cancelar',{id:job.id,justificativa:'Solicitado'},'other','municipal','Itapevi'),/não pode/);
  assert.equal((await op('cancelar',{id:job.id,justificativa:'Solicitado'})).status,'CANCELANDO');
  await assert.rejects(op('criar',payload()),/mesma administração/);
  const cancel=(await worker('buscar')).job;assert.equal(cancel.status,'CANCELANDO');
  await worker('resultado',{id:cancel.id,lease_token:cancel.lease_token,resultado:'cancelado'});
  assert.equal((await op('criar',payload())).status,'PRONTO');
});
test('SQL: external cross conflict goes to Regional; same administration is refused',async()=>{
  await reset();await op('criar',payload());let {job}=await worker('buscar');
  let e=await worker('resultado',{id:job.id,lease_token:job.lease_token,resultado:'conflito_externo',conflitos:[{administracao_id:'cotia',google_event_id:'external',etag:'v1'}]});
  assert.equal(e.status,'PENDENTE_REGIONAL');
  e=await decide(e,'regional',null);assert.equal(e.status,'PRONTO');
  job=(await worker('buscar')).job;assert.equal(job.conflitos_externos[0].google_event_id,'external');
  e=await worker('resultado',{id:job.id,lease_token:job.lease_token,resultado:'conflito_externo',conflitos:[{administracao_id:'jandira',google_event_id:'new-external',etag:'v1'}]});
  assert.equal(e.conflitos_externos.length,2);
  e=await decide(e,'regional',null);job=(await worker('buscar')).job;
  e=await worker('resultado',{id:job.id,lease_token:job.lease_token,resultado:'conflito_externo',conflitos:[{administracao_id:'itapevi',google_event_id:'occupied'}]});
  assert.equal(e.status,'RECUSADO');
});
test('SQL: configuration is global-only and only one titular per administration',async()=>{
  await assert.rejects(op('configurar',{tipo:'responsavel',user_id:ids.other,papel:'REGIONAL'},'regional','regional'),/global/);
  await assert.rejects(op('configurar',{tipo:'responsavel',user_id:ids.other,papel:'ENCARREGADO',administracao_id:'itapevi'}),/duplicate/);
});
test('SQL: notification lease and acknowledgment prevent repeated acknowledgments',async()=>{
  await reset();await op('criar',payload());const {notification}=await worker('notificacao');assert.ok(notification);
  const ack={id:notification.id,lease_token:notification.lease_token};
  assert.equal((await worker('notificado',ack)).ok,true);assert.equal((await worker('notificado',ack)).ok,false);
});
test('SQL: browser roles cannot read tables or invoke machine RPC',async()=>{
  await db.exec('set role authenticated');
  try {await assert.rejects(run('select * from agenda_eventos'),/permission denied/);
    await assert.rejects(run("select agenda_trabalho('buscar')"),/permission denied/);
  } finally {await db.exec('reset role');}
});
test('SQL: service role can invoke RPC but cannot bypass reservation with direct insert',async()=>{
  await reset();await db.exec('set role service_role');
  try {assert.equal((await worker('buscar')).job,null);
    await assert.rejects(run("insert into agenda_administracoes(id,nome,municipios) values('other','Other','{}')"),/permission denied/);
  }finally{await db.exec('reset role');}
});
test('065: migration preserves roles, original Google binding and municipal identity',()=>{
  assert.equal(migrationSnapshot.roles.length,3);
  assert.equal(migrationSnapshot.event.agenda_id,'caucaia');
  assert.equal(migrationSnapshot.event.google_calendar_id,'cotia@group.calendar.google.com');
  assert.equal(migrationSnapshot.event.status,'CONFIRMADO');
  assert.equal(migrationSnapshot.calendars.length,7);
  assert.equal(migrationSnapshot.calendars.find(c=>c.id==='itapevi').calendar_id,'itapevi@group.calendar.google.com');
  assert.equal(migrationSnapshot.calendars.find(c=>c.id==='cotia').calendar_id,'');
  assert.equal(migrationSnapshot.calendars.find(c=>c.id==='caucaia').calendar_id,'');
  assert.equal(migrationSnapshot.calendars.filter(c=>c.administracao_id==='cotia').length,3);
  assert.equal(migrationSnapshot.calendars.filter(c=>c.administracao_id==='santana').length,2);
});
test('065: every municipality publishes to its own destination',async()=>{
  const calendars=await run('select * from agenda_calendarios');
  for(const c of calendars){
    await reset();const e=await op('criar',{...payload(c.administracao_id),municipio:c.municipio});
    assert.equal(e.agenda_id,c.id);
    const {job}=await worker('buscar');assert.equal(job.google_calendar_id,c.calendar_id);
    assert.equal(job.calendars.length,7);assert.equal(job.calendar_schema,'municipal-v1');
  }
});
test('065: different municipalities in the same administration remain blocked on overlap',async()=>{
  await reset();await op('criar',payload('cotia'));
  await assert.rejects(op('criar',{...payload('cotia'),municipio:'Caucaia do Alto'}),/mesma administração/);
});
test('065: municipality cannot be forged by choosing another administration',async()=>{
  await reset();await assert.rejects(op('criar',{...payload('itapevi'),municipio:'Caucaia do Alto'}),/incompatível/);
});
test('065: municipal scope is not expanded by the shared administration',async()=>{
  await reset();await assert.rejects(op('criar',{...payload('cotia'),municipio:'Caucaia do Alto'},'other','municipal','Cotia'),/escopo/);
});
test('065: no Google Calendar ID can be shared between municipalities',async()=>{
  await reset();const target=(await run("select calendar_id from agenda_calendarios where id='cotia'"))[0];
  await assert.rejects(op('configurar',{tipo:'agenda',agenda_id:'caucaia',calendar_id:target.calendar_id}),/duplicate/);
});
test('065: deadlines remain properties of the administration',async()=>{
  await reset();await op('configurar',{tipo:'prazo',administracao_id:'cotia',prazo_horas:24});
  const e=await op('criar',{...payload('cotia'),municipio:'Vargem Grande Paulista'});
  assert.ok(Math.abs(Date.parse(e.prazo_em)-Date.parse(e.criado_em)-24*3600000)<1000);
});
test('065: old n8n workflow cannot claim work',async()=>{
  await assert.rejects(run("select agenda_trabalho('buscar','{}'::jsonb)"),/protocolo 2/);
});
