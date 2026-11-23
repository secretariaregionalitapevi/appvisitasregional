/* Lógica pura compartilhada pelo workflow n8n e pelos testes locais. */
function agendaResult(job, result, extra = {}) {
  return {id: job.id, lease_token: job.lease_token, protocol_version:2, resultado: result, ...extra};
}
function agendaNativeList(items) {
  if(!Array.isArray(items) || !items.length || items.some(item=>!item || item.error)) {
    return {statusCode:0,body:{error:'Falha na consulta nativa do Google Calendar'}};
  }
  // Always Output Data mantém a execução quando Get Many retorna zero eventos.
  const events=items.filter(item=>Object.keys(item).length>0);
  if(events.some(event=>!event.id || !event.start || !event.end)) {
    return {statusCode:0,body:{error:'Resposta nativa incompleta'}};
  }
  return {statusCode:200,body:{kind:'calendar#events',items:events}};
}
function agendaNativeCreated(job, event) {
  return agendaCreated(job,event?.error ? {statusCode:0,body:event} : {statusCode:200,body:event});
}
function agendaSyncResult(job, items) {
  const response=agendaNativeList(items);
  if(response.statusCode!==200 || response.body.items.length>3000) {
    return {id:job.id,lease_token:job.lease_token,resultado:'erro',mensagem:'Leitura incompleta ou acima de 3000 eventos. Confira a execução do nó Google Calendar.'};
  }
  return {id:job.id,lease_token:job.lease_token,resultado:'ok',eventos:response.body.items.map(e=>({
    id:e.id,summary:e.summary,location:e.location,start:e.start,end:e.end,status:e.status,transparency:e.transparency
  }))};
}
function agendaMatches(expected, event) {
  return event.id === (expected.google_id || expected.id.replace(/-/g,'')) && event.status !== 'cancelled'
    && event.summary === expected.titulo && (event.location || '') === expected.local
    && Date.parse(event.start?.dateTime) === Date.parse(expected.inicio)
    && Date.parse(event.end?.dateTime) === Date.parse(expected.fim);
}
function agendaConflicts(job, sources, responses) {
  const ids=['cotia','caucaia','vargem_grande','itapevi','jandira','santana','pirapora'];
  if(!Array.isArray(job.calendars)||job.calendars.length!==7||!ids.every(id=>job.calendars.some(c=>c.id===id))||
      !Array.isArray(sources)||sources.some(c=>!c||!c.calendar_id||!c.administracao_id)||
      ![7,8].includes(sources.length)||responses.length!==sources.length||
      !job.calendars.every(c=>sources.some(s=>s.id===c.id&&s.calendar_id===c.calendar_id))||
      sources.some(s=>!ids.includes(s.id)&&(s.id!=='legado'||s.calendar_id!==job.google_calendar_id))) {
    return agendaResult(job, 'erro', {mensagem:'A consulta das sete agendas municipais ficou incompleta.'});
  }
  const conflicts=[];
  for(let i=0;i<responses.length;i++) {
    const response=responses[i], source=sources[i], body=response.body;
    const items=body?.items ?? (body?.kind==='calendar#events' ? [] : null);
    if(Number(response.statusCode)!==200 || !body || !Array.isArray(items) || body.nextPageToken) {
      return agendaResult(job,'erro',{mensagem:'Não foi possível consultar todos os compromissos. Confira permissões e paginação.'});
    }
    for(const event of items) {
      if(event.status==='cancelled' || event.transparency==='transparent') continue;
      if(source.calendar_id===job.google_calendar_id && event.id===job.google_id) {
        return agendaMatches(job,event) ? agendaResult(job,'confirmado',{google_event_id:job.google_id}) :
          agendaResult(job,'erro',{mensagem:'O evento com este protocolo foi alterado no Google. Concilie antes de continuar.'});
      }
      const start=event.start?.dateTime || (event.start?.date ? event.start.date+'T00:00:00-03:00':null);
      const end=event.end?.dateTime || (event.end?.date ? event.end.date+'T00:00:00-03:00':null);
      if(!start || !end || !Number.isFinite(Date.parse(start)) || !Number.isFinite(Date.parse(end))) {
        return agendaResult(job,'erro',{mensagem:'Um compromisso Google está sem intervalo válido.'});
      }
      if(Date.parse(start)>=Date.parse(job.fim)||Date.parse(end)<=Date.parse(job.inicio)) continue;
      const approved=(job.allowed_google_events||[]).some(e=>e.google_calendar_id===source.calendar_id && agendaMatches(e,event));
      const authorizedExternal=(job.conflitos_externos||[]).some(e=>e.calendar_id===source.calendar_id &&
        e.google_event_id===event.id && e.etag===event.etag && e.inicio===start && e.fim===end);
      if(approved || authorizedExternal) continue;
      conflicts.push({administracao_id:source.administracao_id,agenda_id:source.id,municipio:source.municipio,
        calendar_id:source.calendar_id,google_event_id:event.id,titulo:String(event.summary||'Compromisso externo').slice(0,180),inicio:start,fim:end,etag:event.etag});
    }
  }
  if(conflicts.length>100) return agendaResult(job,'erro',{mensagem:'Há muitos conflitos nesse período. Reduza o intervalo ou confira as agendas.'});
  return conflicts.length ? agendaResult(job,'conflito_externo',{conflitos:conflicts}) : agendaResult(job,'livre');
}
function agendaCreated(job, response) {
  if([200,201].includes(Number(response.statusCode)) && agendaMatches(job,response.body||{})) {
    return agendaResult(job,'confirmado',{google_event_id:job.google_id});
  }
  return agendaResult(job,'erro',{mensagem:'A criação não foi confirmada. Reprocesse para conciliar pelo identificador único, sem duplicar o evento.'});
}
function agendaDeleted(job, response) {
  // Aqui a resposta é de GET após falha do Delete nativo: HTTP 200 significa
  // que o evento ainda existe, não uma exclusão bem-sucedida.
  return [404,410].includes(Number(response.statusCode)) || Number(response.statusCode)===200 && response.body?.status==='cancelled' ? agendaResult(job,'cancelado') :
    agendaResult(job,'erro',{mensagem:'A remoção no Google não foi confirmada. O horário permanece reservado.'});
}
if(typeof module!=='undefined') module.exports={agendaResult,agendaMatches,agendaConflicts,agendaCreated,agendaDeleted,agendaNativeList,agendaNativeCreated,agendaSyncResult};
