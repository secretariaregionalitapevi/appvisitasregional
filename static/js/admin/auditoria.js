(function () {
  'use strict';
  let data = { profiles: [], logs: [], sessions: [], access_levels: [], module_access: [] };
  const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const pageSize = 50, pages = {usuarios: 1, auditoria: 1, sessoes: 1};
  const rendered = new Set();
  let loading = null;
  function activeSection() {
    return document.querySelector('#admin-tabs .nav-link.active')?.getAttribute('href')?.slice(1) || 'pendentes';
  }
  function renderActiveSection() {
    const section = activeSection();
    if (rendered.has(section)) return;
    if (section === 'usuarios') renderUsers();
    if (section === 'auditoria') renderLogs();
    if (section === 'sessoes') renderSessions();
    rendered.add(section);
  }
  function syncTabFromHash() {
    const hash = location.hash || '#pendentes';
    const tab = Array.from(document.querySelectorAll('#admin-tabs [data-bs-toggle="tab"]'))
      .find(item => item.getAttribute('href') === hash);
    if (tab) bootstrap.Tab.getOrCreateInstance(tab).show();
  }
  function paginated(rows, section) {
    const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
    pages[section] = Math.min(pages[section], totalPages);
    const page = pages[section], start = (page - 1) * pageSize;
    $(`#${section}-pagination`).html(`<span>${rows.length ? start + 1 : 0}&ndash;${Math.min(start + pageSize, rows.length)} de ${fmt(rows.length)}</span><div><button type="button" class="btn btn-sm admin-page admin-page-previous me-2" data-section="${section}" data-page="${page - 1}" ${page === 1 ? 'disabled' : ''}><i class="fa fa-arrow-left me-2" aria-hidden="true"></i>Anterior</button><button type="button" class="btn btn-sm admin-page admin-page-next" data-section="${section}" data-page="${page + 1}" ${page === totalPages ? 'disabled' : ''}>Pr&oacute;xima<i class="fa fa-arrow-right ms-2" aria-hidden="true"></i></button></div>`);
    return rows.slice(start, start + pageSize);
  }
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
  const AUDIT_ACTIONS = {
    LOGIN:['Login','Autenticou-se no sistema.','success','Acesso'], LOGOUT:['Logout','Encerrou a sess\u00e3o no sistema.','secondary','Acesso'],
    LOGIN_FAILED:['Falha no login','Tentativa de login n\u00e3o conclu\u00edda.','danger','Seguran\u00e7a'], LOGIN_DENIED:['Acesso negado','Tentativa de acesso bloqueada.','danger','Seguran\u00e7a'],
    REGISTER:['Cadastro','Realizou um novo cadastro.','primary','Cria\u00e7\u00e3o'], VIEW_PAGE:['Navega\u00e7\u00e3o','Acessou uma p\u00e1gina do sistema.','info','Navega\u00e7\u00e3o'],
    VIEW_AUDIT_CENTER:['Consulta da auditoria','Acessou a central de auditoria.','info','Navega\u00e7\u00e3o'],
    CREATE:['Cria\u00e7\u00e3o','Criou um novo registro.','primary','Cria\u00e7\u00e3o'], UPDATE:['Atualiza\u00e7\u00e3o','Alterou um registro existente.','warning','Atualiza\u00e7\u00e3o'], DELETE:['Exclus\u00e3o','Excluiu um registro.','danger','Exclus\u00e3o'],
    CREATE_TEAM:['Criacao de equipe','Criou uma equipe de visitas.','primary','Cria\u00e7\u00e3o'], DELETE_TEAM:['Exclusao de equipe','Excluiu uma equipe de visitas.','danger','Exclus\u00e3o'],
    ASSIGN_TEAM_MEMBER:['Vinculo em equipe','Vinculou um integrante a uma equipe.','warning','Atualiza\u00e7\u00e3o'], REMOVE_TEAM_MEMBER:['Remocao de integrante','Removeu um integrante de uma equipe.','danger','Exclus\u00e3o'],
    UPDATE_USER_ACCESS:['Permissoes do usuario','Alterou perfil, status ou escopo de acesso.','warning','Atualiza\u00e7\u00e3o'], DELETE_USER:['Exclusao de usuario','Excluiu uma conta de usu\u00e1rio.','danger','Exclus\u00e3o'],
    UPDATE_USER_MODULE_ACCESS:['Pastas autorizadas','Alterou as pastas permitidas para um usu\u00e1rio.','warning','Atualiza\u00e7\u00e3o'],
    MUTATION_FAILED:['Opera\u00e7\u00e3o n\u00e3o conclu\u00edda','Uma altera\u00e7\u00e3o administrativa falhou.','danger','Falha'], RECONCILE:['Reconcilia\u00e7\u00e3o','Reconciliou dados operacionais.','warning','Atualiza\u00e7\u00e3o']
  };
  const MODULE_LABELS={AUTH:'Autentica\u00e7\u00e3o',AUDITORIA:'Auditoria',ADMIN:'Usuarios e acessos',ADMINISTRACAO:'Administra\u00e7\u00e3o',MINISTERIO_REGIONAL:'Minist\u00e9rio Regional',SANTA_CEIA:'Santa Ceia',NAVIGATION:'Navega\u00e7\u00e3o',VISITAS_IRMANDADE:'Visitas - Irmandade',VISITAS_EQUIPES:'Visitas - Equipes',VISITAS_AGENDA:'Visitas - Agenda',VISITAS_LANCAMENTOS:'Visitas - Lancamentos'};
  const actionMeta=log=>AUDIT_ACTIONS[String(log.action||'').toUpperCase()]||[String(log.action||'Evento').replaceAll('_',' '),'Evento registrado na trilha de auditoria.','info','Evento'];
  const moduleLabel=module=>MODULE_LABELS[String(module||'').toUpperCase()]||String(module||'Global').replaceAll('_',' ');
  const detailSummary=log=>{const d=log.details||{},meta=actionMeta(log);if(log.action==='VIEW_PAGE')return `Acessou ${d.page_title||d.path||d.request?.path||'uma pagina do sistema'}.`;if(d.entity)return `${meta[1]} Entidade: ${d.entity}${d.entity_id?' #'+d.entity_id:''}.`;return d.description||d.message||meta[1]};
  const detailRows=(value,prefix='')=>Object.entries(value||{}).flatMap(([key,item])=>{const label=(prefix?prefix+' / ':'')+key.replaceAll('_',' ');return item&&typeof item==='object'&&!Array.isArray(item)?detailRows(item,label):[[label,Array.isArray(item)?JSON.stringify(item):item]]});
  const formatPersonName = value => {
    const particles=new Set(['da','das','de','do','dos','e']);
    return String(value||'').trim().toLocaleLowerCase('pt-BR').split(/\s+/).filter(Boolean).map((word,index)=>{
      if(index>0&&particles.has(word))return word;
      return word.split('-').map(part=>part?part.charAt(0).toLocaleUpperCase('pt-BR')+part.slice(1):part).join('-');
    }).join(' ');
  };

  function alertMessage(message, type='danger') { $('#admin-alert').attr('class',`alert alert-${type}`).text(message); setTimeout(()=>$('#admin-alert').addClass('d-none'),5000); }
  function adminToast(message,type='success',highlight=''){return AppFeedback.show({type:type==='success'?'success':'error',title:type==='success'?'Operação concluída':'Não foi possível concluir',message,highlight,duration:type==='success'?4600:6000})}
  const successToast = (message, highlight = '') => adminToast(message, 'success', highlight);
  async function fetchJsonWithTimeout(url, options={}, timeout=20000) {
    const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),timeout);
    try {
      const response=await fetch(url,{...options,signal:controller.signal}), contentType=response.headers.get('content-type')||'', payload=contentType.includes('application/json')?await response.json():{};
      if(!response.ok)throw new Error(payload.error||`O servidor respondeu com erro ${response.status}.`);
      return payload;
    } catch(error) {
      if(error.name==='AbortError')throw new Error('O servidor demorou demais para responder. Tente novamente.');
      throw error;
    } finally { clearTimeout(timer); }
  }

  function load() {
    if (loading) return loading;
    $('#refresh-admin').prop('disabled', true);
    $('#refresh-admin i').addClass('fa-spin');
    loading = (async () => {
      try {
        data = await fetchJsonWithTimeout('/administracao/api/dados/');
        data.profiles = (data.profiles || []).map(profile => ({...profile, full_name: formatPersonName(profile.full_name)}));
        rendered.clear();
        render();
      } catch (error) { alertMessage(error.message); }
      finally {
        $('#refresh-admin').prop('disabled', false);
        $('#refresh-admin i').removeClass('fa-spin');
        loading = null;
      }
    })();
    return loading;
  }

  function render() {
    const pending=data.profiles.filter(profile=>profile.status==='pending');
    $('#kpi-users').text(fmt(data.profiles.length)); $('#kpi-pending,#pending-badge').text(fmt(pending.length)); $('#kpi-sessions').text(fmt(data.sessions.length)); $('#kpi-logs').text(fmt(data.logs.length));
    $('#pending-users').html(pending.length ? pending.map(profile => `<div class="col-xl-4 col-md-6 mb-3"><div class="card h-100 border-warning"><div class="card-body"><div class="d-flex align-items-center mb-3"><div class="admin-avatar me-2">${esc(initials(profile.full_name))}</div><div class="text-truncate"><strong>${esc(profile.full_name || profile.username || 'Sem nome')}</strong><div class="small text-gray-500">Cadastrado em ${date(profile.created_at)}</div></div></div><div class="mb-2"><i class="fa fa-location-dot fa-fw text-gray-500"></i> ${esc(profile.comum || 'Comum não informada')}</div><div class="mb-2"><i class="fa fa-map-location-dot fa-fw text-gray-500"></i> ${esc(profile.municipio || profile.cidade || 'Município não informado')}</div><div class="mb-3"><span class="badge origin-badge">${esc(origin(profile))}</span></div><button class="btn btn-sm btn-theme w-100 edit-user" data-id="${profile.user_id}" data-approve="true"><i class="fa fa-user-check me-1"></i>Analisar e liberar</button></div></div></div>`).join('') : '<div class="col-12"><div class="alert alert-success"><i class="fa fa-check-circle me-2"></i>Não há usuários aguardando liberação.</div></div>');
    const selectedModule = $('#module-filter').val();
    const modules=[...new Set(data.logs.map(log=>log.module).filter(Boolean))].sort(); $('#module-filter').html('<option value="">Todos os módulos</option>'+modules.map(module=>`<option>${esc(module)}</option>`).join(''));
    $('#module-filter').val(modules.includes(selectedModule) ? selectedModule : '');
    renderActiveSection();
  }

  function renderUsers() {
    const search=norm($('#user-search').val()), status=$('#status-filter').val();
    const rows=data.profiles.filter(profile=>(!status||profile.status===status)&&(!search||norm([profile.full_name,profile.username,profile.comum,profile.municipio,profile.cidade,origin(profile)].join(' ')).includes(search)));
    $('#users-table').html(paginated(rows, 'usuarios').map(profile=>`<tr><td><div class="d-flex align-items-center"><div class="admin-avatar me-2">${esc(initials(profile.full_name))}</div><div><strong>${esc(profile.full_name||profile.username||'Sem nome')}</strong><div class="small text-gray-500">${esc(profile.user_id)}</div></div></div></td><td><strong>${roleLabel(profile.role_id)}</strong><div class="small text-gray-500">${esc(profile.municipio||profile.cidade||'—')} · ${esc(profile.comum||'—')}</div></td><td><span class="badge origin-badge">${esc(origin(profile))}</span><div class="small text-gray-500 mt-1">${date(profile.created_at)}</div></td><td><strong>${fmt(profile.contador_logins)}</strong> acessos<div class="small text-gray-500">Último: ${date(profile.data_ultimo_login)}</div></td><td><span class="badge bg-${statusBadge(profile.status)}">${statusLabel(profile.status)}</span></td><td class="text-nowrap"><button class="btn btn-sm btn-outline-theme edit-user" data-id="${profile.user_id}" title="Editar usuário"><i class="fa fa-pen"></i></button> <button class="btn btn-sm btn-outline-danger delete-user" data-id="${profile.user_id}" title="Excluir usuário"><i class="fa fa-trash"></i></button></td></tr>`).join('') || '<tr><td colspan="6" class="text-center text-gray-500 py-4">Nenhum usuário encontrado.</td></tr>');
  }

  function renderLogs() {
    const search=norm($('#log-search').val()), module=$('#module-filter').val(), day=$('#log-date').val(), profiles=profileMap();
    const rows=data.logs.filter(log=>(!module||log.module===module)&&(!day||String(log.created_at).startsWith(day))&&(!search||norm([log.action,moduleLabel(log.module),detailSummary(log),JSON.stringify(log.details),profiles[log.user_id]?.full_name].join(' ')).includes(search)));
    $('#logs-table').html(paginated(rows, 'auditoria').map(log=>{const profile=profiles[log.user_id]||{},meta=actionMeta(log),actor=profile.full_name||log.details?.actor?.name||log.user_id||'Sistema';return `<tr><td class="text-nowrap">${date(log.created_at)}</td><td><strong>${esc(actor)}</strong><div class="small text-gray-500">${esc(profile.comum||log.details?.actor?.scope||'')}</div></td><td><span class="badge bg-${meta[2]}">${esc(meta[3])}</span><div class="small mt-1">${esc(meta[0])}</div></td><td>${esc(moduleLabel(log.module))}</td><td><span class="small">${esc(log.ip_address||'\u2014')}</span><div class="small text-gray-500 admin-detail" title="${esc(log.user_agent)}">${esc(log.user_agent||'')}</div></td><td><div>${esc(detailSummary(log))}</div><button class="btn btn-xs btn-outline-theme mt-1 audit-detail" data-id="${esc(log.id)}"><i class="fa fa-magnifying-glass-plus me-1"></i>Detalhes</button></td></tr>`}).join('')||'<tr><td colspan="6" class="text-center text-gray-500 py-4">Nenhum evento encontrado.</td></tr>');
  }

  function openAuditDetail(id){const log=data.logs.find(item=>String(item.id)===String(id));if(!log)return;const profile=profileMap()[log.user_id]||{},meta=actionMeta(log),rows=detailRows(log.details);$('#audit-detail-content').html(`<div class="row g-3 mb-3"><div class="col-md-4"><small class="text-muted d-block">Data e hora</small><strong>${date(log.created_at)}</strong></div><div class="col-md-4"><small class="text-muted d-block">Ator</small><strong>${esc(profile.full_name||log.details?.actor?.name||log.user_id||'Sistema')}</strong></div><div class="col-md-4"><small class="text-muted d-block">Classificacao</small><span class="badge bg-${meta[2]}">${esc(meta[3])}</span></div><div class="col-md-4"><small class="text-muted d-block">Operacao</small>${esc(meta[0])}</div><div class="col-md-4"><small class="text-muted d-block">Modulo</small>${esc(moduleLabel(log.module))}</div><div class="col-md-4"><small class="text-muted d-block">IP de origem</small>${esc(log.ip_address||'\u2014')}</div></div><div class="alert alert-light border"><strong>Resumo:</strong> ${esc(detailSummary(log))}</div><h6>Informacoes registradas</h6><div class="table-responsive"><table class="table table-sm table-striped"><thead><tr><th>Campo</th><th>Valor registrado</th></tr></thead><tbody>${rows.map(([k,v])=>`<tr><td class="fw-bold">${esc(k)}</td><td class="text-break">${esc(v==null?'\u2014':v)}</td></tr>`).join('')||'<tr><td colspan="2">Sem detalhes adicionais.</td></tr>'}</tbody></table></div><details><summary class="text-muted">Visualizar registro tecnico JSON</summary><pre class="bg-light border rounded p-3 mt-2 text-break">${esc(JSON.stringify(log.details||{},null,2))}</pre></details>`);bootstrap.Modal.getOrCreateInstance(document.querySelector('#audit-detail-modal')).show()}


  function renderSessions() {
    const profiles=profileMap();
    $('#sessions-table').html(paginated(data.sessions, 'sessoes').map(session=>{const profile=profiles[session.user_id]||{}; return `<tr><td>${date(session.started_at)}</td><td><strong>${esc(profile.full_name||session.user_id||'Desconhecido')}</strong><div class="small text-gray-500">${esc(profile.comum||'')}</div></td><td><span class="badge bg-${session.status==='active'?'success':'secondary'}">${esc(session.status)}</span></td><td>${date(session.last_activity_at)}</td><td>${date(session.ended_at)}</td><td>${esc(session.logout_reason||'—')}</td></tr>`}).join('') || '<tr><td colspan="6" class="text-center text-gray-500 py-4">Nenhuma sessão registrada.</td></tr>');
  }

  let metadataRequest = 0;
  async function loadUserMetadata(id, profile) {
    const requestId = ++metadataRequest;
    $('#user-metadata-error').text('');
    $('#user-email,#user-registered-by,#user-updated-by').text('Carregando...');
    $('#user-created-at').text(date(profile.created_at));
    $('#user-update-at').text('');
    try {
      const metadata = await fetchJsonWithTimeout(`/administracao/api/usuarios/${id}/metadados/`);
      if (requestId !== metadataRequest) return;
      const author = record => record?.name || (record?.user_id ? `Responsável sem nome (${record.user_id})` : 'Autoria não registrada');
      $('#user-email').text(metadata.email || 'E-mail não informado');
      $('#user-registered-by').text(author(metadata.registration));
      $('#user-updated-by').text(author(metadata.last_update));
      $('#user-update-at').text(metadata.last_update?.at ? date(metadata.last_update.at) : 'Sem alteração registrada na auditoria');
    } catch (error) {
      if (requestId !== metadataRequest) return;
      $('#user-email,#user-registered-by,#user-updated-by').text('Consulta indisponível');
      $('#user-metadata-error').text(error.message);
    }
  }

  function openUser(id, approve) {
    const profile=data.profiles.find(item=>item.user_id===id); if(!profile) return;
    const sector=profile.sector||profile.setor||'Visitas';
    const normSec = norm(sector);
    const isGlobalSec = normSec === 'global' || normSec === 'administrativo' || Number(profile.role_id) === 1;
    const isMusicalSec = normSec.includes('musical') || normSec === 'ebi' || normSec === 'musica';
    const primary = isMusicalSec ? 'musicalizacao' : (isGlobalSec ? 'global' : 'visitas');
    const grants=new Set((data.module_access||[]).filter(row=>row.user_id===id&&row.active).map(row=>row.module));
    if(primary==='global') {
      ['visitas','musicalizacao'].forEach(item=>grants.add(item));
    } else {
      grants.add(primary);
    }
    $('#edit-user-id').val(id);
    $('#edit-name').val(profile.full_name||'');
    $('#edit-role').val(String(profile.role_id||4));
    $('#edit-status').val(approve?'approved':profile.status||'pending');
    $('#edit-sector').val(isGlobalSec ? 'Global' : (primary === 'musicalizacao' ? 'Musicalização' : 'Visitas'));
    $('#edit-comum').val(profile.comum||'');
    $('#edit-municipio').val(profile.municipio||profile.cidade||'');
    $('#edit-cargo').val(profile.cargo||'');
    $('.module-check').each(function(){this.checked=grants.has(this.value)});
    $('#edit-origin').text(origin(profile));
    loadUserMetadata(id, profile);
    bootstrap.Modal.getOrCreateInstance(document.querySelector('#user-modal')).show();
  }

  async function saveUser() {
    const id=$('#edit-user-id').val(), body={full_name:$('#edit-name').val().trim(),role_id:Number($('#edit-role').val()),status:$('#edit-status').val(),sector:$('#edit-sector').val(),comum:$('#edit-comum').val().trim(),municipio:$('#edit-municipio').val().trim(),cidade:$('#edit-municipio').val().trim(),cargo:$('#edit-cargo').val().trim()}, modules=$('.module-check:checked').map((_,item)=>item.value).get();
    $('#save-user').prop('disabled',true);
    try { const response=await fetch(`/administracao/api/usuarios/${id}/`,{method:'PATCH',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify(body)}); const payload=await response.json(); if(!response.ok) throw new Error(payload.error||'Falha ao salvar'); const moduleResponse=await fetch(`/administracao/api/usuarios/${id}/modulos/`,{method:'PUT',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify({modules})}); const modulePayload=await moduleResponse.json(); if(!moduleResponse.ok)throw new Error(modulePayload.error||'Falha ao salvar as pastas autorizadas'); bootstrap.Modal.getInstance(document.querySelector('#user-modal')).hide(); alertMessage('Autorização atualizada com sucesso.','success'); await load(); }
    catch(error){alertMessage(error.message)} finally{$('#save-user').prop('disabled',false)}
  }

  async function saveUserWithToast() {
    const id=$('#edit-user-id').val(),previous=data.profiles.find(item=>String(item.user_id)===String(id))||{},body={full_name:formatPersonName($('#edit-name').val().trim()),role_id:Number($('#edit-role').val()),status:$('#edit-status').val(),sector:$('#edit-sector').val(),comum:$('#edit-comum').val().trim(),municipio:$('#edit-municipio').val().trim(),cidade:$('#edit-municipio').val().trim(),cargo:$('#edit-cargo').val().trim()},modules=$('.module-check:checked').map((_,item)=>item.value).get(),button=$('#save-user'),originalButton=button.html(),displayUserName=body.full_name||previous.full_name||previous.username||'Usuário';
    $('#edit-name').val(body.full_name);button.prop('disabled',true).html('<i class="fa fa-spinner fa-spin me-1"></i>Salvando...');
    const notice=AppFeedback.show({type:'loading',flow:'update',highlight:displayUserName,title:'Atualizando autorização',message:`Aguarde, o cadastro de ${displayUserName} está sendo atualizado.`});
    try{await fetchJsonWithTimeout(`/administracao/api/usuarios/${id}/`,{method:'PATCH',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify(body)});await fetchJsonWithTimeout(`/administracao/api/usuarios/${id}/modulos/`,{method:'PUT',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify({modules})});const modal=bootstrap.Modal.getInstance(document.querySelector('#user-modal')),approvedNow=previous.status!=='approved'&&body.status==='approved';if(modal)modal.hide();await load();successToast(approvedNow?`${displayUserName} foi aprovado e salvo com sucesso.`:`Cadastro de ${displayUserName} atualizado com sucesso.`,displayUserName)}catch(error){notice.close();adminToast(`Não foi possível salvar o cadastro de ${displayUserName}. ${error.message||'Tente novamente.'}`,'error')}finally{button.prop('disabled',false).html(originalButton)}
  }

  async function deleteUser(id) {
    const profile=data.profiles.find(item=>item.user_id===id);if(!profile)return;const name=profile.full_name||profile.username||'Este usuário';
    const confirmed=await AppFeedback.confirm({title:'Excluir usuário?',message:`${name} perderá definitivamente o acesso ao sistema.`,highlight:name,confirmText:'Excluir definitivamente'});if(!confirmed)return;
    const notice=AppFeedback.show({type:'loading',flow:'delete',title:'Excluindo usuário',message:'Aguarde, o acesso e os vínculos estão sendo removidos.'});
    try{const response=await fetch(`/administracao/api/usuarios/${id}/`,{method:'DELETE',headers:{'X-CSRFToken':csrf()}}),payload=await response.json();if(!response.ok)throw new Error(payload.error||'Falha ao excluir o usuário.');await load();successToast(payload.message||'Usuário excluído com sucesso.')}catch(error){notice.close();adminToast(error.message,'error')}
  }

  $(function(){
    $('#refresh-admin').on('click',load);
    $(document).on('click','.edit-user',function(){openUser($(this).data('id'),$(this).data('approve'))});
    $(document).on('click','.delete-user',function(){deleteUser(String($(this).data('id')))});
    $(document).on('click','.audit-detail',function(){openAuditDetail(String($(this).data('id')))});
    $('#save-user').on('click',saveUserWithToast);
    $('#edit-role').on('change', function(){
      if($(this).val() === '1') {
        $('#edit-sector').val('Global');
        $('.module-check').prop('checked', true);
      }
    });
    $('#edit-sector').on('change', function(){
      const val = $(this).val();
      if(val === 'Global') {
        $('.module-check').prop('checked', true);
      } else if(val === 'Visitas') {
        $('#module-visitas').prop('checked', true);
      } else if(val === 'Musicalização') {
        $('#module-musicalizacao').prop('checked', true);
      }
    });
    $('.module-check').on('change', function(){
      const v = $('#module-visitas').is(':checked'), m = $('#module-musicalizacao').is(':checked');
      if(v && m) $('#edit-sector').val('Global');
      else if(m) $('#edit-sector').val('Musicalização');
      else if(v) $('#edit-sector').val('Visitas');
    });
    let userSearchTimer, logSearchTimer;
    $('#user-search').on('input', () => {clearTimeout(userSearchTimer); userSearchTimer = setTimeout(() => {pages.usuarios = 1; renderUsers();}, 180);});
    $('#status-filter').on('change', () => {pages.usuarios = 1; renderUsers();});
    $('#log-search').on('input', () => {clearTimeout(logSearchTimer); logSearchTimer = setTimeout(() => {pages.auditoria = 1; renderLogs();}, 180);});
    $('#module-filter,#log-date').on('change', () => {pages.auditoria = 1; renderLogs();});
    $(document).on('click', '.admin-page', function () {
      const section = this.dataset.section;
      if (!(section in pages)) return;
      pages[section] = Math.max(1, Number(this.dataset.page) || 1);
      rendered.delete(section);
      renderActiveSection();
    });
    document.querySelectorAll('#admin-tabs [data-bs-toggle="tab"]').forEach(tab => {
      tab.addEventListener('shown.bs.tab', () => {
        const hash = tab.getAttribute('href');
        if (location.hash !== hash) history.pushState(null, '', hash);
        renderActiveSection();
      });
    });
    window.addEventListener('hashchange', syncTabFromHash);
    window.addEventListener('popstate', syncTabFromHash);
    syncTabFromHash();
    load();
  });
})();
