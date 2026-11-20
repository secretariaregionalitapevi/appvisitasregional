(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const fields = {municipio:'jp-city', comum:'jp-common', evento:'jp-event'};
  const endpoint = '/musica/justificativas/api/painel/';
  let controller, version = 0, exporting = false, loaded = false;
  let agendaSyncAttempted = false;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const date = value => value.split('-').reverse().join('/');
  const feedback = (message, type = 'error') => AppFeedback.show({type, title:'Justificativas', message});
  function query() {
    const params = new URLSearchParams();
    Object.entries(fields).forEach(([key,id]) => {if ($(id).value) params.set(key,$(id).value);});
    return params;
  }
  function exportState() {['jp-excel','jp-pdf'].forEach(id => {$(id).disabled = exporting || !loaded;});}
  function options(id, rows, placeholder) {
    const select = $(id), selected = select.value;
    select.replaceChildren(new Option(placeholder, ''), ...rows.map(r => new Option(r.titulo || r, r.id || r)));
    select.value = selected;
    if (window.jQuery?.fn.select2 && id === 'jp-common') jQuery(select).trigger('change.select2');
  }
  const normalize = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().trim();
  const displayName = value => String(value || '').toLocaleLowerCase('pt-BR').split(/\s+/).map((word,index) =>
    index && ['de','da','do','das','dos','e'].includes(word) ? word : word.charAt(0).toLocaleUpperCase('pt-BR') + word.slice(1)).join(' ');
  function reasonCell(row) {
    let text = String(row.motivo || '').trim();
    const colon = text.indexOf(':');
    if (colon >= 0 && normalize(text.slice(0,colon)) === normalize(row.nome)) text = text.slice(colon+1).trim();
    const match = text.match(/^(Trabalho|Viagem|Enfermidade|Outros?)\b/i);
    const category = match ? (/^outro/i.test(match[1]) ? 'Outros' : displayName(match[1])) : 'Outros';
    let detail = match ? text.slice(match[0].length).replace(/^[\s:–—-]+/,'') : text;
    if (normalize(text) === 'OUTRO MOTIVO') detail = '';
    const tone = {Trabalho:'work',Viagem:'travel',Enfermidade:'health',Outros:'other'}[category];
    const icon = {Trabalho:'fa-briefcase',Viagem:'fa-suitcase-rolling',Enfermidade:'fa-heart-pulse',Outros:'fa-comment-dots'}[category];
    return `<span class="jp-reason-tag ${tone}"><i class="fa ${icon}" aria-hidden="true"></i><span>${category}</span></span>${detail ? `<p class="jp-reason-detail">${esc(detail)}</p>` : ''}`;
  }
  function recordTime(value) {
    const time = new Date(value);
    if (!Number.isFinite(time.getTime())) return '<span class="jp-muted">Não informado</span>';
    const day = time.toLocaleDateString('pt-BR',{timeZone:'America/Sao_Paulo'});
    const hour = time.toLocaleTimeString('pt-BR',{timeZone:'America/Sao_Paulo',hour:'2-digit',minute:'2-digit'});
    return `<time datetime="${esc(value)}">${day}<small>${hour}</small></time>`;
  }
  function renderRecords(data) {
    const events = new Map();
    for (const row of data.items) {
      const key = row.event_key || row.agenda_id || [row.data_evento,row.tipo,row.familia,row.evento_titulo].join('|');
      if (!events.has(key)) events.set(key,[]);
      events.get(key).push(row);
    }
    const cityCount = new Set(data.items.map(r=>r.municipio)).size;
    $('jp-records-count').textContent = `${data.items.length} ${data.items.length === 1 ? 'registro' : 'registros'} · ${cityCount} ${cityCount === 1 ? 'município' : 'municípios'}`;
    $('jp-rows').innerHTML = [...events.values()].map(rows => {
      const event = rows[0], municipalities = new Map();
      rows.sort((a,b)=>String(a.municipio).localeCompare(b.municipio,'pt-BR') || String(a.comum).localeCompare(b.comum,'pt-BR') || String(a.nome).localeCompare(b.nome,'pt-BR'));
      for (const row of rows) {
        if (!municipalities.has(row.municipio)) municipalities.set(row.municipio,[]);
        municipalities.get(row.municipio).push(row);
      }
      const title = event.evento_titulo.replaceAll(date(event.data_evento),'').replaceAll(event.data_evento,'').replace(/^[\s·|–—-]+|[\s·|–—-]+$/g,'');
      const linked = rows.find(row=>row.destino);
      const family = event.familia && event.familia !== 'GERAL' ? ` · ${displayName(event.familia)}` : '';
      return `<section class="jp-record-event"><header class="jp-record-event-head"><div><h3>${esc(title)}</h3><p><i class="fa fa-calendar-day" aria-hidden="true"></i>${date(event.data_evento)}${event.hora ? ' · '+esc(event.hora) : ''}${esc(family)}</p></div><div class="jp-event-actions"><span>${rows.length} ${rows.length === 1 ? 'justificativa' : 'justificativas'}</span>${linked ? `<a href="${esc(linked.destino_url)}">Ver Evento <i class="fa fa-arrow-up-right-from-square" aria-hidden="true"></i></a>` : ''}</div></header>${[...municipalities.entries()].map(([city,people]) => `<div class="jp-record-city"><div class="jp-record-city-head"><h4><i class="fa fa-location-dot" aria-hidden="true"></i>${esc(displayName(city))}</h4><span>${people.length} ${people.length === 1 ? 'participante' : 'participantes'}</span></div><div class="table-responsive"><table class="jp-record-table"><caption class="visually-hidden">Justificativas de ${esc(city)} · ${esc(title)}</caption><thead><tr><th>Comum Congregação</th><th>Nome Completo</th><th>Motivo da Ausência</th><th>Registrado em</th>${data.can_delete ? '<th class="jp-actions-heading">Ações</th>' : ''}</tr></thead><tbody>${people.map(row => {
        const code = String(row.comum).match(/^(BR-\d+-\d+)/i)?.[1] || '';
        const commonName = String(row.comum).replace(/^BR-\d+-\d+\s*-?\s*/i,'');
        const candidates = row.candidates || [];
        const pending = !row.destino ? `<div class="jp-record-pending"><span>Aguardando vínculo ao evento</span>${data.can_manage && candidates.length ? `<select class="form-select form-select-sm" aria-label="Destino da justificativa"><option value="">Selecione o evento correto</option>${candidates.map(c=>`<option value="${esc(c.id)}">${esc(c.titulo)}</option>`).join('')}</select><button class="btn btn-sm btn-outline-primary jp-bind" data-id="${esc(row.id)}" type="button">Vincular ao painel</button>` : ''}</div>` : '';
        return `<tr><td><strong class="jp-common-name">${esc(displayName(commonName))}</strong><small class="jp-common-code">${esc(code)}</small></td><td><span class="jp-person-name">${esc(displayName(row.nome))}</span><small class="jp-person-role">${esc(row.cargo || 'Cargo a Conferir')}</small>${row.cadastro_manual ? '<small class="jp-origin-note">Cadastro Manual</small>' : ''}${row.fora_municipio ? '<small class="jp-origin-note">Fora do Município do Evento</small>' : ''}</td><td>${reasonCell(row)}${pending}</td><td class="jp-record-time">${recordTime(row.created_at)}</td>${data.can_delete && row.delete_token ? `<td class="jp-delete-cell"><button type="button" class="btn btn-outline-danger btn-sm jp-delete" data-token="${esc(row.delete_token)}" data-name="${esc(row.nome)}" aria-label="Excluir justificativa de ${esc(row.nome)}" title="Excluir Justificativa"><i class="fa fa-trash" aria-hidden="true"></i></button></td>` : data.can_delete ? '<td></td>' : ''}</tr>`;
      }).join('')}</tbody></table></div></div>`).join('')}</section>`;
    }).join('') || '<div class="jp-record-empty"><i class="fa fa-clipboard-check" aria-hidden="true"></i><strong>Nenhuma justificativa neste recorte</strong><p>Selecione outro evento, município ou comum para consultar os registros.</p></div>';
  }
  async function load() {
    controller?.abort(); controller = new AbortController(); const current = ++version;
    const params = query(); loaded = false; exportState();
    $('jp-refresh').disabled = true;
    $('jp-refresh').innerHTML = '<i class="fa fa-spinner fa-spin me-1"></i>Atualizando';
    try {
      const response = await fetch(`${endpoint}?${params}`, {signal:controller.signal});
      const data = await response.json();
      if (!response.ok) throw Error(data.error || 'Não foi possível carregar as justificativas.');
      if (current !== version) return;
      if (!agendaSyncAttempted && data.can_manage && data.metrics.pendentes) {
        agendaSyncAttempted = true;
        const response = await fetch(endpoint, {method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify({action:'sync_agenda'})});
        const result = await response.json();
        if (!response.ok) throw Error(result.error || 'Não foi possível sincronizar a agenda.');
        if (result.linked) {await load(); return;}
      }
      options('jp-city', data.options.cities, 'Todos os municípios');
      options('jp-common', data.options.commons.filter(c => !$('jp-city').value || c.municipio === $('jp-city').value), 'Todas as comuns');
      options('jp-event', data.options.events, 'Todos os eventos');
      const metrics = [['total','Justificativas Recebidas','#2f8de4','fa-clipboard-check'],['ENSAIO_REGIONAL','Ensaios Regionais','#10acaa','fa-music'],['REUNIAO_TECNICA','Reuniões Técnicas','#e5a01d','fa-users'],['REUNIAO_MINISTERIO','Reuniões do Ministério','#7d61e7','fa-user-tie']];
      const groups = data.groups || [];
      const labels = ['Itapevi','Jandira','Cotia / Caucaia / VGP','Santana / Pirapora'];
      $('jp-metrics').innerHTML = metrics.map(([key,title,color,icon]) => {
        const max = Math.max(1,...groups.map(g => g[key] || 0));
        return `<article class="management-metric" style="--metric-color:${color}"><div class="management-metric-head"><span>${title}</span><i class="fa ${icon}" aria-hidden="true"></i></div><strong>${data.metrics[key]}</strong><div class="management-metric-note">Contabilizadas no evento selecionado</div><div class="management-metric-chart">${groups.map((g,i) => `<div><b>${g[key] || 0}</b><div class="management-bar-track"><i style="--bar-height:${(g[key] || 0)/max*100}%"></i></div><small>${labels[i]}</small></div>`).join('')}</div><p class="management-metric-footer">Quantidade por administração</p></article>`;
      }).join('');
      const selected = data.options.events.find(e => e.id === $('jp-event').value);
      $('jp-status').textContent = `${selected?.titulo || 'Todos os eventos'} · ${$('jp-city').value || 'Todos os municípios'} · ${$('jp-common').value || 'Todas as comuns'}`;
      $('jp-executive-reading').textContent = `Leitura executiva: ${data.items.length} justificativas dos cargos e ministérios da música nos quatro agrupamentos municipais.${data.metrics.pendentes ? ' ' + data.metrics.pendentes + ' aguardando vínculo ao evento.' : ''}`;
      $('jp-summary').innerHTML = groups.map(g => `<tr><td><i class="fa fa-location-dot text-danger me-1" aria-hidden="true"></i>${esc(g.name)}</td><td>${g.ENSAIO_REGIONAL}</td><td>${g.REUNIAO_TECNICA}</td><td>${g.REUNIAO_MINISTERIO}</td><td><span class="jp-total-badge">${g.total}</span></td></tr>`).join('') + `<tr class="fw-bold"><td>TOTAL GERAL</td><td>${data.metrics.ENSAIO_REGIONAL}</td><td>${data.metrics.REUNIAO_TECNICA}</td><td>${data.metrics.REUNIAO_MINISTERIO}</td><td>${data.metrics.total}</td></tr>`;
      renderRecords(data);
      loaded = true; exportState();
      if (data.agenda_unavailable) feedback('A agenda está indisponível neste momento. As justificativas registradas continuam disponíveis.', 'warning');
    } catch (error) {if (error.name !== 'AbortError') {$('jp-status').textContent = 'Falha ao atualizar. Os dados exibidos podem estar desatualizados.'; feedback(error.message);}}
    finally {if (current === version) {$('jp-refresh').disabled = false; $('jp-refresh').innerHTML = '<i class="fa fa-sync-alt text-primary me-1"></i>Atualizar';}}
  }
  $('jp-filters').addEventListener('submit', e => {e.preventDefault(); load();});
  if (window.jQuery?.fn.select2) {
    jQuery('#jp-common').select2({width:'100%',minimumResultsForSearch:0,language:{noResults:()=> 'Nenhuma comum encontrada'},matcher:(params,item)=>normalize(params.term).split(/\s+/).filter(Boolean).every(word=>normalize(item.text).includes(word))?item:null});
    jQuery('#jp-common').on('select2:open',function(){
      const search=jQuery(this).data('select2').dropdown.$search[0];
      search.placeholder='Pesquisar comum por nome ou código...';
      search.setAttribute('aria-label','Pesquisar comum por nome ou código');
      setTimeout(()=>search.focus(),0);
    }).on('change',load);
  } else $('jp-common').addEventListener('change',load);
  $('jp-event').addEventListener('change',load);
  $('jp-city').addEventListener('change', () => {$('jp-common').value = ''; if(window.jQuery?.fn.select2)jQuery('#jp-common').trigger('change.select2'); load();});
  $('jp-clear').addEventListener('click', () => {Object.values(fields).forEach(id => {$(id).value = '';}); if(window.jQuery?.fn.select2)jQuery('#jp-common').trigger('change.select2'); load();});
  $('jp-rows').addEventListener('click', async e => {
    const deleting = e.target.closest('.jp-delete');
    if (deleting && !deleting.disabled) {
      const confirmed = await AppFeedback.confirm({title:'Excluir Justificativa?',message:`Excluir a justificativa de ${deleting.dataset.name}?`,detail:'O registro deixará de ser contabilizado nos painéis do evento.',confirmText:'Excluir',confirmIcon:'fa-trash',cancelText:'Cancelar'});
      if (!confirmed) return;
      deleting.disabled=true; deleting.innerHTML='<i class="fa fa-spinner fa-spin"></i>';
      try {
        const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify({action:'delete',token:deleting.dataset.token})});
        const result=await response.json(); if(!response.ok)throw Error(result.error || 'Não foi possível excluir.');
        await load();
        AppFeedback.show({type:'success',title:'Justificativa Excluída',message:'O registro foi excluído e os totais foram atualizados.',detail:'Operação concluída.'});
      } catch(error) {feedback(error.message); await load();}
      return;
    }
    const button = e.target.closest('.jp-bind'); if (!button || button.disabled) return;
    const destino = button.parentElement.querySelector('select').value;
    if (!destino) {feedback('Selecione o evento de destino.'); return;}
    button.disabled = true; button.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Vinculando';
    try {
      const response = await fetch(endpoint, {method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify({id:button.dataset.id,destino})});
      const result = await response.json(); if (!response.ok) throw Error(result.error);
      feedback('A justificativa está vinculada ao evento e será contabilizada no painel correspondente.', 'success'); await load();
    } catch (error) {feedback(error.message); button.disabled = false; button.textContent = 'Vincular ao painel';}
  });
  async function download(format) {
    if (exporting || !loaded) return;
    exporting = true; exportState();
    const button = $('jp-' + format), original = button.innerHTML;
    button.innerHTML = '<i class="fa fa-spinner fa-spin me-1"></i>Gerando'; button.setAttribute('aria-busy','true');
    try {
      const response = await fetch(`/musica/justificativas/exportar-${format}/?${query()}`);
      if (!response.ok || response.redirected || (response.headers.get('Content-Type') || '').includes('text/html')) {
        let message = 'Não foi possível exportar. Confira sua sessão e tente novamente.';
        try {message = (await response.json()).error || message;} catch {}
        throw Error(message);
      }
      const disposition = response.headers.get('Content-Disposition') || '';
      const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
      const filename = encoded ? decodeURIComponent(encoded[1]) : disposition.match(/filename="([^"]+)"/)?.[1] || `Justificativas.${format === 'pdf' ? 'pdf' : 'xlsx'}`;
      const url = URL.createObjectURL(await response.blob()), anchor = document.createElement('a');
      anchor.href = url; anchor.download = filename; document.body.append(anchor); anchor.click(); anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url),30000);
    } catch (error) {feedback(error.message);}
    finally {exporting = false; button.innerHTML = original; button.removeAttribute('aria-busy'); exportState();}
  }
  $('jp-excel').addEventListener('click', () => download('excel'));
  $('jp-pdf').addEventListener('click', () => download('pdf'));
  load();
})();
