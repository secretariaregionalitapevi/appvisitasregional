(() => {
  'use strict';
  const $=s=>document.querySelector(s), multi=window.MusicMultiSelect;
  multi.setupAll($('#ministry-app'));
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const day=v=>String(v||'').slice(0,10).split('-').reverse().join('/');
  const values=select=>[...select.selectedOptions].map(option=>option.value);
  let data=null,preview=null,review=null,version=0,controller=null,targetEvent=null,previewVersion=0;
  const feedback=(message,tone='danger')=>$('#ministry-feedback').innerHTML=message?`<div class="alert alert-${tone}">${esc(message)}</div>`:'';
  async function request(url,options={}){
    const response=await fetch(url,{cache:'no-store',...options});
    if(response.redirected)throw Error('Sua sessão expirou. Entre novamente.');
    const result=await response.json();
    if(!response.ok)throw Error(result.error||'Não foi possível concluir a operação.');
    return result;
  }
  const csrf=()=>document.querySelector('[name=csrfmiddlewaretoken]').value;
  const post=(action,body)=>request(`/musica/ministerio/api/${action}/`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify(body)});
  function params(){
    const result=new URLSearchParams({ano:$('#ministry-year').value,cargo:$('#ministry-role').value,tipo:$('#ministry-kind').value,busca:$('#ministry-search').value,evento:$('#ministry-event').value,situacao:$('#ministry-state').value});
    multi.values($('#ministry-city')).forEach(v=>result.append('municipio',v));
    multi.values($('#ministry-common')).forEach(v=>result.append('comum',v));
    return result;
  }
  function ratio(cells){
    const present=cells.filter(c=>c.situacao==='PRESENTE').length;
    const verified=cells.filter(c=>['PRESENTE','JUSTIFICOU','SEM_REGISTRO'].includes(c.situacao)).length;
    const pending=cells.filter(c=>['CONFERIR','SEM_DADOS'].includes(c.situacao)).length;
    return `${verified?`<span class="ministry-ratio ${present===0?'zero':present===verified?'':'partial'}">${present}/${verified}</span>`:'<span class="ministry-neutral">Sem conferência</span>'}${pending?`<small>${pending} ${pending===1?'encontro pendente':'encontros pendentes'}</small>`:''}`;
  }
  function details(row,index){
    return `<p class="text-muted">${esc(row.comum)} · ${esc(row.municipio)}</p><div class="ministry-timeline">${row.cells.map((cell,cellIndex)=>`<article><div class="ministry-timeline-date">${day(cell.date)}</div><div><strong>${esc(cell.titulo)}</strong><p>${esc(cell.local)} · ${esc(cell.modalidade)}</p>${cell.observacoes?`<small>${esc(cell.observacoes)}</small>`:''}</div><div><span class="ministry-status ${cell.situacao}">${esc(data.states[cell.situacao])}</span>${data.can_manage&&data.available&&cell.editable?`<button class="btn btn-sm btn-outline-primary mt-2" type="button" data-review="${index}:${cellIndex}">Conferir</button>`:''}</div></article>`).join('')||'<p>Nenhum encontro para o recorte selecionado.</p>'}</div>`;
  }
  function render(){
    const summary=data.summary;
    const commons=summary.commons??new Set(data.rows.map(row=>`${row.municipio}:${row.comum}`)).size;
    $('#ministry-metrics').innerHTML=[['Comuns no recorte',commons,'blue','fa-location-dot'],['Pessoas com presença no recorte',summary.people_present??data.rows.filter(row=>row.present>0).length,'green','fa-user-check'],['Pessoas sem nenhuma presença registrada',summary.without_presence,'red','fa-user-minus'],['Participações a conferir',summary.pending,'amber','fa-clock']].map(([label,value,tone,icon])=>`<article class="ministry-metric ${tone}"><div><span>${label}</span><strong>${value.toLocaleString('pt-BR')}</strong></div><i class="fa ${icon}" aria-hidden="true"></i></article>`).join('');
    $('#ministry-totals').textContent=`${commons} comuns · ${summary.people} pessoas distintas · ${summary.present} presenças somadas por pessoa e encontro. Os cards resumem o período completo; o filtro de situação seleciona as pessoas da lista. Uma comum com dois encarregados conta uma única vez como comum. Pendências não são presenças confirmadas.${summary.commons_present!==undefined?` Comuns com alguma presença: ${summary.commons_present}; sem presença: ${summary.commons_without_presence}; sem conclusão: ${summary.commons_pending}.`:''}`;

    const selectedCities=multi.values($('#ministry-city'));
    $('#ministry-cities').innerHTML=`<button type="button" data-city="" class="${selectedCities.length?'':'active'}" aria-pressed="${!selectedCities.length}">Toda a Regional</button>`+data.options.cities.map(city=>`<button type="button" data-city="${esc(city)}" class="${selectedCities.includes(city)?'active':''}" aria-pressed="${selectedCities.includes(city)}"><i class="fa fa-location-dot" aria-hidden="true"></i>${esc(city)}</button>`).join('');
    $('#ministry-count').textContent=`${data.rows.length} pessoas na lista`;
    const selectedEvent=$('#ministry-event').value;
    const columns=data.event_options.filter(event=>data.rows.some(row=>row.cells.some(cell=>cell.event_id===event.id)));
    const count=selectedEvent?4:columns.length+3;
    const selectedInfo=data.event_options.find(event=>event.id===selectedEvent);
    $('#ministry-state').querySelectorAll('option').forEach(option=>{if(option.value==='SEM_REGISTRO')option.textContent=selectedEvent?'N\u00e3o participou deste evento':'Sem presen\u00e7a em nenhum evento do per\u00edodo';});
    $('#ministry-event-shortcuts').innerHTML=[{id:'',titulo:'Todos os eventos do ano'},...data.event_options].map(event=>`<button type="button" data-select-event="${esc(event.id)}" class="${event.id===selectedEvent?'active':''}" aria-pressed="${event.id===selectedEvent}">${event.date?`<strong>${day(event.date)}</strong>`:''}<span>${esc(event.titulo)}</span></button>`).join('');
    $('#ministry-view-context').textContent=selectedInfo?`Exibindo somente: ${selectedInfo.titulo} | ${day(selectedInfo.date)}. Os totais, a lista e as exportações seguem este encontro e os filtros abaixo.`:`Visão anual de ${data.year}: ${columns.length} encontro(s). As presenças são somadas entre eventos. Selecione um encontro para ver presentes e ausentes daquela data.`;

    $('#ministry-list-title').textContent=selectedEvent?(data.filters.situacao==='PRESENTE'?'Presentes no encontro':'Participação no encontro'):'Acompanhamento anual por pessoa';
    $('#ministry-list-hint').textContent=selectedInfo?`${selectedInfo.titulo} · ${day(selectedInfo.date)}`:'Cada coluna representa um encontro. Abra o nome para consultar o histórico.';
    $('#ministry-head').innerHTML=selectedEvent?'<tr><th>Pessoa / comum</th><th>Ministério / cargo</th><th>Situação</th><th>Local de participação</th></tr>':`<tr><th>Pessoa / comum</th><th>Ministério / cargo</th>${columns.map(event=>`<th><strong>${day(event.date)}</strong><small>${esc(event.titulo)}</small><button class="btn btn-sm btn-white border" type="button" data-header-export="${esc(event.id)}">PDF de presentes</button></th>`).join('')}<th>Presenças no recorte</th></tr>`;
    let city=null, common=null;
    $('#ministry-body').innerHTML=data.rows.map((row,index)=>{
      const group=city!==row.municipio?`<tr class="ministry-city-group"><td colspan="${count}"><i class="fa fa-location-dot me-2" aria-hidden="true"></i>${esc(row.municipio)}</td></tr>`:'';
      const commonKey=`${row.municipio}:${row.comum}`;
      const commonGroup=common!==commonKey?`<tr class="ministry-common-group"><td colspan="${count}">${esc(row.comum)} <span class="ministry-role-badge">${data.rows.filter(p=>p.municipio===row.municipio&&p.comum===row.comum).length} pessoa(s)</span></td></tr>`:'';
      city=row.municipio;common=commonKey;
      const byId=new Map(row.cells.map(cell=>[cell.event_id,cell]));
      const status=cell=>cell?`<span class="ministry-status ${cell.situacao}">${esc(data.states[cell.situacao])}</span>`:'<span class="ministry-neutral">Não se aplica</span>';
      const cells=selectedEvent?`<td>${status(byId.get(selectedEvent))}</td><td>${esc(byId.get(selectedEvent)?.local||'—')}</td>`:columns.map(event=>`<td>${status(byId.get(event.id))}${byId.get(event.id)?.situacao==='PRESENTE'?`<small>${esc(byId.get(event.id).local)}</small>`:''}</td>`).join('')+`<td>${ratio(row.cells)}</td>`;
      return group+commonGroup+`<tr><td><button type="button" class="ministry-person" data-person="${index}" aria-haspopup="dialog">${esc(row.nome)}</button><small>${esc(row.comum)}</small></td><td>${row.roles.map(role=>`<span class="ministry-role-badge">${esc(data.roles[role]||role)}</span>`).join(' ')}</td>${cells}</tr>`;
    }).join('')||`<tr><td colspan="${count}" class="events-empty">Nenhuma pessoa para os filtros selecionados.</td></tr>`;
    $('#ministry-events').innerHTML=data.events.map(event=>`<article><div class="ministry-event-top"><span class="ministry-event-date">${day(event.data_evento)}</span><span class="ministry-status ${event.arquivo_sha256?'PRESENTE':'SEM_DADOS'}">${event.arquivo_sha256?'Lista carregada':'Sem lista'}</span></div><h3>${esc(event.titulo)}</h3><p>${esc(event.local)} · ${esc(event.modalidade)}</p><div class="ministry-event-actions"><button class="btn btn-sm btn-primary" type="button" data-event-present="${esc(event.id)}">Ver presentes</button><button class="btn btn-sm btn-white border" type="button" data-event-format="pdf" data-export-event="${esc(event.id)}">PDF de presentes</button><button class="btn btn-sm btn-white border" type="button" data-event-format="excel" data-export-event="${esc(event.id)}">Excel de presentes</button>${data.can_manage&&!event.arquivo_sha256?`<button class="btn btn-sm btn-outline-primary" type="button" data-event-import="${esc(event.id)}">Carregar lista</button>`:''}</div></article>`).join('')||'<p class="text-muted mb-0">Nenhum encontro individual cadastrado neste recorte. Selecione um ensaio ou RT no campo “Evento em análise”.</p>';
    $('#ministry-scope').textContent=`${selectedInfo?selectedInfo.titulo+' | '+day(selectedInfo.date):'Todos os eventos do ano'} · Ano ${data.year} · ${multi.labels($('#ministry-city'),'Toda a Regional')} · ${$('#ministry-role').selectedOptions[0].textContent}`;
    if(!data.available)feedback('A consulta dos ensaios e RTs está disponível. Para cadastrar os novos encontros, é necessário aplicar a migração 036 no banco.','warning');
    else if(data.unmatched)feedback(`${data.unmatched} registros de cargos nos ensaios/RTs não têm uma identidade individual inequívoca no cadastro. Eles não foram atribuídos por aproximação.`,'warning');
    else feedback('');
    if($('#ministry-new'))$('#ministry-new').disabled=!data.available;
  }
  async function load(force=false){
    const current=++version;
    controller?.abort();const currentController=new AbortController();controller=currentController;data=null;
    let timedOut=false;
    const timeout=setTimeout(()=>{timedOut=true;currentController.abort();},45000);
    try{
      if($('#ministry-person-dialog')?.open)$('#ministry-person-dialog').close();
      $('#ministry-app').setAttribute('aria-busy','true');
      $('#ministry-pdf').disabled=$('#ministry-excel').disabled=true;
      $('#ministry-body').innerHTML='<tr><td colspan="8" class="events-empty">Carregando acompanhamento…</td></tr>';
      $('#ministry-head').innerHTML='';$('#ministry-metrics').innerHTML='';$('#ministry-events').innerHTML='';
      const query=params();if(force)query.set('atualizar','1');
      const result=await request('/musica/ministerio/api/painel/?'+query,{signal:currentController.signal});
      if(current!==version)return;
      data=result;
      multi.setOptions($('#ministry-city'),data.options.cities,'Toda a Regional');
      const selected=multi.values($('#ministry-common'));
      $('#ministry-common').innerHTML=data.options.commons.map(c=>`<option value="${esc(c.key)}">${esc(c.name)}</option>`).join('');
      multi.setValues($('#ministry-common'),selected);multi.refresh($('#ministry-common'));
      const chosenEvent=$('#ministry-event').value;
      $('#ministry-event').innerHTML='<option value="">Todos os eventos do ano</option>'+data.event_options.map(event=>`<option value="${esc(event.id)}">${esc(event.titulo)} · ${day(event.date)}</option>`).join('');
      if(chosenEvent&&!data.event_options.some(event=>event.id===chosenEvent))$('#ministry-event').add(new Option('Encontro sem pessoas neste recorte',chosenEvent));
      $('#ministry-event').value=chosenEvent;
      render();$('#ministry-pdf').disabled=$('#ministry-excel').disabled=false;
    }catch(error){if(current===version&&(timedOut||error.name!=='AbortError')){data=null;feedback(timedOut?'A consulta demorou além do esperado. Clique em Atualizar para tentar novamente.':error.message);$('#ministry-body').innerHTML='<tr><td colspan="8" class="events-empty">Não foi possível carregar o acompanhamento. Use Atualizar para tentar novamente.</td></tr>';}}
    finally{clearTimeout(timeout);if(current===version)$('#ministry-app').setAttribute('aria-busy','false');}
  }
  async function download(format,overrides={},trigger=null){
    const button=trigger||$(`#ministry-${format}`);if(button.disabled||!data)return;
    button.disabled=true;const original=button.innerHTML;button.textContent='Gerando…';
    try{
      const query=params();Object.entries(overrides).forEach(([key,value])=>query.set(key,value));
      const response=await fetch(`/musica/ministerio/exportar-${format}/?${query}`,{cache:'no-store'});
      if(!response.ok||response.redirected)throw Error('Não foi possível exportar o acompanhamento.');
      const url=URL.createObjectURL(await response.blob());
      const link=document.createElement('a');link.href=url;
      link.download=decodeURIComponent(response.headers.get('Content-Disposition')?.match(/filename\*=UTF-8''([^;]+)/i)?.[1]||response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]||'')||`Ministerio_${data.year}.${format==='pdf'?'pdf':'xlsx'}`;
      link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(error){feedback(error.message);}finally{button.innerHTML=original;button.disabled=!data;}
  }
  $('#ministry-pdf').onclick=()=>download('pdf');$('#ministry-excel').onclick=()=>download('excel');
  $('#ministry-refresh').onclick=()=>load(true);
  ['#ministry-role','#ministry-common','#ministry-state'].forEach(selector=>$(selector).addEventListener('change',()=>load()));
  ['#ministry-year','#ministry-kind'].forEach(selector=>$(selector).addEventListener('change',()=>{$('#ministry-event').value='';void load();}));
  $('#ministry-event').onchange=()=>load();
  $('#ministry-event-shortcuts').onclick=event=>{const button=event.target.closest('[data-select-event]');if(button){$('#ministry-event').value=button.dataset.selectEvent;void load();}};

  $('#ministry-cities').onclick=event=>{const button=event.target.closest('[data-city]');if(button){multi.setValues($('#ministry-city'),button.dataset.city?[button.dataset.city]:[]);multi.refresh($('#ministry-city'));multi.clear($('#ministry-common'));void load();}};
  $('#ministry-city').addEventListener('change',()=>{multi.clear($('#ministry-common'));void load();});
  let timer;$('#ministry-search').oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>load(),350);};
  $('#ministry-clear').onclick=()=>{multi.clear($('#ministry-city'));multi.clear($('#ministry-common'));$('#ministry-role').value='ENCARREGADO_LOCAL';$('#ministry-event').value=$('#ministry-state').value=$('#ministry-kind').value=$('#ministry-search').value='';void load();};
  const onPersonAction=event=>{
    const person=event.target.closest('[data-person]');
    if(person){const index=Number(person.dataset.person),row=data.rows[index];$('#ministry-person-title').textContent=row.nome;$('#ministry-person-history').innerHTML=details(row,index);$('#ministry-person-dialog').showModal();}
    const button=event.target.closest('[data-review]');
    if(button){const [rowIndex,cellIndex]=button.dataset.review.split(':').map(Number);const row=data.rows[rowIndex];const cell=row.cells[cellIndex];review={...cell,person_key:cell.person_key||row.key};$('#review-context').textContent=`${row.nome} · ${cell.titulo} · ${day(cell.date)}`;$('#review-state').value=cell.situacao;$('#review-note').value=cell.observacoes||'';$('#review-error').textContent='';$('#ministry-review-dialog').showModal();}
  };
  $('#ministry-body').onclick=onPersonAction;$('#ministry-person-history').onclick=onPersonAction;
  $('#ministry-head').onclick=event=>{const button=event.target.closest('[data-header-export]');if(button)void download('pdf',{evento:button.dataset.headerExport,situacao:'PRESENTE',cargo:'',tipo:'',busca:''},button);};
  document.querySelectorAll('[data-close]').forEach(button=>button.onclick=()=>$('#'+button.dataset.close).close());
  $('#ministry-review-form').onsubmit=async event=>{
    event.preventDefault();$('#review-save').disabled=true;
    try{await post('conferir',{...review,situacao:$('#review-state').value,observacoes:$('#review-note').value});$('#ministry-review-dialog').close();await load(true);}
    catch(error){$('#review-error').textContent=error.message;}finally{$('#review-save').disabled=false;}
  };
  function clearPreview(){previewVersion++;preview=null;$('#meeting-preview-result').innerHTML='';$('#meeting-file').value='';$('#meeting-complete').checked=false;}
  function openEvent(event=null){
    if(!data)return;targetEvent=event;$('#ministry-event-form').reset();clearPreview();$('#meeting-error').textContent='';
    $('#meeting-cities').innerHTML=data.options.cities.map(city=>`<option value="${esc(city)}" selected>${esc(city)}</option>`).join('');
    $('#meeting-roles').querySelectorAll('option').forEach(option=>option.selected=option.value==='ENCARREGADO_LOCAL');
    for(const [id,field] of [['title','titulo'],['date','data_evento'],['kind','tipo'],['mode','modalidade'],['place','local'],['family','familia']]){
      $(`#meeting-${id}`).disabled=!!event;if(event)$(`#meeting-${id}`).value=event[field];
    }
    $('#meeting-cities').disabled=$('#meeting-roles').disabled=!!event;
    if(event){[...$('#meeting-cities').options].forEach(o=>o.selected=event.municipios.includes(o.value));[...$('#meeting-roles').options].forEach(o=>o.selected=event.cargos.includes(o.value));}
    $('#ministry-event-dialog').showModal();
  }
  if($('#ministry-new'))$('#ministry-new').onclick=()=>openEvent();
  $('#ministry-events').onclick=event=>{
    const importer=event.target.closest('[data-event-import]');if(importer)openEvent(data.events.find(e=>e.id===importer.dataset.eventImport));
    const exporter=event.target.closest('[data-event-format]');if(exporter)void download(exporter.dataset.eventFormat,{evento:exporter.dataset.exportEvent,situacao:'PRESENTE',cargo:'',tipo:'',busca:''},exporter);
    const present=event.target.closest('[data-event-present]');if(present){$('#ministry-event').value=present.dataset.eventPresent;$('#ministry-state').value='PRESENTE';$('#ministry-role').value='';$('#ministry-kind').value=$('#ministry-search').value='';void load();}
  };
  $('#meeting-file').onchange=()=>{previewVersion++;preview=null;$('#meeting-preview-result').innerHTML='';$('#meeting-complete').checked=false;};
  $('#meeting-preview').onclick=async()=>{
    const file=$('#meeting-file').files[0];if(!file){$('#meeting-error').textContent='Selecione a planilha.';return;}
    const currentPreview=++previewVersion;$('#meeting-preview').disabled=true;$('#meeting-error').textContent='';
    try{
      const body=new FormData();body.append('arquivo',file);
      const result=await request('/musica/ministerio/api/previa/',{method:'POST',headers:{'X-CSRFToken':csrf()},body});
      if(currentPreview!==previewVersion)return;preview=result;
      const cities=new Set(preview.rows.map(row=>row.municipio)),roles=new Set(preview.rows.flatMap(row=>row.roles));
      if(!targetEvent){
        [...$('#meeting-cities').options].forEach(option=>option.selected=cities.has(option.value));
        [...$('#meeting-roles').options].forEach(option=>option.selected=roles.has(option.value));
        if(preview.suggested_date)$('#meeting-date').value=preview.suggested_date;
      }
      $('#meeting-preview-result').innerHTML=`<p><b>${preview.count} registros.</b> Confira cada vínculo antes de salvar.${preview.duplicates.length?' Há nomes repetidos na mesma comum; confira as duplicidades.':''}</p><div class="ministry-preview-scroll"><table class="table"><thead><tr><th>Nome / cargo</th><th>Comum de origem</th><th>Identidade individual</th></tr></thead><tbody>${preview.rows.map(row=>`<tr data-import-row="${row.row}"><td>${esc(row.nome)}<small class="d-block">${row.roles.map(role=>esc(data.roles[role])).join(' / ')}</small></td><td>${row.common_resolved?esc(row.comum):`<select class="form-select" data-import-common><option value="">Selecione a comum</option>${preview.commons.map(c=>`<option value="${esc(c.key)}">${esc(c.key)} · ${esc(c.city)}</option>`).join('')}</select>`}</td><td><select class="form-select" data-import-key><option value="">Selecione a identidade</option>${row.candidates.map(p=>`<option value="${esc(p.key)}" ${row.candidates.length===1?'selected':''}>${esc(p.nome)} · Cadastro existente</option>`).join('')}<option value="${esc(row.source_key)}" ${row.candidates.length===0?'selected':''}>Manter identidade própria desta lista</option></select></td></tr>`).join('')}</tbody></table></div>`;
    }catch(error){if(currentPreview===previewVersion){preview=null;$('#meeting-error').textContent=error.message;}}finally{$('#meeting-preview').disabled=false;}
  };
  $('#ministry-event-form').onsubmit=async event=>{
    event.preventDefault();$('#meeting-error').textContent='';
    if($('#meeting-file').files.length&&!preview){$('#meeting-error').textContent='Confira a planilha antes de salvar.';return;}
    $('#meeting-save').disabled=true;
    try{
      const raw={titulo:$('#meeting-title').value,data_evento:$('#meeting-date').value,tipo:$('#meeting-kind').value,
        modalidade:$('#meeting-mode').value,local:$('#meeting-place').value,familia:$('#meeting-family').value,
        municipios:values($('#meeting-cities')),cargos:values($('#meeting-roles')),conferido:$('#meeting-confirmed').checked,
        lista_completa:$('#meeting-complete').checked,token:preview?.token,event_id:targetEvent?.id,
        mappings:[...document.querySelectorAll('[data-import-row]')].map(row=>({row:Number(row.dataset.importRow),key:row.querySelector('[data-import-key]').value,common:row.querySelector('[data-import-common]')?.value}))};
      const result=await post('salvar',raw);$('#ministry-event-dialog').close();$('#ministry-year').value=raw.data_evento.slice(0,4);await load(true);
      feedback(result.existing?'A lista já estava importada. Nenhum encontro foi duplicado.':'Encontro salvo com histórico individual e autoria.','success');
    }catch(error){$('#meeting-error').textContent=error.message;}finally{$('#meeting-save').disabled=false;}
  };
  void load();
})();
