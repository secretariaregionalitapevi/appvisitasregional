(function () {
  'use strict';

  moment.locale('pt-br');
  const categories = [
    { key: 'gvi', fields: ['gvi'], label: 'Irmandade (GVI)', color: '#8753de' },
    { key: 'gvm', fields: ['gvm'], label: 'Mocidade (GVM)', color: '#348fe2' },
    { key: 'gvmu', fields: ['gvmu', 'gve'], label: 'Músicos (GVMu)', color: '#49b6d6' },
    { key: 'rf', fields: ['rf'], label: 'Reunião familiar (RF)', color: '#f59c1a' },
    { key: 're', fields: ['re'], label: 'Evangelização (RE)', color: '#ff5b57' }
  ];
  const num = value => Number(value || 0);
  const fmt = value => num(value).toLocaleString('pt-BR');
  const norm = value => String(value || '').trim().toLocaleLowerCase('pt-BR');
  const esc = value => $('<div>').text(String(value || '')).html();
  const catValue = (row, category) => category.fields.reduce((sum, field) => sum + num(row[field]), 0);
  const rowTotal = row => num(row.total_visitas || row.total) || categories.reduce((sum, category) => sum + catValue(row, category), 0);
  const agendaDate = row => moment(row.data_inicio || row.data || row.inicio);
  const card = title => $('b').filter(function () { return $(this).text().trim() === title; }).first().closest('.card');
  let allVisits = [], allAgenda = [], allPeople = [], allCommons = [], mainChart, cityMap;
  let start = moment('2026-07-29'), end = moment('2026-08-05');

  function setAnimated(selector, value) {
    $(selector).removeAttr('data-animation data-value').text(fmt(value));
  }

  function renderSparkline(selector, data, colors) {
    $(selector).empty();
    const colorStops = colors.map((color, index) => ({
      offset: colors.length === 1 ? 0 : Math.round(index * 100 / (colors.length - 1)),
      color,
      opacity: 1
    }));
    new ApexCharts(document.querySelector(selector), {
      chart: { type: 'line', height: 32, width: 120, sparkline: { enabled: true } },
      series: [{ data: data.length ? data : [0] }],
      colors: [colors[0]],
      stroke: { curve: 'smooth', width: 3 },
      fill: { type: 'gradient', gradient: { opacityFrom: 1, opacityTo: 1, colorStops } },
      tooltip: { enabled: false }
    }).render();
  }

  function monthlyRows(rows) {
    const months = [];
    const cursor = start.clone().startOf('month');
    while (cursor.isSameOrBefore(end, 'month')) { months.push(cursor.clone()); cursor.add(1, 'month'); }
    return months.map(month => ({
      month,
      rows: rows.filter(row => num(row.referencia_ano) === month.year() && num(row.referencia_mes) === month.month() + 1)
    }));
  }

  function renderMainChart(grouped) {
    if (mainChart) mainChart.destroy();
    $('#visitors-line-chart').empty();
    mainChart = new ApexCharts(document.querySelector('#visitors-line-chart'), {
      chart: { type: 'area', height: 254, stacked: true, toolbar: { show: false }, foreColor: '#d3d8de', animations: { enabled: true, speed: 700 } },
      series: categories.map(category => ({ name: category.label, data: grouped.map(group => group.rows.reduce((sum, row) => sum + catValue(row, category), 0)) })),
      colors: categories.map(category => category.color), dataLabels: { enabled: false },
      stroke: { curve: 'straight', width: 1.5 }, fill: { type: 'solid', opacity: .78 },
      xaxis: { categories: grouped.map(group => group.month.format('MMM/YY')), axisBorder: { color: '#4b5560' }, axisTicks: { color: '#4b5560' } },
      yaxis: { labels: { formatter: value => Math.round(value) } },
      grid: { borderColor: '#4b5560', strokeDashArray: 0 },
      legend: { position: 'top', horizontalAlign: 'right', labels: { colors: '#fff' } },
      tooltip: { theme: 'dark', y: { formatter: value => `${fmt(value)} visitas` } }, noData: { text: 'Sem visitas no período' }
    });
    mainChart.render();
  }

  function renderCities(rows) {
    const cityByCommon = Object.fromEntries(allCommons.map(item => [norm(item.comum), item.cidade || item.municipio || 'Não informado']));
    const referenceMonth = end.clone().startOf('month');
    const previousMonth = referenceMonth.clone().subtract(1, 'month');
    const rowsFromMonth = month => allVisits.filter(row => num(row.referencia_ano) === month.year() && num(row.referencia_mes) === month.month() + 1);
    const totalsByCity = sourceRows => sourceRows.reduce((result, row) => {
      const city = row.municipio || row.cidade || cityByCommon[norm(row.comum)] || 'Não informado';
      result[norm(city)] = (result[norm(city)] || 0) + rowTotal(row);
      return result;
    }, {});
    const currentTotals = totalsByCity(rowsFromMonth(referenceMonth));
    const previousTotals = totalsByCity(rowsFromMonth(previousMonth));
    const regionalCities = [
      'Caucaia do Alto', 'Cotia', 'Itapevi', 'Jandira', 'Pirapora do Bom Jesus',
      'Santana de Parnaíba', 'Vargem Grande Paulista'
    ];
    const ranking = regionalCities.map(name => {
      const current = currentTotals[norm(name)] || 0;
      const previous = previousTotals[norm(name)] || 0;
      const direction = current > previous ? 'up' : current < previous ? 'down' : 'stable';
      const percent = previous ? Math.round(Math.abs(current - previous) / previous * 100) : current ? null : 0;
      return [name, current, { previous, direction, percent }];
    });
    const coordinates = {
      'itapevi': [-46.9340, -23.5488], 'jandira': [-46.9023, -23.5275], 'cotia': [-46.9190, -23.6022],
      'santana de parnaiba': [-46.9178, -23.4439], 'santana de parnaíba': [-46.9178, -23.4439],
      'caucaia do alto': [-47.0234, -23.6802], 'carapicuiba': [-46.8350, -23.5226], 'carapicuíba': [-46.8350, -23.5226],
      'barueri': [-46.8765, -23.5112], 'osasco': [-46.7917, -23.5325], 'vargem grande paulista': [-47.0267, -23.6035],
      'pirapora do bom jesus': [-47.0069, -23.3966], 'aracariguama': [-47.0608, -23.4366], 'araçariguama': [-47.0608, -23.4366]
    };
    const features = ranking.map(([name, value, trend]) => ({ type: 'Feature', properties: { name, value, trend: trend.direction, percent: trend.percent }, geometry: { type: 'Point', coordinates: coordinates[norm(name)] } })).filter(feature => feature.geometry.coordinates);
    const geojson = { type: 'FeatureCollection', features };
    if (!window.maplibregl) return;
    if (!cityMap) {
      cityMap = new maplibregl.Map({
        container: 'visitors-map',
        style: { version: 8, sources: { osm: { type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256, attribution: '© OpenStreetMap' } }, layers: [{ id: 'osm', type: 'raster', source: 'osm', paint: { 'raster-saturation': 0, 'raster-brightness-min': .08, 'raster-brightness-max': 1 } }] },
        center: [-46.93, -23.55], zoom: 9.4, minZoom: 8, maxZoom: 15, attributionControl: true
      });
      cityMap.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
      cityMap.on('load', () => {
        cityMap.addSource('municipios-visitas', { type: 'geojson', data: geojson });
        cityMap.addLayer({ id: 'municipios-halo', type: 'circle', source: 'municipios-visitas', paint: { 'circle-radius': ['interpolate',['linear'],['get','value'],0,12,500,28], 'circle-color': '#ff3b30', 'circle-opacity': .18, 'circle-stroke-width': 0 } });
        cityMap.addLayer({ id: 'municipios-atividade', type: 'circle', source: 'municipios-visitas', paint: { 'circle-radius': ['interpolate',['linear'],['get','value'],0,5,500,12], 'circle-color': '#ff3b30', 'circle-opacity': .92, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 } });
        cityMap.on('mouseenter','municipios-atividade',event => { cityMap.getCanvas().style.cursor='pointer'; const feature=event.features[0]; const trendLabel=feature.properties.trend==='up'?'aumento':feature.properties.trend==='down'?'redução':'estabilidade'; cityMap._visitasPopup=new maplibregl.Popup({ closeButton:false, closeOnClick:false, className:'map-visitas-popup', offset:12 }).setLngLat(feature.geometry.coordinates).setHTML(`<strong>${esc(feature.properties.name)}</strong><br><span>${fmt(feature.properties.value)} visitas · ${trendLabel}</span>`).addTo(cityMap); });
        cityMap.on('mouseleave','municipios-atividade',() => { cityMap.getCanvas().style.cursor=''; if(cityMap._visitasPopup) cityMap._visitasPopup.remove(); });
        fitMunicipalBounds(features);
      });
    } else if (cityMap.isStyleLoaded() && cityMap.getSource('municipios-visitas')) {
      cityMap.getSource('municipios-visitas').setData(geojson); fitMunicipalBounds(features);
    }
    function fitMunicipalBounds(items) {
      if (!items.length) return;
      const bounds=new maplibregl.LngLatBounds(); items.forEach(item => bounds.extend(item.geometry.coordinates));
      cityMap.fitBounds(bounds,{padding:35,maxZoom:11.3,duration:650});
    }
    const locationCard = card('ATIVIDADE POR MUNICÍPIO');
    const list = locationCard.find('#visitors-map').next('div');
    const trendHtml = trend => {
      if (trend.direction === 'up') return `<span class="text-teal ms-2"><i class="fa fa-arrow-up"></i> ${trend.percent === null ? 'novo' : `${trend.percent}%`}</span>`;
      if (trend.direction === 'down') return `<span class="text-red ms-2"><i class="fa fa-arrow-down"></i> ${trend.percent}%</span>`;
      return '<span class="text-gray-500 ms-2"><i class="fa fa-minus"></i> estável</span>';
    };
    list.html(`<div class="small text-gray-500 mb-2">Comparativo: ${referenceMonth.format('MMMM/YYYY')} × ${previousMonth.format('MMMM/YYYY')}</div>` + ranking.map(([name, value, trend]) => `<div class="d-flex align-items-center text-white mb-2"><div class="widget-img widget-img-xs rounded bg-dark me-2 w-40px d-flex align-items-center justify-content-center"><i class="fa fa-location-dot text-teal fs-18px"></i></div><div class="d-flex align-items-center w-100"><div>${esc(name)}</div><div class="ms-auto text-nowrap"><strong>${fmt(value)}</strong>${trendHtml(trend)}</div></div></div>`).join(''));
  }

  function renderCategories(rows) {
    const totals = categories.map(category => rows.reduce((sum, row) => sum + catValue(row, category), 0));
    const total = totals.reduce((sum, value) => sum + value, 0);
    const categoryCard = card('VISITAS POR CATEGORIA');
    categoryCard.find('.card-body h3').html(`<span>${fmt(total)}</span>`);
    categoryCard.find('.card-body .text-gray-500.mb-1px').html('<i class="fa fa-chart-pie"></i> composição do período selecionado');
    categoryCard.find('.widget-list-item').each(function (index) {
      const category = categories[index], value = totals[index], percent = total ? Math.round(value / total * 100) : 0;
      $(this).attr('href', 'javascript:;').find('.widget-list-title').text(category.label);
      $(this).find('.widget-list-action').html(`<strong>${fmt(value)}</strong> <span class="small">(${percent}%)</span>`);
      $(this).find('i').attr('class', `fa fa-${['heart','users','music','house','book-bible'][index]} text-white`).css('background-color', category.color);
    });
  }

  function renderCommons(rows) {
    const totals = {};
    rows.forEach(row => { const name = row.comum || 'Comum não informada'; totals[name] = (totals[name] || 0) + rowTotal(row); });
    const ranking = Object.entries(totals).sort((a, b) => b[1] - a[1]).slice(0, 5);
    const rowsDom = card('COMUNS COM MAIOR ATIVIDADE').find('.card-body > .d-flex.align-items-center');
    rowsDom.each(function (index) {
      const entry = ranking[index]; $(this).toggle(!!entry); if (!entry) return;
      $(this).find('.widget-img').removeClass('bg-white').addClass('bg-teal bg-opacity-25').html('<div class="h-100 w-100 d-flex align-items-center justify-content-center"><i class="fa fa-location-dot text-teal"></i></div>');
      const text = $(this).find('.text-truncate > div'); text.eq(0).text(entry[0]).attr('title', entry[0]); text.eq(1).text(index === 0 ? 'Maior volume no período' : 'Atividade consolidada');
      $(this).find('.fs-13px').text(fmt(entry[1])); $(this).find('.fs-10px').text('visitas');
    });
  }

  function renderUpcoming() {
    const upcoming = allAgenda.filter(row => { const date = agendaDate(row); return date.isValid() && date.isSameOrAfter(moment(), 'day') && !norm(row.status).includes('cancel'); }).sort((a,b) => agendaDate(a) - agendaDate(b)).slice(0,2);
    const rows = card('PRÓXIMAS VISITAS').find('.card-body > .row');
    rows.each(function (index) {
      const item = upcoming[index]; $(this).toggle(!!item); if (!item) return;
      const date = agendaDate(item), content = $(this).find('.col-8');
      content.find('.mb-2px.text-truncate').first().text(item.titulo || item.comum || 'Visita agendada');
      content.find('.text-gray-500.small').first().text(`${date.format('ddd, DD/MM/YYYY [às] HH:mm')} · ${item.comum || item.categoria || 'Local a definir'}`);
      content.find('.progress-bar').attr('data-value','100%').css('width','100%'); content.find('.w-30px span').text('100');
      content.find('.small.mb-15px').text(item.equipe_responsavel ? `Equipe: ${item.equipe_responsavel}` : 'Equipe responsável a definir');
      content.find('.btn').attr('href','/visitas/calendario/').text('Ver agenda');
    });
    if (!upcoming.length) card('PRÓXIMAS VISITAS').find('.card-body').append('<div class="text-gray-500 text-center py-4 dashboard-empty-agenda"><i class="fa fa-calendar-check fa-2x mb-2 d-block"></i>Nenhuma visita futura agendada.</div>');
  }

  function render() {
    $('.dashboard-empty-agenda').remove();
    const rows = allVisits.filter(row => {
      if (!row.referencia_ano || !row.referencia_mes) return true;
      const date = moment({ year: num(row.referencia_ano), month: num(row.referencia_mes) - 1, day: 1 });
      return date.isBetween(start.clone().startOf('month'), end.clone().endOf('month'), 'month', '[]');
    });
    const grouped = monthlyRows(rows), total = rows.reduce((sum, row) => sum + rowTotal(row), 0);
    const activeCommons = new Set(rows.map(row => row.comum).filter(Boolean));
    const agendaPeriod = allAgenda.filter(row => { const date = agendaDate(row); return date.isValid() && date.isBetween(start, end, 'day', '[]'); });
    const realized = agendaPeriod.filter(row => norm(row.status) === 'realizada').length;
    const scheduled = agendaPeriod.filter(row => ['marcada','agendada'].includes(norm(row.status))).length;
    const failed = agendaPeriod.filter(row => norm(row.status).includes('cancel') || norm(row.status).includes('não realizada') || norm(row.status).includes('nao realizada')).length;
    const cutoff = end.clone().subtract(60,'days');
    const never = allPeople.filter(row => !row.ultima_visita).length;
    const overdue = allPeople.filter(row => row.ultima_visita && moment(row.ultima_visita).isBefore(cutoff,'day')).length;
    const recent = Math.max(allPeople.length - never - overdue, 0);

    setAnimated('#kpi-total-visitas', total); setAnimated('#kpi-comuns-ativas', activeCommons.size); setAnimated('#kpi-media-comum', activeCommons.size ? Math.round(total / activeCommons.size) : 0);
    setAnimated('#kpi-taxa-conclusao', agendaPeriod.length ? Math.round(realized / agendaPeriod.length * 100) : 0); setAnimated('#kpi-total-irmandade', allPeople.length);
    const executionCard = card('EXECUÇÃO DA AGENDA');
    [realized, scheduled, failed].forEach((value,index) => {
      executionCard.find('.w-50px').eq(index).text(fmt(value));
      executionCard.find('.text-gray-500.small').eq(index).html(`${agendaPeriod.length ? Math.round(value / agendaPeriod.length * 100) : 0}%`);
    });
    executionCard.find('.mb-4.text-gray-500').html(`<i class="fa fa-calendar-check"></i> ${fmt(agendaPeriod.length)} compromissos no período`);
    const peopleCard = card('ACOMPANHAMENTO');
    [recent, overdue, never].forEach((value,index) => {
      peopleCard.find('.w-50px').eq(index).text(fmt(value));
      peopleCard.find('.text-gray-500.small').eq(index).html(`${allPeople.length ? Math.round(value / allPeople.length * 100) : 0}%`);
    });
    peopleCard.find('.mb-4.text-gray-500').html('<i class="fa fa-heart-pulse"></i> situação atual da irmandade');

    const analytics = card('EVOLUÇÃO DAS VISITAS');
    [total, realized, activeCommons.size].forEach((value,index) => analytics.find('h3').eq(index).html(`<span>${fmt(value)}</span>`));
    analytics.find('.small.text-truncate').eq(0).text('volume consolidado no escopo'); analytics.find('.small.text-truncate').eq(1).text('compromissos concluídos'); analytics.find('.small.text-truncate').eq(2).text(`${fmt(allCommons.length)} comuns disponíveis`);
    renderSparkline('#total-sales-sparkline', grouped.map(group => group.rows.reduce((sum,row) => sum + rowTotal(row),0)), ['#348fe2','#8753de']);
    renderSparkline('#conversion-rate-sparkline', [scheduled, realized, failed], ['#ff5b57','#f59c1a','#84bd00']);
    renderSparkline('#store-session-sparkline', [recent, overdue, never], ['#00acac','#348fe2','#49b6d6']);
    renderMainChart(grouped); renderCities(rows); renderCategories(rows); renderCommons(rows); renderUpcoming();
  }

  function setupDatePicker() {
    $('#daterange-filter').daterangepicker({ startDate:start, endDate:end, minDate:moment('2026-01-01'), maxDate:moment('2026-12-31'), opens:'right', showDropdowns:true, alwaysShowCalendars:true,
      ranges:{'Hoje':[moment(),moment()],'Ontem':[moment().subtract(1,'day'),moment().subtract(1,'day')],'Últimos 7 dias':[moment().subtract(6,'day'),moment()],'Últimos 30 dias':[moment().subtract(29,'day'),moment()],'Este mês':[moment().startOf('month'),moment().endOf('month')],'Mês anterior':[moment().subtract(1,'month').startOf('month'),moment().subtract(1,'month').endOf('month')]},
      locale:{format:'DD/MM/YYYY',separator:' - ',applyLabel:'Aplicar',cancelLabel:'Cancelar',fromLabel:'De',toLabel:'Até',customRangeLabel:'Personalizado',weekLabel:'S',daysOfWeek:['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'],monthNames:['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'],firstDay:0}
    }, function (newStart,newEnd) {
      start=newStart; end=newEnd; $('#daterange-filter span').text(`${start.format('D MMMM YYYY')} - ${end.format('D MMMM YYYY')}`);
      const days=end.diff(start,'days')+1; $('#daterange-prev-date').text(`${start.clone().subtract(days,'days').format('D MMMM')} - ${end.clone().subtract(days,'days').format('D MMMM YYYY')}`); render();
    });
  }

  $(async function () {
    setupDatePicker();
    try {
      const responses=await Promise.all([fetch('/visitas/api/dashboard/?ano=all&mes=all&comum=all'),fetch('/visitas/api/agenda/'),fetch('/visitas/api/irmandade/'),fetch('/visitas/api/comuns/')]);
      if(responses.some(response=>!response.ok)) throw new Error('Falha em uma das consultas');
      [allVisits,allAgenda,allPeople,allCommons]=await Promise.all(responses.map(response=>response.json()));
      render();
      $('#dashboard-data-content').removeClass('dashboard-is-loading').attr('aria-busy', 'false');
    } catch(error) { console.error('Falha ao carregar dashboard:',error); $('<div class="alert alert-danger">Não foi possível carregar os indicadores do dashboard.</div>').insertAfter('.page-header'); }
  });
})();
