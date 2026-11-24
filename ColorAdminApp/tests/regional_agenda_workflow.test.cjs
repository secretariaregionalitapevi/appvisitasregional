/* Executa o grafo exportado com saídas nativas/HTTP simuladas; sem acesso a contas. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const path=require('node:path');
const workflow=JSON.parse(readFileSync(path.resolve(__dirname,'../../scripts/n8n/agenda_regional.workflow.json'),'utf8'));
const job={id:'12345678-1234-1234-1234-123456789abc',google_id:'12345678123412341234123456789abc',lease_token:'lease',administracao_id:'itapevi',status:'INTEGRANDO',google_calendar_id:'itapevi@example.com',titulo:'Reunião',local:'Central',inicio:'2099-12-01T19:00:00-03:00',fim:'2099-12-01T21:00:00-03:00',calendars:['itapevi','cotia','jandira','santana','caucaia','vargem_grande','pirapora'].map(id=>({id,administracao_id:{caucaia:'cotia',vargem_grande:'cotia',pirapora:'santana'}[id]||id,calendar_id:id+'@example.com'})),allowed_google_events:[],conflitos_externos:[]};
const googleEvent={id:job.google_id,summary:job.titulo,location:job.local,start:{dateTime:job.inicio},end:{dateTime:job.fim}};
function execute(options={}) {
  const outputs=new Map(),calls=[], callbacks=[];
  const lookup=name=>({first:()=>outputs.get(name)?.[0],all:()=>outputs.get(name)||[]});
  function expression(value,json) {
    if(typeof value!=='string'||!value.startsWith('={{'))return value;
    return new Function('$json','$','return ('+value.slice(3,-2)+');')(json,lookup);
  }
  function visit(name,items) {
    const node=workflow.nodes.find(n=>n.name===name);let result=items, branch=0;
    if(node.type.endsWith('.set')) result=[{json:{app_url:'https://app.example'}}];
    if(node.type.endsWith('.httpRequest')) {
      result=items.map(item=>{
        const url=expression(node.parameters.url,item.json), body=node.parameters.jsonBody?JSON.parse(expression(node.parameters.jsonBody,item.json)):null;
        calls.push({name,url,body});let data;
        if(name==='Reservar trabalho')data={job:options.noJob?null:{...job,...options.job}};
        else if(name==='Conferir remoção após falha')data=options.removalCheck||{statusCode:404,body:{}};
        else if(name==='Registrar resultado'){callbacks.push(body);data={ok:true};}
        else throw new Error('HTTP inesperado: '+name);
        return {json:data};
      });
    }
    if(node.type.endsWith('.googleCalendar')) {
      const p=node.parameters,calendar=expression(p.calendar.value,items[0].json);
      const source=job.calendars.find(c=>c.calendar_id===calendar)||{id:'legado',administracao_id:options.job?.administracao_id||job.administracao_id,calendar_id:calendar};
      const body=p.operation==='create'?{id:expression(p.additionalFields.id,items[0].json),
        summary:expression(p.additionalFields.summary,items[0].json),location:expression(p.additionalFields.location,items[0].json),
        start:{dateTime:expression(p.start,items[0].json),timeZone:workflow.settings.timezone},
        end:{dateTime:expression(p.end,items[0].json),timeZone:workflow.settings.timezone}}:null;
      calls.push({name,calendar,body,operation:p.operation});
      let rows;
      if(p.operation==='getAll') rows=options.calendarEvents?.(source) || (options.existing&&source.id==='itapevi'?[options.existing]:[{}]);
      else if(p.operation==='create')rows=[options.created||body];
      else if(p.operation==='delete')rows=[options.deleted||{success:true}];
      else throw new Error('Operação nativa inesperada: '+p.operation);
      // Get Many emite um item por evento; Always Output Data emite {} quando vazio.
      result=(rows.length?rows:[{}]).map(json=>({json}));
    }
    if(node.type.endsWith('.code')) result=new Function('$','$input',node.parameters.jsCode)(lookup,{first:()=>items[0],all:()=>items});
    if(node.type.endsWith('.if')) {
      const c=node.parameters.conditions.conditions[0];
      branch=expression(c.leftValue,items[0].json)===c.rightValue?0:1;
    }
    outputs.set(name,result);
    for(const edge of workflow.connections[name]?.main[branch]||[])visit(edge.node,result);
  }
  visit('Solicitação do sistema',[{json:{}}]);return {calls,callbacks};
}
test('exported workflow checks seven municipalities and the previously bound destination',()=>{
  const {calls,callbacks}=execute();assert.equal(calls.filter(c=>c.operation==='getAll').length,8);
  const create=calls.find(c=>c.name==='Criar no Google');assert.equal(create.calendar,'itapevi@example.com');
  assert.equal(create.body.id,job.google_id);assert.equal(create.body.start.timeZone,'America/Sao_Paulo');
  assert.equal(callbacks[0].resultado,'confirmado');assert.equal(callbacks[0].lease_token,job.lease_token);
  assert.equal(calls.find(c=>c.name==='Reservar trabalho').body.protocol_version,2);assert.equal(callbacks[0].protocol_version,2);
});
test('exported workflow stops cleanly with no pending job',()=>assert.equal(execute({noJob:true}).callbacks.length,0));
test('exported workflow reports external conflict without creating',()=>{
  const {calls,callbacks}=execute({calendarEvents:c=>c.id==='cotia'?[{...googleEvent,id:'external'}]:[]});
  assert.equal(callbacks[0].resultado,'conflito_externo');assert.equal(callbacks[0].conflitos[0].administracao_id,'cotia');
  assert.equal(calls.some(c=>c.name==='Criar no Google'),false);
});
test('exported workflow does not create when any calendar fails',()=>{
  const {calls,callbacks}=execute({calendarEvents:c=>c.id==='santana'?[{error:'The caller does not have permission'}]:[]});
  assert.equal(callbacks[0].resultado,'erro');assert.equal(calls.some(c=>c.name==='Criar no Google'),false);
});
test('exported workflow reconciles existing event without repeating creation',()=>{
  const {calls,callbacks}=execute({existing:googleEvent});
  assert.equal(callbacks[0].resultado,'confirmado');assert.equal(calls.some(c=>c.name==='Criar no Google'),false);
});
test('exported workflow handles cancellation through the deletion branch',()=>{
  const {calls,callbacks}=execute({job:{status:'CANCELANDO'}});assert.equal(callbacks[0].resultado,'cancelado');
  assert.equal(calls.some(c=>c.operation==='delete'),true);assert.equal(calls.some(c=>c.operation==='getAll'),false);
});
test('exported workflow records ambiguous create for later reconciliation',()=>{
  const {callbacks}=execute({created:{error:'The resource already exists'}});assert.equal(callbacks[0].resultado,'erro');
});
test('native Get Many preserves multiple events and checks all of them',()=>{
  const {callbacks}=execute({calendarEvents:c=>c.id==='jandira'?[{...googleEvent,id:'a'},{...googleEvent,id:'b'}]:[]});
  assert.equal(callbacks[0].resultado,'conflito_externo');assert.equal(callbacks[0].conflitos.length,2);
});
test('failed native Delete reconciles an already absent event',()=>{
  const {calls,callbacks}=execute({job:{status:'CANCELANDO'},deleted:{error:'The resource could not be found'}});
  assert.ok(calls.some(c=>c.name==='Conferir remoção após falha'));assert.equal(callbacks[0].resultado,'cancelado');
});
test('failed native Delete does not release an event that still exists',()=>{
  const {callbacks}=execute({job:{status:'CANCELANDO'},deleted:{error:'Network error'},removalCheck:{statusCode:200,body:googleEvent}});
  assert.equal(callbacks[0].resultado,'erro');
});
test('native Google nodes expose editable fields and paginate complete results',()=>{
  const native=workflow.nodes.filter(n=>n.type==='n8n-nodes-base.googleCalendar');
  assert.equal(native.length,10);
  for(const n of native.filter(n=>n.parameters.operation==='getAll')) {
    assert.equal(n.parameters.returnAll,true);assert.equal(n.alwaysOutputData,true);
    assert.equal(n.parameters.options.recurringEventHandling,'expand');
    assert.ok(n.parameters.timeMin.includes('.inicio'));assert.ok(n.parameters.timeMax.includes('.fim'));
  }
  const create=native.find(n=>n.parameters.operation==='create');
  assert.ok(create.parameters.additionalFields.id.includes('.google_id'));
  assert.ok(create.parameters.additionalFields.summary.includes('.titulo'));
  const googleHttp=workflow.nodes.filter(n=>n.type.endsWith('.httpRequest')&&n.parameters.nodeCredentialType==='googleCalendarOAuth2Api');
  assert.equal(googleHttp.length,1);assert.equal(googleHttp[0].name,'Conferir remoção após falha');
});
test('exported workflows contain no live credential identifiers and remain inactive',()=>{
  for(const file of ['agenda_regional.workflow.json','agenda_notificacoes.workflow.json','agenda_sincronizacao.workflow.json']) {
    const w=JSON.parse(readFileSync(path.resolve(__dirname,'../../scripts/n8n/'+file),'utf8'));
    assert.equal(w.active,false);
    for(const n of w.nodes) {
      if(n.type.endsWith('.code'))assert.doesNotThrow(()=>new Function(n.parameters.jsCode));
      for(const c of Object.values(n.credentials||{}))assert.equal(c.id,'');
      for(const branches of w.connections[n.name]?.main||[])for(const edge of branches)assert.ok(w.nodes.some(other=>other.name===edge.node));
    }
  }
});
test('Caucaia event is created in Caucaia Calendar while retaining Cotia administration',()=>{
  const {calls,callbacks}=execute({job:{agenda_id:'caucaia',municipio:'Caucaia do Alto',administracao_id:'cotia',google_calendar_id:'caucaia@example.com'}});
  assert.equal(calls.find(c=>c.name==='Criar no Google').calendar,'caucaia@example.com');
  assert.equal(callbacks[0].resultado,'confirmado');
});
test('a previously bound shared calendar is reconciled without moving the existing event',()=>{
  const {calls,callbacks}=execute({job:{google_calendar_id:'old-shared@example.com',administracao_id:'cotia'},calendarEvents:c=>c.id==='legado'?[googleEvent]:[]});
  assert.equal(callbacks[0].resultado,'confirmado');assert.equal(calls.some(c=>c.operation==='create'),false);
});
