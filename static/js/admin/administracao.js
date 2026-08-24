(function () {
  'use strict';
  let data = { profiles: [], logs: [], sessions: [], access_levels: [], module_access: [] };
  const esc = value => $('<div>').text(String(value == null ? '' : value)).html();
  const fmt = value => Number(value || 0).toLocaleString('pt-BR');
  const norm = value => String(value || '').trim().toLocaleLowerCase('pt-BR');
  const date = value => value ? new Date(value).toLocaleString('pt-BR') : '—';
  const profileMap = () => Object.fromEntries(data.profiles.map(profile => [profile.user_id, profile]));
  const roleLabel = id => ({1:'Global',2:'Regional',3:'Municipal',4:'Local'}[Number(id)] || 'Não definido');
  const statusBadge = status => ({approved:'success',pending:'warning',rejected:'danger'}[status] || 'secondary');
  const statusLabel = status => ({approved:'Aprovado',pending:'Pendente',rejected:'Rejeitado'}[status] || status || 'Não definido');
  const origin = profile => profile.cadastro_origem_label || profile.cadastro_origem || profile.cadastro_origem_rota || 'Cadastro direto';
  const csrf = () => document.querySelector('[name=csrfmiddlewaretoken]').value;
  const initials = name => String(name || '?').split(/\s+/).slice(0,2).map(item => item[0]).join('').toUpperCase();

  function alertMessage(message, type='danger') { $('#admin-alert').attr('class',`alert alert-${type}`).text(message); setTimeout(()=>$('#admin-alert').addClass('d-none'),5000); }
  function successToast(message) {
    $('#admin-success-toast-message').text(message);
    bootstrap.Toast.getOrCreateInstance(document.querySelector('#admin-success-toast'), {delay:3500}).show();
  }

  async function load() {
    $('#refresh-admin i').addClass('fa-spin');
    try {
      const response=await fetch('/administracao/api/dados/');
      const payload=await response.json();
      if(!response.ok) throw new Error(payload.error || 'Falha ao carregar');
      data=payload; render();
    } catch(error) { alertMessage(error.message); }
    finally { $('#refresh-admin i').removeClass('fa-spin'); }
  }

  function render() {
    const pending=data.profiles.filter(profile=>profile.status==='pending');
    $('#kpi-users').text(fmt(data.profiles.length)); $('#kpi-pending,#pending-badge').text(fmt(pending.length)); $('#kpi-sessions').text(fmt(data.sessions.length)); $('#kpi-logs').text(fmt(data.logs.length));
    $('#pending-users').html(pending.length ? pending.map(profile => `<div class="col-xl-4 col-md-6 mb-3"><div class="card h-100 border-warning"><div class="card-body"><div class="d-flex align-items-center mb-3"><div class="admin-avatar me-2">${esc(initials(profile.full_name))}</div><div class="text-truncate"><strong>${esc(profile.full_name || profile.username || 'Sem nome')}</strong><div class="small text-gray-500">Cadastrado em ${date(profile.created_at)}</div></div></div><div class="mb-2"><i class="fa fa-location-dot fa-fw text-gray-500"></i> ${esc(profile.comum || 'Comum não informada')}</div><div class="mb-2"><i class="fa fa-map-location-dot fa-fw text-gray-500"></i> ${esc(profile.municipio || profile.cidade || 'Município não informado')}</div><div class="mb-3"><span class="badge origin-badge">${esc(origin(profile))}</span></div><button class="btn btn-sm btn-theme w-100 edit-user" data-id="${profile.user_id}" data-approve="true"><i class="fa fa-user-check me-1"></i>Analisar e liberar</button></div></div></div>`).join('') : '<div class="col-12"><div class="alert alert-success"><i class="fa fa-check-circle me-2"></i>Não há usuários aguardando liberação.</div></div>');
    renderUsers(); renderLogs(); renderSessions();
    const modules=[...new Set(data.logs.map(log=>log.module).filter(Boolean))].sort(); $('#module-filter').html('<option value="">Todos os módulos</option>'+modules.map(module=>`<option>${esc(module)}</option>`).join(''));
  }

  function renderUsers() {
    const search=norm($('#user-search').val()), status=$('#status-filter').val();
    const rows=data.profiles.filter(profile=>(!status||profile.status===status)&&(!search||norm([profile.full_name,profile.username,profile.comum,profile.municipio,profile.cidade,origin(profile)].join(' ')).includes(search)));
    $('#users-table').html(rows.map(profile=>`<tr><td><div class="d-flex align-items-center"><div class="admin-avatar me-2">${esc(initials(profile.full_name))}</div><div><strong>${esc(profile.full_name||profile.username||'Sem nome')}</strong><div class="small text-gray-500">${esc(profile.user_id)}</div></div></div></td><td><strong>${roleLabel(profile.role_id)}</strong><div class="small text-gray-500">${esc(profile.municipio||profile.cidade||'—')} · ${esc(profile.comum||'—')}</div></td><td><span class="badge origin-badge">${esc(origin(profile))}</span><div class="small text-gray-500 mt-1">${date(profile.created_at)}</div></td><td><strong>${fmt(profile.contador_logins)}</strong> acessos<div class="small text-gray-500">Último: ${date(profile.data_ultimo_login)}</div></td><td><span class="badge bg-${statusBadge(profile.status)}">${statusLabel(profile.status)}</span></td><td class="text-nowrap"><button class="btn btn-sm btn-outline-theme edit-user" data-id="${profile.user_id}" title="Editar usuário"><i class="fa fa-pen"></i></button> <button class="btn btn-sm btn-outline-danger delete-user" data-id="${profile.user_id}" title="Excluir usuário"><i class="fa fa-trash"></i></button></td></tr>`).join('') || '<tr><td colspan="6" class="text-center text-gray-500 py-4">Nenhum usuário encontrado.</td></tr>');
  }

  function renderLogs() {
    const search=norm($('#log-search').val()), module=$('#module-filter').val(), day=$('#log-date').val(), profiles=profileMap();
    const rows=data.logs.filter(log=>(!module||log.module===module)&&(!day||String(log.created_at).startsWith(day))&&(!search||norm([log.action,log.module,JSON.stringify(log.details),profiles[log.user_id]?.full_name].join(' ')).includes(search)));
    $('#logs-table').html(rows.map(log=>{const profile=profiles[log.user_id]||{}; return `<tr><td class="text-nowrap">${date(log.created_at)}</td><td>${esc(profile.full_name||log.user_id||'Sistema')}<div class="small text-gray-500">${esc(profile.comum||'')}</div></td><td><span class="badge bg-gray-700">${esc(log.action)}</span></td><td>${esc(log.module||'GLOBAL')}</td><td><span class="small">${esc(log.ip_address||'—')}</span><div class="small text-gray-500 admin-detail" title="${esc(log.user_agent)}">${esc(log.user_agent||'')}</div></td><td><div class="admin-detail" title="${esc(JSON.stringify(log.details||{}))}">${esc(JSON.stringify(log.details||{}))}</div></td></tr>`}).join('') || '<tr><td colspan="6" class="text-center text-gray-500 py-4">Nenhum evento encontrado.</td></tr>');
  }

  function renderSessions() {
    const profiles=profileMap();
    $('#sessions-table').html(data.sessions.map(session=>{const profile=profiles[session.user_id]||{}; return `<tr><td>${date(session.started_at)}</td><td><strong>${esc(profile.full_name||session.user_id||'Desconhecido')}</strong><div class="small text-gray-500">${esc(profile.comum||'')}</div></td><td><span class="badge bg-${session.status==='active'?'success':'secondary'}">${esc(session.status)}</span></td><td>${date(session.last_activity_at)}</td><td>${date(session.ended_at)}</td><td>${esc(session.logout_reason||'—')}</td></tr>`}).join('') || '<tr><td colspan="6" class="text-center text-gray-500 py-4">Nenhuma sessão registrada.</td></tr>');
  }

  function openUser(id, approve) {
    const profile=data.profiles.find(item=>item.user_id===id); if(!profile) return;
    const sector=profile.sector||profile.setor||'Visitas', primary=norm(sector).includes('musical')?'musicalizacao':norm(sector)==='global'?'global':'visitas', grants=new Set((data.module_access||[]).filter(row=>row.user_id===id&&row.active).map(row=>row.module)); if(primary!=='global')grants.add(primary); else ['visitas','musicalizacao'].forEach(item=>grants.add(item));
    $('#edit-user-id').val(id); $('#edit-name').val(profile.full_name||''); $('#edit-role').val(String(profile.role_id||4)); $('#edit-status').val(approve?'approved':profile.status||'pending'); $('#edit-sector').val(sector); $('#edit-comum').val(profile.comum||''); $('#edit-municipio').val(profile.municipio||profile.cidade||''); $('#edit-cargo').val(profile.cargo||''); $('.module-check').each(function(){this.checked=grants.has(this.value)}); $('#edit-origin').text(origin(profile)); bootstrap.Modal.getOrCreateInstance(document.querySelector('#user-modal')).show();
  }

  async function saveUser() {
    const id=$('#edit-user-id').val(), body={full_name:$('#edit-name').val().trim(),role_id:Number($('#edit-role').val()),status:$('#edit-status').val(),sector:$('#edit-sector').val(),comum:$('#edit-comum').val().trim(),municipio:$('#edit-municipio').val().trim(),cidade:$('#edit-municipio').val().trim(),cargo:$('#edit-cargo').val().trim()}, modules=$('.module-check:checked').map((_,item)=>item.value).get();
    $('#save-user').prop('disabled',true);
    try { const response=await fetch(`/administracao/api/usuarios/${id}/`,{method:'PATCH',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify(body)}); const payload=await response.json(); if(!response.ok) throw new Error(payload.error||'Falha ao salvar'); const moduleResponse=await fetch(`/administracao/api/usuarios/${id}/modulos/`,{method:'PUT',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify({modules})}); const modulePayload=await moduleResponse.json(); if(!moduleResponse.ok)throw new Error(modulePayload.error||'Falha ao salvar as pastas autorizadas'); bootstrap.Modal.getInstance(document.querySelector('#user-modal')).hide(); alertMessage('Autorização atualizada com sucesso.','success'); await load(); }
    catch(error){alertMessage(error.message)} finally{$('#save-user').prop('disabled',false)}
  }

  async function deleteUser(id) {
    const profile=data.profiles.find(item=>item.user_id===id); if(!profile) return;
    const confirmed=await swal({
      title:'Excluir usuário?',
      text:`${profile.full_name||profile.username||'Este usuário'} perderá definitivamente o acesso ao sistema.`,
      icon:'warning',
      buttons:{cancel:{text:'Cancelar',visible:true,value:false},confirm:{text:'Excluir definitivamente',visible:true,value:true,closeModal:true}},
      dangerMode:true,
    });
    if(!confirmed) return;
    try {
      const response=await fetch(`/administracao/api/usuarios/${id}/`,{method:'DELETE',headers:{'X-CSRFToken':csrf()}});
      const payload=await response.json(); if(!response.ok) throw new Error(payload.error||'Falha ao excluir o usuário.');
      await load(); successToast(payload.message||'Usuário excluído com sucesso.');
    } catch(error) { alertMessage(error.message); }
  }

  $(function(){ $('#refresh-admin').on('click',load); $(document).on('click','.edit-user',function(){openUser($(this).data('id'),$(this).data('approve'))}); $(document).on('click','.delete-user',function(){deleteUser(String($(this).data('id')))}); $('#save-user').on('click',saveUser); $('#user-search,#status-filter').on('input change',renderUsers); $('#log-search,#module-filter,#log-date').on('input change',renderLogs); if(location.hash) $(`[href="${location.hash}"]`).tab('show'); load(); });
})();
