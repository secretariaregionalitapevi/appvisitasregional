(() => {
const init=() => {
  const root=document.getElementById('regional-planner'); if(!root)return;
  if(root.dataset.initialized)return;root.dataset.initialized='1';
  const el=id=>document.getElementById('regional-'+id);
  const catalog=JSON.parse(document.getElementById('regional-common-data').textContent);
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const timestamp=value=>{
    const dt=new Date(value),zone={timeZone:'America/Sao_Paulo'};
    return dt.toLocaleDateString('pt-BR',zone)+' '+dt.toLocaleTimeString('pt-BR',{...zone,hour:'2-digit',minute:'2-digit'});
  };
  let groups=[],plan=null,token='',dirty=true,loading=false,generation=0,confirmed=false,groupsLoaded=false,agendaSummary=null,savedManifest=null;
  let assignments={},familyPage=1,familyPages=1;const pageSize=10;
  let exportGeneration=0,choosingRemoval=false,regionalMembers=[],regionalTitulares={};
  const context=()=>({data:el('date').value,municipio:el('city').value});
  const feedback=(message,type='error')=>window.AppFeedback?.show({type,title:type==='success'?'Operação concluída':'Confira o planejamento',message});
  async function request(payload,query=false){
    const url=root.dataset.api+(query?'?'+new URLSearchParams(payload):'');
    const response=await fetch(url,query?{credentials:'same-origin'}:{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':root.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify(payload)});
    if(response.redirected)throw Error('Sua sessão expirou. Entre novamente.');
    if(!(response.headers.get('content-type')||'').includes('application/json'))throw Error('O servidor não retornou o planejamento. Atualize a página e confira sua sessão.');
    const result=await response.json();if(!response.ok)throw Error(result.error||'Não foi possível concluir.');return result;
  }
  async function busy(button,work){
    if(loading)return;loading=true;const original=button.innerHTML;
    const controls=[...root.querySelectorAll('input,select,button')].map(node=>[node,node.disabled]);controls.forEach(([node])=>node.disabled=true);
    button.innerHTML='<i class="fa fa-spinner fa-spin me-2" aria-hidden="true"></i>Aguarde...';
    try{await work();}catch(error){el('load-error').hidden=false;el('load-error').textContent=error.message;feedback(error.message);}finally{loading=false;button.innerHTML=original;controls.forEach(([node,disabled])=>node.disabled=disabled);updateButtons();if(pendingLoad){pendingLoad=false;queueMicrotask(()=>busy(el('load'),load));}}
  }
  let pendingLoad=false;
  function reload(){if(loading){pendingLoad=true;return;}busy(el('load'),load);}
  function invalidate(){if(plan)el('common-panel').open=true;plan=null;token='';assignments={};savedManifest=null;exportGeneration++;familyPage=1;confirmed=false;el('preview-panel').hidden=true;el('exports').hidden=true;el('result').replaceChildren();updateButtons();}
  function distributionCounts(){
    if(!plan)return {};
    const counts=Object.fromEntries(plan.groups.map(g=>[g.id,0]));
    plan.houses.forEach(h=>counts[assignments[h.key]||h.group_id]++);
    return counts;
  }
  function updateDashboard(){
    const available=groups.filter(g=>g.confirmado&&g.coordenador_nome.trim()),selected=el('commons').selectedOptions.length;
    const day=el('date').value,formatted=day?day.split('-').reverse().join('/'):'Selecione uma data';
    el('hero-city').textContent=el('city').value;el('hero-date').textContent=formatted;
    el('dashboard-context').textContent=`${el('city').value} · ${formatted}`;
    el('common-count').textContent=selected?`${selected} ${selected===1?'comum selecionada':'comuns selecionadas'}`:'Nenhuma comum selecionada';
    el('common-state').textContent=el('common-count').textContent;el('common-state').title=[...el('commons').selectedOptions].map(o=>o.textContent).join(' / ');
    el('metric-groups').textContent=groupsLoaded?available.length:'—';
    el('metric-groups-note').textContent=groupsLoaded?`${available.length} disponíveis entre ${groups.length} grupos ativos`:'Carregue os coordenadores da data';
    el('metric-groups-progress').max=groups.length||1;el('metric-groups-progress').value=available.length;
    el('team-state').textContent=groupsLoaded?`${available.length} grupos disponíveis · ${dirty?'alterações pendentes':'disponibilidade salva para a data'}`:'Disponibilidade e responsáveis pela data selecionada';
    el('team-save-note').textContent=dirty?'Alterações serão salvas ao calcular a distribuição.':'Coordenadores salvos. Clique em Gerenciar para fazer ajustes.';
    el('metric-families').textContent=plan?plan.houses.length:'—';
    el('metric-families-note').textContent=plan?(confirmed?'Distribuição gravada na agenda':`${plan.records_in_plan??plan.houses.reduce((n,h)=>n+h.members.length,0)} cadastros reunidos por endereço`):'Selecione as comuns e calcule a distribuição';
    const counts=Object.values(distributionCounts()),minimum=counts.length?Math.min(...counts):0,maximum=counts.length?Math.max(...counts):0;
    el('metric-distribution').textContent=counts.length?(minimum===maximum?minimum:`${minimum}–${maximum}`):'—';
    el('metric-distribution-note').textContent=counts.length?(maximum-minimum<=1?'Famílias distribuídas igualmente entre os grupos':'Distribuição ajustada manualmente'):'Divisão automática de todas as famílias elegíveis';
    el('metric-scheduled').textContent=agendaSummary?agendaSummary.families:'—';
    el('metric-scheduled-note').textContent=agendaSummary?`${agendaSummary.groups} grupo(s) com roteiros na agenda desta data`:(groupsLoaded?'Indicador da agenda temporariamente indisponível':'Roteiros regionais já gravados na agenda');
    const state=confirmed?'Roteiros gravados':plan?'Prévia pronta':groupsLoaded?(dirty?'Conferir disponibilidade':'Grupos carregados'):'Aguardando carregamento';
    el('dashboard-state').textContent=state;el('dashboard-state').dataset.state=confirmed?'saved':plan?'ready':'draft';
    el('preview-state').textContent=confirmed?'Gravado na agenda':'Prévia não gravada';
  }
  function updateButtons(){
    const available=groups.filter(g=>g.confirmado);
    el('preview').disabled=loading||!available.length||available.some(g=>!g.coordenador_nome.trim())||!el('commons').selectedOptions.length;
    el('save').disabled=loading||!groups.length||!dirty;
    el('groups').querySelectorAll('input,button').forEach(node=>node.disabled=loading);
    el('summary').querySelectorAll('button').forEach(node=>node.disabled=loading);
    el('houses').querySelectorAll('select').forEach(s=>s.disabled=loading||confirmed);
    el('family-prev').disabled=loading||familyPage<=1;el('family-next').disabled=loading||familyPage>=familyPages;
    el('delete-plan').disabled=loading||!savedManifest?.deletion?.available;
    updateDashboard();
  }
  function renderCommons(){
    const select=el('commons');
    if(window.jQuery?.fn.select2&&jQuery(select).hasClass('select2-hidden-accessible'))jQuery(select).select2('destroy');
    select.replaceChildren(...catalog.filter(c=>c.cidade===el('city').value).map(c=>new Option(c.comum,c.comum)));
    if(window.jQuery?.fn.select2){
      const pin=option=>option.id?jQuery('<span class="rr-common-option"><i class="fa fa-location-dot" aria-hidden="true"></i><span></span></span>').find('span').text(option.text).end():option.text;
      const widget=jQuery(select);widget.off('.regionalCommons').select2({width:'100%',language:'pt-BR',placeholder:'Pesquise o código ou nome da comum...',closeOnSelect:true,templateResult:pin,templateSelection:pin})
        .on('change.regionalCommons',invalidate)
        .on('select2:select.regionalCommons',()=>{widget.select2('close');widget.next('.select2').find('.select2-search__field').val('');})
        .on('select2:close.regionalCommons',()=>widget.next('.select2').find('.select2-search__field').val(''));
    }
  }
  function coordinatorControl(g){
    if(!regionalMembers.length)return `<input class="form-control" maxlength="180" aria-label="Coordenador de ${esc(g.nome)}" value="${esc(g.coordenador_nome)}">`;
    const person=regionalMembers.find(p=>p.nome===g.coordenador_nome);
    const options=regionalMembers.map(p=>`<option value="${esc(p.id)}" ${person?.id===p.id?'selected':''}>${esc(p.nome)}</option>`).join('');
    return `<select class="form-select rr-coordinator-picker" aria-label="Coordenador de ${esc(g.nome)}"><option value=""></option>${!person&&g.coordenador_nome?`<option value="legacy" selected>${esc(g.coordenador_nome)}</option>`:''}${options}</select>`;
  }
  function renderGroups(){
    el('groups').innerHTML=groups.length?`<table class="table"><thead><tr><th>Disponível nesta data</th><th>Grupo</th><th>Coordenador nesta data</th></tr></thead><tbody>${groups.map((g,index)=>`<tr data-group="${esc(g.id)}"><td><input type="checkbox" class="form-check-input" aria-label="Confirmar ${esc(g.nome)}" ${g.confirmado?'checked':''}></td><td><span class="rr-team-badge rr-team-badge-${index%5}"><i class="fa fa-users" aria-hidden="true"></i>${esc(g.nome)}</span></td><td><div class="d-flex gap-2 align-items-center">${coordinatorControl(g)}<button type="button" class="btn btn-outline-danger" data-remove-coordinator="${esc(g.id)}" title="Remover coordenador somente desta data" aria-label="Remover coordenador de ${esc(g.nome)} nesta data"><i class="fa fa-user-minus" aria-hidden="true"></i></button></div>${(regionalTitulares[String(g.id)]||g.coordenador_cadastrado)?`<small class="d-block text-muted mt-1"><strong>Titular:</strong> ${esc(regionalTitulares[String(g.id)]||g.coordenador_cadastrado)}</small>`:''}${!g.coordenador_nome?'<small class="text-muted">Informe um coordenador para habilitar este grupo.</small>':''}</td></tr>`).join('')}</tbody></table>`:'<p>Nenhum grupo regional ativo cadastrado neste município. Cadastre os grupos em Equipes de Visita.</p>';
    if(window.jQuery?.fn.select2){
      jQuery(el('groups')).find('.rr-coordinator-picker').select2({width:'100%',placeholder:'Pesquisar integrante pelo nome',allowClear:true,
        matcher:(params,data)=>!params.term||normalize(data.text).includes(normalize(params.term))?data:null
      }).on('change.regionalCoordinator',function(){
        const row=this.closest('[data-group]'),group=groups.find(g=>g.id===row.dataset.group);
        const person=regionalMembers.find(p=>String(p.id)===this.value);
        group.coordenador_integrante_id=person?.id||null;
        group.coordenador_nome=person?.nome||(this.value==='legacy'?group.coordenador_nome:'');
        group.confirmado=!!group.coordenador_nome;
        row.querySelector('[type=checkbox]').checked=group.confirmado;
        dirty=true;invalidate();updateButtons();
      });
    }
    updateButtons();
  }
  async function load(){
    el('load-error').hidden=true;el('exports').hidden=true;
    const selected=context(),current=++generation;groups=[];groupsLoaded=false;agendaSummary=null;dirty=true;invalidate();
    el('groups').textContent='Nenhum grupo carregado para esta seleção.';
    if(!selected.data)throw Error('Selecione a data das visitas.');
    const [result,registry]=await Promise.all([request({...selected,incluir_indicadores:'1'},true),request({...selected,action:'integrants'},true)]);if(current!==generation||JSON.stringify(selected)!==JSON.stringify(context()))return;
    regionalMembers=registry.integrantes||[];
    regionalTitulares=registry.titulares||{};
    groups=result.groups.filter(g=>g.ativo);groupsLoaded=true;agendaSummary=result.agenda_summary||null;dirty=groups.some(g=>!g.participacao_salva);renderGroups();
    if(result.warning){el('load-error').hidden=false;el('load-error').textContent=result.warning;}
    if(result.plans?.length){
      el('saved-plans').innerHTML=result.plans.map(p=>`<option value="${esc(p.print_url)}">Visitas em ${esc((p.date||context().data).split('-').reverse().join('/'))} · ${p.historical?'Histórico substituído':'Salvo em'} ${esc(timestamp(p.created_at))}</option>`).join('');
      await showExports(result.plans[0].print_url);
    }
    updateButtons();
  }
  el('load').onclick=()=>busy(el('load'),load);
  el('city').onchange=()=>{generation++;groups=[];groupsLoaded=false;agendaSummary=null;dirty=true;invalidate();renderCommons();updateButtons();reload();};
  el('date').onchange=()=>{generation++;groups=[];groupsLoaded=false;agendaSummary=null;dirty=true;invalidate();updateButtons();reload();};
  el('groups').addEventListener('input',event=>{
    const row=event.target.closest('[data-group]');if(!row)return;
    const group=groups.find(g=>g.id===row.dataset.group),checkbox=row.querySelector('[type=checkbox]'),input=row.querySelector('input:not([type=checkbox])');
    if(!input){
      if(event.target===checkbox){group.confirmado=checkbox.checked;dirty=true;invalidate();updateButtons();}
      return;
    }
    if(event.target===checkbox&&checkbox.checked&&!input.value.trim())input.value=group.coordenador_cadastrado||'';
    if(event.target===input&&!input.value.trim())checkbox.checked=false;
    if(event.target===input&&input.value.trim()&&!group.coordenador_nome.trim())checkbox.checked=true;
    group.confirmado=checkbox.checked;group.coordenador_nome=input.value;
    if(event.target===input)group.coordenador_alterado=true;
    dirty=true;invalidate();updateButtons();
  });
  el('groups').addEventListener('click',event=>{
    const button=event.target.closest('[data-remove-coordinator]');if(!button)return;
    const group=groups.find(g=>g.id===button.dataset.removeCoordinator);group.coordenador_nome='';group.coordenador_integrante_id=null;group.confirmado=false;group.coordenador_alterado=true;
    dirty=true;invalidate();renderGroups();
  });
  async function saveGroups(notify=false){
    const result=await request({...context(),action:'participation',groups:groups.map(g=>({id:g.id,confirmado:g.confirmado,coordenador_nome:g.coordenador_nome,coordenador_integrante_id:g.coordenador_integrante_id||regionalMembers.find(p=>p.nome===g.coordenador_nome)?.id||null,expected_updated_at:g.participacao_updated_at||'',atualizar_cadastro:false,expected_coordenador_cadastrado:g.coordenador_cadastro_valor??null}))});
    groups=result.groups.filter(g=>g.ativo);
    dirty=false;renderGroups();el('team-panel').open=false;
    if(notify){el('team-panel').querySelector('summary').focus({preventScroll:true});feedback('Confirmações e coordenadores salvos para a data selecionada.','success');}
  }
  el('save').onclick=()=>busy(el('save'),()=>saveGroups(true));
  el('commons').onchange=invalidate;
  function renderCoverage(rows,id){
    const empty=rows?.filter(c=>!c.families).length||0;
    el(id).innerHTML=rows?.length?`<details ${empty?'open':''}><summary>Conferir cobertura das ${rows.length} comuns${empty?` <span class="text-danger">· ${empty} sem famílias incluídas</span>`:''}</summary><div class="table-responsive"><table class="table"><thead><tr><th>Comum</th><th>Cadastros</th><th>Incluídos</th><th>Famílias / paradas</th></tr></thead><tbody>${rows.map(c=>`<tr class="${c.families?'':'text-danger'}"><td><i class="fa fa-location-dot me-2" aria-hidden="true"></i>${esc(c.common)}${!c.families?'<small class="d-block">Nenhuma família incluída desta comum. Confira a seleção, os vínculos e a agenda.</small>':''}</td><td>${c.records??'—'}</td><td>${c.included_records}</td><td><strong>${c.families}</strong></td></tr>`).join('')}</tbody></table></div></details>`:'';
  }
  const normalize=value=>String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('pt-BR');
  function renderHouses(){
    if(!plan)return;
    const query=normalize(el('family-search').value),group=el('family-group').value;
    const filtered=plan.houses.filter(h=>(!group||assignments[h.key]===group)&&(!query||normalize([h.address,h.bairro,...h.members.flatMap(m=>[m.nome,m.comum])].join(' ')).includes(query)));
    familyPages=Math.max(1,Math.ceil(filtered.length/pageSize));familyPage=Math.min(familyPage,familyPages);
    const start=(familyPage-1)*pageSize,visible=filtered.slice(start,start+pageSize);
    el('houses').innerHTML=visible.length?`<table class="table"><thead><tr><th>Família e comum</th><th>Endereço</th><th>Grupo responsável</th></tr></thead><tbody>${visible.map(h=>`<tr><td>${h.members.map(m=>`<div>${esc(m.nome)}<span class="planning-family-common">${esc(m.comum)}</span></div>`).join('')}</td><td>${esc(h.address)}<br><small>${esc(h.bairro)}</small></td><td><select class="form-select" data-house="${esc(h.key)}" aria-label="Grupo para ${esc(h.members[0].nome)}">${plan.groups.map(g=>`<option value="${esc(g.id)}" ${g.id===assignments[h.key]?'selected':''}>${esc(g.nome)} · ${esc(g.coordenador_nome)}</option>`).join('')}</select></td></tr>`).join('')}</tbody></table>`:'<p class="p-3 mb-0 text-muted">Nenhuma família encontrada neste filtro.</p>';
    el('family-page-info').textContent=filtered.length?`${start+1}–${Math.min(start+pageSize,filtered.length)} de ${filtered.length} famílias · página ${familyPage}/${familyPages}`:'0 famílias';
    el('family-total').textContent=plan.houses.length;
    updateButtons();
  }
  function renderSummary(){
    const roadFallback=plan.road_routing_fallback_groups||[];
    el('road-order-note').hidden=!roadFallback.length;
    el('road-order-note').textContent=roadFallback.length?`Não foi possível validar a sequência pelas ruas em: ${roadFallback.join(', ')}. Confira o percurso no Mapa Google antes de confirmar.`:'';
    renderCoverage(plan.coverage,'coverage');
    const counts=distributionCounts();
    el('summary').innerHTML=plan.groups.map(g=>`<button type="button" class="rr-group-card ${el('family-group').value===g.id?'is-selected':''}" data-group-summary="${esc(g.id)}" aria-pressed="${el('family-group').value===g.id}" title="Conferir famílias de ${esc(g.nome)}${g.max_leg_meters>=1000?` · Maior trecho: ${(g.max_leg_meters/1000).toFixed(2)} km`:''}"><span class="rr-group-name">${esc(g.nome)}</span><strong class="rr-group-value">${counts[g.id]}</strong><span>visitas</span><small>${esc(g.coordenador_nome)}</small></button>`).join('')+`<p class="rr-distribution-note">${plan.houses.length} famílias · ${plan.groups.length} grupos. Clique em um grupo para conferir as famílias.</p>`;
    updateDashboard();
  }
  el('preview').onclick=()=>busy(el('preview'),async()=>{
    el('exports').hidden=true;
    if(!el('commons').selectedOptions.length)throw Error('Selecione as comuns a atender.');
    if(dirty)await saveGroups();
    const result=await request({...context(),action:'preview',comuns:[...el('commons').selectedOptions].map(c=>c.value),grupos:groups.filter(g=>g.confirmado).map(g=>g.id)});
    plan=result.plan;token=result.token;assignments=Object.fromEntries(plan.houses.map(h=>[h.key,h.group_id]));familyPage=1;el('result').replaceChildren();
    el('family-search').value='';el('family-group').replaceChildren(new Option('Todos os grupos',''),...plan.groups.map(g=>new Option(g.nome,g.id)));
    el('families-panel').open=false;el('common-panel').open=false;
    el('preview-panel').hidden=false;el('confirm').hidden=false;el('cancel').hidden=false;renderHouses();renderSummary();
  });
  el('houses').onchange=event=>{if(!plan||confirmed||!event.target.matches('[data-house]'))return;assignments[event.target.dataset.house]=event.target.value;renderHouses();renderSummary();};
  el('family-search').oninput=()=>{familyPage=1;renderHouses();};
  el('family-group').onchange=()=>{familyPage=1;renderHouses();renderSummary();};
  el('family-prev').onclick=()=>{familyPage=Math.max(1,familyPage-1);renderHouses();};
  el('family-next').onclick=()=>{familyPage=Math.min(familyPages,familyPage+1);renderHouses();};
  el('summary').onclick=event=>{const card=event.target.closest('[data-group-summary]');if(!card||!plan)return;el('family-group').value=card.dataset.groupSummary;el('families-panel').open=true;familyPage=1;renderHouses();renderSummary();};
  el('confirm').onclick=()=>busy(el('confirm'),async()=>{
    if(!plan||!token)throw Error('Gere uma nova prévia antes de confirmar.');
    const result=await request({action:'confirm',token,assignments});
    confirmed=true;agendaSummary=result.agenda_summary||null;
    el('result').innerHTML='<p>Distribuição gravada. Os PDFs individuais estão no painel de exportação abaixo.</p>';
    el('saved-plans').innerHTML=`<option value="${esc(result.print_url)}">Visitas em ${esc(context().data.split('-').reverse().join('/'))} · Salvo agora</option>`;
    await showExports(result.print_url);
    el('confirm').hidden=true;el('cancel').hidden=true;el('families-panel').open=false;el('preview-panel').hidden=true;
    feedback('Distribuição concluída. Os roteiros identificam a comum de cada família e o coordenador da data.','success');
  });
  el('cancel').onclick=invalidate;
  async function showExports(url){
    const current=++exportGeneration,selectedContext=JSON.stringify(context());savedManifest=null;
    el('delete-plan').disabled=true;el('delete-note').hidden=true;
    el('exports').hidden=false;el('export-groups').innerHTML='<p>Carregando os roteiros salvos...</p>';
    ['export-pdf','export-excel'].forEach(id=>{el(id).removeAttribute('href');el(id).setAttribute('aria-disabled','true');});
    try{
      const response=await fetch(url+'?formato=manifesto',{credentials:'same-origin'});
      if(!response.ok||response.redirected)throw Error('Não foi possível carregar a lista de arquivos. Clique em Carregar planejamento para tentar novamente.');
      const manifest=await response.json();
      if(current!==exportGeneration||selectedContext!==JSON.stringify(context())||el('saved-plans').value!==url)return;
      savedManifest=manifest;renderCoverage(manifest.coverage,'export-coverage');
      el('delete-plan').disabled=!manifest.removal?.available;
      el('delete-plan').title='Excluir comuns deste roteiro e escolher se deseja limpar a agenda';
      el('delete-plan').setAttribute('aria-label',el('delete-plan').title);
      const removalReason=manifest.removal?.reason||(!manifest.removal?'Atualize o sistema para habilitar a exclusão por comum.':'');
      el('delete-note').textContent=removalReason;el('delete-note').hidden=!removalReason;
      el('refresh-route').hidden=!!manifest.historical;
      el('route-refresh-note').textContent=manifest.requires_route_refresh?'Este roteiro foi salvo sem GPS. Recalcule e confirme a sequência para liberar os PDFs atualizados.':'A primeira distância parte da igreja; as seguintes partem sempre da casa anterior.';
      el('export-groups').innerHTML=manifest.groups.map(g=>`<article class="rr-export-group"><div><strong><i class="fa fa-users me-2" aria-hidden="true"></i>${esc(g.name)}</strong><small>${esc(g.coordinator)} · ${g.families} famílias</small><span><i class="fa fa-location-dot me-1" aria-hidden="true"></i>${esc(g.commons.join(' / '))}</span></div><div class="d-flex flex-wrap gap-2">${g.google_url?`<a class="btn btn-white border" data-map-road target="_blank" rel="noopener" href="${esc(g.google_url)}"><i class="fa fa-map-location-dot me-1"></i>Mapa Google</a>`:''}<a class="btn btn-outline-primary" target="_blank" rel="noopener" href="${esc(g.print_url)}"><i class="fa fa-print me-1"></i>Visualizar</a><a class="btn btn-white border" data-app-export href="${esc(g.pdf_url)}"><i class="fa fa-file-pdf text-danger me-1"></i>PDF</a></div></article>`).join('');
      el('export-pdf').href=manifest.zip_url;el('export-excel').href=manifest.excel_url;applyMapMode();
      ['export-pdf','export-excel'].forEach(id=>el(id).removeAttribute('aria-disabled'));
      if(manifest.requires_route_refresh){
        [el('export-pdf'),...el('export-groups').querySelectorAll('[data-app-export]')].forEach(a=>{a.removeAttribute('href');a.setAttribute('aria-disabled','true');a.classList.add('disabled');});
      }else el('export-pdf').classList.remove('disabled');
    }catch(error){if(current===exportGeneration)el('export-groups').textContent=error.message;}
  }
  function chooseRemoval(manifest){
    return new Promise(resolve=>{
      const node=el('remove-modal'),form=node.querySelector('form');
      const options=manifest.removal.commons;
      let selection=null;
      el('remove-context').textContent=`Data: ${el('date').value.split('-').reverse().join('/')} · Município: ${el('city').value}`;
      el('remove-rows').innerHTML=options.map((item,index)=>`<tr><td><strong class="rr-remove-common-name">${esc(item.common)}</strong><small class="rr-remove-count">${item.scheduled} agendamento(s) com status Marcada</small></td><td><label class="rr-remove-choice"><input type="checkbox" class="form-check-input" data-remove-common="${index}" aria-label="Remover ${esc(item.common)} do roteiro"></label></td><td><label class="rr-remove-choice"><input type="checkbox" class="form-check-input" data-remove-agenda="${index}" aria-label="Excluir visitas de ${esc(item.common)} também da agenda" disabled></label></td></tr>`).join('');
      el('remove-submit').disabled=true;
      const onChange=()=>{
        node.querySelectorAll('[data-remove-common]').forEach(input=>{
          const agenda=node.querySelector(`[data-remove-agenda="${input.dataset.removeCommon}"]`);
          agenda.disabled=!input.checked;if(!input.checked)agenda.checked=false;
        });
        el('remove-submit').disabled=!node.querySelector('[data-remove-common]:checked');
      };
      const modal=bootstrap.Modal.getOrCreateInstance(node);
      const onSubmit=event=>{
        event.preventDefault();
        const commons=[...node.querySelectorAll('[data-remove-common]:checked')].map(input=>options[Number(input.dataset.removeCommon)].common);
        if(!commons.length)return;
        selection={comuns:commons,agenda_comuns:[...node.querySelectorAll('[data-remove-agenda]:checked')].map(input=>options[Number(input.dataset.removeAgenda)].common)};
        modal.hide();
      };
      form.addEventListener('submit',onSubmit);node.addEventListener('change',onChange);
      node.addEventListener('hidden.bs.modal',()=>{
        form.removeEventListener('submit',onSubmit);node.removeEventListener('change',onChange);resolve(selection);
      },{once:true});
      modal.show();
    });
  }
  el('delete-plan').onclick=async()=>{
    const manifest=savedManifest;if(!manifest?.removal?.available||loading||choosingRemoval)return;
    choosingRemoval=true;
    try{
    const selection=await chooseRemoval(manifest);if(!selection)return;
    if(manifest!==savedManifest)return feedback('A distribuição selecionada mudou. Carregue novamente antes de excluir.');
    const label=el('saved-plans').selectedOptions[0]?.textContent||'Distribuição selecionada';
    const agendaCount=manifest.removal.commons.filter(c=>selection.agenda_comuns.includes(c.common)).reduce((sum,c)=>sum+c.scheduled,0);
    const approved=await window.AppFeedback.confirm({title:'Confirmar exclusão por comum?',
      message:`${label}. Remover do roteiro: ${selection.comuns.join(' / ')}. ${selection.agenda_comuns.length?`Excluir também da agenda: ${selection.agenda_comuns.join(' / ')} (${agendaCount} agendamento(s) com status Marcada).`:'Manter todas as visitas na agenda.'}`,
      detail:'As comuns não selecionadas serão preservadas.',highlight:label,confirmText:'Excluir seleção',confirmIcon:'fa-trash'});
    if(!approved)return;
    if(manifest!==savedManifest)return feedback('A distribuição selecionada mudou. Confira a seleção e tente novamente.');
    await busy(el('delete-plan'),async()=>{
      const result=await request({action:'remove_commons',token:manifest.removal.token,...selection});
      savedManifest=null;await load();
      feedback(`${result.removed_commons.length} comum(ns) removida(s) do roteiro. ${selection.agenda_comuns.length?`${result.deleted} agendamento(s) removido(s) da agenda.`:'Agenda preservada.'}`,'success');
    });
    }finally{choosingRemoval=false;}
  };
  function applyMapMode(){
    root.querySelectorAll('#regional-export-pdf[href],#regional-export-groups a[href]').forEach(a=>{if(a.hasAttribute('data-map-road'))return;const url=new URL(a.href,location.href);url.searchParams.set('mapa',el('map-mode').value);a.href=url.href;});
  }
  el('map-mode').onchange=applyMapMode;
  el('refresh-route').onclick=()=>{
    if(!savedManifest?.commons?.length)return feedback('Carregue o roteiro salvo novamente.');
    const commons=el('commons');[...commons.options].forEach(option=>option.selected=savedManifest.commons.includes(option.value));
    if(window.jQuery?.fn.select2)jQuery(commons).trigger('change');else invalidate();
    updateButtons();
    if(el('preview').disabled)return feedback('Confirme os grupos disponíveis e seus coordenadores para recalcular o roteiro.');
    el('preview').click();
  };
  el('saved-plans').onchange=()=>showExports(el('saved-plans').value);
  el('clear').onclick=()=>{generation++;groups=[];groupsLoaded=false;agendaSummary=null;dirty=true;invalidate();renderCommons();el('exports').hidden=true;reload();};
  const now=new Date();el('date').value=root.dataset.date||[now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),String(now.getDate()).padStart(2,'0')].join('-');
  renderCommons();updateButtons();
  reload();
};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
