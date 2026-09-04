(() => {
  const root = document.querySelector('#activity-workspace');
  if (!root) return;

  const mode = root.dataset.mode;
  const reportUser = root.dataset.reportUser || 'Usuário do Sistema';
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const norm = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toUpperCase();
  const number = value => Number(value) || 0;
  const iso = value => String(value || '').slice(0, 10);
  const dateLabel = value => value ? new Date(`${iso(value)}T12:00:00`).toLocaleDateString('pt-BR') : '—';
  const aggregateAttendance = row => number(row.meninos_presentes) + number(row.meninas_presentes) + number(row.instrutores_presentes) + number(row.colaboradores_presentes) + number(row.coordenadores_presentes);
  const csrf = () => document.cookie.split('; ').find(item => item.startsWith('csrftoken='))?.split('=')[1] || '';
  const monthNames = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
  const state = { aulas: [], polos: [], criancas: [], instrutores: [], presencas: [], municipios: [], selected: null };

  const filters = {
    month: $('#activity-month'), from: $('#activity-from'), to: $('#activity-to'),
    city: $('#activity-city'), polo: $('#activity-polo')
  };
  const multi = window.MusicMultiSelect;
  multi.setupAll(root);

  function feedback(title, text, icon = 'success') {
    return Promise.resolve(AppFeedback.show({
      type: icon === 'success' ? 'success' : icon === 'warning' ? 'warning' : 'error',
      title,
      message: text,
      duration: icon === 'success' ? 4600 : 6000
    }));
  }

  function setOptions(select, values, placeholder) {
    multi.setOptions(select, values, placeholder);
  }

  function unique(values) {
    return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, 'pt-BR'));
  }

  function poloName(row) { return row.nome_polo || row.polo || ''; }
  function poloCity(row) { return row.localidade || row.cidade || ''; }

  function syncFilters(firstLoad = false) {
    const cities = unique([...state.municipios, ...state.polos.map(poloCity), ...state.aulas.map(row => row.cidade)]);
    setOptions(filters.city, cities, 'Todos os municípios');
    const polos = unique(state.polos.filter(row => multi.matches(filters.city, poloCity(row))).map(poloName));
    setOptions(filters.polo, polos, 'Todos os polos');
    const months = unique(state.aulas.map(row => iso(row.data_aula).slice(0, 7))).sort().reverse();
    const monthSelected = filters.month.value;
    filters.month.innerHTML = '<option value="">Todos os meses</option>' + months.map(key => {
      const [year, month] = key.split('-');
      return `<option value="${key}">${monthNames[Number(month) - 1]} de ${year}</option>`;
    }).join('');
    if (months.includes(monthSelected)) filters.month.value = monthSelected;
    if (firstLoad) {
      const query = new URLSearchParams(location.search);
      const queryCities = query.getAll('municipio');
      const queryPolos = query.getAll('polo');
      multi.setValues(filters.city, queryCities);
      const availablePolos = unique(state.polos.filter(row => multi.matches(filters.city, poloCity(row))).map(poloName));
      setOptions(filters.polo, availablePolos, 'Todos os polos');
      multi.setValues(filters.polo, queryPolos);
    }
  }

  function filteredAulas() {
    return state.aulas.filter(row => {
      const activityDate = iso(row.data_aula);
      return (!filters.month.value || activityDate.startsWith(filters.month.value)) &&
        (!filters.from.value || activityDate >= filters.from.value) &&
        (!filters.to.value || activityDate <= filters.to.value) &&
        multi.matches(filters.city, row.cidade) &&
        multi.matches(filters.polo, row.polo);
    }).sort((a, b) => iso(b.data_aula).localeCompare(iso(a.data_aula)));
  }

  function kpi(label, value, note, icon, tone, tint) {
    return `<article class="activity-kpi" style="--tone:${tone};--tint:${tint}"><div class="activity-kpi-head"><div class="activity-kpi-icon"><i class="fa ${icon}"></i></div><div class="activity-kpi-label">${esc(label)}</div></div><div class="activity-kpi-value">${esc(value)}</div><div class="activity-kpi-note">${esc(note)}</div></article>`;
  }

  function metrics(rows) {
    const attendance = rows.reduce((sum, row) => sum + number(row.meninos_presentes) + number(row.meninas_presentes), 0);
    const team = rows.reduce((sum, row) => sum + number(row.instrutores_presentes) + number(row.colaboradores_presentes) + number(row.coordenadores_presentes), 0);
    const activePolos = new Set(rows.map(row => norm(row.polo)).filter(Boolean)).size;
    const catalog = state.polos.filter(row => multi.matches(filters.city, poloCity(row))).filter(row => multi.matches(filters.polo, poloName(row)));
    const coverage = catalog.length ? Math.round(activePolos / catalog.length * 100) : 0;
    return { launches: rows.length, attendance, team, average: rows.length ? Math.round(attendance / rows.length * 10) / 10 : 0, coverage, activePolos, catalog: catalog.length };
  }

  function operationalRows() {
    const today = new Date(); today.setHours(12, 0, 0, 0);
    const catalog = state.polos.filter(row => multi.matches(filters.city, poloCity(row))).filter(row => multi.matches(filters.polo, poloName(row)));
    return catalog.map(polo => {
      const name = poloName(polo);
      const launches = state.aulas.filter(row => norm(row.polo) === norm(name)).sort((a, b) => iso(b.data_aula).localeCompare(iso(a.data_aula)));
      const latest = launches[0];
      let days = null, status = 'SEM HISTÓRICO', tone = 'empty', detail = 'Nenhuma atividade registrada';
      if (latest) {
        const last = new Date(`${iso(latest.data_aula)}T12:00:00`);
        days = Math.max(0, Math.floor((today - last) / 86400000));
        if (days <= 7) { status = 'EM DIA'; tone = 'ok'; detail = days === 0 ? 'Enviado hoje' : `Enviado há ${days} dia${days === 1 ? '' : 's'}`; }
        else if (days <= 14) { status = 'ATENÇÃO'; tone = 'attention'; detail = `${days} dias sem novo diário`; }
        else { status = 'ATRASADO'; tone = 'late'; detail = `${days} dias sem novo diário`; }
      }
      return {polo, name, city:poloCity(polo), latest, days, status, tone, detail, total:launches.length};
    }).sort((a, b) => ({late:0,empty:1,attention:2,ok:3}[a.tone] - {late:0,empty:1,attention:2,ok:3}[b.tone]) || a.name.localeCompare(b.name, 'pt-BR'));
  }

  function renderKpis(rows) {
    const m = metrics(rows);
    $('#activity-kpis').innerHTML = mode === 'aulas'
      ? kpi('Diários lançados', m.launches, 'Atividades no recorte selecionado', 'fa-book-open', '#2f8de4', '#eaf4ff') +
        kpi('Presenças', m.attendance, 'Meninos e meninas registrados', 'fa-children', '#10a590', '#e8f8f4') +
        kpi('Média por aula', m.average, 'Participantes por lançamento', 'fa-chart-line', '#7b61d1', '#f0edff') +
        kpi('Cobertura de polos', `${m.coverage}%`, `${m.activePolos} de ${m.catalog} polos com lançamento`, 'fa-map-location-dot', '#f39c12', '#fff4df')
      : kpi('Atividades', m.launches, 'Lançamentos encontrados', 'fa-clock-rotate-left', '#2f8de4', '#eaf4ff') +
        kpi('Participações', m.attendance, 'Presenças acumuladas', 'fa-user-check', '#10a590', '#e8f8f4') +
        kpi('Equipe presente', m.team, 'Participações da equipe', 'fa-user-graduate', '#7b61d1', '#f0edff') +
        kpi('Média por aula', m.average, 'Crianças por atividade', 'fa-chart-column', '#f39c12', '#fff4df');
    $('#activity-executive-text').textContent = `${m.launches} atividades, ${m.attendance} presenças, média de ${m.average} crianças por aula e ${m.activePolos} polos com lançamentos no recorte.`;
  }

  function actionButtons(row, history = false) {
    return `<div class="history-row-actions"><button class="btn btn-sm btn-outline-theme" data-activity-action="attendance" data-id="${row.id}" title="Frequência"><i class="fa fa-user-check"></i>${history ? '<span class="ms-1">Frequência</span>' : ''}</button><button class="btn btn-sm btn-outline-primary" data-activity-action="details" data-id="${row.id}" title="Detalhes"><i class="fa fa-eye"></i></button><button class="btn btn-sm btn-outline-warning" data-activity-action="edit" data-id="${row.id}" title="Editar"><i class="fa fa-pen"></i></button><button class="btn btn-sm btn-outline-danger" data-activity-action="delete" data-id="${row.id}" title="Excluir"><i class="fa fa-trash"></i></button></div>`;
  }

  function genderBadges(row) {
    return `<div class="activity-gender-counts"><span class="activity-gender-badge activity-gender-boys" title="Meninos"><i class="fa fa-child-reaching"></i>${number(row.meninos_presentes)}</span><span class="activity-gender-badge activity-gender-girls" title="Meninas"><i class="fa fa-child-dress"></i>${number(row.meninas_presentes)}</span></div>`;
  }

  function launchesTable(rows, limit = null) {
    const list = limit ? rows.slice(0, limit) : rows;
    if (!list.length) return '<div class="history-empty"><i class="fa fa-calendar-xmark"></i>Nenhum lançamento encontrado neste recorte.</div>';
    return `<div class="table-responsive"><table class="table activity-table"><thead><tr><th>Data</th><th>Município</th><th>Polo</th><th>Atividade</th><th>Lançado por</th><th class="text-center">Meninos / Meninas</th><th class="text-center">Equipe</th><th class="text-end">Ações</th></tr></thead><tbody>${list.map(row => `<tr><td><strong>${dateLabel(row.data_aula)}</strong><span class="activity-small">${esc(row.ciclo || 'Ciclo não informado')}</span></td><td>${esc(row.cidade || '—')}</td><td><span class="activity-polo-name">${esc(row.polo || '—')}</span></td><td>${esc(row.nome_atividade || (row.numero_aula ? `Atividade ${row.numero_aula}` : '—'))}</td><td><strong>${esc(row.created_by_name || 'Não identificado')}</strong><span class="activity-small">${row.created_by_name ? 'Responsável pelo lançamento' : 'Registro anterior à auditoria'}</span></td><td class="text-center">${genderBadges(row)}</td><td class="text-center">${number(row.instrutores_presentes) + number(row.colaboradores_presentes) + number(row.coordenadores_presentes)}</td><td>${actionButtons(row)}</td></tr>`).join('')}</tbody></table></div>`;
  }

  function renderOperations(rows) {
    const operations = operationalRows();
    const counts = {ok:0,attention:0,late:0,empty:0}; operations.forEach(row => counts[row.tone]++);
    const alerts = counts.attention + counts.late + counts.empty;
    $('#activity-content').innerHTML = `<div class="activity-alert ${alerts ? '' : 'success'}"><i class="fa ${alerts ? 'fa-bell' : 'fa-circle-check'}"></i><div><strong>${alerts ? 'Alerta operacional:' : 'Operação em dia:'}</strong> ${alerts ? `${alerts} polo(s) exigem atenção — ${counts.late} atrasado(s), ${counts.attention} em atenção e ${counts.empty} sem histórico.` : 'Todos os polos do recorte possuem lançamento recente.'}</div></div>
      <section class="activity-section"><div class="activity-section-head"><div><h3 class="activity-section-title">Acompanhamento operacional dos polos</h3><div class="activity-section-subtitle">Situação calculada pelo último diário: em dia até 7 dias, atenção de 8 a 14 e atrasado acima de 14 dias.</div></div><span class="activity-count-pill">${operations.length} polos</span></div><div class="activity-section-body"><div class="activity-status-strip"><div class="activity-status-card"><span>Polos cadastrados</span><strong>${operations.length}</strong></div><div class="activity-status-card"><span>Em dia</span><strong class="text-success">${counts.ok}</strong></div><div class="activity-status-card"><span>Atenção / atrasados</span><strong class="text-warning">${counts.attention + counts.late}</strong></div><div class="activity-status-card"><span>Sem histórico</span><strong class="text-danger">${counts.empty}</strong></div></div><div class="table-responsive"><table class="table activity-table"><thead><tr><th>Polo</th><th>Município</th><th>Última atividade</th><th>Status</th><th class="text-center">Lançamentos</th><th class="text-end">Ações</th></tr></thead><tbody>${operations.map(item => `<tr><td><span class="activity-polo-name">${esc(item.name)}</span></td><td>${esc(item.city || '—')}</td><td><strong>${item.latest ? dateLabel(item.latest.data_aula) : '—'}</strong><span class="activity-small">${esc(item.detail)}</span></td><td><span class="activity-status-badge activity-status-${item.tone}">${item.status}</span></td><td class="text-center">${item.total}</td><td class="text-end"><button class="btn btn-sm btn-outline-theme" data-activity-action="view-polo" data-polo="${esc(item.name)}"><i class="fa fa-list me-1"></i>Ver lançamentos</button></td></tr>`).join('') || '<tr><td colspan="6" class="text-center text-muted py-4">Nenhum polo neste recorte.</td></tr>'}</tbody></table></div></div></section>
      <section class="activity-section"><div class="activity-section-head"><div><h3 class="activity-section-title">Lançamentos do período</h3><div class="activity-section-subtitle">Diários mais recentes conforme os filtros selecionados.</div></div><span class="activity-count-pill">${rows.length} atividades</span></div><div class="activity-section-body p-0">${launchesTable(rows, 15)}</div></section>`;
  }

  function groupHistory(rows) {
    const cities = new Map();
    rows.forEach(row => {
      const cityName = row.cidade || 'Município não informado';
      const poloNameValue = row.polo || 'Polo não informado';
      const monthKey = iso(row.data_aula).slice(0, 7) || 'sem-data';
      if (!cities.has(cityName)) cities.set(cityName, new Map());
      const polos = cities.get(cityName);
      if (!polos.has(poloNameValue)) polos.set(poloNameValue, new Map());
      const months = polos.get(poloNameValue);
      if (!months.has(monthKey)) months.set(monthKey, []);
      months.get(monthKey).push(row);
    });
    return cities;
  }

  function renderHistory(rows) {
    const groups = groupHistory(rows);
    let cityIndex = 0;
    const html = [...groups.entries()].sort((a,b)=>a[0].localeCompare(b[0],'pt-BR')).map(([city, polos]) => {
      const cityId = `history-city-${cityIndex++}`;
      const cityTotal = [...polos.values()].reduce((sum, months) => sum + [...months.values()].reduce((subtotal, list) => subtotal + list.length, 0), 0);
      let poloIndex = 0;
      const poloHtml = [...polos.entries()].sort((a,b)=>a[0].localeCompare(b[0],'pt-BR')).map(([polo, months]) => {
        const poloId = `${cityId}-polo-${poloIndex++}`;
        const poloTotal = [...months.values()].reduce((sum, list) => sum + list.length, 0);
        let monthIndex = 0;
        const monthHtml = [...months.entries()].sort((a,b)=>b[0].localeCompare(a[0])).map(([monthKey, items]) => {
          const monthId = `${poloId}-month-${monthIndex++}`;
          const [year, month] = monthKey.split('-');
          const monthLabel = monthKey === 'sem-data' ? 'Data não informada' : `${monthNames[Number(month)-1]} de ${year}`;
          return `<div class="history-month"><button class="history-month-head" data-collapse-target="${monthId}"><span class="history-month-title"><i class="fa fa-calendar me-2"></i>${esc(monthLabel)}</span><span>${items.length} <i class="fa fa-chevron-down ms-1"></i></span></button><div class="history-month-body" id="${monthId}"><div class="table-responsive"><table class="table activity-table"><thead><tr><th>Status</th><th>Ciclo</th><th>Atividade</th><th>Data</th><th>Lançado por</th><th class="text-center">Meninos / Meninas</th><th class="text-end">Ações</th></tr></thead><tbody>${items.map(row => `<tr><td><span class="activity-status-badge activity-status-ok">CONCLUÍDA</span></td><td>${esc(row.ciclo || '—')}</td><td>${esc(row.nome_atividade || (row.numero_aula ? `Atividade ${row.numero_aula}` : '—'))}</td><td>${dateLabel(row.data_aula)}</td><td><strong>${esc(row.created_by_name || 'Não identificado')}</strong><span class="activity-small">${row.created_by_name ? 'Responsável pelo lançamento' : 'Registro anterior à auditoria'}</span></td><td class="text-center">${genderBadges(row)}</td><td>${actionButtons(row, true)}</td></tr>`).join('')}</tbody></table></div></div></div>`;
        }).join('');
        return `<div class="history-polo"><button class="history-polo-head" data-collapse-target="${poloId}"><span class="history-polo-title"><i class="fa fa-building me-2"></i>${esc(polo)}</span><span>${poloTotal} <i class="fa fa-minus-square ms-1"></i></span></button><div class="history-polo-body" id="${poloId}">${monthHtml}</div></div>`;
      }).join('');
      return `<div class="history-city"><button class="history-city-head" data-collapse-target="${cityId}"><span class="history-city-title"><i class="fa fa-location-dot me-2"></i>${esc(city)}</span><span><span class="history-city-count">${cityTotal} atividades</span><i class="fa fa-chevron-up ms-2"></i></span></button><div class="history-city-body" id="${cityId}">${poloHtml}</div></div>`;
    }).join('');
    $('#activity-content').innerHTML = `<section class="activity-section"><div class="activity-section-head"><div><h3 class="activity-section-title">Histórico de atividades</h3><div class="activity-section-subtitle">Navegue por município, polo e mês para consultar frequência, detalhes ou editar um lançamento.</div></div><span class="activity-count-pill">${rows.length} atividades</span></div><div class="activity-section-body">${html || '<div class="history-empty"><i class="fa fa-folder-open"></i>Nenhuma atividade encontrada neste recorte.</div>'}</div></section>`;
  }

  function render() {
    const rows = filteredAulas();
    renderKpis(rows);
    if (mode === 'aulas') renderOperations(rows); else renderHistory(rows);
  }

  function setupEntryOptions(selectedCity = '', selectedPolo = '') {
    const citySelect = $('#entry-city'), poloSelect = $('#entry-polo');
    const cities = unique([...state.municipios, ...state.polos.map(poloCity)]);
    citySelect.innerHTML = '<option value="">Selecione</option>' + cities.map(city => `<option value="${esc(city)}">${esc(city)}</option>`).join('');
    if (selectedCity) citySelect.value = cities.find(city => norm(city) === norm(selectedCity)) || '';
    const polos = unique(state.polos.filter(row => !citySelect.value || norm(poloCity(row)) === norm(citySelect.value)).map(poloName));
    poloSelect.innerHTML = '<option value="">Selecione</option>' + polos.map(polo => `<option value="${esc(polo)}">${esc(polo)}</option>`).join('');
    if (selectedPolo) poloSelect.value = polos.find(polo => norm(polo) === norm(selectedPolo)) || '';
  }

  function openEntry(row = null) {
    state.selected = row;
    $('#activity-entry-title').textContent = row ? 'Editar lançamento' : 'Novo lançamento';
    const selectedCity = multi.values(filters.city), selectedPolo = multi.values(filters.polo);
    setupEntryOptions(row?.cidade || (selectedCity.length === 1 ? selectedCity[0] : ''), row?.polo || (selectedPolo.length === 1 ? selectedPolo[0] : ''));
    document.querySelectorAll('.activity-entry').forEach(input => {
      const field = input.dataset.field;
      let value = row?.[field] ?? '';
      if (input.type === 'number' && value === '') value = 0;
      if (!row && field === 'data_aula') value = new Date().toISOString().slice(0,10);
      if (!row && field === 'ciclo') value = 'Ciclo 1';
      if (!row && field === 'cidade') value = selectedCity.length === 1 ? selectedCity[0] : '';
      if (!row && field === 'polo') value = selectedPolo.length === 1 ? selectedPolo[0] : '';
      input.value = value;
    });
    bootstrap.Modal.getOrCreateInstance($('#activity-entry-modal')).show();
  }

  async function saveEntry() {
    const form = $('#activity-entry-form');
    if (!form.reportValidity()) return;
    const button = $('#activity-save'), original = button.innerHTML;
    button.disabled = true; button.innerHTML = '<i class="fa fa-spinner fa-spin me-1"></i>Salvando…';
    try {
      const payload = {};
      document.querySelectorAll('.activity-entry').forEach(input => payload[input.dataset.field] = input.type === 'number' ? number(input.value) : input.value.trim());
      const url = state.selected ? `/musicalizacao/api/aulas/${state.selected.id}/` : '/musicalizacao/api/aulas/';
      const response = await fetch(url, {method:state.selected?'PATCH':'POST', headers:{'Content-Type':'application/json','X-CSRFToken':csrf()}, body:JSON.stringify(payload)});
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || 'Não foi possível salvar o lançamento.');
      bootstrap.Modal.getInstance($('#activity-entry-modal'))?.hide();
      await feedback('Salvo com sucesso!', state.selected ? 'O lançamento foi atualizado.' : 'O novo lançamento foi registrado.', 'success');
      await load();
    } catch (exception) { feedback('Não foi possível salvar', exception.message, 'error'); }
    finally { button.disabled = false; button.innerHTML = original; }
  }

  function showDetails(row) {
    $('#activity-details-subtitle').textContent = `${row.polo || 'Polo não informado'} · ${dateLabel(row.data_aula)}`;
    const items = [['Município',row.cidade],['Polo',row.polo],['Data',dateLabel(row.data_aula)],['Ciclo',row.ciclo],['Número da aula',row.numero_aula],['Atividade',row.nome_atividade],['Lançado por',row.created_by_name||'Não identificado (registro legado)'],['Última alteração por',row.updated_by_name||row.created_by_name||'Não identificado'],['Meninos',number(row.meninos_presentes)],['Meninas',number(row.meninas_presentes)],['Instrutores',number(row.instrutores_presentes)],['Colaboradores',number(row.colaboradores_presentes)],['Coordenação',number(row.coordenadores_presentes)],['Observações',row.observacoes]];
    $('#activity-details-body').innerHTML = `<h6 class="fw-bold text-muted mb-3">Resumo da atividade</h6><div class="activity-modal-summary"><div class="activity-modal-metric activity-detail-children"><strong>${number(row.meninos_presentes)+number(row.meninas_presentes)}</strong><span>Crianças</span></div><div class="activity-modal-metric activity-detail-team"><strong>${number(row.instrutores_presentes)+number(row.colaboradores_presentes)+number(row.coordenadores_presentes)}</strong><span>Equipe</span></div><div class="activity-modal-metric activity-detail-total"><strong>${number(row.meninos_presentes)+number(row.meninas_presentes)+number(row.instrutores_presentes)+number(row.colaboradores_presentes)+number(row.coordenadores_presentes)}</strong><span>Total</span></div></div><div class="activity-detail-list">${items.map(([label,value])=>`<div class="activity-detail-item"><span>${esc(label)}</span><strong>${esc(value || value === 0 ? value : '—')}</strong></div>`).join('')}</div>`;
    bootstrap.Modal.getOrCreateInstance($('#activity-details-modal')).show();
  }

  function showAttendance(row) {
    const calls = state.presencas.filter(item => String(item.aula_id) === String(row.id));
    // Um diário zerado e sem qualquer chamada individual registra que a atividade
    // não aconteceu. Nesse caso, ausência não pode ser inferida pela lista do polo.
    const activityNotHeld = calls.length === 0 && aggregateAttendance(row) === 0;
    const callByParticipant = new Map();
    calls.forEach(call => {
      const key = call.colaborador_id ? `staff:${call.colaborador_id}` : `child:${call.aluno_id}`;
      callByParticipant.set(key, call);
    });

    const children = state.criancas
      .filter(child => norm(child.status) !== 'INATIVO' && norm(child.polo_participacao) === norm(row.polo))
      .map(child => ({key:`child:${child.id}`, name:child.nome_crianca, role:'Aluno(a)', group:0}))
      .sort((a,b)=>String(a.name).localeCompare(String(b.name),'pt-BR'));
    const staff = (state.instrutores || [])
      .filter(person => norm(person.status) !== 'INATIVO' && norm(person.polo_auxilio || person.comum_congregacao) === norm(row.polo))
      .map(person => {
        const coordinator = norm(person.role).includes('COORDEN');
        return {key:`staff:${person.id}`, name:person.nome_completo, role:coordinator?'Coordenador (a)':'Monitora', group:coordinator?2:1};
      })
      .sort((a,b)=>a.group-b.group||String(a.name).localeCompare(String(b.name),'pt-BR'));
    const participants = [...children, ...staff];

    let monitorsToRecover = number(row.colaboradores_presentes);
    let coordinatorsToRecover = number(row.coordenadores_presentes);
    staff.forEach(person => {
      const saved = callByParticipant.get(person.key);
      if (saved && (saved.presente === true || norm(saved.status) === 'PRESENTE')) {
        if (person.group === 2) coordinatorsToRecover--; else monitorsToRecover--;
      }
    });

    const attendance = participants.map(person => {
      const saved = callByParticipant.get(person.key);
      let status = activityNotHeld ? 'Não se aplica' : 'Faltou';
      let tone = activityNotHeld ? 'empty' : 'late';
      let observation = activityNotHeld ? 'Atividade não realizada; nenhuma falta atribuída.' : (saved?.observacoes || '');
      if (norm(observation).startsWith('PRESENCA RECUPERADA DO LANCAMENTO ORIGINAL DA ATIVIDADE')) observation = '';
      if (!activityNotHeld && saved && norm(saved.status).includes('JUSTIFIC')) { status='Justificado'; tone='attention'; }
      else if (saved && (saved.presente === true || norm(saved.status) === 'PRESENTE')) { status='Presente'; tone='ok'; }
      else if (!activityNotHeld && !saved && person.group === 2 && coordinatorsToRecover > 0) { status='Presente'; tone='ok'; coordinatorsToRecover--; }
      else if (!activityNotHeld && !saved && person.group === 1 && monitorsToRecover > 0) { status='Presente'; tone='ok'; monitorsToRecover--; }
      return {...person,status,tone,observation};
    });

    const totals = {
      present: attendance.filter(item=>item.status==='Presente').length,
      absent: attendance.filter(item=>item.status==='Faltou').length,
      justified: attendance.filter(item=>item.status==='Justificado').length
    };
    $('#activity-attendance-subtitle').textContent = `Polo: ${row.polo || 'não informado'} | Data: ${dateLabel(row.data_aula)}`;
    let previousGroup = 0;
    const rowsHtml = attendance.map((item,index)=>{
      let groupHeader='';
      if(item.group>0&&item.group!==previousGroup){
        const coordination=item.group===2;
        groupHeader=`<tr class="attendance-group-row"><td colspan="5"><i class="fa ${coordination?'fa-star':'fa-users'} me-2"></i>${coordination?'Coordenação':'Monitoras'}</td></tr>`;
      }
      previousGroup=item.group;
      return groupHeader+`<tr class="attendance-participant-row" data-attendance-search="${esc(norm(item.name+' '+item.role+' '+item.status))}"><td>${index+1}</td><td><strong>${esc(item.name||'Participante não identificado')}</strong></td><td><span class="activity-role-badge activity-role-${item.group===0?'child':item.group===2?'coordinator':'monitor'}">${esc(item.role)}</span></td><td><span class="activity-status-badge activity-status-${item.tone}">${esc(item.status)}</span></td><td><div class="activity-observation">${esc(item.observation||'—')}</div></td></tr>`;
    }).join('');
    const noActivityNotice = activityNotHeld ? `<div class="attendance-no-activity"><i class="fa fa-calendar-xmark"></i><div><strong>Não houve atividade nesta data.</strong><span>${esc(row.observacoes || 'Motivo não informado.')}</span><span>Nenhuma falta foi gerada.</span></div></div>` : '';
    $('#activity-attendance-body').innerHTML = `<h6 class="fw-bold text-muted mb-3">Resumo da frequência</h6>${noActivityNotice}<div class="activity-modal-summary"><div class="activity-modal-metric activity-metric-present"><strong>${totals.present}</strong><span>Presentes</span></div><div class="activity-modal-metric activity-metric-absent"><strong>${totals.absent}</strong><span>Faltas</span></div><div class="activity-modal-metric activity-metric-justified"><strong>${totals.justified}</strong><span>Justificados</span></div></div><div class="attendance-search"><i class="fa fa-search"></i><input class="form-control" id="attendance-search-input" placeholder="Pesquisar participante do polo…"></div><div class="table-responsive"><table class="table activity-table attendance-table"><thead><tr><th>#</th><th>Participante</th><th>Função</th><th>Status</th><th>Justificativa / Observação</th></tr></thead><tbody>${rowsHtml||'<tr><td colspan="5" class="text-center text-muted py-4">Nenhum participante cadastrado neste polo.</td></tr>'}</tbody></table></div>`;
    $('#attendance-search-input')?.addEventListener('input', event => {
      const query=norm(event.target.value);
      document.querySelectorAll('.attendance-participant-row').forEach(tableRow=>tableRow.hidden=!!query&&!tableRow.dataset.attendanceSearch.includes(query));
    });
    bootstrap.Modal.getOrCreateInstance($('#activity-attendance-modal')).show();
  }

  async function deleteEntry(row) {
    const activityDate = dateLabel(row.data_aula);
    const activityPolo = row.polo || 'polo não informado';
    const confirmed = await AppFeedback.confirm({
      title: 'Excluir lançamento?',
      message: `A atividade de ${activityDate} em ${activityPolo} será removida definitivamente.`,
      highlight: activityPolo,
      confirmText: 'Sim, excluir'
    });
    if (!confirmed) return;
    const notice = AppFeedback.show({
      type: 'loading',
      flow: 'delete',
      title: 'Excluindo lançamento',
      message: 'Aguarde enquanto a atividade é removida e o histórico é atualizado.'
    });
    try {
      const response = await fetch(`/musicalizacao/api/aulas/${row.id}/`, {method:'DELETE', headers:{'X-CSRFToken':csrf()}});
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || 'Falha ao excluir.');
      notice.close();
      await load();
      await feedback('Lançamento excluído', 'A atividade foi removida e os dados foram atualizados.', 'success');
    } catch (exception) {
      notice.close();
      feedback('Não foi possível excluir', exception.message, 'error');
    }
  }

  function exportRows() {
    return filteredAulas().map(row => [dateLabel(row.data_aula),row.cidade||'',row.polo||'',row.ciclo||'',row.numero_aula||'',row.nome_atividade||'',number(row.meninos_presentes),number(row.meninas_presentes),number(row.instrutores_presentes)+number(row.colaboradores_presentes)+number(row.coordenadores_presentes)]);
  }

  function exportExcel() {
    const data = [['Data','Município','Polo','Ciclo','Aula','Atividade','Meninos','Meninas','Equipe'],...exportRows()];
    const csv='\ufeff'+data.map(line=>line.map(value=>'"'+String(value).replaceAll('"','""')+'"').join(';')).join('\r\n');
    const link=document.createElement('a'); link.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'})); link.download=`Musicalizacao_${mode}_${new Date().toISOString().slice(0,10)}.csv`; link.click(); URL.revokeObjectURL(link.href);
  }

  function exportPdf() {
    if (!window.pdfMake) return feedback('PDF indisponível','O gerador de PDF não foi carregado.','error');
    const rows = exportRows();
    if (!rows.length) return feedback('Sem registros','Não há atividades neste recorte para exportar.','warning');
    const now = new Date(), pad = value => String(value).padStart(2, '0');
    const timestamp = `${pad(now.getDate())}/${pad(now.getMonth()+1)}/${now.getFullYear()} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
    const cities = multi.labels(filters.city, 'Todos os municípios'), polos = multi.labels(filters.polo, 'Todos os polos');
    const scope = `Municípios: ${cities} · Polos: ${polos}`;
    const title = mode === 'aulas' ? 'Relatório Operacional de Atividades' : 'Histórico de Atividades';
    const tableBody = [['Data','Município','Polo','Ciclo','Aula','Atividade','Meninos','Meninas','Equipe'].map(text => ({text,style:'tableHeader'})), ...rows];
    const definition = {pageSize:'A4',pageOrientation:'landscape',pageMargins:[28,100,28,34],header:(page,pageCount)=>({margin:[28,16,28,0],columns:[{width:210,text:''},{width:'*',stack:[{text:'CONGREGAÇÃO CRISTÃ NO BRASIL',style:'entityName'},{text:'Regional Itapevi - São Paulo',style:'entitySub'},{text:'MUSICALIZAÇÃO INFANTIL',style:'moduleName'},{text:title,style:'reportTitle'}]},{width:210,stack:[{text:`Página ${page} de ${pageCount}`,bold:true},{text:`Emissão: ${timestamp}`},{text:`Recorte: ${scope}`,fontSize:7},{text:`Responsável: ${reportUser}`,fontSize:7}],alignment:'right',fontSize:8}]}),footer:(page,pageCount)=>({margin:[28,5,28,0],columns:[{text:`Musicalização Infantil · ${rows.length} registros · ${scope}`,fontSize:7,color:'#6b7280'},{text:`Página ${page} de ${pageCount}`,alignment:'right',fontSize:7,color:'#6b7280'}]}),content:[{table:{widths:['*'],body:[[{text:`RECORTE DO RELATÓRIO • ${scope} • ${rows.length} REGISTROS`,fillColor:'#eaf2f8',color:'#1e4b7a',bold:true,fontSize:8,margin:[6,4,6,4]}]]},layout:'noBorders',margin:[0,0,0,8]},{table:{headerRows:1,dontBreakRows:true,widths:[45,62,105,48,34,'*',38,38,38],body:tableBody},layout:{fillColor:row=>row>0?(row%2?'#ffffff':'#f4f6f8'):null,hLineColor:()=>'#c8d1da',vLineColor:()=>'#d8dee5',hLineWidth:()=>.45,vLineWidth:()=>.35,paddingLeft:()=>4,paddingRight:()=>4,paddingTop:()=>4,paddingBottom:()=>4}}],styles:{entityName:{fontSize:15,bold:true,alignment:'center'},entitySub:{fontSize:9,alignment:'center'},moduleName:{fontSize:12,bold:true,color:'#1e4b7a',alignment:'center',margin:[0,5,0,0]},reportTitle:{fontSize:9,alignment:'center'},tableHeader:{color:'#ffffff',bold:true,alignment:'center',fillColor:'#1e4b7a',fontSize:7}},defaultStyle:{fontSize:7,color:'#263238'}};
    pdfMake.createPdf(definition).download(`Musicalizacao_${mode}_${pad(now.getDate())}-${pad(now.getMonth()+1)}-${now.getFullYear()}_${pad(now.getHours())}-${pad(now.getMinutes())}.pdf`);
  }

  async function load() {
    const content = $('#activity-content');
    content.innerHTML='<div class="activity-section"><div class="activity-loading"><i class="fa fa-circle-notch fa-spin"></i>Carregando dados operacionais…</div></div>';
    try {
      const [summaryResponse, activitiesResponse] = await Promise.all([fetch('/musicalizacao/api/resumo/',{cache:'no-store'}),fetch('/musicalizacao/api/aulas/',{cache:'no-store'})]);
      const [summary, activities] = await Promise.all([summaryResponse.json(),activitiesResponse.json()]);
      if (!summaryResponse.ok) throw new Error(summary.error || 'Não foi possível carregar os indicadores.');
      if (!activitiesResponse.ok) throw new Error(activities.error || 'Não foi possível carregar as atividades.');
      state.aulas=activities.items||[]; state.polos=summary.polos||[]; state.criancas=summary.criancas||[]; state.instrutores=summary.instrutores||[]; state.presencas=summary.presencas||[]; state.municipios=summary.municipios||[];
      syncFilters(!root.dataset.ready); root.dataset.ready='true'; render();
    } catch (exception) {
      content.innerHTML=`<div class="activity-section"><div class="history-empty"><i class="fa fa-triangle-exclamation text-danger"></i>${esc(exception.message)}</div></div>`;
      feedback('Não foi possível carregar', exception.message, 'error');
    }
  }

  Object.values(filters).forEach(control => control.addEventListener('change', () => {
    if (control === filters.city) { multi.clear(filters.polo); syncFilters(); }
    render();
  }));
  $('#activity-refresh').onclick=load;
  $('#activity-clear').onclick=()=>{multi.clear(filters.city);multi.clear(filters.polo);filters.month.value='';filters.from.value='';filters.to.value='';syncFilters();render()};
  $('#activity-excel').onclick=exportExcel;
  $('#activity-pdf').onclick=exportPdf;
  $('#activity-new')?.addEventListener('click',()=>openEntry());
  $('#activity-save').onclick=saveEntry;
  $('#entry-city').onchange=()=>setupEntryOptions($('#entry-city').value,'');
  $('#activity-content').addEventListener('click', event => {
    const collapse = event.target.closest('[data-collapse-target]');
    if (collapse) { const target=document.getElementById(collapse.dataset.collapseTarget); if(target)target.hidden=!target.hidden; return; }
    const button=event.target.closest('[data-activity-action]'); if(!button)return;
    if(button.dataset.activityAction==='view-polo'){multi.setValues(filters.polo,[button.dataset.polo]);render();document.querySelector('.activity-section:last-child')?.scrollIntoView({behavior:'smooth'});return;}
    const row=state.aulas.find(item=>String(item.id)===String(button.dataset.id)); if(!row)return;
    if(button.dataset.activityAction==='details')showDetails(row);
    if(button.dataset.activityAction==='attendance')showAttendance(row);
    if(button.dataset.activityAction==='edit')openEntry(row);
    if(button.dataset.activityAction==='delete')deleteEntry(row);
  });
  load();
})();
