
(()=>{
  let currentModule = 'all';
  let allRecords = [];
  let displayedRecords = [];
  let currentPage = 1;
  const pageSize = 15;
  let timelineChart = null;
  let actionChart = null;

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const reportUser = 'null';

  // Configuração inicial de datas (default: últimos 30 dias)
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const fmtDate = d => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;

  function applyDatePreset(days){
    const end = new Date();
    if(days === 'custom') return;
    const start = new Date();
    start.setDate(end.getDate() - parseInt(days));
    document.getElementById('filter-end').value = fmtDate(end);
    document.getElementById('filter-start').value = fmtDate(start);
  }
  applyDatePreset(30);

  document.getElementById('filter-period-preset').addEventListener('change', function(){
    if(this.value !== 'custom'){
      applyDatePreset(this.value);
      loadAuditData();
    }
  });

  // Pílulas de Módulos
  document.querySelectorAll('.module-pill').forEach(btn => {
    btn.addEventListener('click', function(){
      document.querySelectorAll('.module-pill').forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      currentModule = this.dataset.module;
      loadAuditData();
    });
  });

  // Parâmetros de consulta
  function buildParams(){
    const params = new URLSearchParams();
    params.set('module', currentModule);
    const start = document.getElementById('filter-start').value;
    const end = document.getElementById('filter-end').value;
    if(start) params.set('date_from', start);
    if(end) params.set('date_to', end);
    const action = document.getElementById('filter-action').value;
    if(action) params.set('action', action);
    const operator = document.getElementById('filter-operator').value.trim();
    if(operator) params.set('operator', operator);
    return params;
  }

  // Carregamento de dados com feedback visual
  async function loadAuditData(){
    const tbody = document.getElementById('audit-tbody');
    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-5 text-muted"><i class="fa fa-spinner fa-spin fa-2x mb-2 d-block text-primary"></i>Consultando a trilha de auditoria dos módulos…</td></tr>`;
    document.getElementById('last-update').textContent = 'Sincronizando…';

    try {
      const response = await fetch(`/api/auditoria/generic/?${buildParams()}`);
      if(!response.ok) throw new Error('Não foi possível carregar a auditoria.');
      const data = await response.json();

      allRecords = data.records || [];
      displayedRecords = allRecords.slice();
      currentPage = 1;

      // Atualiza KPIs
      document.getElementById('kpi-total').textContent = (data.total_events || 0).toLocaleString('pt-BR');
      document.getElementById('kpi-operators').textContent = (data.active_operators || 0).toLocaleString('pt-BR');
      document.getElementById('kpi-creates').textContent = (data.action_counts?.creates || 0).toLocaleString('pt-BR');
      document.getElementById('kpi-updates').textContent = (data.action_counts?.updates || 0).toLocaleString('pt-BR');
      document.getElementById('kpi-total-context').textContent = `${data.total_events || 0} operações no período`;

      if(data.scope) document.getElementById('scope-badge').textContent = data.scope;
      document.getElementById('last-update').textContent = `Atualizado às ${new Date().toLocaleTimeString('pt-BR', {hour:'2-digit', minute:'2-digit'})}`;

      // Nota executiva
      document.getElementById('executive-note').innerHTML = `
        <div class="health-icon"><i class="fa fa-list-check"></i></div>
        <div>
          <strong>Prioridades da Gestão e Conformidade</strong>
          <div class="mt-1">${esc(data.executive_note || 'Auditoria atualizada sem inconformidades no período.')}</div>
        </div>
      `;

      // Atualiza contadores nas pílulas se fornecidos
      if(data.module_counts){
        let sumAll = 0;
        Object.entries(data.module_counts).forEach(([m, count]) => {
          sumAll += count;
          const badge = document.getElementById(`count-${m}`);
          if(badge) badge.textContent = count.toLocaleString('pt-BR');
        });
        document.getElementById('count-all').textContent = sumAll.toLocaleString('pt-BR');
      }

      // Renderiza gráficos e tabela
      renderCharts(data);
      renderTable();

    } catch (err) {
      console.error(err);
      tbody.innerHTML = `<tr><td colspan="7" class="text-center py-5 text-danger"><i class="fa fa-triangle-exclamation fa-2x mb-2 d-block"></i>Erro ao carregar a trilha de auditoria: ${esc(err.message)}</td></tr>`;
      document.getElementById('last-update').textContent = 'Falha na conexão';
    }
  }

  // Renderização de Gráficos com ApexCharts
  function renderCharts(data){
    const timelineData = data.timeline_series || [];
    const timelineDates = timelineData.map(d => d.label);
    const timelineCounts = timelineData.map(d => d.count);

    // 1. Gráfico Temporal (Linha/Área Suave)
    const timelineOptions = {
      series: [{ name: 'Operações Auditadas', data: timelineCounts }],
      chart: { type: 'area', height: 260, toolbar: { show: false }, zoom: { enabled: false } },
      colors: ['#0d7377'],
      fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.45, opacityTo: 0.05, stops: [0, 95, 100] } },
      dataLabels: { enabled: false },
      stroke: { curve: 'smooth', width: 2.5 },
      xaxis: { categories: timelineDates, labels: { style: { fontSize: '10px', colors: '#64748b' } }, tickAmount: 10 },
      yaxis: { labels: { style: { fontSize: '10px', colors: '#64748b' } } },
      tooltip: { y: { formatter: v => `${v} registros` } }
    };

    if(timelineChart) timelineChart.destroy();
    timelineChart = new ApexCharts(document.querySelector('#audit-timeline-chart'), timelineOptions);
    timelineChart.render();

    // 2. Gráfico Donut de Ações
    const counts = data.action_counts || { creates: 0, updates: 0, deletes: 0, accesses: 0, others: 0 };
    const actionLabels = ['Criações', 'Atualizações', 'Exclusões', 'Acessos / Sessões', 'Outros'];
    const actionValues = [counts.creates, counts.updates, counts.deletes, counts.accesses, counts.others];

    const actionOptions = {
      series: actionValues.some(v => v > 0) ? actionValues : [1],
      labels: actionValues.some(v => v > 0) ? actionLabels : ['Sem operações'],
      chart: { type: 'donut', height: 260 },
      colors: ['#16a34a', '#2563eb', '#dc2626', '#7c3aed', '#64748b'],
      legend: { position: 'bottom', fontSize: '11px', markers: { radius: 12 } },
      dataLabels: { enabled: true, formatter: val => `${val.toFixed(0)}%` },
      plotOptions: { pie: { donut: { size: '65%', labels: { show: true, total: { show: true, label: 'Total', formatter: () => (data.total_events || 0).toLocaleString('pt-BR') } } } } },
      tooltip: { y: { formatter: v => `${v} operações` } }
    };

    if(actionChart) actionChart.destroy();
    actionChart = new ApexCharts(document.querySelector('#audit-action-chart'), actionOptions);
    actionChart.render();
  }

  // Filtro instantâneo na busca de texto da tabela
  document.getElementById('table-search').addEventListener('input', function(){
    const query = this.value.toLowerCase().trim();
    if(!query){
      displayedRecords = allRecords.slice();
    } else {
      displayedRecords = allRecords.filter(r =>
        (r.details && r.details.toLowerCase().includes(query)) ||
        (r.created_by && r.created_by.toLowerCase().includes(query)) ||
        (r.location && r.location.toLowerCase().includes(query)) ||
        (r.resource && r.resource.toLowerCase().includes(query)) ||
        (r.action_label && r.action_label.toLowerCase().includes(query))
      );
    }
    currentPage = 1;
    renderTable();
  });

  function renderDetails(rec){
    const fields = rec.detail_fields || {};
    if(fields.kind !== 'gem'){
      return `<div class="main-desc">${esc(rec.details)}</div>`;
    }

    const metadata = [fields.instrument, fields.level]
      .filter(Boolean)
      .map(value => `<span>${esc(value)}</span>`)
      .join('<span>•</span>');
    const status = fields.status
      ? `<span class="audit-gem-status">${esc(fields.status)}</span>`
      : '';
    return `
      <div class="audit-gem-details">
        <div class="audit-gem-title">${esc(fields.title || 'Ficha pedagógica')}</div>
        <div class="audit-gem-student">${esc(fields.student_name || 'Aluno não informado')}</div>
        <div class="audit-gem-meta">${metadata}${status}</div>
      </div>
    `;
  }

  function renderLocation(location){
    const parts = String(location || '—').split(' · ');
    if(parts.length < 2){
      return `<span class="audit-location-main">${esc(parts[0])}</span>`;
    }
    const city = parts.shift();
    return `
      <span class="audit-location-main">${esc(parts.join(' · '))}</span>
      <span class="audit-location-city">${esc(city)}</span>
    `;
  }

  // Renderização da Tabela de Eventos e Paginação
  function renderTable(){
    const tbody = document.getElementById('audit-tbody');
    tbody.innerHTML = '';

    const total = displayedRecords.length;
    document.getElementById('record-count').textContent = `${total.toLocaleString('pt-BR')} registros`;

    if(!total){
      tbody.innerHTML = `<tr><td colspan="7" class="text-center py-5 text-muted"><i class="fa fa-inbox fa-2x mb-2 d-block"></i>Nenhum evento auditado encontrado para os filtros selecionados.</td></tr>`;
      document.getElementById('page-info').textContent = 'Nenhum registro para exibir';
      renderPaginationControls(0);
      return;
    }

    const totalPages = Math.ceil(total / pageSize);
    if(currentPage > totalPages) currentPage = totalPages;
    const startIdx = (currentPage - 1) * pageSize;
    const endIdx = Math.min(startIdx + pageSize, total);
    const pageRecords = displayedRecords.slice(startIdx, endIdx);

    document.getElementById('page-info').textContent = `Mostrando ${startIdx + 1} a ${endIdx} de ${total.toLocaleString('pt-BR')} registros`;

    pageRecords.forEach(rec => {
      const tr = document.createElement('tr');
      const initials = (rec.created_by || 'S').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();

      tr.innerHTML = `
        <td>
          <span class="audit-module-badge" style="background:${rec.module_badge_bg};color:${rec.module_badge_color}">
            <i class="fa ${rec.module_icon}"></i>${esc(rec.module_label)}
          </span>
          <div class="small text-muted mt-1 font-monospace" style="font-size:10px">${esc(rec.resource)}</div>
        </td>
        <td>
          <span class="audit-action-badge" style="background:${rec.action_bg};color:${rec.action_color}">
            ${esc(rec.action_label)}
          </span>
        </td>
        <td>
          <div class="audit-operator">
            <div class="audit-avatar">${esc(initials)}</div>
            <div>
              <strong class="d-block" style="font-size:.78rem;color:#1e293b">${esc(rec.created_by || 'Sistema')}</strong>
              <small class="text-muted" style="font-size:9px">${esc(rec.location || 'Regional')}</small>
            </div>
          </div>
        </td>
        <td>
          <div style="font-weight:600;color:#1e293b">${esc(rec.created_at_display)}</div>
          <small class="text-muted" style="font-size:9px">${esc(rec.time_ago)}</small>
        </td>
        <td class="audit-location-cell">
          ${renderLocation(rec.location)}
        </td>
        <td class="audit-details-cell">
          ${renderDetails(rec)}
        </td>
        <td class="text-center">
          <button type="button" class="btn btn-xs btn-white border shadow-none btn-inspect" title="Inspecionar detalhes completos">
            <i class="fa fa-eye text-primary"></i>
          </button>
        </td>
      `;

      tr.querySelector('.btn-inspect').addEventListener('click', () => openDetailModal(rec));
      tbody.appendChild(tr);
    });

    renderPaginationControls(totalPages);
  }

  function renderPaginationControls(totalPages){
    const container = document.getElementById('page-numbers');
    container.innerHTML = '';
    const prevBtn = document.getElementById('btn-prev');
    const nextBtn = document.getElementById('btn-next');

    prevBtn.disabled = currentPage <= 1;
    nextBtn.disabled = currentPage >= totalPages;

    if(totalPages <= 1) return;

    const maxVisible = 5;
    let startPage = Math.max(1, currentPage - 2);
    let endPage = Math.min(totalPages, startPage + maxVisible - 1);
    if(endPage - startPage < maxVisible - 1) startPage = Math.max(1, endPage - maxVisible + 1);

    for(let i = startPage; i <= endPage; i++){
      const btn = document.createElement('button');
      btn.className = `btn-page ${i === currentPage ? 'active' : ''}`;
      btn.textContent = i;
      btn.addEventListener('click', () => { currentPage = i; renderTable(); });
      container.appendChild(btn);
    }
  }

  document.getElementById('btn-prev').addEventListener('click', () => {
    if(currentPage > 1){ currentPage--; renderTable(); }
  });
  document.getElementById('btn-next').addEventListener('click', () => {
    currentPage++; renderTable();
  });

  // Modal de Detalhes
  function openDetailModal(rec){
    const raw = rec.raw_data || {};
    const recordId = String(rec.id || '');
    const origin = rec.source_label || raw.device || raw.platform || 'Aplicação web';
    const fields = rec.detail_fields || {};

    document.getElementById('modal-operator').textContent = rec.created_by || 'Sistema';
    document.getElementById('modal-datetime').textContent = rec.created_at_display || '—';
    document.getElementById('modal-relative-time').textContent = rec.time_ago || '';
    document.getElementById('modal-module').textContent = `${rec.module_label} · ${rec.resource}`;
    document.getElementById('modal-action').innerHTML = `<span class="audit-action-badge" style="background:${rec.action_bg};color:${rec.action_color}">${esc(rec.action_label)}</span>`;
    document.getElementById('modal-record-id').textContent = recordId || '—';
    document.getElementById('modal-record-id').title = recordId;
    document.getElementById('modal-origin').textContent = origin;
    document.getElementById('modal-location').textContent = rec.location || 'Regional Itapevi';
    const descriptionLabel = document.getElementById('modal-description-label');
    const description = document.getElementById('modal-description');
    if(fields.kind === 'gem'){
      descriptionLabel.textContent = 'Dados da Ficha Pedagógica';
      description.innerHTML = `
        <div class="modal-gem-details">
          <div class="modal-gem-detail"><span>Aluno</span><strong>${esc(fields.student_name || 'Não informado')}</strong></div>
          <div class="modal-gem-detail"><span>Instrumento</span><strong>${esc(fields.instrument || 'Não informado')}</strong></div>
          <div class="modal-gem-detail"><span>Nível</span><strong>${esc(fields.level || 'Não informado')}</strong></div>
          <div class="modal-gem-detail"><span>Status</span><strong><span class="audit-gem-status">${esc(fields.status || 'Não informado')}</span></strong></div>
        </div>
      `;
    } else {
      descriptionLabel.textContent = 'Descrição Semântica do Evento';
      description.textContent = rec.details || 'Sem descrição adicional.';
    }

    document.getElementById('modal-json').textContent = JSON.stringify(raw, null, 2);

    const modal = new bootstrap.Modal(document.getElementById('audit-detail-modal'));
    modal.show();
  }

  function showFeedback(type, title, message, detail){
    if(window.AppFeedback){
      return window.AppFeedback.show({ type, title, message, detail, flow: 'export' });
    }
    return null;
  }

  // Exportação CSV UTF-8 com BOM para abertura compatível no Excel.
  document.getElementById('btn-csv').addEventListener('click', () => {
    if(!displayedRecords.length){
      showFeedback('warning', 'Nenhum registro para exportar', 'Ajuste os filtros e tente novamente.', 'Não há dados no recorte atual.');
      return;
    }
    const headers = ['Módulo', 'Recurso', 'Ação', 'Usuário', 'Data e Hora', 'Localização', 'Descrição Completa'];
    const rows = displayedRecords.map(r => [
      r.module_label || '',
      r.resource || '',
      r.action_label || '',
      r.created_by || '',
      r.created_at_display || '',
      r.location || '',
      r.details || ''
    ]);

    const csvContent = '\ufeff' + [headers, ...rows].map(row =>
      row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(';')
    ).join('\r\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    const stamp = new Date().toISOString().slice(0, 10);
    link.download = `Auditoria_Modulos_${currentModule}_${stamp}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
    showFeedback('success', 'Arquivo CSV gerado', 'O download da auditoria foi iniciado.', `${displayedRecords.length} registro(s) exportado(s).`);
  });

  // Exportação PDF Canônica em 3 colunas (conforme REPORT_EXPORT_STANDARD.md)
  document.getElementById('btn-pdf').addEventListener('click', () => {
    if(!displayedRecords.length){
      showFeedback('warning', 'Nenhum registro para exportar', 'Ajuste os filtros e tente novamente.', 'Não há dados no recorte atual.');
      return;
    }
    const button = document.getElementById('btn-pdf');
    button.disabled = true;
    const origHtml = button.innerHTML;
    button.innerHTML = '<i class="fa fa-spinner fa-spin me-1"></i>Gerando…';
    const loadingFeedback = showFeedback('loading', 'Gerando PDF', 'Preparando o relatório de auditoria.', 'Aguarde a conclusão do download.');

    try {
      const now = new Date();
      const pad = n => String(n).padStart(2, '0');
      const stamp = `${pad(now.getDate())}/${pad(now.getMonth()+1)}/${now.getFullYear()} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
      const fileStamp = `${pad(now.getDate())}-${pad(now.getMonth()+1)}-${now.getFullYear()}_${pad(now.getHours())}-${pad(now.getMinutes())}`;
      const scopeLabel = document.getElementById('scope-badge').textContent || 'Regional Itapevi';

      const tableBody = [
        [
          { text: 'MÓDULO', style: 'tableHeader' },
          { text: 'AÇÃO', style: 'tableHeader' },
          { text: 'OPERADOR', style: 'tableHeader' },
          { text: 'DATA/HORA', style: 'tableHeader' },
          { text: 'LOCALIZAÇÃO', style: 'tableHeader' },
          { text: 'DETALHES DA OPERAÇÃO AUDITADA', style: 'tableHeader' }
        ]
      ];

      displayedRecords.forEach(r => {
        tableBody.push([
          { text: r.module_label || '', fontSize: 7, bold: true },
          { text: r.action_label || '', fontSize: 7, alignment: 'center' },
          { text: r.created_by || 'Sistema', fontSize: 7 },
          { text: r.created_at_display || '', fontSize: 7, alignment: 'center' },
          { text: r.location || '—', fontSize: 7 },
          { text: r.details || '', fontSize: 7 }
        ]);
      });

      const docDefinition = {
        pageSize: 'A4',
        pageOrientation: 'landscape',
        pageMargins: [28, 100, 28, 34],
        header: (currentPage, pageCount) => ({
          margin: [28, 16, 28, 0],
          columns: [
            { width: 220, text: '' },
            {
              width: '*',
              stack: [
                { text: 'CONGREGAÇÃO CRISTÃ NO BRASIL', style: 'entityName' },
                { text: 'Regional Itapevi - São Paulo', style: 'entitySub' },
                { text: 'TRILHA DE AUDITORIA', style: 'moduleName' },
                { text: 'Auditoria Consolidada de Módulos Educacionais e Operacionais', style: 'reportTitle' }
              ]
            },
            {
              width: 220,
              stack: [
                { text: `Página ${currentPage} de ${pageCount}`, bold: true },
                { text: [{ text: 'Emissão: ', bold: true }, { text: stamp }] },
                { text: [{ text: 'Recorte: ', bold: true }, { text: scopeLabel }], fontSize: 7 },
                { text: [{ text: 'Impresso por: ', bold: true }, { text: reportUser }], fontSize: 7 }
              ],
              alignment: 'right',
              fontSize: 8
            }
          ]
        }),
        footer: (currentPage, pageCount) => ({
          margin: [28, 5, 28, 0],
          columns: [
            { text: `Auditoria de Módulos · ${displayedRecords.length} registro(s) auditado(s) · ${scopeLabel}`, color: '#6b7280', fontSize: 7 },
            { text: `Página ${currentPage} de ${pageCount}`, alignment: 'right', color: '#6b7280', fontSize: 7 }
          ]
        }),
        content: [
          {
            table: {
              widths: ['*'],
              body: [
                [{
                  text: `RECORTE DE AUDITORIA • ${scopeLabel.toUpperCase()} • ${displayedRecords.length} OPERAÇÕES AUDITADAS NO PERÍODO`,
                  fillColor: '#eaf2f8',
                  color: '#1e4b7a',
                  bold: true,
                  fontSize: 8,
                  margin: [6, 4, 6, 4]
                }]
              ]
            },
            layout: 'noBorders',
            margin: [0, 0, 0, 8]
          },
          {
            table: {
              headerRows: 1,
              dontBreakRows: true,
              widths: [110, 75, 120, 85, 120, '*'],
              body: tableBody
            },
            layout: {
              fillColor: (row) => row > 0 ? (row % 2 ? '#ffffff' : '#f4f6f8') : null,
              hLineColor: () => '#c8d1da',
              vLineColor: () => '#d8dee5',
              hLineWidth: () => 0.45,
              vLineWidth: () => 0.35,
              paddingLeft: () => 4,
              paddingRight: () => 4,
              paddingTop: () => 3,
              paddingBottom: () => 3
            }
          }
        ],
        styles: {
          entityName: { fontSize: 15, bold: true, alignment: 'center' },
          entitySub: { fontSize: 9, alignment: 'center' },
          moduleName: { fontSize: 12, bold: true, color: '#1e4b7a', alignment: 'center', margin: [0, 5, 0, 0] },
          reportTitle: { fontSize: 9, alignment: 'center' },
          tableHeader: { color: '#ffffff', bold: true, alignment: 'center', fillColor: '#1e4b7a', fontSize: 7.5 }
        },
        defaultStyle: { fontSize: 7.2, color: '#263238' }
      };

      pdfMake.createPdf(window.AppReportIdentity.prepare(docDefinition)).download(`Auditoria_Modulos_${currentModule}_${fileStamp}.pdf`);
      loadingFeedback?.close();
      showFeedback('success', 'Relatório PDF gerado', 'O download do relatório foi iniciado.', `${displayedRecords.length} registro(s) exportado(s).`);
    } catch (e) {
      console.error(e);
      loadingFeedback?.close();
      showFeedback('error', 'Falha ao gerar o PDF', 'Não foi possível gerar o relatório de auditoria.', 'Tente novamente em alguns instantes.');
    } finally {
      button.disabled = false;
      button.innerHTML = origHtml;
    }
  });

  // Botões de Ação
  document.getElementById('btn-refresh').addEventListener('click', loadAuditData);
  document.getElementById('btn-clear').addEventListener('click', () => {
    document.getElementById('filter-period-preset').value = '30';
    applyDatePreset(30);
    document.getElementById('filter-action').value = '';
    document.getElementById('filter-operator').value = '';
    document.getElementById('table-search').value = '';
    currentModule = 'all';
    document.querySelectorAll('.module-pill').forEach(b => b.classList.remove('active'));
    document.querySelector('.module-pill[data-module="all"]')?.classList.add('active');
    loadAuditData();
  });

  document.getElementById('filter-action').addEventListener('change', loadAuditData);
  document.getElementById('filter-operator').addEventListener('keyup', e => { if(e.key === 'Enter') loadAuditData(); });
  document.getElementById('filter-start').addEventListener('change', () => {
    document.getElementById('filter-period-preset').value = 'custom';
    loadAuditData();
  });
  document.getElementById('filter-end').addEventListener('change', () => {
    document.getElementById('filter-period-preset').value = 'custom';
    loadAuditData();
  });

  // Carregamento inicial automático
  loadAuditData();
})();
