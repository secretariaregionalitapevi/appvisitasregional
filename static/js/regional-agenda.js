(() => {
  'use strict';
  const root = document.getElementById('regional-agenda');
  if (!root) return;
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const labels = {PENDENTE_ADM:'Aguardando encarregados',PENDENTE_REGIONAL:'Aguardando Regional',PRONTO:'Aguardando integração',INTEGRANDO:'Integrando com o Google',CONFIRMADO:'Confirmado',CANCELANDO:'Cancelamento em andamento',CANCELADO:'Cancelado',RECUSADO:'Não autorizado',ERRO_INTEGRACAO:'Integração em verificação',GOOGLE:'Cadastrado no Google',GOOGLE_DISPONIVEL:'Google · Disponível'};
  const dateFormat = new Intl.DateTimeFormat('pt-BR', {timeZone:'America/Sao_Paulo',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});
  const clock = new Intl.DateTimeFormat('pt-BR', {timeZone:'America/Sao_Paulo',hour:'2-digit',minute:'2-digit'});
  const saoDate = new Intl.DateTimeFormat('en-CA', {timeZone:'America/Sao_Paulo',year:'numeric',month:'2-digit',day:'2-digit'});
  const nowParts = saoDate.formatToParts(new Date());
  const getPart = type => Number(nowParts.find(p => p.type === type).value);
  let month = new Date(Date.UTC(getPart('year'),getPart('month')-1,1));
  let view = 'calendar', state = null, selected = null, loading = false, opening = false;
  const form = $('agenda-form');
  const dayKey = value => { const p=saoDate.formatToParts(new Date(value)); return ['year','month','day'].map(t=>p.find(x=>x.type===t).value).join('-'); };
  const key = d => d.toISOString().slice(0,10);
  let selectedDay = dayKey(new Date());
  const normalize = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  const active = e => !['RECUSADO','CANCELADO'].includes(e.status);
  const onDay = (e, day) => dayKey(e.inicio)<=day && dayKey(new Date(new Date(e.fim).getTime()-1))>=day;
  const shortDate = day => new Date(day+'T12:00:00Z');
  const capitalize = value => value.charAt(0).toUpperCase()+value.slice(1);
  const adminName = id => state?.administrations.find(a => a.id === id)?.nome || id;
  const cityName = e => e.municipio||(state?.calendars||[]).find(c=>c.id===e.agenda_id)?.municipio||'';
  const feedback = (type,title,message) => window.AppFeedback.show({type,title,message,toast:true});
  const api = async (url, data) => {
    const response = await fetch(url,{method:data ? 'POST':'GET',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':form.querySelector('[name=csrfmiddlewaretoken]').value},...(data ? {body:JSON.stringify(data)}:{})});
    let result; try { result=await response.json(); } catch { throw new Error('A sessão ou o serviço está indisponível. Atualize a página.'); }
    if (!response.ok) throw new Error(result.error || 'Não foi possível concluir a operação.');
    return result;
  };
  const busy = async (button, action) => {
    if (button.disabled) return;
    const original=button.innerHTML; button.disabled=true; button.innerHTML='<i class="fa fa-circle-notch fa-spin me-1" aria-hidden="true"></i>Aguarde…';
    try { await action(); } catch(e) { feedback('error','Operação não concluída',e.message); }
    finally {button.disabled=false;button.innerHTML=original;}
  };
  const eventUrl = id => root.dataset.api + encodeURIComponent(id) + '/';
  const badge = status => `<span class="agenda-status ${['CONFIRMADO','GOOGLE','GOOGLE_DISPONIVEL'].includes(status)?'confirmed':['CANCELADO','RECUSADO'].includes(status)?'closed':'pending'}">${esc(labels[status] || status)}</span>`;
  function renderConnection() {
    const c=state.connection,s=state.sync,notice=$('agenda-setup');
    if(!c)return;
    const messages=[];
    let title='Conclua a conexão das agendas',footer=state.configurada?'Integração configurada':'Configuração pendente';
    if(c.missing_calendars.length)messages.push('IDs ainda não salvos: '+c.missing_calendars.join(', ')+'.');
    if(!c.token_configurado)messages.push(state.master?'Configure AGENDA_N8N_TOKEN no servidor e o mesmo valor na credencial Header Auth do n8n.':'A autenticação da integração precisa ser concluída pela administração.');
    if(c.leitura_configurada===false)messages.push(state.master?'Configure AGENDA_N8N_LEITURA_URL no servidor.':'A leitura das agendas precisa ser configurada pela administração.');
    if(c.processar_configurada===false)messages.push(state.master?'Configure AGENDA_N8N_PROCESSAR_URL no servidor.':'O processamento dos eventos precisa ser configurado pela administração.');
    if(s?.instalada===false){messages.push(state.master?s.mensagem:'A leitura das agendas está sendo preparada pela administração.');footer='Leitura ainda não instalada';}
    if(s?.instalada&&c.token_configurado){
      if(s.acionada===false){title='Não foi possível iniciar a leitura';messages.push('Confira a URL do webhook de leitura no servidor e se o fluxo está publicado no n8n.');footer='Leitura não iniciada';}
      const errors=s.leituras.filter(j=>j.status==='ERRO');
      if(s.pending&&s.acionada!==false){title='Leitura pendente';messages.push(`${s.ok||0} de ${c.ids_configurados} agendas consultadas. Use Atualizar para tentar novamente.`);footer=`Leitura: ${s.ok||0} de ${c.ids_configurados}`;}
      else if(errors.length){title='Algumas agendas não puderam ser consultadas';messages.push('Confira a conexão Google no n8n: '+errors.map(j=>(state.calendars||[]).find(a=>a.id===j.agenda_id)?.nome||j.agenda_id).join(', ')+'. O último resultado válido foi preservado.');footer='Falha na leitura';}
      else if(s.ok){footer='Eventos do Google atualizados';}
    }
    notice.hidden=!messages.length;
    if(messages.length){notice.querySelector('strong').textContent=title;notice.querySelector('p').textContent=messages.join(' ');}
    $('agenda-connection-label').textContent=footer;
    $('agenda-connection-dot').classList.toggle('ready',!messages.length&&s?.ok===7);
    root.dataset.setup=messages.length?'pending':'ready';
  }
  const option = (value,label) => `<option value="${esc(value)}">${esc(label)}</option>`;
  function filteredEvents() {
    const query=normalize($('agenda-search').value.trim());
    return state.events.filter(e => (!$('agenda-filter').value || e.administracao_id===$('agenda-filter').value) &&
      (!$('agenda-calendar-filter').value || e.agenda_id===$('agenda-calendar-filter').value) &&
      (!query || normalize([e.titulo,e.categoria,e.local,cityName(e),adminName(e.administracao_id)].join(' ')).includes(query)));
  }
  function renderAdministrations() {
    const names={cotia:['Cotia, Caucaia e VGP','3 agendas municipais'],itapevi:['Itapevi','1 agenda municipal'],jandira:['Jandira','1 agenda municipal'],santana:['Santana e Pirapora','2 agendas municipais']};
    $('agenda-all').setAttribute('aria-pressed',$('agenda-filter').value?'false':'true');
    $('agenda-legend').innerHTML=state.administrations.map(a=>{
      const count=state.events.filter(e=>e.administracao_id===a.id&&active(e)).length;
      const [name,caption]=names[a.id]||[a.nome,'Agenda da administração'];
      return `<button type="button" class="agenda-administration adm-${esc(a.id)}" data-admin="${esc(a.id)}" aria-pressed="${$('agenda-filter').value===a.id}" aria-label="Filtrar ${esc(a.nome)}"><span class="agenda-adm-dot" aria-hidden="true"></span><span><strong>${esc(name)}</strong><small>${esc(caption)}</small></span><span class="agenda-adm-count" aria-label="${count} compromissos">${count}</span></button>`;
    }).join('');
  }
  function renderDay(events) {
    const entries=events.filter(e=>active(e)&&onDay(e,selectedDay));
    const date=shortDate(selectedDay);
    const title=new Intl.DateTimeFormat('pt-BR',{day:'numeric',month:'long',timeZone:'UTC'}).format(date);
    const weekday=capitalize(new Intl.DateTimeFormat('pt-BR',{weekday:'long',timeZone:'UTC'}).format(date));
    const caption=`${weekday} · ${entries.length} ${entries.length===1?'compromisso':'compromissos'}`;
    const content=entries.length?entries.map(e=>{
      const tag=e.detalhes?'button':'div';
      return `<${tag} ${e.detalhes?`type="button" data-event="${esc(e.id)}"`:''} class="agenda-day-entry adm-${esc(e.administracao_id)}"><small>${e.dia_inteiro?'Dia inteiro':esc(clock.format(new Date(e.inicio)))+' — '+esc(clock.format(new Date(e.fim)))}</small><strong>${esc(e.titulo)}</strong><small>${esc(cityName(e)||adminName(e.administracao_id))}</small></${tag}>`;
    }).join(''):'<div class="agenda-day-empty"><strong>Nenhum compromisso neste dia</strong>Selecione outra data no calendário.</div>';
    $('agenda-day-title').textContent=title;$('agenda-day-caption').textContent=caption;
    $('agenda-day-events').innerHTML=content;
    $('agenda-day-summary').hidden=view!=='calendar';
    $('agenda-day-new').disabled=$('agenda-new').disabled||selectedDay<dayKey(new Date());
    $('agenda-mobile-day').hidden=view!=='calendar';
    $('agenda-mobile-day-content').innerHTML=`<div class="agenda-mobile-day-heading"><div><span>Dia selecionado</span><h3>${esc(title)}</h3></div><small>${esc(weekday)}</small></div>${content}`;
  }
  function render() {
    const municipality=$('agenda-calendar-filter').value;
    const available=(state.calendars||[]).filter(c=>!$('agenda-filter').value||c.administracao_id===$('agenda-filter').value);
    $('agenda-calendar-filter').innerHTML=option('','Todos os municípios')+available.map(c=>option(c.id,c.nome)).join('');
    $('agenda-calendar-filter').value=available.some(c=>c.id===municipality)?municipality:'';
    const filtered=filteredEvents();
    root.dataset.view=view;
    const pending=view==='pending';
    const monthName=capitalize(new Intl.DateTimeFormat('pt-BR',{month:'long',timeZone:'UTC'}).format(month));
    $('agenda-month-label').innerHTML=pending?'Pendências de aprovação':`${esc(monthName)}<span>${month.getUTCFullYear()}</span>`;
    $('agenda-period-context').textContent=pending?'Autorizações e acompanhamento':'Planejamento mensal';
    $('agenda-calendar').hidden=view!=='calendar';
    $('agenda-list').hidden=view==='calendar';
    $('agenda-prev').hidden=$('agenda-next').hidden=$('agenda-today').hidden=pending;
    const pendingCount=state.events.filter(e=>e.detalhes&&['PENDENTE_ADM','PENDENTE_REGIONAL','ERRO_INTEGRACAO'].includes(e.status)).length;
    $('agenda-pending-count').textContent=pendingCount;$('agenda-pending-count').hidden=!pendingCount;
    $('agenda-pending-count').title=pending?'Pendências em todas as datas':'Pendências no período exibido';
    renderAdministrations();renderDay(filtered);
    const today=dayKey(new Date());
    if (view==='calendar') {
      const first=new Date(month);first.setUTCDate(1-first.getUTCDay());
      const monthDays=new Date(Date.UTC(month.getUTCFullYear(),month.getUTCMonth()+1,0)).getUTCDate();
      const cells=Math.ceil((month.getUTCDay()+monthDays)/7)*7;
      root.style.setProperty('--ag-week-count',cells/7);
      let html='<div class="agenda-grid">'+['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'].map((d,i)=>`<div class="agenda-weekday ${i===0||i===6?'weekend':''}">${d}</div>`).join('');
      for(let i=0;i<cells;i++) {
        const day=new Date(first);day.setUTCDate(first.getUTCDate()+i);const d=key(day);
        const entries=filtered.filter(e=>active(e)&&onDay(e,d));
        const dayLabel=new Intl.DateTimeFormat('pt-BR',{dateStyle:'full',timeZone:'UTC'}).format(day);
        html+=`<div class="agenda-day ${day.getUTCMonth()!==month.getUTCMonth()?'outside':''} ${d===today?'today':''} ${d===selectedDay?'selected':''}" data-date="${d}"><div class="agenda-day-heading"><span>${d===today?'Hoje':''}</span><button type="button" class="agenda-date" data-day="${d}" tabindex="${d===selectedDay?0:-1}" aria-pressed="${d===selectedDay}" aria-label="${esc(dayLabel)}; ${entries.length} compromissos" ${d===today?'aria-current="date"':''}><time datetime="${d}">${day.getUTCDate()}</time></button></div>${entries.slice(0,3).map(e=>{
          const tag=e.detalhes?'button':'span';
          return `<${tag} class="agenda-event-pill adm-${esc(e.administracao_id)}" ${e.detalhes?`type="button" data-event="${esc(e.id)}"`:''} title="${esc(e.titulo)} · ${esc(cityName(e))} — ${esc(labels[e.status])}" aria-label="${esc((e.dia_inteiro?'Dia inteiro':clock.format(new Date(e.inicio)))+' '+e.titulo+', '+cityName(e)+', '+labels[e.status])}"><small>${e.dia_inteiro?'Dia':esc(clock.format(new Date(e.inicio)))}</small><span class="agenda-pill-title">${esc(e.titulo)}</span>${!['CONFIRMADO','GOOGLE','GOOGLE_DISPONIVEL'].includes(e.status)?'<span class="agenda-pending-dot" aria-hidden="true"></span>':''}</${tag}>`;
        }).join('')}${entries.length>3?`<button type="button" class="agenda-more" data-day="${d}">+${entries.length-3} compromissos</button>`:''}</div>`;
      }
      $('agenda-calendar').innerHTML=html+'</div>';
    }
    const displayed=view==='pending'?filtered.filter(e=>e.detalhes):filtered;
    const count=displayed.length;
    const scopeName=$('agenda-calendar-filter').value?(state.calendars||[]).find(c=>c.id===$('agenda-calendar-filter').value)?.nome:$('agenda-filter').value?adminName($('agenda-filter').value):'Todas as administrações';
    $('agenda-period-count').textContent=pending?`${count} ${count===1?'solicitação para acompanhar':'solicitações para acompanhar'} · Todas as datas`:`${filtered.filter(active).length} compromissos no período · ${scopeName}`;
    $('agenda-list').innerHTML=`<div class="agenda-list-heading"><h3>${pending?'Solicitações para acompanhar':'Compromissos do período'}</h3><span>${count} ${count===1?'registro':'registros'}</span></div>`+(count?displayed.map(e=>{
      const day=shortDate(dayKey(e.inicio));
      const period=e.dia_inteiro?'Dia inteiro':dateFormat.format(new Date(e.inicio))+' até '+clock.format(new Date(e.fim))+(dayKey(e.inicio)!==dayKey(e.fim)?' · '+dayKey(e.fim).split('-').reverse().join('/'):'');
      return `<article class="agenda-event adm-${esc(e.administracao_id)}"><div class="agenda-event-date"><strong>${day.getUTCDate()}</strong><small>${esc(new Intl.DateTimeFormat('pt-BR',{month:'short',timeZone:'UTC'}).format(day))}</small></div><div><h3>${esc(e.titulo)}</h3><p>${esc(period)}</p><div class="agenda-event-meta"><span class="agenda-adm-label">${esc(adminName(e.administracao_id))}</span>${badge(e.status)}${e.detalhes?`<span>${esc(e.local)}</span>`:''}</div></div><div>${e.detalhes?`<button type="button" class="btn agenda-btn-secondary" data-event="${esc(e.id)}">${pending?'Analisar solicitação':'Ver detalhes'}<i class="fa fa-arrow-up-right-from-square" aria-hidden="true"></i></button>`:''}</div></article>`;
    }).join(''):`<div class="agenda-empty"><i class="fa ${pending?'fa-circle-check':'fa-calendar-days'}" aria-hidden="true"></i><strong>${$('agenda-search').value?'Nenhum resultado encontrado':pending?'Tudo em dia por aqui':'Uma agenda pronta para os próximos encontros'}</strong><p>${$('agenda-search').value?'Tente outro termo ou selecione uma administração diferente.':pending?'Não há solicitações pendentes para seu acesso.':'Selecione um dia no calendário para consultar ou solicitar um compromisso.'}</p></div>`);
  }
  async function load(force=false) {
    if(loading) return; loading=true;root.setAttribute('aria-busy','true');$('agenda-loading').hidden=false;$('agenda-loading').textContent='Atualizando compromissos…';
    try {
      const first=new Date(month);first.setUTCDate(1-first.getUTCDay());const end=new Date(first);
      const days=new Date(Date.UTC(month.getUTCFullYear(),month.getUTCMonth()+1,0)).getUTCDate();
      end.setUTCDate(end.getUTCDate()+Math.ceil((month.getUTCDay()+days)/7)*7);
      state=await api(root.dataset.api+'?'+new URLSearchParams({start:key(first),end:key(end),pending:view==='pending'?'1':'0',sync:force?'1':'0'}));
      const chosen=$('agenda-filter').value;
      $('agenda-filter').innerHTML=option('','Todas as administrações')+state.administrations.map(a=>option(a.id,a.nome)).join('');$('agenda-filter').value=chosen;
      $('agenda-setup').hidden=state.configurada;
      root.dataset.setup=state.configurada?'ready':'pending';
      $('agenda-new').disabled=!state.configurada||!state.administrations.some(a=>a.municipios.length);
      $('agenda-connection-label').textContent=state.configurada?'Integração configurada':'Conexão pendente';
      $('agenda-connection-dot').classList.toggle('ready',state.configurada);
      renderConnection();
      render();$('agenda-loading').hidden=true;
    } catch(e) {$('agenda-loading').textContent='Não foi possível carregar a agenda. Use Atualizar para tentar novamente.';feedback('error','Agenda indisponível',e.message);}
    finally {loading=false;root.setAttribute('aria-busy','false');}
  }
  function municipalities() {
    const admin=state.administrations.find(a=>a.id===form.elements.administracao_id.value);
    form.elements.municipio.innerHTML=(admin?.municipios||[]).map(c=>option(c,c)).join('');
  }
  function newEvent() {
    if(!state||$('agenda-new').disabled)return;
    form.reset();form.dataset.id=crypto.randomUUID();
    form.elements.administracao_id.innerHTML=state.administrations.filter(a=>a.municipios.length).map(a=>option(a.id,a.nome)).join('');
    if([...form.elements.administracao_id.options].some(o=>o.value===$('agenda-filter').value))form.elements.administracao_id.value=$('agenda-filter').value;
    if(selectedDay>=dayKey(new Date())) {form.elements.inicio.value=selectedDay+'T19:00';form.elements.fim.value=selectedDay+'T21:00';}
    municipalities();$('agenda-form-dialog').showModal();
    const municipal=(state.calendars||[]).find(c=>c.id===$('agenda-calendar-filter').value);
    if(municipal&&[...form.elements.administracao_id.options].some(o=>o.value===municipal.administracao_id)){
      form.elements.administracao_id.value=municipal.administracao_id;municipalities();
      if([...form.elements.municipio.options].some(o=>o.value===municipal.municipio))form.elements.municipio.value=municipal.municipio;
    }
  }
  $('agenda-new').addEventListener('click',newEvent);
  $('agenda-day-new').addEventListener('click',newEvent);
  form.elements.administracao_id.addEventListener('change',municipalities);
  form.addEventListener('submit',event=>{event.preventDefault();busy(form.querySelector('[type=submit]'),async()=>{
    const data=Object.fromEntries(new FormData(form));data.id=form.dataset.id;delete data.csrfmiddlewaretoken;
    data.inicio+=':00-03:00';data.fim+=':00-03:00';
    const result=await api(root.dataset.api,data);$('agenda-form-dialog').close();
    const eventStatus=result.event.status;
    if(eventStatus==='CONFIRMADO')feedback('success','Evento confirmado','O evento foi registrado no Google Calendar.');
    else if(eventStatus==='PENDENTE_ADM'||eventStatus==='PENDENTE_REGIONAL')feedback('warning','Solicitação aguardando autorização',eventStatus==='PENDENTE_ADM'?'Os encarregados precisam analisar o conflito. O evento ainda não está confirmado.':'A equipe Regional precisa analisar o conflito. O evento ainda não está confirmado.');
    else if(eventStatus==='RECUSADO')feedback('error','Horário indisponível','Foi encontrado um compromisso conflitante. O evento não foi confirmado; escolha outro horário.');
    else if(result.event.acionado===false||eventStatus==='ERRO_INTEGRACAO')feedback('warning','Solicitação salva, sem confirmação','Não foi possível concluir a consulta ao Google. O horário permanece reservado no sistema; procure a Regional para verificar a integração.');
    else feedback('warning','Solicitação em processamento','A confirmação no Google ainda não foi concluída. Confira a situação antes de considerar o evento agendado.');
    await load();
  });});
  async function detail(id) {
    if(opening) return;opening=true;
    try {
      selected=await api(eventUrl(id));const e=selected.event;
      $('agenda-detail-title').textContent=e.titulo;
      const rows=[['Administração',adminName(e.administracao_id)],['Agenda municipal',cityName(e)],['Situação',labels[e.status]],['Início',dateFormat.format(new Date(e.inicio))],['Término',dateFormat.format(new Date(e.fim))],['Local',e.local],['Solicitante',e.criado_por_nome]];
      $('agenda-detail').innerHTML=`<dl class="agenda-detail-grid">${rows.map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>${e.mensagem_integracao?'<p class="alert alert-warning">'+esc(e.mensagem_integracao)+'</p>':''}<h3>Compromissos envolvidos</h3>${selected.conflicts.length?selected.conflicts.map(c=>`<div class="agenda-conflict"><strong>${esc(c.titulo)}</strong><div>${esc(adminName(c.administracao_id))} · ${esc(dateFormat.format(new Date(c.inicio)))} · ${esc(labels[c.status])}</div></div>`).join(''):'<p>Nenhuma sobreposição registrada no sistema.</p>'}${e.conflitos_externos.length?'<h3>Compromissos encontrados no Google</h3>'+e.conflitos_externos.map(c=>`<div class="agenda-conflict">${esc(c.titulo||'Compromisso externo')} · ${esc(adminName(c.administracao_id))}</div>`).join(''):''}<h3>Pareceres</h3>${selected.opinions.length?selected.opinions.map(p=>`<div class="agenda-conflict"><strong>${esc(p.nome)} · ${esc(p.etapa==='REGIONAL'?'Regional':adminName(p.administracao_id))}</strong><div>${esc(p.decisao==='APROVAR'?'Aprovado':p.decisao==='IMPEDIMENTO'?'Impedimento':'Recusado')} · Rodada ${p.versao}</div><p>${esc(p.justificativa)}</p></div>`).join(''):'<p>Nenhum parecer registrado.</p>'}<h3>Histórico</h3><ol class="agenda-history">${selected.history.map(h=>`<li><strong>${esc(h.nome)}</strong> · ${esc(h.acao)}<br><small>${esc(dateFormat.format(new Date(h.criado_em)))}</small>${h.dados?.justificativa?'<p>'+esc(h.dados.justificativa)+'</p>':''}</li>`).join('')}</ol>`;
      if(e.somente_leitura)$('agenda-detail').innerHTML=`<dl class="agenda-detail-grid">${rows.map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl><p class="agenda-form-note"><i class="fa fa-google" aria-hidden="true"></i>Este compromisso já existe no Google Calendar. Para alterá-lo, use a agenda de origem.</p>`;
      const involved=new Set([e.administracao_id,...selected.conflicts.filter(c=>!['CANCELADO','RECUSADO'].includes(c.status)).map(c=>c.administracao_id)]);
      const already=new Set(selected.opinions.filter(p=>p.versao===e.versao&&p.etapa==='ADM').map(p=>p.administracao_id));
      const allowed=state.roles.filter(r=>r.papel!=='REGIONAL'&&involved.has(r.administracao_id)&&!already.has(r.administracao_id));
      const decision=$('agenda-decision');decision.reset();
      decision.hidden=!(e.status==='PENDENTE_ADM'&&allowed.length||e.status==='PENDENTE_REGIONAL'&&state.regional);
      $('agenda-decision-title').textContent=e.status==='PENDENTE_REGIONAL'?'Decisão final da Regional':'Parecer da administração';
      $('agenda-decision-adm-label').hidden=e.status==='PENDENTE_REGIONAL';
      decision.elements.administracao_id.innerHTML=[...new Set(allowed.map(r=>r.administracao_id))].map(a=>option(a,adminName(a))).join('');
      decision.elements.decisao.innerHTML=option('APROVAR','Autorizar simultaneidade')+(e.status==='PENDENTE_REGIONAL'?option('RECUSAR','Recusar solicitação'):option('IMPEDIMENTO','Apontar impedimento e encaminhar à Regional'));
      $('agenda-cancellation').reset();$('agenda-cancellation').hidden=['INTEGRANDO','ERRO_INTEGRACAO','CANCELANDO','CANCELADO','RECUSADO'].includes(e.status)||!(e.criado_por===state.user_id||state.regional||state.roles.some(r=>r.administracao_id===e.administracao_id));
      $('agenda-retry').hidden=e.status!=='ERRO_INTEGRACAO'||!(state.regional||state.master);
      if(e.somente_leitura){decision.hidden=true;$('agenda-cancellation').hidden=true;$('agenda-retry').hidden=true;}
      if(!$('agenda-detail-dialog').open)$('agenda-detail-dialog').showModal();
    } catch(e){feedback('error','Análise indisponível',e.message);} finally{opening=false;}
  }
  root.addEventListener('click',event=>{
    const button=event.target.closest('[data-event]');if(button){detail(button.dataset.event);return;}
    if(event.target.closest('[data-close]')){event.preventDefault();event.target.closest('dialog').close();}
    const admin=event.target.closest('[data-admin]');
    if(admin&&!admin.matches('form')){const id=admin.dataset.admin;$('agenda-filter').value=$('agenda-filter').value===id?'':id;render();root.querySelector(`button[data-admin="${id}"]`)?.focus();return;}
    const day=event.target.closest('[data-day]');
    if(day){selectDay(day.dataset.day);return;}
    const cell=event.target.closest('.agenda-day');if(cell){selectDay(cell.dataset.date);return;}
    if(event.target.closest('[data-open-config]'))$('agenda-config')?.click();
  });
  async function selectDay(day,focus=false) {
    if(loading)return;
    selectedDay=day;
    const target=new Date(day+'T00:00:00Z');
    if(target.getUTCMonth()!==month.getUTCMonth()||target.getUTCFullYear()!==month.getUTCFullYear()){
      month=new Date(Date.UTC(target.getUTCFullYear(),target.getUTCMonth(),1));await load();
    }else render();
    root.querySelector(`.agenda-date[data-day="${day}"]`)?.focus({preventScroll:!focus});
    if(!focus&&view==='calendar'&&window.matchMedia?.('(max-width:1000px)').matches){
      const summary=$('agenda-mobile-day');
      if(summary.getBoundingClientRect().bottom>window.innerHeight)summary.scrollIntoView?.({block:'nearest',behavior:window.matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'});
    }
  }
  $('agenda-calendar').addEventListener('keydown',event=>{
    const target=event.target.closest('.agenda-date');if(!target)return;
    const date=new Date(target.dataset.day+'T00:00:00Z');
    const movements={ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7,Home:-date.getUTCDay(),End:6-date.getUTCDay()};
    if(!(event.key in movements))return;event.preventDefault();date.setUTCDate(date.getUTCDate()+movements[event.key]);selectDay(key(date),true);
  });
  $('agenda-decision').addEventListener('submit',event=>{event.preventDefault();const f=event.currentTarget;busy(f.querySelector('[type=submit]'),async()=>{
    const result=await api(eventUrl(selected.event.id),{...Object.fromEntries(new FormData(f)),acao:'parecer',versao:selected.event.versao});
    feedback(result.event.reanalise?'warning':'success',result.event.reanalise?'Nova análise necessária':'Decisão registrada',result.event.reanalise?'Os conflitos mudaram. Confira a nova rodada antes de decidir.':labels[result.event.status]);await load();await detail(selected.event.id);
  });});
  $('agenda-cancellation').addEventListener('submit',event=>{event.preventDefault();const f=event.currentTarget;busy(f.querySelector('[type=submit]'),async()=>{
    await api(eventUrl(selected.event.id),{acao:'cancelar',justificativa:f.elements.justificativa.value});feedback('success','Cancelamento registrado','Se o evento estiver no Google, o horário será liberado após a remoção.');await load();await detail(selected.event.id);
  });});
  $('agenda-retry').addEventListener('click',event=>busy(event.currentTarget,async()=>{await api(eventUrl(selected.event.id),{acao:'reenviar'});feedback('success','Verificação solicitada','A integração vai conferir o Google antes de repetir a operação.');await load();await detail(selected.event.id);}));
  $('agenda-filter').addEventListener('change',()=>state&&render());
  $('agenda-calendar-filter').addEventListener('change',()=>state&&render());
  $('agenda-all').addEventListener('click',()=>{if(!state)return;$('agenda-filter').value='';$('agenda-calendar-filter').value='';render();});
  $('agenda-search').addEventListener('input',()=>state&&render());
  function changeMonth(offset){if(loading)return;month.setUTCMonth(month.getUTCMonth()+offset);selectedDay=key(month);load(true);}
  $('agenda-prev').addEventListener('click',()=>changeMonth(-1));
  $('agenda-next').addEventListener('click',()=>changeMonth(1));
  $('agenda-today').addEventListener('click',()=>{if(loading)return;selectedDay=dayKey(new Date());const now=shortDate(selectedDay);month=new Date(Date.UTC(now.getUTCFullYear(),now.getUTCMonth(),1));load(true);});
  $('agenda-refresh').addEventListener('click',event=>busy(event.currentTarget,()=>load(true)));
  root.querySelectorAll('button[data-view]').forEach(button=>button.addEventListener('click',()=>{if(loading)return;view=button.dataset.view;root.querySelectorAll('button[data-view]').forEach(b=>b.setAttribute('aria-pressed',b===button?'true':'false'));load();}));
  async function configuration() {
    const data=await api(root.dataset.config);
    $('agenda-config-content').innerHTML=data.administrations.map(a=>{
      const calendars=(data.calendars||[]).filter(c=>c.administracao_id===a.id);
      return `<section class="agenda-config-group"><header><div><h3>${esc(a.nome)}</h3><p>${calendars.length} ${calendars.length===1?'agenda municipal':'agendas municipais'} · Responsáveis da administração</p></div></header><form class="agenda-deadline-form" data-config-kind="prazo" data-admin="${esc(a.id)}"><label>Prazo para parecer (horas)<input class="form-control" name="prazo_horas" type="number" min="1" max="720" value="${a.prazo_horas}" required></label><button type="submit" class="btn agenda-btn-secondary">Salvar prazo</button></form>${calendars.map(c=>`<div class="agenda-config-row"><strong>${esc(c.nome)}</strong><form class="agenda-municipal-form" data-config-kind="agenda" data-calendar="${esc(c.id)}"><label>ID Google Calendar de ${esc(c.nome)}<input class="form-control" name="calendar_id" value="${esc(c.calendar_id)}" maxlength="300" placeholder="ID da agenda municipal" required></label><button type="submit" class="btn agenda-btn-primary">Salvar agenda</button></form></div>`).join('')}${calendars.length>1&&a.calendar_id?`<details class="agenda-legacy-note"><summary>Consultar ID compartilhado anterior</summary><p>Preservado para consulta. Confirme qual agenda municipal deve utilizá-lo antes de cadastrar.</p><code>${esc(a.calendar_id)}</code></details>`:''}</section>`;
    }).join('');
    const f=$('agenda-responsible-form');f.elements.user_id.innerHTML=option('','Selecione um usuário aprovado')+data.users.map(u=>option(u.user_id,`${u.full_name||'Sem nome'}${u.municipio?' · '+u.municipio:''}`)).join('');
    f.elements.administracao_id.innerHTML=data.administrations.map(a=>option(a.id,a.nome)).join('');
    $('agenda-responsibles').innerHTML=data.responsibles.length?data.responsibles.map(r=>`<div class="agenda-config-row"><strong>${esc(r.nome)}</strong> · ${esc(r.papel)} · ${esc(r.administracao_id?adminName(r.administracao_id):'Regional')} <button class="btn btn-sm btn-outline-danger" data-remove="${esc(r.id)}">Remover vínculo</button></div>`).join(''):'<p>Nenhum responsável designado.</p>';
  }
  $('agenda-config')?.addEventListener('click',event=>busy(event.currentTarget,async()=>{await configuration();$('agenda-config-dialog').showModal();}));
  $('agenda-config-content')?.addEventListener('submit',event=>{event.preventDefault();const f=event.target;busy(f.querySelector('[type=submit]'),async()=>{await api(root.dataset.config,{tipo:f.dataset.configKind,administracao_id:f.dataset.admin,agenda_id:f.dataset.calendar,...Object.fromEntries(new FormData(f))});feedback('success',f.dataset.configKind==='prazo'?'Prazo atualizado':'Agenda municipal configurada','Configuração salva.');await load();});});
  $('agenda-responsible-form')?.elements.papel.addEventListener('change',event=>{const f=event.target.form;f.elements.administracao_id.disabled=event.target.value==='REGIONAL';});
  $('agenda-responsible-form')?.addEventListener('submit',event=>{event.preventDefault();const f=event.currentTarget;busy(f.querySelector('[type=submit]'),async()=>{await api(root.dataset.config,{tipo:'responsavel',...Object.fromEntries(new FormData(f))});feedback('success','Responsável designado','O vínculo foi registrado.');await configuration();await load();});});
  $('agenda-responsibles')?.addEventListener('click',event=>{const b=event.target.closest('[data-remove]');if(b)busy(b,async()=>{await api(root.dataset.config,{tipo:'remover_responsavel',id:b.dataset.remove});feedback('success','Vínculo removido','A autorização para novos pareceres foi revogada.');await configuration();await load();});});
  load(true).then(()=>{const id=new URLSearchParams(window.location.search).get('evento');if(state&&id&&/^[0-9a-f-]{36}$/i.test(id))detail(id);});
})();
