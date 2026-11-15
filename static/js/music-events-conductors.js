(() => {
  const $=s=>document.querySelector(s),{esc,request,feedback}=window.MusicEventsDashboard;
  let current={rows:[],catalog:[],sites:[]},events=[];
  const modal=document.createElement('div');modal.className='modal fade';modal.id='conductor-modal';modal.tabIndex=-1;
  modal.innerHTML=`<div class="modal-dialog"><div class="modal-content"><form id="conductor-form"><div class="modal-header"><h5 class="modal-title">Conferência individual do encarregado local</h5><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Fechar"></button></div><div class="modal-body"><label class="form-label" for="conductor-event">Evento</label><select class="form-select mb-3" id="conductor-event" required></select><label class="form-label" for="conductor-common">Comum</label><select class="form-select mb-3" id="conductor-common" required></select><label class="form-label" for="conductor-person">Encarregado</label><select class="form-select mb-3" id="conductor-person" required></select><label class="form-label" for="conductor-status">SITUA\u00c7\u00c3O DO ENCARREGADO</label><select class="form-select mb-3" id="conductor-status" required><option value="" disabled>Selecione a situação</option><option value="PRESENTE">PRESENTE</option><option value="JUSTIFICOU">JUSTIFICOU</option><option value="NAO_JUSTIFICOU">NJ</option><option value="SEM_ENCARREGADO">SEM ENCARREGADO</option><option value="ENFERMO">ENFERMO</option></select><label class="form-label" for="conductor-site">Local de comparecimento</label><select class="form-select mb-3" id="conductor-site"></select><label class="form-label" for="conductor-notes">Observação / justificativa</label><textarea class="form-control" id="conductor-notes" maxlength="500" rows="3"></textarea><div id="conductor-error" class="text-danger small mt-2" role="alert"></div></div><div class="modal-footer"><button class="btn border btn-danger app-btn-cancel" type="button" data-bs-dismiss="modal"><i class="fa fa-xmark me-1" aria-hidden="true"></i>Cancelar</button><button class="btn btn-primary" id="conductor-save" type="submit">Salvar conferência</button></div></form></div></div>`;
  document.body.append(modal);
  function fillSites(){const old=$('#conductor-site').value;$('#conductor-site').innerHTML='<option value="">Selecione o local</option>'+current.sites.filter(s=>s.evento_id===$('#conductor-event').value&&s.nome!=='LOCAL A CONFERIR').map(s=>`<option value="${esc(s.id)}">${esc(s.nome)}</option>`).join('');$('#conductor-site').value=old;}
  function fillPeople(row){
    const key=$('#conductor-common').value,catalog=current.catalog.find(item=>item.key===key);
    const names=new Set([...(catalog?.encarregados||[]),...current.rows.filter(item=>item.comum_chave===key).map(item=>item.encarregado_nome).filter(Boolean)]);
    if(row?.encarregado_nome)names.add(row.encarregado_nome);
    const select=$('#conductor-person'),selected=row?.encarregado_nome||'';
    select.innerHTML=`<option value="">${row&&!selected?'Registro anterior sem identificação':'Selecione o encarregado'}</option>`+[...names].sort((a,b)=>a.localeCompare(b)).map(name=>`<option value="${esc(name)}">${esc(name)}</option>`).join('');
    select.value=selected;select.required=!row&&names.size>0;select.disabled=!!row;
  }
  function status(){const present=$('#conductor-status').value==='PRESENTE';$('#conductor-site').disabled=!present;$('#conductor-site').required=present;$('#conductor-notes').required=$('#conductor-status').value==='JUSTIFICOU';}
  function open(row){$('#conductor-error').textContent='';$('#conductor-event').innerHTML=events.map(e=>`<option value="${esc(e.id)}">${esc(e.titulo)}</option>`).join('');
    const commons=new Map(current.catalog.map(c=>[c.key,c.name]));current.rows.forEach(r=>commons.set(r.comum_chave,r.comum));
    $('#conductor-common').innerHTML='<option value="">Selecione a comum</option>'+[...commons].sort((a,b)=>a[1].localeCompare(b[1])).map(([k,n])=>`<option value="${esc(k)}">${esc(n)}</option>`).join('');
    $('#conductor-event').disabled=!!row;$('#conductor-common').disabled=!!row;
    if(row){$('#conductor-event').value=row.evento_id;$('#conductor-common').value=row.comum_chave;}
    fillPeople(row);
    $('#conductor-status').value=row?.presenca_situacao==='NAO_INFORMADO'?'':(row?.presenca_situacao||'');$('#conductor-notes').value=row?.observacoes||'';fillSites();
    if(row?.locais?.length){const site=current.sites.find(s=>s.evento_id===row.evento_id&&s.nome===row.locais[0]);if(site)$('#conductor-site').value=site.id;}
    status();bootstrap.Modal.getOrCreateInstance(modal).show();
  }
  function table(){const filter=$('#conductor-filter').value,city=$('#conductor-city-filter').value;$('#conductor-body').innerHTML=current.rows.map((r,i)=>({...r,index:i})).filter(r=>(!filter||(filter===r.presenca_situacao))&&(!city||city===r.municipio)).map(r=>`<tr><td>${esc(r.evento)}<small>${esc(String(r.data).split('-').reverse().join('/'))}</small></td><td><strong>${esc(r.comum)}</strong><small>${esc(r.municipio)}</small><div class="events-conductor-name">${esc(r.encarregado_nome||'Não localizado no cadastro')}</div></td><td><span class="conductor-status ${r.presenca_situacao}">${esc(r.presenca_situacao==='NAO_INFORMADO'?'PENDENTE DE CONFERÊNCIA':r.presenca_lista_label)}</span>${r.locais_validos?.length?`<small>LOCAL: ${esc(r.locais_validos.join(' / '))}</small>`:''}</td><td>${esc(r.observacoes)}</td><td><button type="button" class="btn btn-sm btn-outline-primary" data-conductor="${r.index}" ${!current.available?'disabled':''}>Conferir</button></td></tr>`).join('')||'<tr><td colspan="5" class="events-empty">Sem registros para esse município e situação.</td></tr>';}
  document.addEventListener('music-events-data',e=>{current=e.detail.conductors;events=e.detail.events;const t=current.totals;
    const citySelect=$('#conductor-city-filter'),selected=citySelect.value,cities=[...new Set(current.rows.map(r=>r.municipio))].sort((a,b)=>a.localeCompare(b));citySelect.innerHTML='<option value="">Todos os municípios</option>'+cities.map(city=>`<option value="${esc(city)}">${esc(city)}</option>`).join('');if(cities.includes(selected))citySelect.value=selected;
    const statuses=['PRESENTE','JUSTIFICOU','NAO_JUSTIFICOU','SEM_ENCARREGADO','ENFERMO'],labels={PRESENTE:'PRESENTE',JUSTIFICOU:'JUSTIFICOU',NAO_JUSTIFICOU:'NÃO JUSTIFICOU',SEM_ENCARREGADO:'SEM ENCARREGADO',ENFERMO:'ENFERMO'};
    const previous=$('#conductor-filter').value;
    $('#conductor-filter').innerHTML='<option value="">TODOS OS REGISTROS</option>'+statuses.map(status=>`<option value="${status}">${labels[status]}</option>`).join('');
    if(statuses.includes(previous))$('#conductor-filter').value=previous;
    const icons={PRESENTE:'fa-user-check',JUSTIFICOU:'fa-comment-dots',NAO_JUSTIFICOU:'fa-user-xmark',NAO_INFORMADO:'fa-circle-question',SEM_ENCARREGADO:'fa-user-minus',ENFERMO:'fa-heart-pulse'};
    const badge=status=>`<span class="conductor-status ${status}">${labels[status]}</span>`;
    $('#conductor-summary').innerHTML=statuses.map(status=>`<div class="conductor-kpi ${status}"><i class="fa ${icons[status]}" aria-hidden="true"></i>${badge(status)}<strong>${current.rows.filter(r=>r.presenca_situacao===status).length}</strong></div>`).join('');
    const classified=current.rows.length;
    $('#conductor-review-progress').innerHTML=`<div class="conductor-review-state"><div><strong>${classified} registros nas cinco situa\u00e7\u00f5es</strong><p>Presen\u00e7a na lista confirma comparecimento. Sem presen\u00e7a e sem justificativa ou outra situa\u00e7\u00e3o registrada: NJ (n\u00e3o justificou).</p></div></div>`;
    $('#conductor-city-summary').innerHTML=`<div class="table-responsive"><table class="table events-table conductor-city-table"><thead><tr><th scope="col">MUNICÍPIO</th>${statuses.map(status=>`<th scope="col">${badge(status)}</th>`).join('')}</tr></thead><tbody>${cities.map(city=>{const cityRows=current.rows.filter(row=>row.municipio===city),done=cityRows.filter(row=>statuses.includes(row.presenca_situacao)).length;return `<tr><th scope="row">${esc(city)}<small class="conductor-city-coverage">${done} classificados${cityRows.length-done?` · ${cityRows.length-done} pendentes`:''}</small></th>${statuses.map(status=>{const count=cityRows.filter(r=>r.presenca_situacao===status).length;return `<td><span class="conductor-status conductor-count ${status}${count===0?' conductor-count-zero':''}">${count}</span></td>`;}).join('')}</tr>`;}).join('')}</tbody></table></div>`;
    $('#conductor-add').disabled=!current.available||!events.length;
    $('#conductor-notice').innerHTML='<span>Situa\u00e7\u00e3o do encarregado:</span> '+statuses.map(badge).join('');table();
  });
  $('#conductor-filter').onchange=table;$('#conductor-city-filter').onchange=table;$('#conductor-add').onclick=()=>open(null);$('#conductor-body').onclick=e=>{const b=e.target.closest('[data-conductor]');if(b)open(current.rows[Number(b.dataset.conductor)]);};

  const conductorExport=format=>window.MusicEventsDashboard.download(format,'encarregados',$('#conductor-city-filter').value?{municipio:$('#conductor-city-filter').value}:{});
  $('#conductor-excel').onclick=()=>conductorExport('excel');
  $('#conductor-pdf').onclick=()=>conductorExport('pdf');
  $('#conductor-event').onchange=fillSites;$('#conductor-common').onchange=()=>fillPeople();$('#conductor-status').onchange=status;
  $('#conductor-form').onsubmit=async e=>{e.preventDefault();$('#conductor-save').disabled=true;$('#conductor-error').textContent='';try{
    const csrf=document.querySelector('[name=csrfmiddlewaretoken]').value;
    await request(`/musica/eventos/api/eventos/${encodeURIComponent($('#conductor-event').value)}/encarregado/`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify({comum_chave:$('#conductor-common').value,encarregado_nome:$('#conductor-person').value,situacao:$('#conductor-status').value,local_id:$('#conductor-site').value,observacoes:$('#conductor-notes').value})});
    bootstrap.Modal.getOrCreateInstance(modal).hide();await window.MusicEventsDashboard.refresh();feedback('Conferência do encarregado registrada.','success');
  }catch(error){$('#conductor-error').textContent=error.message;}finally{$('#conductor-save').disabled=false;}};
})();
