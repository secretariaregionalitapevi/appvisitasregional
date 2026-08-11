document.addEventListener('DOMContentLoaded', () => {
  const state = { teams: [], members: [], commons: [] };
  const byId = id => document.getElementById(id);
  const teamModal = new bootstrap.Modal(byId('team-modal'));
  const memberModal = new bootstrap.Modal(byId('member-modal'));
  const csrf = () => document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1] || '';
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const normalizeKey = value => String(value || '').trim().toLocaleUpperCase('pt-BR');
  state.commons = Array.from(byId('member-common').options).slice(1).map(option => ({ common: option.value, city: option.dataset.city }));

  function alertMessage(message, type='danger') { byId('teams-alert').innerHTML = `<div class="alert alert-${type}">${escapeHtml(message)}</div>`; }
  async function jsonFetch(url, options={}) {
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 15000);
    let response;
    try { response = await fetch(url, {...options, signal: controller.signal}); }
    catch (error) { if (error.name === 'AbortError') throw new Error('A consulta demorou mais de 15 segundos. Tente atualizar a página.'); throw error; }
    finally { clearTimeout(timeout); }
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Não foi possível concluir a operação.');
    return payload;
  }
  function rebuildCommons(select, city, keep='') {
    const $select=jQuery(select), initialized=$select.hasClass('select2-hidden-accessible');
    select.replaceChildren(new Option('Selecione...', ''));
    state.commons.filter(item => !city || normalizeKey(item.city) === normalizeKey(city)).forEach(item => select.add(new Option(item.common, item.common)));
    select.value = Array.from(select.options).some(option => option.value === keep) ? keep : '';
    if(initialized)$select.trigger('change.select2');
  }
  function availableTeams(city, common) { return state.teams.filter(team => team.ativo !== false && team.municipio === city && (team.tipo === 'REGIONAL' || team.comum === common)); }

  function render() {
    const city=byId('filter-city').value, common=byId('filter-common').value, type=byId('filter-type').value;
    const search=byId('filter-search').value.trim().toLocaleLowerCase('pt-BR');
    const teams=state.teams.filter(team => (!city||team.municipio===city)&&(!common||team.tipo==='REGIONAL'||team.comum===common)&&(!type||team.tipo===type));
    const visibleTeams=teams.filter(team => {
      const members=state.members.filter(member => String(team.tipo==='REGIONAL'?member.grupo_regional_id||'':member.equipe_id||'')===String(team.id));
      return !search || `${team.nome} ${team.municipio} ${team.comum||''} ${members.map(member=>member.nome).join(' ')}`.toLocaleLowerCase('pt-BR').includes(search);
    });
    const renderTeam=team => {
      const members=state.members.filter(member => String(team.tipo==='REGIONAL'?member.grupo_regional_id||'':member.equipe_id||'')===String(team.id));
      const rows=members.map(member => `<tr>
        <td><div class="member-profile"><span class="member-avatar">${escapeHtml((member.nome||'?').trim().charAt(0).toUpperCase())}</span><div><div class="member-name">${escapeHtml(member.nome)}</div><div class="member-status">${escapeHtml(member.status||'Ativo')}</div></div></div></td>
        <td><span class="team-pill">${escapeHtml(team.nome)}</span></td>
        <td><span class="text-muted">${escapeHtml(member.municipio||team.municipio)}</span><br><span class="small">${escapeHtml(member.comum||team.comum||'Abrangência municipal')}</span></td>
        <td><div class="member-actions"><button type="button" class="btn btn-outline-primary edit-member" data-id="${escapeHtml(member.id)}" data-team-id="${escapeHtml(team.id)}" title="Alterar equipe"><i class="fa fa-pen"></i></button><button type="button" class="btn btn-outline-danger unlink-member" data-id="${escapeHtml(member.id)}" data-type="${team.tipo}" title="Desvincular da equipe"><i class="fa fa-unlink"></i></button></div></td>
      </tr>`).join('');
      return `<section class="team-section ${team.tipo==='REGIONAL'?'regional':''}">
        <header class="team-section-header"><div class="team-heading"><span class="team-icon"><i class="fa ${team.tipo==='REGIONAL'?'fa-earth-americas':'fa-people-group'}"></i></span><div><div class="mb-1"><span class="badge ${team.tipo==='REGIONAL'?'bg-purple':'bg-primary'} team-type">${team.tipo==='REGIONAL'?'Grupo regional':'Equipe local'}</span></div><h3 class="team-title">${escapeHtml(team.nome)}</h3><div class="team-location"><i class="fa fa-location-dot me-1"></i>${escapeHtml(team.municipio)}${team.comum?` / ${escapeHtml(team.comum)}`:''}</div></div></div><div class="team-header-actions"><span class="team-count"><i class="fa fa-users me-1"></i>${members.length} participante${members.length===1?'':'s'}</span><button type="button" class="btn btn-outline-danger delete-team" data-id="${escapeHtml(team.id)}" data-name="${escapeHtml(team.nome)}" data-members="${members.length}" title="Excluir equipe ou grupo"><i class="fa fa-trash"></i></button></div></header>
        ${members.length?`<div class="table-responsive"><table class="table table-hover team-table"><thead><tr><th>Participante</th><th>Equipe atribuída</th><th>Município / comum</th><th class="text-end">Ações</th></tr></thead><tbody>${rows}</tbody></table></div>`:'<div class="empty-team"><i class="fa fa-user-plus me-2"></i>Nenhum participante atribuído a esta equipe.</div>'}
      </section>`;
    };
    const local=visibleTeams.filter(team=>team.tipo==='LOCAL').map(renderTeam);
    const regional=visibleTeams.filter(team=>team.tipo==='REGIONAL').map(renderTeam);
    const groups=[];
    if(local.length)groups.push(`<div class="team-directory-group"><div class="team-directory-title"><i class="fa fa-house"></i>Equipes locais</div>${local.join('')}</div>`);
    if(regional.length)groups.push(`<div class="team-directory-group"><div class="team-directory-title regional"><i class="fa fa-earth-americas"></i>Grupos regionais</div>${regional.join('')}</div>`);
    byId('teams-list').innerHTML=groups.length?groups.join(''):'<div class="text-center text-muted py-5">Nenhuma equipe encontrada.</div>';
  }
  async function load() {
    byId('teams-list').innerHTML='<div class="text-center py-5"><i class="fa fa-spinner fa-spin me-2"></i>Carregando equipes...</div>';
    try {
      const city=byId('filter-city').value, common=byId('filter-common').value;
      const teamQuery=new URLSearchParams({modo:'catalogo'}), memberQuery=new URLSearchParams({modo:'membros'});
      if(city)teamQuery.set('municipio',city);
      if(common){teamQuery.set('comum',common);memberQuery.set('comum',common);}
      [state.teams,state.members]=await Promise.all([jsonFetch(`/visitas/api/equipes/?${teamQuery}`),jsonFetch(`/visitas/api/equipes/?${memberQuery}`)]);
      render();
    } catch(error) { alertMessage(error.message); byId('teams-list').innerHTML='<div class="text-center text-danger py-5">Não foi possível carregar as equipes.</div>'; }
  }
  async function loadPeople(common) {
    const select=byId('member-person'); select.disabled=true; select.replaceChildren(new Option('Carregando...', ''));
    if(!common)return;
    try {
      const rows=await jsonFetch(`/visitas/api/equipes/?modo=membros&elegiveis=true&comum=${encodeURIComponent(common)}`);
      select.replaceChildren(new Option('Selecione...', '')); rows.forEach(item=>select.add(new Option(item.nome,item.id))); select.disabled=false;
      if(jQuery(select).hasClass('select2-hidden-accessible'))jQuery(select).select2('destroy');
      jQuery(select).select2({width:'100%',language:'pt-BR',dropdownParent:jQuery('#member-modal'),placeholder:'Pesquise o participante...'});
    } catch(error){alertMessage(error.message);}
  }
  function loadTeamChoices() {
    const select=byId('member-team'), teams=availableTeams(byId('member-city').value,byId('member-common').value);
    select.replaceChildren(new Option('Selecione...', '')); teams.forEach(team=>{const option=new Option(`${team.nome} — ${team.tipo==='LOCAL'?'Local':'Regional'}`,team.id);option.dataset.name=team.nome;select.add(option);}); select.disabled=!teams.length;
  }
  async function openMemberModal(member=null, selectedTeamId='') {
    byId('member-form').reset(); const city=member?.municipio||'', common=member?.comum||'';
    byId('member-city').value=city; rebuildCommons(byId('member-common'),city,common);
    await loadPeople(common); byId('member-person').value=member?.id||''; jQuery(byId('member-person')).trigger('change');
    loadTeamChoices(); byId('member-team').value=selectedTeamId||(member?.equipe_id||''); memberModal.show();
  }

  byId('create-team').onclick=()=>{byId('team-form').reset();rebuildCommons(byId('team-common'),'','');teamModal.show();};
  byId('assign-member').onclick=()=>openMemberModal();
  byId('teams-list').onclick=async event=>{
    const edit=event.target.closest('.edit-member'), unlink=event.target.closest('.unlink-member'), deleteTeam=event.target.closest('.delete-team');
    if(deleteTeam){
      const count=Number(deleteTeam.dataset.members||0), name=deleteTeam.dataset.name||'Esta equipe';
      const detail=count?`Os ${count} participantes serão desvinculados, mas seus cadastros serão preservados.`:'Esta ação removerá a equipe cadastrada.';
      const confirmed=await swal({title:`Excluir ${name}?`,text:detail,icon:'warning',dangerMode:true,buttons:{cancel:{text:'Cancelar',visible:true,value:false},confirm:{text:'Excluir equipe',visible:true,value:true}}});
      if(!confirmed)return;
      try{deleteTeam.disabled=true;await jsonFetch('/visitas/api/equipes/?equipe_id='+encodeURIComponent(deleteTeam.dataset.id),{method:'DELETE',headers:{'X-CSRFToken':csrf()}});alertMessage(name+' foi excluída com sucesso.','success');await load();}catch(error){deleteTeam.disabled=false;alertMessage(error.message);}return;
    }
    if(edit){const member=state.members.find(item=>String(item.id)===String(edit.dataset.id));if(member)await openMemberModal(member,edit.dataset.teamId);return;}
    if(!unlink)return;
    const member=state.members.find(item=>String(item.id)===String(unlink.dataset.id));
    const memberName=(member && member.nome) ? member.nome : 'Este participante';
    const confirmed=await swal({
      title:'Desvincular participante?',
      text:memberName + ' sera removido da equipe atual.',
      icon:'warning',
      dangerMode:true,
      buttons:{cancel:{text:'Cancelar',visible:true,value:false},confirm:{text:'Desvincular',visible:true,value:true}}
    });
    if(!confirmed)return;
    try{unlink.disabled=true;await jsonFetch('/visitas/api/equipes/?id='+encodeURIComponent(unlink.dataset.id)+'&tipo='+encodeURIComponent(unlink.dataset.type||'LOCAL'),{method:'DELETE',headers:{'X-CSRFToken':csrf()}});alertMessage(memberName+' foi desvinculado da equipe.','success');await load();}catch(error){unlink.disabled=false;alertMessage(error.message);}
  };
  byId('team-type').onchange=()=>{const regional=byId('team-type').value==='REGIONAL';byId('team-common-wrap').style.display=regional?'none':'';byId('team-common').required=!regional;byId('team-name').placeholder=regional?'Ex.: Grupo A':'Ex.: Equipe 1';byId('team-name-help').textContent=regional?'Grupo com abrangência municipal.':'Equipe vinculada à comum selecionada.';};
  byId('team-city').onchange=()=>rebuildCommons(byId('team-common'),byId('team-city').value);
  byId('member-city').onchange=()=>{rebuildCommons(byId('member-common'),byId('member-city').value);loadTeamChoices();};
  byId('member-common').onchange=()=>{loadPeople(byId('member-common').value);loadTeamChoices();};
  byId('team-form').onsubmit=async event=>{event.preventDefault();try{await jsonFetch('/visitas/api/equipes/',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify({acao:'cadastrar_equipe',tipo:byId('team-type').value,municipio:byId('team-city').value,comum:byId('team-common').value,nome:byId('team-name').value})});teamModal.hide();alertMessage('Equipe criada. Agora você já pode atribuir os participantes.','success');await load();}catch(error){alertMessage(error.message);}};
  byId('member-form').onsubmit=async event=>{event.preventDefault();const option=byId('member-team').selectedOptions[0];try{await jsonFetch('/visitas/api/equipes/',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify({membro_id:byId('member-person').value,equipe_id:byId('member-team').value,equipe:option?.dataset.name||''})});memberModal.hide();alertMessage('Participante atribuído com sucesso.','success');await load();}catch(error){alertMessage(error.message);}};
  function rebuildFilterCommons(keep=''){
    const select=byId('filter-common'),$select=jQuery(select),initialized=$select.hasClass('select2-hidden-accessible');
    select.replaceChildren(new Option('Todas',''));
    state.commons.filter(item=>!byId('filter-city').value||normalizeKey(item.city)===normalizeKey(byId('filter-city').value)).forEach(item=>select.add(new Option(item.common,item.common)));
    select.value=Array.from(select.options).some(option=>option.value===keep)?keep:'';
    if(initialized)$select.trigger('change.select2');
  }
  rebuildFilterCommons(byId('filter-common').value);
  jQuery('#filter-common').select2({width:'100%',language:'pt-BR',placeholder:'Pesquise a comum...',allowClear:true,dropdownParent:jQuery('.team-filter')}).on('change',load);
  jQuery('#member-common').select2({width:'100%',language:'pt-BR',placeholder:'Pesquise a comum...',dropdownParent:jQuery('#member-modal')});
  jQuery('#team-common').select2({width:'100%',language:'pt-BR',placeholder:'Pesquise a comum...',dropdownParent:jQuery('#team-modal')});
  byId('filter-type').onchange=render; byId('filter-search').oninput=render;
  byId('filter-city').onchange=()=>{const keep=byId('filter-common').value;rebuildFilterCommons(keep);load();};
  load();
});
