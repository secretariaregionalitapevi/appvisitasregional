(() => {
  const {esc, request} = window.MusicEventsDashboard;
  const panel = document.createElement('section');
  panel.className = 'events-panel justifications-panel mb-4';
  panel.innerHTML = `<div class="events-heading"><div><h2>Justificativas de encarregados</h2><p>Cadastre ou importe as justificativas e acompanhe os registros deste evento.</p></div></div>
    <div class="p-3"><div class="row g-3"><div class="col-md-6"><label for="just-event" class="form-label">Evento das justificativas</label><select id="just-event" class="form-select"><option value="">Selecione o evento</option></select></div>
    <div class="col-md-6"><label for="just-file" class="form-label">Arquivo de justificativas</label><div class="justification-upload"><span class="justification-upload-action"><i class="fa fa-folder-open me-2" aria-hidden="true"></i>Escolher arquivo</span><span class="justification-upload-name" id="just-filename">Nenhum arquivo selecionado</span><input id="just-file" type="file" accept=".pdf,.xlsx,.csv,.png,.jpg,.jpeg,.webp" aria-describedby="just-file-help"></div></div></div>
    <div class="justification-import-actions"><button class="btn btn-primary" id="just-preview" type="button" disabled><i class="fa fa-magnifying-glass me-1" aria-hidden="true"></i>Conferir arquivo</button><button class="btn btn-outline-primary" id="just-register" type="button" disabled><i class="fa fa-plus me-1" aria-hidden="true"></i>Registrar justificativa</button><span id="just-import-hint" role="status" aria-live="polite">Carregando os eventos...</span></div>
    <div id="just-block-wrap" class="mt-3" hidden><label class="form-label" for="just-block">Bloco de origem deste evento</label><select class="form-select" id="just-block"><option value="">Selecione o bloco</option></select><small>Somente o bloco escolhido será lido. Depois de escolher, clique em Conferir arquivo.</small></div>
    <p class="small text-muted mt-2" id="just-file-help">PDF, Excel (.xlsx), CSV ou imagem, até 12 MB. Somente encarregados; identificações incertas ficam pendentes para conferência.</p>
    <div id="just-summary" role="status" aria-live="polite"></div><div id="just-preview-wrap" hidden><div class="table-responsive"><table class="table events-table"><thead><tr><th>Nome recebido / cargo</th><th>Comum / município identificado</th><th>Encarregado cadastrado</th><th>Conferência</th></tr></thead><tbody id="just-rows"></tbody></table></div>
    <label class="form-check"><input class="form-check-input" type="checkbox" id="just-reviewed"> Conferi o evento, a data e os encarregados identificados.</label>
    <button class="btn btn-success mt-3" id="just-confirm" type="button" disabled>Gravar justificativas identificadas</button></div>
    <hr><h3 class="h5">Justificativas vinculadas ao evento</h3><p class="small" id="just-event-reading">Selecione um evento para visualizar as justificativas.</p>
    <div class="d-flex gap-2 flex-wrap align-items-end mb-3"><div><label for="just-lot" class="form-label">Lote importado</label><select id="just-lot" class="form-select"><option value="">Todos os lotes deste evento</option></select></div><button id="just-reload" type="button" class="btn btn-outline-primary">Atualizar lista</button><button id="just-view-selected" type="button" class="btn btn-outline-primary" disabled>Visualizar selecionadas</button><button id="just-edit-selected" type="button" class="btn btn-outline-primary" disabled>Editar selecionadas</button><button id="just-delete-selected" type="button" class="btn btn-danger" disabled><i class="fa fa-trash me-1"></i>Excluir selecionadas</button></div>
    <p class="small text-muted">Cada encarregado tem sua própria justificativa e situação. Excluir remove apenas os registros selecionados e preserva o histórico.</p>
    <div class="table-responsive"><table class="table events-table"><thead><tr><th><input id="just-select-all" type="checkbox" aria-label="Selecionar todas as justificativas visíveis"></th><th>Nome / comum / município</th><th>Motivo</th><th>Lote / origem</th><th class="justification-actions-cell">Ações</th></tr></thead><tbody id="just-saved"></tbody></table></div></div>`;
  document.querySelector('[data-view-panel="conductors"]').prepend(panel);
  const $ = id => panel.querySelector('#just-' + id);
  let token = '', ready = 0, saved = [], selected = new Set(), editorIds = [], listedEvent = '', eventItems = [], eventsLoaded = false, busy = false, dashboardSelection = null;
  const editor = document.createElement('div'); editor.className = 'modal fade'; editor.tabIndex = -1;
  editor.setAttribute('aria-label', 'Justificativa do evento');
  editor.innerHTML = `<div class="modal-dialog modal-lg modal-dialog-centered justification-record-modal"><div class="modal-content"><form><div class="modal-header"><div><h5 class="modal-title">Justificativa do evento</h5><p id="just-dialog-caption" class="mb-0"></p></div><button class="btn-close" type="button" data-bs-dismiss="modal" aria-label="Fechar"></button></div><div class="modal-body"><div id="just-detail"></div><div id="just-edit-person" class="mt-3"><label for="just-edit-name" class="form-label">Nome do encarregado desta comum</label><input id="just-edit-name" class="form-control" maxlength="180"><small>O nome ser\u00e1 conferido no cadastro de encarregados locais desta comum.</small></div><div id="just-reason-wrap" class="justification-reason-card mt-3"><label for="just-edit-reason" class="form-label">Motivo da justificativa</label><textarea id="just-edit-reason" class="form-control" rows="4" maxlength="500" required></textarea></div></div><div class="modal-footer"><button type="button" class="btn btn-danger app-btn-cancel" data-bs-dismiss="modal"><i class="fa fa-xmark me-1"></i>Cancelar</button><button id="just-edit-save" type="submit" class="btn btn-primary">Salvar alterações</button></div></form></div></div>`;
  document.body.appendChild(editor);
  const registerModal = document.createElement('div'); registerModal.className = 'modal fade'; registerModal.tabIndex = -1;
  registerModal.setAttribute('aria-label', 'Registrar justificativa');
  registerModal.innerHTML = `<div class="modal-dialog modal-lg"><div class="modal-content"><form><div class="modal-header"><h5 class="modal-title">Registrar justificativa</h5><button class="btn-close" type="button" data-bs-dismiss="modal" aria-label="Fechar"></button></div><div class="modal-body"><p class="justification-register-event"></p><label class="form-label" for="just-new-common">Comum de congregação</label><select id="just-new-common" class="form-select mb-3" required></select><p id="just-new-city" class="small text-muted"></p><label class="form-label" for="just-new-person">Encarregado local</label><select id="just-new-person" class="form-select mb-3" required></select><label class="form-label" for="just-new-reason">Motivo da ausência</label><textarea id="just-new-reason" class="form-control" rows="4" maxlength="500" required></textarea></div><div class="modal-footer"><button class="btn btn-danger app-btn-cancel" type="button" data-bs-dismiss="modal"><i class="fa fa-xmark me-1"></i>Cancelar</button><button class="btn btn-primary" id="just-new-save" type="submit">Salvar justificativa</button></div></form></div></div>`;
  document.body.appendChild(registerModal);
  let registrationCommons = [];
  function reset() { token = ''; ready = 0; $('reviewed').checked = false; $('confirm').disabled = true; $('rows').innerHTML = ''; $('summary').textContent = ''; $('preview-wrap').hidden = true; }
  function notify(message, type) { window.AppFeedback.show({type, title: type === 'success' ? 'Justificativas' : 'Não foi possível concluir', message, toast: true}); }
  function updateControls() {
    const event = eventItems.find(e => e.id === $('event').value), file = $('file').files[0];
    const writable = !!event && event.status !== 'ENCERRADO';
    $('preview').disabled = busy || !writable || !file;
    $('register').disabled = busy || !writable;
    $('reload').disabled = busy || !event;
    $('import-hint').textContent = !eventsLoaded ? 'Carregando os eventos...' : !event ? 'Selecione o evento para cadastrar ou conferir um arquivo.' : !writable ? 'Evento encerrado: a consulta permanece disponível.' : !file ? 'Escolha um arquivo para habilitar a conferência ou registre a justificativa.' : 'Arquivo selecionado. Clique em Conferir arquivo para revisar os registros.';
  }
  async function run(button, operation) {
    const buttons = [...panel.querySelectorAll('button'), ...editor.querySelectorAll('button'), ...registerModal.querySelectorAll('button')];
    const label = button.innerHTML;
    buttons.forEach(b => b.disabled = true);
    busy = true;
    $('event').disabled = true; $('file').disabled = true;
    button.innerHTML = '<i class="fa fa-spinner fa-spin me-1" aria-hidden="true"></i>Aguarde';
    const loading = window.AppFeedback.show({type: 'loading', title: 'Justificativas', message: 'Processando os registros. Aguarde.', toast: true});
    try { await operation(); } catch(error) { try { await loadSaved(); } catch {} notify(error.message, 'error'); }
    finally { loading?.close(); busy = false; button.innerHTML = label; buttons.forEach(b => b.disabled = false); $('event').disabled = false; $('file').disabled = false; $('confirm').disabled = !token || !ready || !$('reviewed').checked; selectionState(); updateControls(); }
  }
  const endpoint = action => `/musica/eventos/api/eventos/${encodeURIComponent($('event').value)}/justificativas/${action}/`;
  const csrf = () => document.querySelector('[name=csrfmiddlewaretoken]').value;
  async function preview(button) {
    if (!$('event').value) { notify('Selecione o evento das justificativas.', 'error'); return; }
    if (!$('file').files.length) { notify('Selecione o arquivo.', 'error'); return; }
    await run(button, async () => {
      const block = $('block').value;
      reset();
      const body = new FormData(); body.append('arquivo', $('file').files[0]);
      if (block) body.append('bloco', block);
      const result = await request(endpoint('previa'), {method:'POST', headers:{'X-CSRFToken':csrf()}, body});
      if (result.blocos) {
        $('block-wrap').hidden = false;
        $('block').innerHTML = '<option value="">Selecione o bloco</option>' + result.blocos.map(b => `<option value="${esc(b.id)}">${esc(b.nome)} · ${esc(b.data)} · ${b.total} registros</option>`).join('');
        $('summary').textContent = 'Há mais de um bloco na origem. Escolha somente o bloco deste evento e confira novamente.';
        return;
      }
      token = result.token; ready = result.rows.filter(r => !r.problema).length;
      $('preview-wrap').hidden = false;
      $('summary').textContent = `${ready} encarregado(s) identificado(s); ${result.rows.length - ready} pendência(s); ${result.ignorados} registro(s) de outros cargos ignorado(s).`;
      $('rows').innerHTML = result.rows.map(r => {
        const leaders = r.encarregados_identificados?.length || 0;
        const status = r.problema || (leaders > 1 ? `${leaders} encarregados reconhecidos · uma conferência por comum` : 'Identificado · Justificou');
        return `<tr><td>${esc(r.nome)}<small>${esc(r.cargo)}</small></td><td>${esc(r.comum_identificada || r.comum)}<small>${esc(r.municipio)}</small></td><td>${esc(r.encarregado || 'Não confirmado')}</td><td>${esc(status)}</td></tr>`;
      }).join('');
    });
  }
  $('preview').onclick = () => preview($('preview'));
  function clearBlocks() { $('block').innerHTML = '<option value="">Selecione o bloco</option>'; $('block-wrap').hidden = true; }
  $('event').onchange = () => { reset(); clearBlocks(); updateControls(); loadSaved().catch(error => notify(error.message, 'error')); };
  $('file').onchange = () => { reset(); clearBlocks(); const file = $('file').files[0]; $('filename').textContent = file ? file.name : 'Nenhum arquivo selecionado'; $('filename').title = file?.name || ''; updateControls(); };
  $('block').onchange = reset;
  $('reviewed').onchange = () => $('confirm').disabled = !token || !ready || !$('reviewed').checked;
  $('confirm').onclick = () => run($('confirm'), async () => {
    const result = await request(endpoint('confirmar'), {method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':csrf()}, body:JSON.stringify({token, conferido:$('reviewed').checked})});
    reset(); await Promise.all([window.MusicEventsDashboard.refresh(), loadSaved()]);
    notify(`${result.novos} nova(s) justificativa(s) registrada(s); ${result.atualizados} existente(s) atualizada(s); ${result.preservados} registro(s) pendente(s) preservado(s).`, 'success');
  });
  request('/musica/eventos/api/eventos/').then(data => {
    if (!data.can_manage) { panel.hidden = true; return; }
    eventItems = data.items; eventsLoaded = true;
    $('event').innerHTML += data.items.map(e => `<option value="${esc(e.id)}">${esc(e.titulo)} · ${esc(e.data_evento.split('-').reverse().join('/'))}${e.status === 'ENCERRADO' ? ' (encerrado)' : ''}</option>`).join('');
    syncDashboardEvent(dashboardSelection, false); updateControls();
    return loadSaved();
  }).catch(error => notify(error.message, 'error'));
  function syncDashboardEvent(detail, reload = true) {
    if (!eventsLoaded || busy) return;
    for (const item of detail?.events || []) {
      if (eventItems.some(e => e.id === item.id)) continue;
      eventItems.push(item);
      $('event').add(new Option(`${item.titulo} · ${item.data_evento.split('-').reverse().join('/')}`, item.id));
    }
    const id = detail?.filters?.evento || document.querySelector('#events-event').value;
    if (!eventItems.some(e => e.id === id) || $('event').value === id) return;
    $('event').value = id; reset(); clearBlocks(); updateControls();
    if (reload) loadSaved().catch(error => notify(error.message, 'error'));
  }
  document.addEventListener('music-events-data', e => { dashboardSelection = e.detail; syncDashboardEvent(e.detail); });
  document.querySelector('#events-event').addEventListener('change', () => syncDashboardEvent());
  const post = (action, values) => request(endpoint(action), {method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':csrf()}, body:JSON.stringify(values)});
  const visibleRows = () => saved.filter(r => !$('lot').value || (r.lote || 'manual') === $('lot').value);
  function selectionState() {
    const visible = visibleRows(), count = visible.filter(r => selected.has(r.id)).length;
    const closed = eventItems.find(e => e.id === $('event').value)?.status === 'ENCERRADO';
    $('edit-selected').disabled = busy || closed || count !== 1; $('delete-selected').disabled = busy || closed || count === 0;
    $('view-selected').disabled = busy || count === 0;
    $('select-all').checked = visible.length > 0 && count === visible.length;
    $('select-all').indeterminate = count > 0 && count < visible.length;
  }
  function renderSaved() {
    $('saved').innerHTML = visibleRows().map(r => `<tr><td><input type="checkbox" data-pick="${esc(r.id)}" ${selected.has(r.id) ? 'checked' : ''} aria-label="Selecionar ${esc(r.comum_nome)}"></td><td><strong>${esc(r.nome || 'Conferência por comum')}</strong><small>${esc(r.comum_nome)} · ${esc(r.municipio)}</small></td><td>${esc(r.motivo)}</td><td>${esc(r.origem)}<small>${esc(r.lote || 'Manual / legado')}</small></td><td class="justification-actions-cell"><div class="justification-row-actions"><button class="btn btn-sm btn-outline-primary" data-view="${esc(r.id)}" type="button" title="Visualizar justificativa" aria-label="Visualizar justificativa"><i class="fa fa-eye" aria-hidden="true"></i></button><button class="btn btn-sm btn-outline-warning" data-edit="${esc(r.id)}" type="button" title="Editar justificativa" aria-label="Editar justificativa"><i class="fa fa-pen" aria-hidden="true"></i></button><button class="btn btn-sm btn-outline-danger" data-delete="${esc(r.id)}" type="button" title="Excluir justificativa" aria-label="Excluir justificativa"><i class="fa fa-trash" aria-hidden="true"></i></button></div></td></tr>`).join('') || '<tr><td colspan="5">Nenhuma justificativa neste evento e lote.</td></tr>';
    selectionState();
  }
  async function loadSaved() {
    const event = $('event').value;
    if (listedEvent !== event) { $('lot').innerHTML = '<option value="">Todos os lotes deste evento</option>'; listedEvent = event; }
    saved = []; selected.clear(); renderSaved();
    if (!event) { $('event-reading').textContent = 'Selecione um evento para visualizar as justificativas.'; return; }
    const result = await post('listar', {});
    if ($('event').value !== event) return;
    saved = result.items;
    const lots = new Map(saved.map(r => [r.lote || 'manual', `${r.origem} · ${r.lote || 'Manual / legado'}`]));
    const current = $('lot').value;
    $('lot').innerHTML = '<option value="">Todos os lotes deste evento</option>' + [...lots].map(([value,label]) => `<option value="${esc(value)}">${esc(label)}</option>`).join('');
    if (lots.has(current)) $('lot').value = current;
    $('event-reading').textContent = `${result.evento.titulo} · ${result.evento.data_evento.split('-').reverse().join('/')} · ${saved.length} justificativa(s). Somente registros vinculados a este evento.`;
    renderSaved();
  }
  function showEditor(ids, readOnly = false) {
    const rows = saved.filter(r => ids.includes(r.id));
    if (!rows.length) return;
    editorIds = rows.map(r => r.id);
    const event = eventItems.find(item => item.id === $('event').value);
    const detailCard = (icon, label, value, extra = '') => `<article class="justification-detail-card"><i class="fa ${icon}" aria-hidden="true"></i><div><span>${esc(label)}</span><strong>${esc(value || 'Não informado')}</strong>${extra ? `<small>${esc(extra)}</small>` : ''}</div></article>`;
    const eventCard = `<div class="justification-event-card"><i class="fa fa-calendar-check" aria-hidden="true"></i><div><span>Evento</span><strong>${esc(event?.titulo || $('event').selectedOptions[0]?.textContent || 'Evento selecionado')}</strong><small>${esc(event?.data_evento ? event.data_evento.split('-').reverse().join('/') : '')}</small></div><b>Justificou</b></div>`;
    const cards = rows.map(row => {
      if (rows.length > 1) return `<article class="justification-batch-card"><div><strong>${esc(row.nome || 'Encarregado não informado')}</strong><small>${esc(row.comum_nome)} · ${esc(row.municipio)}</small></div><p><span>Motivo</span>${esc(row.motivo || 'Não informado')}</p></article>`;
      return `<div class="justification-detail-grid">${detailCard('fa-user', 'Encarregado', row.nome)}
        ${detailCard('fa-location-dot', 'Comum', row.comum_nome, row.municipio)}
        ${detailCard('fa-file-lines', 'Arquivo de origem', row.origem, `Bloco: ${row.bloco || 'Manual / legado'}`)}</div>
        <p class="justification-record-audit">Registrado por <strong>${esc(row.created_by_name || 'Não informado')}</strong> · Última alteração por <strong>${esc(row.updated_by_name || 'Não informado')}</strong></p>`;
    }).join('');
    editor.querySelector('#just-detail').innerHTML = eventCard + cards;
    editor.querySelector('.modal-title').textContent = `${readOnly ? 'Visualizar' : 'Editar'} justificativa${rows.length > 1 ? 's' : ''}`;
    editor.querySelector('#just-dialog-caption').textContent = rows.length > 1
      ? `${rows.length} registros selecionados${readOnly ? '.' : ' · O motivo informado será aplicado a todos.'}`
      : readOnly ? 'Confira o encarregado, a comum e a origem deste registro.' : 'Altere os dados desta justificativa.';
    editor.querySelector('#just-edit-person').hidden = readOnly || rows.length !== 1;
    editor.querySelector('#just-edit-name').value = rows.length === 1 ? rows[0].nome : '';
    const reason = editor.querySelector('#just-edit-reason'); reason.value = rows.length === 1 ? rows[0].motivo : ''; reason.readOnly = readOnly;
    editor.querySelector('#just-edit-save').hidden = readOnly;
    editor.querySelector('#just-reason-wrap').hidden = readOnly && rows.length > 1;
    bootstrap.Modal.getOrCreateInstance(editor).show();
  }
  async function remove(ids, button) {
    const eventName = $('event').selectedOptions[0]?.textContent || '';
    const confirmed = await window.AppFeedback.confirm({title:'Excluir justificativas?', message:`Excluir ${ids.length} justificativa(s) de ${eventName}? O relatório deixará de considerar essas justificativas.`, confirmText:'Excluir justificativas'});
    if (!confirmed) return;
    await run(button, async () => {
      const result = await post('excluir', {ids, lote:$('lot').value === 'manual' ? '' : $('lot').value});
      await Promise.all([loadSaved(), window.MusicEventsDashboard.refresh()]);
      notify(`${result.alterados} justificativa(s) excluída(s) deste evento.`, 'success');
    });
  }
  $('lot').onchange = () => { selected.clear(); renderSaved(); };
  $('select-all').onchange = e => { visibleRows().forEach(r => e.target.checked ? selected.add(r.id) : selected.delete(r.id)); renderSaved(); };
  $('saved').onchange = e => { const id = e.target.dataset.pick; if (id) { e.target.checked ? selected.add(id) : selected.delete(id); selectionState(); } };
  $('saved').onclick = e => { const b = e.target.closest('button'); if (!b) return; if (b.dataset.view) showEditor([b.dataset.view], true); if (b.dataset.edit) showEditor([b.dataset.edit]); if (b.dataset.delete) remove([b.dataset.delete], $('reload')); };
  $('edit-selected').onclick = () => showEditor([...selected]);
  $('view-selected').onclick = () => showEditor([...selected], true);
  $('delete-selected').onclick = () => remove([...selected], $('delete-selected'));
  $('reload').onclick = () => run($('reload'), loadSaved);
  editor.querySelector('form').onsubmit = e => { e.preventDefault(); run(editor.querySelector('#just-edit-save'), async () => {
    const enteredName = editor.querySelector('#just-edit-name').value.trim();
    const originalName = saved.find(r => r.id === editorIds[0])?.nome || '';
    const result = await post('editar', {ids:editorIds, nome:editorIds.length === 1 && enteredName !== originalName ? enteredName : undefined, motivo:editor.querySelector('#just-edit-reason').value, lote:$('lot').value === 'manual' ? '' : $('lot').value});
    bootstrap.Modal.getOrCreateInstance(editor).hide();
    await Promise.all([loadSaved(), window.MusicEventsDashboard.refresh()]);
    notify(`${result.alterados} justificativa(s) atualizada(s).`, 'success');
  }); };
  $('register').onclick = () => run($('register'), async () => {
    const result = await post('cadastro', {});
    registrationCommons = result.comuns;
    if (!registrationCommons.length) throw Error('Nenhum encarregado local foi identificado no cadastro. Confira o cadastro de encarregados antes de registrar.');
    registerModal.dataset.eventId = $('event').value;
    registerModal.querySelector('.justification-register-event').textContent = $('event').selectedOptions[0].textContent;
    registerModal.querySelector('#just-new-common').innerHTML = '<option value="">Selecione a comum</option>' + registrationCommons.map(c => `<option value="${esc(c.id)}">${esc(c.municipio)} · ${esc(c.comum)}</option>`).join('');
    registerModal.querySelector('#just-new-person').innerHTML = '<option value="">Selecione primeiro a comum</option>';
    registerModal.querySelector('#just-new-city').textContent = '';
    registerModal.querySelector('#just-new-reason').value = '';
    bootstrap.Modal.getOrCreateInstance(registerModal).show();
  });
  registerModal.querySelector('#just-new-common').onchange = e => {
    const common = registrationCommons.find(c => c.id === e.target.value);
    registerModal.querySelector('#just-new-city').textContent = common ? `Município: ${common.municipio}` : '';
    registerModal.querySelector('#just-new-person').innerHTML = '<option value="">Selecione o encarregado</option>' + (common?.encarregados || []).map(name => `<option value="${esc(name)}">${esc(name)}</option>`).join('');
    if (common?.encarregados.length === 1) registerModal.querySelector('#just-new-person').value = common.encarregados[0];
  };
  registerModal.querySelector('form').onsubmit = e => { e.preventDefault(); run(registerModal.querySelector('#just-new-save'), async () => {
    if (registerModal.dataset.eventId !== $('event').value) throw Error('O evento selecionado mudou. Reabra o cadastro para conferir o vínculo.');
    await post('registrar', {comum_chave: registerModal.querySelector('#just-new-common').value, nome:registerModal.querySelector('#just-new-person').value, motivo:registerModal.querySelector('#just-new-reason').value});
    bootstrap.Modal.getOrCreateInstance(registerModal).hide();
    await Promise.all([loadSaved(), window.MusicEventsDashboard.refresh()]);
    notify('Justificativa registrada neste evento.', 'success');
  }); };
  updateControls();
})();
