(function () {
  'use strict';

  moment.locale('pt-br');
  const CATEGORIES = [
    ['gvi', ['gvi'], 'Irmandade (GVI)', 'text-blue'],
    ['gvm', ['gvm'], 'Mocidade (GVM)', 'text-purple'],
    ['gvmu', ['gvmu', 'gve'], 'Músicos (GVMu)', 'text-warning'],
    ['rf', ['rf'], 'Reunião familiar (RF)', 'text-teal'],
    ['re', ['re'], 'Evangelização (RE)', 'text-red']
  ];
  const number = value => Number(value || 0);
  const format = value => number(value).toLocaleString('pt-BR');
  const norm = value => String(value || '').trim().toLowerCase();
  const categoryValue = (row, fields) => fields.reduce((sum, field) => sum + number(row[field]), 0);
  const rowTotal = row => {
    const categories = CATEGORIES.reduce((sum, item) => sum + categoryValue(row, item[1]), 0);
    return number(row.total_visitas || row.total) || categories;
  };
  const escapeHtml = value => $('<div>').text(String(value || '')).html();
  const setText = (selector, value) => document.querySelector(selector).textContent = format(value);
  const empty = message => `<div class="text-gray-500 py-4 text-center"><i class="fa fa-circle-info me-1"></i>${message}</div>`;
  let visits = [], agenda = [], people = [], commons = [], evolutionChart, coverageChart, visitsSpark, peopleSpark, agendaSpark;
  let rangeStart = moment('2026-07-29'), rangeEnd = moment('2026-08-05');

  function inSelectedMonth(row) {
    const year = number(row.referencia_ano);
    const month = number(row.referencia_mes);
    if (!year || !month) return true;
    const date = moment({ year, month: month - 1, day: 1 });
    return date.isSameOrAfter(rangeStart.clone().startOf('month')) && date.isSameOrBefore(rangeEnd.clone().endOf('month'));
  }

  function agendaDate(row) { return moment(row.data_inicio || row.data || row.inicio); }

  function renderCharts(rows, activeCount, totalCommons) {
    const months = [];
    const cursor = rangeStart.clone().startOf('month');
    while (cursor.isSameOrBefore(rangeEnd, 'month')) { months.push(cursor.clone()); cursor.add(1, 'month'); }
    const series = CATEGORIES.map(([, fields, label]) => ({
      name: label,
      data: months.map(month => rows.filter(row => number(row.referencia_ano) === month.year() && number(row.referencia_mes) === month.month() + 1).reduce((sum, row) => sum + categoryValue(row, fields), 0))
    }));
    if (evolutionChart) evolutionChart.destroy();
    evolutionChart = new ApexCharts(document.querySelector('#visitas-evolucao-chart'), {
      chart: { type: 'area', height: 300, toolbar: { show: false }, foreColor: '#adb5bd' },
      series, xaxis: { categories: months.map(month => month.format('MMM/YY')) },
      dataLabels: { enabled: false }, stroke: { curve: 'smooth', width: 2 },
      fill: { type: 'gradient', gradient: { opacityFrom: .35, opacityTo: .05 } },
      colors: ['#348fe2', '#8753de', '#f59c1a', '#00acac', '#ff5b57'],
      legend: { position: 'top', labels: { colors: '#adb5bd' } },
      noData: { text: 'Sem lançamentos no período' }
    });
    evolutionChart.render();

    const coverage = totalCommons ? Math.round(activeCount / totalCommons * 100) : 0;
    if (coverageChart) coverageChart.destroy();
    coverageChart = new ApexCharts(document.querySelector('#cobertura-chart'), {
      chart: { type: 'radialBar', height: 200, sparkline: { enabled: true } }, series: [coverage],
      colors: ['#00acac'], labels: ['Cobertura'],
      plotOptions: { radialBar: { hollow: { size: '62%' }, dataLabels: { name: { color: '#adb5bd' }, value: { color: '#fff', fontSize: '25px', formatter: value => `${Math.round(value)}%` } } } }
    });
    coverageChart.render();

    const monthlyTotals = months.map(month => rows.filter(row => number(row.referencia_ano) === month.year() && number(row.referencia_mes) === month.month() + 1).reduce((sum, row) => sum + rowTotal(row), 0));
    const sparkOptions = (element, data, color) => new ApexCharts(document.querySelector(element), {
      chart: { type: 'line', height: 40, sparkline: { enabled: true } }, series: [{ data }], colors: [color], stroke: { curve: 'smooth', width: 3 }, tooltip: { enabled: false }
    });
    [visitsSpark, peopleSpark, agendaSpark].forEach(chart => { if (chart) chart.destroy(); });
    visitsSpark = sparkOptions('#total-visitas-sparkline', monthlyTotals, '#8753de');
    const withoutVisit = people.filter(row => !row.ultima_visita).length;
    const olderVisits = people.filter(row => row.ultima_visita && moment(row.ultima_visita).isBefore(rangeEnd.clone().subtract(60, 'days'), 'day')).length;
    peopleSpark = sparkOptions('#acompanhamento-sparkline', [Math.max(people.length - withoutVisit - olderVisits, 0), olderVisits, withoutVisit], '#f59c1a');
    agendaSpark = sparkOptions('#agenda-sparkline', months.map(month => agenda.filter(row => agendaDate(row).isSame(month, 'month')).length), '#00acac');
    visitsSpark.render(); peopleSpark.render(); agendaSpark.render();
  }

  function renderLists(rows, categoryTotals) {
    const grandTotal = Object.values(categoryTotals).reduce((sum, value) => sum + value, 0);
    document.querySelector('#categorias-lista').innerHTML = CATEGORIES.map(([key,, label, color]) => {
      const value = categoryTotals[key] || 0;
      const percent = grandTotal ? Math.round(value / grandTotal * 100) : 0;
      return `<div class="mb-3"><div class="d-flex"><span><i class="fa fa-circle ${color} fs-8px me-2"></i>${label}</span><strong class="ms-auto">${format(value)}</strong></div><div class="progress h-4px mt-2 bg-gray-700"><div class="progress-bar" style="width:${percent}%"></div></div></div>`;
    }).join('');

    const byCommon = {};
    rows.forEach(row => { const name = row.comum || 'Comum não informada'; byCommon[name] = (byCommon[name] || 0) + rowTotal(row); });
    const ranking = Object.entries(byCommon).sort((a, b) => b[1] - a[1]).slice(0, 5);
    document.querySelector('#ranking-comuns').innerHTML = ranking.length ? ranking.map(([name, value], index) =>
      `<div class="mb-3"><div class="d-flex"><span class="badge bg-blue me-2">${index + 1}</span><div class="text-truncate" title="${escapeHtml(name)}">${escapeHtml(name)}</div><strong class="ms-auto ps-2">${format(value)}</strong></div><div class="progress h-3px mt-2 bg-gray-700"><div class="progress-bar bg-blue" style="width:${ranking[0][1] ? Math.round(value / ranking[0][1] * 100) : 0}%"></div></div></div>`
    ).join('') : empty('Nenhuma atividade encontrada.');

    const upcoming = agenda.filter(row => { const date = agendaDate(row); return date.isValid() && date.isSameOrAfter(moment(), 'day') && !norm(row.status).includes('cancel'); }).sort((a, b) => agendaDate(a) - agendaDate(b)).slice(0, 5);
    document.querySelector('#proximas-visitas').innerHTML = upcoming.length ? upcoming.map(row => {
      const date = agendaDate(row);
      const title = escapeHtml(row.titulo || row.comum || 'Visita');
      const location = escapeHtml(row.comum || row.categoria || 'Local a definir');
      return `<div class="d-flex align-items-start mb-3"><div class="badge bg-teal p-2 me-2"><i class="fa fa-calendar-day"></i></div><div class="text-truncate"><div class="text-truncate" title="${title}">${title}</div><div class="small text-gray-500">${date.format('DD/MM/YYYY [às] HH:mm')} · ${location}</div></div></div>`;
    }).join('') : empty('Nenhuma visita futura agendada.');
  }

  function render() {
    const rows = visits.filter(inSelectedMonth);
    const activeCommons = new Set(rows.map(row => row.comum).filter(Boolean));
    const totalVisits = rows.reduce((sum, row) => sum + rowTotal(row), 0);
    const agendaPeriod = agenda.filter(row => { const date = agendaDate(row); return !date.isValid() || date.isBetween(rangeStart, rangeEnd, 'day', '[]'); });
    const realized = agendaPeriod.filter(row => norm(row.status) === 'realizada').length;
    const scheduled = agendaPeriod.filter(row => ['marcada', 'agendada'].includes(norm(row.status))).length;
    const failed = agendaPeriod.filter(row => norm(row.status).includes('cancel') || norm(row.status).includes('não realizada') || norm(row.status).includes('nao realizada')).length;
    const cutoff = rangeEnd.clone().subtract(60, 'days');
    const neverVisited = people.filter(row => !row.ultima_visita).length;
    const overdue = people.filter(row => row.ultima_visita && moment(row.ultima_visita).isBefore(cutoff, 'day')).length;
    const recent = Math.max(people.length - neverVisited - overdue, 0);
    const categoryTotals = Object.fromEntries(CATEGORIES.map(([key, fields]) => [key, rows.reduce((sum, row) => sum + categoryValue(row, fields), 0)]));

    setText('#exec-total-visitas', totalVisits); setText('#exec-comuns-ativas', activeCommons.size);
    setText('#exec-media-comum', activeCommons.size ? Math.round(totalVisits / activeCommons.size) : 0);
    setText('#exec-irmandade', people.length); setText('#exec-recentes', recent); setText('#exec-atrasados', overdue); setText('#exec-sem-visita', neverVisited);
    setText('#exec-total-agenda', agendaPeriod.length); setText('#agenda-realizadas', realized); setText('#agenda-agendadas', scheduled); setText('#agenda-pendentes', failed);
    setText('#exec-taxa-conclusao', agendaPeriod.length ? Math.round(realized / agendaPeriod.length * 100) : 0);
    setText('#cobertura-ativas', activeCommons.size); setText('#cobertura-total', commons.length);
    setText('#evolucao-total', totalVisits); setText('#evolucao-realizadas', realized); setText('#evolucao-comuns', activeCommons.size);
    const cityByCommon = Object.fromEntries(commons.map(item => [norm(item.comum), item.cidade || item.municipio || 'Não informado']));
    const byCity = {};
    rows.forEach(row => { const city = row.municipio || row.cidade || cityByCommon[norm(row.comum)] || 'Não informado'; byCity[city] = (byCity[city] || 0) + rowTotal(row); });
    const cityRanking = Object.entries(byCity).sort((a,b) => b[1] - a[1]).slice(0,3);
    document.querySelector('#ranking-municipios').innerHTML = cityRanking.length ? cityRanking.map(([city,value]) => `<div class="d-flex small mb-2"><span class="text-truncate">${escapeHtml(city)}</span><strong class="ms-auto">${format(value)}</strong></div>`).join('') : '<div class="small text-gray-500">Sem atividade por município.</div>';
    renderCharts(rows, activeCommons.size, commons.length); renderLists(rows, categoryTotals);
  }

  function setupDateRange() {
    const options = {
      startDate: rangeStart, endDate: rangeEnd, minDate: moment('2026-01-01'), maxDate: moment('2026-12-31'),
      opens: 'right', showDropdowns: true, alwaysShowCalendars: true,
      locale: { format: 'DD/MM/YYYY', separator: ' - ', applyLabel: 'Aplicar', cancelLabel: 'Cancelar', fromLabel: 'De', toLabel: 'Até', customRangeLabel: 'Personalizado', weekLabel: 'S', daysOfWeek: ['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'], monthNames: ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'], firstDay: 0 },
      ranges: { 'Hoje': [moment(), moment()], 'Ontem': [moment().subtract(1,'day'), moment().subtract(1,'day')], 'Últimos 7 dias': [moment().subtract(6,'day'), moment()], 'Últimos 30 dias': [moment().subtract(29,'day'), moment()], 'Este mês': [moment().startOf('month'), moment().endOf('month')], 'Mês anterior': [moment().subtract(1,'month').startOf('month'), moment().subtract(1,'month').endOf('month')] }
    };
    $('#daterange-filter').daterangepicker(options, (start, end) => {
      rangeStart = start.clone(); rangeEnd = end.clone();
      $('#daterange-filter span').text(`${start.format('D MMMM YYYY')} - ${end.format('D MMMM YYYY')}`);
      const days = end.diff(start, 'days') + 1;
      $('#daterange-prev-date').text(`${start.clone().subtract(days,'days').format('D MMMM')} - ${end.clone().subtract(days,'days').format('D MMMM YYYY')}`);
      render();
    });
  }

  $(async function () {
    setupDateRange();
    try {
      const responses = await Promise.all([fetch('/visitas/api/dashboard/?ano=all&mes=all&comum=all'), fetch('/visitas/api/agenda/'), fetch('/visitas/api/irmandade/'), fetch('/visitas/api/comuns/')]);
      if (responses.some(response => !response.ok)) throw new Error('Uma ou mais consultas falharam.');
      [visits, agenda, people, commons] = await Promise.all(responses.map(response => response.json()));
      render();
    } catch (error) {
      $('#dashboard-alert').removeClass('d-none').text('Não foi possível carregar os indicadores. Atualize a página ou verifique a conexão com o banco de dados.');
      console.error('Falha ao carregar o dashboard de visitas:', error);
    }
  });
})();
