(() => {
  'use strict';
  const $=s=>document.querySelector(s),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fields={ano:'year',comum:'common',municipio:'city',tipo:'type',modalidade:'mode',resultado:'result',evento:'event',mes:'month',inicio:'start',fim:'end',busca:'search'};
  const day=v=>String(v||'').slice(0,10).split('-').reverse().join('/');
  let data=null,review=null,loading=false,queued=false,searchTimer;
  const query=()=>new URLSearchParams(Object.entries(fields).map(([k,id])=>[k,$('#letters-'+id).value]));
  const csrf=()=>$('[name=csrfmiddlewaretoken]').value;
  const feedback=(text,tone='danger')=>$('#letters-feedback').innerHTML=text?`<div class="alert alert-${tone}">${esc(text)}</div>`:'';
  async function request(url,options={}){const response=await fetch(url,{cache:'no-store',...options});if(response.redirected)throw Error('Sua sessão expirou. Entre novamente.');const result=await response.json();if(!response.ok)throw Error(result.error||'Não foi possível concluir.');return result;}
  function options(selector,values,first){const select=$(selector),old=select.value;select.innerHTML=`<option value="">${first}</option>`+values.map(([v,t])=>`<option value="${esc(v)}">${esc(t)}</option>`).join('');select.value=old;if(window.jQuery&&jQuery(select).hasClass('select2-hidden-accessible'))jQuery(select).trigger('change.select2');}

  const normalize=value=>String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim().toUpperCase();
  function filteredList(prefix,rows){
    const unique=values=>[...new Map(values.filter(Boolean).map(value=>[normalize(value),value])).values()].sort((a,b)=>a.localeCompare(b,'pt-BR'));
    options('#'+prefix+'-city',(data?.list_municipalities?data.list_municipalities:unique(rows.map(r=>r.municipio))).map(value=>[value,value]),'Todos os municípios');
    const city=$('#'+prefix+'-city').value;
    const inCity=rows.filter(r=>!city||normalize(r.municipio)===normalize(city));
    options('#'+prefix+'-common',unique(inCity.map(r=>r.comum)).map(value=>[value,value]),'Todas as comuns');
    const common=$('#'+prefix+'-common').value;
    return inCity.filter(r=>!common||normalize(r.comum)===normalize(common));
  }
  function activityBadge(r){return r.student_activity?.pending?`<button type="button" data-activity-letter="${esc(r.id)}" aria-haspopup="dialog" class="technical-status letters-activity-state" title="Consultar pendência de análise do aluno">Status: ${esc(String(r.student_activity.status||'').toLocaleLowerCase('pt-BR').replace(/^./,c=>c.toLocaleUpperCase('pt-BR')))}</button>`:'';}
  function programBadges(r){
    return `<div class="letters-program-badges">${(r.program_assessment?.requirements||[]).map((item,index)=>{
      const state=item.status==='ok'?'Documentado':item.status==='review'?'Validar':'Pendente';
      return `<button type="button" class="letters-program-badge ${esc(item.status)}" data-program-letter="${esc(r.id)}" data-program-area="${index}" aria-haspopup="dialog" title="${esc(item.area)}: ${state}. Clique para ver detalhes."><span aria-hidden="true">${item.status==='ok'?'✓':item.status==='review'?'!':'•'}</span> ${esc(item.area)} <span class="letters-badge-state">${state}</span></button>`;
    }).join('')}</div>`;
  }
  function renderProgramPanel(rows){
    const unique=new Map();
    for(const r of rows)if(r.program_assessment)unique.set((r.program_student_id||r.id)+'|'+r.modalidade,r.program_assessment);
    const values=[...unique.values()],count=status=>values.filter(a=>a.status===status).length;
    const assessed=count('eligible')+count('pending')+count('review');
    const percent=assessed?((count('pending')+count('review'))*100/assessed).toLocaleString('pt-BR',{maximumFractionDigits:1})+'%':'Sem base avaliada';
    $('#letters-program-summary').innerHTML=`<strong>${percent}${assessed?' sem comprovação completa':''}</strong><span>${count('eligible')} documentados · ${count('pending')} com requisitos pendentes · ${count('review')} aguardando validação · ${count('no_data')+count('unlinked')} sem histórico/vínculo · ${count('unavailable')} consultas indisponíveis</span><small>Base: ${assessed} alunos/etapas avaliados, de ${values.length} no recorte. Cada aluno conta uma vez por etapa. Consulta atual ao GEM; não representa a situação histórica na emissão. Somente músicos em Culto Oficial ou Oficialização. A emissão continua permitida.</small>`;
    const params=query();params.set('list_city',$('#letters-list-city').value);params.set('list_common',$('#letters-list-common').value);
    $('#letters-program-excel').href='/musica/cartas-exames/programa-minimo/excel/?'+params;
    $('#letters-program-pdf').href='/musica/cartas-exames/programa-minimo/pdf/?'+params;
  }
  function renderLetters(){if(!data)return;const scoped=filteredList('letters-list',data.items);renderProgramPanel(scoped);const rows=scoped.filter(r=>!$('#letters-only-pending').checked||r.activity_review?.status==='pending');
      $('#letters-count').textContent=rows.length+(rows.length===1?' carta encontrada':' cartas encontradas');$('#letters-list-count').textContent=rows.length+' de '+data.items.length+' no recorte';$('#letters-body').innerHTML=rows.map(r=>`<tr><td><div class="letters-candidate-name"><strong>${esc(r.nome)}</strong>${GemTechnicalSummary.badge(r.program_assessment)}${activityBadge(r)}</div><small>${esc(r.comum)}</small><small>${esc(r.instrumento)}</small>${programBadges(r)}</td><td>${esc(r.municipio)}</td><td>${r.tipo==='organista'?'Organista':'Músico'}<small>${esc(data.modalities[r.modalidade]||r.modalidade)}</small></td><td>${day(r.evento.data)}<small>${esc(r.evento.evento)}</small></td><td><span class="letters-state ${r.review_result==='APROVADO'?'approved':r.review_result==='PENDENTE'?'':'other'}">${esc(data.results[r.review_result]||'Aguardando confirmação')}</span>${r.reviewed_name?`<small>${esc(r.reviewed_name)}</small>`:''}</td><td class="letters-actions-cell"><div class="letters-row-actions"><a class="btn btn-outline-primary" href="/musica/cartas-exames/documentos/${esc(r.id)}/" target="_blank" rel="noopener" title="Visualizar carta PDF" aria-label="Visualizar carta PDF"><i class="fa fa-eye" aria-hidden="true"></i></a>${data.can_review?`<button type="button" class="btn btn-outline-warning" data-review-letter="${esc(r.id)}" title="Editar resultado e observações" aria-label="Editar resultado e observações"><i class="fa fa-pen" aria-hidden="true"></i></button><button type="button" class="btn btn-outline-danger" data-delete-letter="${esc(r.id)}" title="Excluir carta" aria-label="Excluir carta"><i class="fa fa-trash" aria-hidden="true"></i></button>`:''}</div></td></tr>`).join('')||'<tr><td colspan="6" class="text-center p-4">Nenhuma carta encontrada com os filtros selecionados.</td></tr>';
  }
  function renderMinistry(){if(!data)return;const rows=filteredList('ministry-list',data.ministry);
    $('#ministry-list-count').textContent=rows.length+' de '+data.ministry.length+(data.ministry.length===1?' comum':' comuns');
      $('#letters-ministry').innerHTML=rows.map(r=>`<tr><td>${esc(r.comum)}<small>${esc(r.municipio)}</small></td>${['anciao','cooperador','regional','encarregado'].map(k=>`<td>${esc(r[k]||'Não informado')}</td>`).join('')}<td>${r.missing.length?`<span class="letters-state">Conferir: ${esc(r.missing.join(', '))}</span>`:'<span class="letters-state approved">Completo</span>'}</td><td class="letters-actions-cell"><div class="letters-row-actions"><button type="button" class="btn btn-outline-primary" data-view-ministry="${esc(r.common_code)}" title="Visualizar ministério" aria-label="Visualizar ministério"><i class="fa fa-eye" aria-hidden="true"></i></button>${data.can_manage_ministry?`<button type="button" class="btn btn-outline-warning" data-edit-ministry="${esc(r.common_code)}" title="Editar ministério" aria-label="Editar ministério"><i class="fa fa-pen" aria-hidden="true"></i></button><button type="button" class="btn btn-outline-danger" data-delete-ministry="${esc(r.common_code)}" title="Excluir relação ministerial" aria-label="Excluir relação ministerial"><i class="fa fa-trash" aria-hidden="true"></i></button>`:''}</div></td></tr>`).join('')||'<tr><td colspan="7">Nenhuma comum encontrada com os filtros selecionados.</td></tr>';
  }
  if(window.jQuery?.fn.select2){
    jQuery('#letters-list-common,#ministry-list-common').select2({width:'100%',minimumResultsForSearch:0,dropdownCssClass:'letters-common-dropdown',language:{noResults:()=> 'Nenhuma comum encontrada'},matcher:(params,item)=>normalize(params.term).split(/\s+/).filter(Boolean).every(word=>normalize(item.text).includes(word))?item:null});
    jQuery('#letters-list-common,#ministry-list-common').on('select2:open',function(){
      const search=jQuery(this).data('select2').dropdown.$search[0];
      search.placeholder='Pesquisar comum por nome ou código...';
      search.setAttribute('aria-label','Pesquisar comum por nome ou código');
      search.setAttribute('autocomplete','off');
      setTimeout(()=>search.focus(),0);
    });
  }
  for(const [prefix,render]of [['letters-list',renderLetters],['ministry-list',renderMinistry]]){
    $('#'+prefix+'-city').addEventListener('change',()=>{$('#'+prefix+'-common').value='';render();});
    if(window.jQuery?.fn.select2)jQuery('#'+prefix+'-common').on('change',render);else $('#'+prefix+'-common').addEventListener('change',render);
    $('#'+prefix+'-clear').addEventListener('click',()=>{$('#'+prefix+'-city').value='';$('#'+prefix+'-common').value='';render();});
  }
  async function load(){
    if(loading){queued=true;return;}loading=true;$('#letters-refresh').disabled=true;
    try{data=await request('/musica/cartas-exames/api/painel/?'+query());window.dispatchEvent(new Event('letters-updated'));
      options('#letters-year',(data.years||[]).map(v=>[v,v]),'Todos');options('#letters-common',(data.commons||[]).map(v=>[v,v]),'Todas as comuns');options('#letters-city',data.municipalities.map(v=>[v,v]),'Todos os municípios');options('#letters-mode',Object.entries(data.modalities),'Todas');options('#letters-result',Object.entries(data.results),'Todos');options('#letters-event',data.events.map(e=>[e.id,day(e.data)+' — '+e.evento]),'Todos os exames');
      const t=data.totals;const approved=g=>['musicos_culto_oficial','musicos_oficializacao','musicos_troca_instrumento','organistas_rjm','organistas_culto_oficial','organistas_oficializacao','organistas_testes_especiais'].reduce((sum,k)=>sum+Number(g[k]||0),0);$('#letters-metrics').innerHTML=MusicManagement.cards([{label:'Cartas preenchidas',value:t.cartas,color:'#2f8de4',icon:'fa-envelope-open-text',note:'Cartas emitidas no recorte',valueFor:g=>g.cartas},{label:'Aguardando confirmação',value:t.pendentes,color:'#e6a124',icon:'fa-clock',note:'Pendentes de conferência do secretário',valueFor:g=>g.pendentes},{label:'Aprovações confirmadas',value:t.aprovados,color:'#12a594',icon:'fa-user-check',note:t.cartas?(t.aprovados/t.cartas*100).toLocaleString('pt-BR',{maximumFractionDigits:1})+'% das cartas do recorte':'Sem cartas no recorte',valueFor:approved},{label:'PDFs conservados',value:t.pdfs,color:'#8265df',icon:'fa-file-pdf',note:'Documentos emitidos e armazenados',valueFor:g=>g.cartas}],data.groups);$('#letters-reading').textContent=[$('#letters-event').selectedOptions[0]?.textContent,$('#letters-year').value,$('#letters-city').value||'Todos os municípios',$('#letters-common').value||'Todas as comuns'].filter(Boolean).join(' · ');

      const columns=['cartas','pendentes','musicos_culto_oficial','musicos_oficializacao','musicos_troca_instrumento','organistas_rjm','organistas_culto_oficial','organistas_oficializacao'];$('#letters-groups').innerHTML=data.groups.map(r=>`<tr><td><i class="fa fa-location-dot text-danger me-1" aria-hidden="true"></i>${esc(r.grupo)}</td>${columns.map(k=>`<td class="text-center">${r[k]}</td>`).join('')}</tr>`).join('');
      renderLetters();
      renderMinistry();
      $('#letters-pdf').href='/musica/cartas-exames/exportar-pdf/?'+query();$('#letters-excel').href='/musica/cartas-exames/exportar-excel/?'+query();feedback('');
    }catch(e){feedback(e.message);}finally{loading=false;$('#letters-refresh').disabled=false;if(queued){queued=false;load();}}
  }
  $('#letters-refresh').addEventListener('click',load);Object.values(fields).forEach(id=>$('#letters-'+id).addEventListener(id==='search'?'input':'change',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(load,id==='search'?300:0);}));$('#letters-clear').addEventListener('click',()=>{$('#letters-only-pending').checked=false;Object.values(fields).forEach(id=>$('#letters-'+id).value='');for(const prefix of ['letters-list','ministry-list']){$('#'+prefix+'-city').value='';$('#'+prefix+'-common').value='';}load();});
  $('#letters-only-pending').checked=false;
  $('#letters-only-pending').addEventListener('change',renderLetters);
  $('#letters-list-clear').addEventListener('click',()=>{$('#letters-only-pending').checked=false;renderLetters();});
  $('#letters-body').addEventListener('click',e=>{
    const button=e.target.closest('[data-activity-letter]');if(!button)return;
    const row=data.items.find(r=>r.id===button.dataset.activityLetter);if(!row)return;
    const activity=row.student_activity||{},review=row.activity_review||{};
    $('#letters-program-title').textContent='Carta pendente de análise - '+activity.status;
    $('#letters-program-person').textContent=row.nome+' - '+row.comum;
    $('#letters-program-detail').innerHTML=`<p>A carta permanece emitida. A situação do aluno exige análise dos responsáveis regionais.</p><p>Último lançamento: ${esc(day(activity.last_activity_at)||'Não informado')}${activity.inactive_days!=null?' - '+esc(activity.inactive_days)+' dias sem atividade':''}.</p><p><b>Ciência dos responsáveis:</b></p><ul>${(review.recipients||[]).map(r=>`<li>${esc(r.label)}${r.name?' - '+esc(r.name):''}</li>`).join('')}</ul><p class="small text-muted">${esc(activity.basis||'Situação registrada na emissão.')} Alerta interno.</p>`;
    $('#letters-program-dialog').showModal();
  });
  $('#letters-body').addEventListener('click',e=>{
    const button=e.target.closest('[data-program-area]');if(!button)return;
    const row=data.items.find(r=>r.id===button.dataset.programLetter),assessment=row?.program_assessment;
    const item=assessment?.requirements?.[Number(button.dataset.programArea)];if(!item)return;
    $('#letters-program-title').textContent='Programa Mínimo · '+item.area;
    $('#letters-program-person').textContent=row.nome+' - '+row.comum;
    $('#letters-program-detail').innerHTML=GemTechnicalSummary.badge(assessment)+GemTechnicalSummary.render({...assessment,requirements:[item]});
    $('#letters-program-dialog').showModal();
  });
  $('#letters-body').addEventListener('click',e=>{const button=e.target.closest('[data-review-letter]');if(!button)return;review=data.items.find(r=>r.id===button.dataset.reviewLetter);if(!review)return;$('#letters-review-person').textContent=review.nome+' · '+review.comum+' · '+day(review.evento.data);$('#letters-review-state').innerHTML=Object.entries(data.results).map(([value,text])=>`<option value="${esc(value)}">${esc(text)}</option>`).join('');$('#letters-review-state').value=review.review_result||'PENDENTE';$('#letters-review-notes').value=review.review_notes||'';$('#letters-review-dialog').showModal();});
  $('#letters-cancel-review').addEventListener('click',()=>$('#letters-review-dialog').close());$('#letters-review-form').addEventListener('submit',async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;try{await request(`/musica/cartas-exames/api/cartas/${review.id}/confirmar/`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify({...Object.fromEntries(new FormData(e.target)),version:review.review_version})});$('#letters-review-dialog').close();await load();feedback('Resultado confirmado. Carta, exame e contagem atualizados.','success');}catch(error){feedback(error.message);$('#letters-review-dialog').close();}finally{button.disabled=false;}});
  $('#letters-ministry-file')?.addEventListener('change',async e=>{const file=e.target.files[0];if(!file)return;const body=new FormData();body.append('arquivo',file);try{const result=await request('/musica/cartas-exames/api/ministerio/importar/',{method:'POST',headers:{'X-CSRFToken':csrf()},body});await load();feedback(`${result.importados} comuns importadas; ${result.incompletos} relações precisam de conferência.`,'success');}catch(error){feedback(error.message);}finally{e.target.value='';}});

  let ministryRecord=null,deletion=null;
  function notify(message){if(window.AppFeedback)AppFeedback.show({type:'success',flow:'save',title:'Operação concluída',message});else feedback(message,'success');}
  function beginDelete(kind,row){deletion={kind,row};$('#letters-delete-name').textContent=kind==='letter'?row.nome+' · '+row.comum:row.comum;$('#letters-delete-description').textContent=kind==='letter'?'A carta será retirada do painel, junto com o resultado vinculado e suas contagens. O PDF e o histórico de auditoria serão preservados.':'A relação será retirada do cadastro usado para novas cartas. Cartas já emitidas conservarão seus responsáveis e assinaturas.';$('#letters-delete-error').textContent='';$('#letters-delete-dialog').showModal();}
  $('#letters-body').addEventListener('click',e=>{const button=e.target.closest('[data-delete-letter]');if(button){const row=data.items.find(r=>r.id===button.dataset.deleteLetter);if(row)beginDelete('letter',row);}});
  $('#letters-ministry').addEventListener('click',e=>{
    const button=e.target.closest('[data-view-ministry],[data-edit-ministry],[data-delete-ministry]');if(!button)return;
    const code=button.dataset.viewMinistry||button.dataset.editMinistry||button.dataset.deleteMinistry;
    const row=data.ministry.find(r=>r.common_code===code);if(!row)return;
    if(button.dataset.deleteMinistry){beginDelete('ministry',row);return;}
    ministryRecord=row;const editing=!!button.dataset.editMinistry;
    $('#letters-ministry-title').textContent=editing?'Editar ministério da comum':'Ministério da comum';$('#letters-ministry-common').textContent=row.comum+' · '+row.municipio;
    for(const field of $('#letters-ministry-form').querySelectorAll('input')){field.value=row[field.name]||'';field.readOnly=!editing;}
    $('#letters-ministry-save').hidden=!editing;$('#letters-ministry-error').textContent='';$('#letters-ministry-dialog').showModal();
  });
  $('#letters-ministry-close').addEventListener('click',()=>$('#letters-ministry-dialog').close());
  $('#letters-ministry-form').addEventListener('submit',async e=>{
    e.preventDefault();if(!data.can_manage_ministry||!ministryRecord)return;const button=e.submitter;button.disabled=true;
    try{await request('/musica/cartas-exames/api/ministerio/'+encodeURIComponent(ministryRecord.common_code)+'/gerir/',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify({...Object.fromEntries(new FormData(e.target)),action:'save',version:ministryRecord.manage_version})});$('#letters-ministry-dialog').close();await load();notify('Relação ministerial atualizada e registrada em auditoria.');}catch(error){$('#letters-ministry-error').textContent=error.message;}finally{button.disabled=false;}
  });
  $('#letters-delete-cancel').addEventListener('click',()=>$('#letters-delete-dialog').close());
  $('#letters-delete-dialog').addEventListener('cancel',e=>{if($('#letters-delete-cancel').disabled)e.preventDefault();});
  $('#letters-delete-form').addEventListener('submit',async e=>{
    e.preventDefault();if(!deletion)return;const button=e.submitter||$('#letters-delete-form [type=submit]');if(button.disabled)return;
    const original=button.innerHTML,{kind,row}=deletion;
    button.disabled=true;button.innerHTML='<i class="fa fa-spinner fa-spin me-1" aria-hidden="true"></i>Excluindo...';$('#letters-delete-cancel').disabled=true;$('#letters-delete-error').textContent='';
    const notice=window.AppFeedback?.show({type:'loading',flow:'delete',toast:true,title:kind==='letter'?'Excluindo carta':'Excluindo relação ministerial',message:'Aguarde, a exclusão está sendo registrada e o painel será atualizado.'});
    try{
      const url=kind==='letter'?'/musica/cartas-exames/api/cartas/'+encodeURIComponent(row.id)+'/excluir/':'/musica/cartas-exames/api/ministerio/'+encodeURIComponent(row.common_code)+'/gerir/';
      await request(url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify({action:'delete',version:kind==='letter'?row.review_version:row.manage_version})});
      $('#letters-delete-dialog').close();deletion=null;await load();
      if(window.AppFeedback)AppFeedback.show({type:'success',flow:'delete',toast:true,title:kind==='letter'?'Carta excluída':'Relação ministerial excluída',message:kind==='letter'?'Carta excluída e contagens atualizadas.':'Relação ministerial excluída do cadastro de novas cartas.',detail:'O histórico de auditoria foi preservado.'});
      else notify(kind==='letter'?'Carta excluída e contagens atualizadas.':'Relação ministerial excluída do cadastro de novas cartas.');
    }catch(error){notice?.close();$('#letters-delete-error').textContent=error.message;window.AppFeedback?.show({type:'error',flow:'delete',toast:true,title:'Não foi possível excluir',message:error.message});}
    finally{button.disabled=false;button.innerHTML=original;$('#letters-delete-cancel').disabled=false;}
  });
  setInterval(()=>{if(!document.hidden&&!document.querySelector('dialog[open]'))load();},45000);load();
})();
