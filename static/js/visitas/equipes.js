document.addEventListener('DOMContentLoaded', () => {
  const state = { atribuicoes: [], grupos: [] };
  const $ = (selector) => document.querySelector(selector);
  const modal = new bootstrap.Modal($('#equipe-modal'));
  const filtroComumCatalogo = Array.from($('#filtro-comum').options).slice(1).map((item) => ({value:item.value, municipio:item.dataset.municipio}));
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const csrf = () => document.cookie.split('; ').find((row) => row.startsWith('csrftoken='))?.split('=')[1] || '';

  function equipeCor(nome) {
    const numero = String(nome).match(/\d+/)?.[0];
    if (numero) return (Number(numero) - 1) % 8;
    return Array.from(String(nome)).reduce((total, caractere) => total + caractere.codePointAt(0), 0) % 8;
  }

  function alerta(message, type = 'danger') { $('#equipes-alerta').innerHTML = `<div class="alert alert-${type}">${escapeHtml(message)}</div>`; }
  function filtrarComuns(select, municipio, manter = '') {
    Array.from(select.options).forEach((item, index) => { if (index) item.hidden = Boolean(municipio && item.dataset.municipio !== municipio); });
    select.value = manter || ''; if (select.selectedOptions[0]?.hidden) select.value = '';
  }

  function configurarPesquisaComum(municipio, manter = '') {
    const select = $('#filtro-comum'), $select = jQuery(select);
    if ($select.hasClass('select2-hidden-accessible')) $select.select2('destroy');
    select.replaceChildren();
    const todas = document.createElement('option'); todas.value = ''; todas.textContent = 'Todas'; select.append(todas);
    filtroComumCatalogo.filter((item) => !municipio || item.municipio === municipio).forEach((item) => {
      const option = document.createElement('option'); option.value = item.value; option.textContent = item.value; select.append(option);
    });
    select.value = filtroComumCatalogo.some((item) => item.value === manter && (!municipio || item.municipio === municipio)) ? manter : '';
    $select.select2({width:'100%', language:'pt-BR', placeholder:'Pesquise a comum...', allowClear:true, dropdownParent:jQuery('.equipes-comum-filtro')});
    $select.off('select2:select.equipes select2:clear.equipes').on('select2:select.equipes select2:clear.equipes', () => carregar($('#filtro-texto').value.trim()));
  }

  function achatar(grupos) {
    return grupos.flatMap((grupo) => (grupo.membros || []).map((membro) => ({
      id: String(membro.id), nome: membro.nome, status: membro.status,
      equipe: grupo.nome, comum: grupo.comum, municipio: grupo.municipio,
    })));
  }

  function render() {
    const municipio = $('#filtro-municipio').value, comum = $('#filtro-comum').value;
    const busca = $('#filtro-texto').value.trim().toLocaleLowerCase('pt-BR');
    const rows = state.atribuicoes.filter((item) => {
      const texto = `${item.nome} ${item.equipe} ${item.comum} ${item.municipio}`.toLocaleLowerCase('pt-BR');
      return (!municipio || item.municipio === municipio) && (!comum || item.comum === comum) && (!busca || texto.includes(busca));
    });
    $('#equipes-lista').innerHTML = rows.length ? rows.map((item) => `<tr>
      <td><i class="fa fa-user text-teal me-2"></i><strong>${escapeHtml(item.nome)}</strong></td>
      <td>${item.equipe ? `<span class="equipe-badge equipe-cor-${equipeCor(item.equipe)}">${escapeHtml(item.equipe)}</span>` : '<span class="badge bg-light text-muted border">Sem equipe</span>'}</td>
      <td><span class="text-muted">${escapeHtml(item.municipio)}</span><br>${escapeHtml(item.comum)}</td>
      <td><span class="badge ${String(item.status).toLowerCase() === 'ativo' ? 'bg-success' : 'bg-secondary'}">${escapeHtml(item.status || 'Ativo')}</span></td>
      <td class="text-end"><button class="btn btn-sm ${item.equipe ? 'btn-outline-primary' : 'btn-teal'} editar" data-id="${item.id}" title="${item.equipe ? 'Alterar equipe' : 'Atribuir equipe'}"><i class="fa ${item.equipe ? 'fa-pen' : 'fa-user-plus'}"></i></button> ${item.equipe ? `<button class="btn btn-sm btn-outline-danger remover" data-id="${item.id}" title="Remover da equipe"><i class="fa fa-unlink"></i></button>` : ''}</td>
    </tr>`).join('') : '<tr><td colspan="5" class="text-center text-muted py-5">Nenhum membro encontrado para os filtros selecionados.</td></tr>';
  }

  async function carregar(busca = '') {
    try {
      const query = new URLSearchParams({modo:'membros'});
      if ($('#filtro-comum').value) query.set('comum', $('#filtro-comum').value);
      if (busca) query.set('busca', busca);
      const response = await fetch(`/visitas/api/equipes/?${query}`), payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Falha ao carregar as atribuições.');
      state.atribuicoes = payload.map((item) => ({
        id:String(item.id), nome:item.nome, status:item.status,
        equipe:item.equipe_visita || '', comum:item.comum, municipio:item.municipio || '',
      }));
      const nomes = [...new Set(state.atribuicoes.map((item) => item.equipe).filter(Boolean))].sort();
      $('#nomes-equipes').replaceChildren(...nomes.map((nome) => { const item = document.createElement('option'); item.value = nome; return item; }));
      render();
    } catch (error) { alerta(error.message); $('#equipes-lista').innerHTML = '<tr><td colspan="5"></td></tr>'; }
  }

  async function carregarMembros(comum, selecionado = '') {
    const select = $('#equipe-membro'); select.disabled = true; select.innerHTML = '<option value="">Carregando membros...</option>';
    if (!comum) return;
    try {
      const query = new URLSearchParams({modo:'membros', elegiveis:'true', comum});
      const response = await fetch(`/visitas/api/equipes/?${query}`), membros = await response.json();
      if (!response.ok) throw new Error(membros.error || 'Falha ao carregar membros.');
      select.replaceChildren();
      const vazio = document.createElement('option'); vazio.value = ''; vazio.textContent = 'Pesquise e selecione um membro...'; select.append(vazio);
      membros.forEach((membro) => { const item = document.createElement('option'); item.value = membro.id; item.textContent = membro.nome; select.append(item); });
      select.value = selecionado;
      const $select = jQuery(select); if ($select.hasClass('select2-hidden-accessible')) $select.select2('destroy');
      $select.select2({width:'100%', language:'pt-BR', placeholder:'Pesquise o nome do membro...', dropdownParent:jQuery('#equipe-modal')});
      select.disabled = false;
    } catch (error) { select.innerHTML = `<option value="">${escapeHtml(error.message)}</option>`; }
  }

  async function abrir(item = null) {
    $('#equipe-form').reset(); $('#equipe-municipio').value = item?.municipio || '';
    filtrarComuns($('#equipe-comum'), $('#equipe-municipio').value, item?.comum || '');
    $('#equipe-nome').value = item?.equipe || '';
    await carregarMembros(item?.comum || '', item?.id || ''); modal.show();
  }

  $('#nova-equipe').addEventListener('click', () => abrir());
  $('#filtro-municipio').addEventListener('change', () => { configurarPesquisaComum($('#filtro-municipio').value); carregar($('#filtro-texto').value.trim()); });
  $('#filtro-comum').addEventListener('change', () => carregar($('#filtro-texto').value.trim()));
  let buscaTimer;
  $('#filtro-texto').addEventListener('input', (event) => {
    clearTimeout(buscaTimer);
    buscaTimer = setTimeout(() => carregar(event.target.value.trim()), 300);
  });
  $('#equipe-municipio').addEventListener('change', () => { filtrarComuns($('#equipe-comum'), $('#equipe-municipio').value); carregarMembros(''); });
  $('#equipe-comum').addEventListener('change', (event) => carregarMembros(event.target.value));
  $('#equipes-lista').addEventListener('click', async (event) => {
    const edit = event.target.closest('.editar'), remove = event.target.closest('.remover');
    if (edit) abrir(state.atribuicoes.find((item) => item.id === edit.dataset.id));
    if (remove && confirm('Remover este membro da equipe?')) {
      const response = await fetch(`/visitas/api/equipes/?id=${remove.dataset.id}`, {method:'DELETE', headers:{'X-CSRFToken':csrf()}});
      const payload = await response.json(); if (!response.ok) return alerta(payload.error || 'Falha ao remover.'); alerta('Membro removido da equipe.', 'success'); carregar($('#filtro-texto').value.trim());
    }
  });
  $('#equipe-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const response = await fetch('/visitas/api/equipes/', {method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':csrf()}, body:JSON.stringify({membro_id:$('#equipe-membro').value, equipe:$('#equipe-nome').value})});
    const payload = await response.json(); if (!response.ok) return alerta(payload.error || 'Falha ao atribuir equipe.'); modal.hide(); alerta('Equipe atribuída ao membro com sucesso.', 'success'); carregar($('#filtro-texto').value.trim());
  });
  configurarPesquisaComum($('#filtro-municipio').value, $('#filtro-comum').value);
  carregar();
});
