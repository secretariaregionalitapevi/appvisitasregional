
document.addEventListener('DOMContentLoaded', () => {
  let reportRows = [], reportTrends = [];
  let rankingChart = null, statusChart = null, effectivenessChart = null, trendChart = null;
  const reportAccessLevel = 'null';
  const userName = 'null';
  const q = id => document.getElementById(id);
  const today = new Date();
  for (let year = today.getFullYear() + 1; year >= today.getFullYear() - 5; year--) q('report-year').add(new Option(year, year));
  q('report-year').value = String(today.getFullYear());
  q('report-month').value = String(today.getMonth() + 1);
  const esc = value => String(value ?? '').replace(/[&<>\"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[char]));
  const number = value => Number(value || 0);
  const effectiveness = row => {
    const closed = number(row.realizadas) + number(row.nao_realizadas) + number(row.canceladas);
    return closed ? Math.round(number(row.realizadas) * 100 / closed) : 0;
  };
  const sortRanking = rows => [...rows].sort((a,b) => number(b.realizadas) - number(a.realizadas) || effectiveness(b) - effectiveness(a) || String(a.equipe).localeCompare(String(b.equipe), 'pt-BR'));
  const activeType = () => q('regional-report').classList.contains('active') ? 'REGIONAL' : 'LOCAL';
  const teamLabel = (row, compact=false) => row.tipo === 'LOCAL' ? `${row.equipe}${compact ? '' : ` • ${row.comum}`}` : `${row.equipe}${compact || !row.municipio ? '' : ` • ${row.municipio}`}`;
  const renderTable = (id, rows, regional=false) => {
    const ranked = sortRanking(rows);
    q(id).innerHTML = ranked.length ? ranked.map((row,index) => {
      const rate = effectiveness(row);
      return `<tr><td><span class="rank-pill">${index + 1}</span></td><td>${esc(row.municipio)}</td>
        <td class="team-cell"><strong>${esc(row.equipe)}</strong>${regional ? '' : `<small>${esc(row.comum)}</small>`}</td>
        <td><strong>${number(row.total)}</strong></td><td class="text-success fw-semibold">${number(row.realizadas)}</td><td>${number(row.agendadas)}</td><td>${number(row.nao_realizadas)}</td><td>${number(row.canceladas)}</td>
        <td><div class="d-flex align-items-center gap-2"><div class="rate-bar"><span style="width:${rate}%"></span></div><strong>${rate}%</strong></div></td></tr>`;
    }).join('') : `<tr><td colspan="9" class="empty-state">Nenhum registro encontrado no período selecionado.</td></tr>`;
  };
  const renderMetrics = rows => {
    const totals = rows.reduce((acc,row) => { ['total','realizadas','agendadas','nao_realizadas','canceladas'].forEach(key => acc[key] += number(row[key])); return acc; }, {total:0,realizadas:0,agendadas:0,nao_realizadas:0,canceladas:0});
    const closed = totals.realizadas + totals.nao_realizadas + totals.canceladas;
    q('metric-total').textContent = totals.total.toLocaleString('pt-BR'); q('metric-realized').textContent = totals.realizadas.toLocaleString('pt-BR');
    q('metric-scheduled').textContent = totals.agendadas.toLocaleString('pt-BR'); q('metric-rate').textContent = `${closed ? Math.round(totals.realizadas * 100 / closed) : 0}%`;
    q('metric-teams').textContent = `${rows.length} ${rows.length === 1 ? 'equipe' : 'equipes'}`;
  };
  const renderPodium = rows => {
    const top = sortRanking(rows).slice(0,3);
    q('report-podium').innerHTML = top.length ? top.map((row,index) => `<div class="podium-place ${index === 0 ? 'first' : ''}"><div class="podium-rank">${index + 1}º</div><div class="podium-name" title="${esc(teamLabel(row))}">${esc(teamLabel(row))}</div><div class="podium-score">${number(row.realizadas)}</div><div class="podium-caption">visitas realizadas</div></div>`).join('') : '<div class="empty-state">Sem resultados para formar o pódio.</div>';
  };
  const destroyCharts = () => { [rankingChart,statusChart,effectivenessChart,trendChart].forEach(chart => chart?.destroy()); rankingChart = statusChart = effectivenessChart = trendChart = null; };
  const renderCharts = rows => {
    destroyCharts();
    const ranked = sortRanking(rows).slice(0,10), labels = ranked.map(row => teamLabel(row, true));
    const base = {chart:{fontFamily:'inherit',toolbar:{show:false},animations:{speed:450}},noData:{text:'Nenhum resultado no período'},grid:{borderColor:'#edf1f5'},tooltip:{theme:'light'}};
    rankingChart = new ApexCharts(q('ranking-chart'), {...base,chart:{...base.chart,type:'bar',height:350},series:[{name:'Realizadas',data:ranked.map(row=>number(row.realizadas))}],colors:['#21a366'],plotOptions:{bar:{horizontal:true,borderRadius:5,barHeight:'48%',distributed:true}},dataLabels:{enabled:true},legend:{show:false},xaxis:{categories:labels,labels:{style:{fontSize:'10px'}}},yaxis:{labels:{maxWidth:180,style:{fontSize:'10px',fontWeight:500}}}});
    statusChart = new ApexCharts(q('status-chart'), {...base,chart:{...base.chart,type:'bar',height:330,stacked:true},series:[{name:'Realizadas',data:ranked.map(row=>number(row.realizadas))},{name:'Não realizadas',data:ranked.map(row=>number(row.nao_realizadas))},{name:'Canceladas',data:ranked.map(row=>number(row.canceladas))}],colors:['#21a366','#f59c1a','#ef5350'],plotOptions:{bar:{borderRadius:4,columnWidth:'48%'}},dataLabels:{enabled:false},xaxis:{categories:labels,labels:{rotate:-25,trim:true,style:{fontSize:'9px'}}},legend:{position:'top',horizontalAlign:'right',fontSize:'10px'}});
    const totals = rows.reduce((acc,row) => { acc[0]+=number(row.realizadas); acc[1]+=number(row.nao_realizadas); acc[2]+=number(row.canceladas); return acc; },[0,0,0]);
    effectivenessChart = new ApexCharts(q('effectiveness-chart'), {...base,chart:{...base.chart,type:'donut',height:330},series:totals,labels:['Realizadas','Não realizadas','Canceladas'],colors:['#21a366','#f59c1a','#ef5350'],plotOptions:{pie:{donut:{size:'68%',labels:{show:true,total:{show:true,label:'Concluídas',formatter:()=>totals.reduce((a,b)=>a+b,0)}}}}},dataLabels:{enabled:true,formatter:value=>`${Math.round(value)}%`},legend:{position:'bottom'}});
    const trendRows = reportTrends.filter(row => row.tipo === activeType());
    const monthLabel = value => { const [year,month] = value.split('-'); return `${month}/${year.slice(2)}`; };
    trendChart = new ApexCharts(q('trend-chart'), {...base,chart:{...base.chart,type:'line',height:320},series:[
      {name:'Concluídas',type:'column',data:trendRows.map(row=>number(row.total))},
      {name:'Realizadas',type:'area',data:trendRows.map(row=>number(row.realizadas))},
      {name:'Efetividade',type:'line',data:trendRows.map(row=>effectiveness(row))}
    ],colors:['#b9d8f7','#21a366','#123c67'],stroke:{width:[0,3,3],curve:'smooth',dashArray:[0,0,5]},fill:{opacity:[.8,.18,1],type:['solid','gradient','solid']},markers:{size:[0,4,4],strokeWidth:2,hover:{size:6}},dataLabels:{enabled:false},xaxis:{categories:trendRows.map(row=>monthLabel(row.mes))},yaxis:[{title:{text:'Quantidade'},min:0},{opposite:true,min:0,max:100,title:{text:'Efetividade (%)'},labels:{formatter:value=>`${Math.round(value)}%`}}],legend:{position:'top',horizontalAlign:'right',itemMargin:{horizontal:10,vertical:0}},tooltip:{shared:true,intersect:false}});
    rankingChart.render(); statusChart.render(); effectivenessChart.render(); trendChart.render();
  };
  const renderDashboard = () => { const rows = reportRows.filter(row => row.tipo === activeType()); renderMetrics(rows); renderPodium(rows); renderCharts(rows); };
  const commonCatalog = Array.from(q('report-common').options).slice(1).map(option => ({value:option.value, city:option.dataset.city}));
  const rebuildCommonSearch = (city, selected='') => {
    const select = q('report-common'), $select = jQuery(select);
    if ($select.hasClass('select2-hidden-accessible')) $select.select2('destroy');
    select.replaceChildren(new Option('Todas', ''));
    commonCatalog.filter(item => !city || item.city === city).forEach(item => select.add(new Option(item.value, item.value)));
    select.value = commonCatalog.some(item => item.value === selected && (!city || item.city === city)) ? selected : '';
    $select.prop('disabled', reportAccessLevel === 'local').select2({width:'100%',language:'pt-BR',placeholder:'Digite o código ou nome da comum...',allowClear:false,dropdownParent:jQuery('.report-common-filter')});
  };
  const activeReport = () => {
    const regional = q('regional-report').classList.contains('active');
    return {
      table: q(regional ? 'regional-report-table' : 'local-report-table'),
      rows: reportRows.filter(row => row.tipo === (regional ? 'REGIONAL' : 'LOCAL')),
      title: regional ? 'Relatório de Grupos Regionais por Município' : 'Relatório de Equipes Locais por Comum',
      sheet: regional ? 'Grupos Regionais' : 'Equipes Locais',
      file: regional ? 'Grupos_Regionais' : 'Equipes_Locais',
    };
  };
  const periodDescription = () => {
    const parts = [];
    if (q('report-start').value) parts.push(`Início: ${q('report-start').value.split('-').reverse().join('/')}`);
    if (q('report-end').value) parts.push(`Fim: ${q('report-end').value.split('-').reverse().join('/')}`);
    if (parts.length) return parts.join(' | ');
    return q('report-month').value === 'all' ? `Ano de ${q('report-year').value}` : `${q('report-month').selectedOptions[0].text} de ${q('report-year').value}`;
  };
  const locationDescription = () => {
    const parts = [];
    if (q('report-city').value) parts.push(`Município: ${q('report-city').value}`);
    if (q('report-common').value) parts.push(`Comum: ${q('report-common').value}`);
    return parts.join(' | ') || 'Todas as localidades';
  };
  async function load() {
    const params = new URLSearchParams({ano:q('report-year').value, mes:q('report-month').value, inicio:q('report-start').value, fim:q('report-end').value, municipio:q('report-city').value, comum:q('report-common').value});
    q('report-loading').classList.add('show');
    try {
      const response = await fetch(`/visitas/api/relatorios-equipes/?${params}`), data = await response.json();
      if (!response.ok) return window.alert(data.error || 'Falha ao gerar relatório.');
      reportRows = data.rows || [];
      reportTrends = data.trends || [];
      renderTable('local-body', data.local || []);
      renderTable('regional-body', data.regional || [], true);
      renderDashboard();
    } catch (error) {
      window.alert('Não foi possível atualizar os indicadores. Verifique sua conexão e tente novamente.');
    } finally {
      q('report-loading').classList.remove('show');
    }
  }
  q('report-filters').onsubmit = event => { event.preventDefault(); load(); };
  [q('report-year'), q('report-month')].forEach(input => input.onchange = () => { q('report-start').value = ''; q('report-end').value = ''; });
  q('report-city').onchange = () => rebuildCommonSearch(q('report-city').value);
  document.querySelectorAll('[data-bs-toggle="tab"]').forEach(tab => tab.addEventListener('shown.bs.tab', renderDashboard));
  q('export-excel').onclick = () => {
    const report = activeReport();
    if (!report.rows.length) return window.alert('Não há registros nesta aba para exportar.');
    const regional = report.rows[0]?.tipo === 'REGIONAL';
    const headers = regional
      ? ['Município','Grupo regional','Concluídas','Realizadas','Agendadas','Não realizadas','Canceladas']
      : ['Município','Comum','Equipe','Concluídas','Realizadas','Agendadas','Não realizadas','Canceladas'];
    const period = periodDescription();
    const location = locationDescription();
    const rows = [
      ['CONGREGAÇÃO CRISTÃ NO BRASIL'],
      ['Regional Itapevi - São Paulo'],
      [regional ? 'GRUPOS REGIONAIS DE VISITAS' : 'EQUIPES LOCAIS DE VISITAS'],
      [report.title],
      ['Período', period],
      ['Localidade', location],
      ['Responsável', 'Secretaria Regional da Música'],
      ['Impresso em', new Date().toLocaleString('pt-BR')],
      [], headers,
      ...report.rows.map(row => regional
        ? [row.municipio,row.equipe,row.total,row.realizadas,row.agendadas,row.nao_realizadas,row.canceladas]
        : [row.municipio,row.comum,row.equipe,row.total,row.realizadas,row.agendadas,row.nao_realizadas,row.canceladas])
    ];
    rows.push([],['Impresso por:',userName]);
    const worksheet = XLSX.utils.aoa_to_sheet(rows);
    worksheet['!merges'] = [0,1,2,3].map(row => ({s:{r:row,c:0},e:{r:row,c:headers.length-1}}));
    worksheet['!cols'] = headers.map((header,index) => ({wch:index < (regional?2:3) ? 34 : Math.max(14,header.length+2)}));
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, report.sheet);
    XLSX.writeFile(workbook, `${report.file}_${new Date().toISOString().slice(0,10).replaceAll('-','')}.xlsx`);
  };
  q('export-pdf').onclick = () => {
    const report = activeReport();
    if (!report.rows.length) return window.alert('Não há registros nesta aba para exportar.');
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF('landscape');
    const pageWidth = doc.internal.pageSize.getWidth();
    const regional = report.rows[0]?.tipo === 'REGIONAL';
    const headers = regional
      ? [['Município','Grupo regional','Concluídas','Realizadas','Agendadas','Não realizadas','Canceladas']]
      : [['Município','Comum','Equipe','Concluídas','Realizadas','Agendadas','Não realizadas','Canceladas']];
    const body = report.rows.map(row => regional
      ? [row.municipio,row.equipe,row.total,row.realizadas,row.agendadas,row.nao_realizadas,row.canceladas]
      : [row.municipio,row.comum,row.equipe,row.total,row.realizadas,row.agendadas,row.nao_realizadas,row.canceladas]);
    const now = new Date();
    const drawHeader = pageNumber => {
      doc.setTextColor(0,0,0); doc.setFont('helvetica','bold'); doc.setFontSize(16);
      doc.text('CONGREGAÇÃO CRISTÃ NO BRASIL', pageWidth / 2, 15, {align:'center'});
      doc.setFont('helvetica','normal'); doc.setFontSize(10);
      doc.text('Regional Itapevi - São Paulo', pageWidth / 2, 21, {align:'center'});
      doc.setTextColor(30,75,122); doc.setFont('helvetica','bold'); doc.setFontSize(12);
      doc.text(regional ? 'GRUPOS REGIONAIS DE VISITAS' : 'EQUIPES LOCAIS DE VISITAS', pageWidth / 2, 29, {align:'center'});
      doc.setTextColor(70,70,70); doc.setFont('helvetica','normal'); doc.setFontSize(10);
      doc.text(report.title, pageWidth / 2, 34, {align:'center'});
      doc.setTextColor(0,0,0); doc.setFontSize(8);
      doc.text(`Página ${pageNumber}`, pageWidth - 14, 8, {align:'right'});
      doc.text(`Emissão: ${now.toLocaleDateString('pt-BR')}`, pageWidth - 14, 15, {align:'right'});
      doc.text(`Período: ${periodDescription()}`, pageWidth - 14, 20, {align:'right'});
      doc.text(`Localidade: ${locationDescription()}`, pageWidth - 14, 25, {align:'right'});
      window.AppReportIdentity.jsPdfHeader(doc,pageWidth-14,30);
      doc.setTextColor(100,100,100); doc.setFontSize(7);
      doc.text(`${now.toLocaleDateString('pt-BR')} às ${now.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})}`, pageWidth - 14, 34, {align:'right'});
    };
    const totals = report.rows.reduce((acc,row) => { ['total','realizadas','agendadas','nao_realizadas','canceladas'].forEach(key => acc[key] += number(row[key])); return acc; },{total:0,realizadas:0,agendadas:0,nao_realizadas:0,canceladas:0});
    const closed = totals.realizadas + totals.nao_realizadas + totals.canceladas;
    const summary = [['CONCLUÍDAS',totals.total,[52,143,226]],['REALIZADAS',totals.realizadas,[33,163,102]],['AGENDADAS',totals.agendadas,[245,156,26]],['EFETIVIDADE',`${closed ? Math.round(totals.realizadas*100/closed) : 0}%`,[40,183,216]]];
    const drawExecutiveSummary = () => {
      summary.forEach((item,index) => {
        const x = 14 + index * 40;
        doc.setFillColor(247,249,252); doc.setDrawColor(224,230,237); doc.roundedRect(x,40,36,23,2,2,'FD');
        doc.setFillColor(...item[2]); doc.roundedRect(x+3,44,3,15,1,1,'F');
        doc.setTextColor(105,118,132); doc.setFont('helvetica','bold'); doc.setFontSize(6.5); doc.text(item[0],x+9,47);
        doc.setTextColor(23,36,59); doc.setFontSize(14); doc.text(String(item[1]),x+9,57);
      });
      const top = sortRanking(report.rows).slice(0,5), max = Math.max(...top.map(row=>number(row.realizadas)),1);
      doc.setTextColor(23,36,59); doc.setFont('helvetica','bold'); doc.setFontSize(7); doc.text('TOP 5 - VISITAS REALIZADAS',181,42);
      top.forEach((row,index) => {
        const y = 47 + index*3.6, value = number(row.realizadas), label = teamLabel(row,true).slice(0,23);
        doc.setTextColor(75,88,102); doc.setFont('helvetica','normal'); doc.setFontSize(5.8); doc.text(`${index+1}. ${label}`,181,y);
        doc.setFillColor(232,237,243); doc.roundedRect(224,y-2.4,50,2.2,.8,.8,'F');
        doc.setFillColor(33,163,102); doc.roundedRect(224,y-2.4,50*value/max,2.2,.8,.8,'F');
        doc.setTextColor(23,36,59); doc.setFont('helvetica','bold'); doc.text(String(value),278,y,{align:'right'});
      });
    };
    drawHeader(1); drawExecutiveSummary();
    doc.autoTable({head:headers,body,startY:70,margin:{top:46},theme:'grid',styles:{fontSize:8},headStyles:{fillColor:[30,75,122],textColor:255},alternateRowStyles:{fillColor:[245,245,245]},didDrawPage:data=>{ drawHeader(data.pageNumber); if(data.pageNumber === 1) drawExecutiveSummary(); }});
    window.AppReportIdentity.jsPdfFooter(doc,userName);doc.save(`${report.file}_${new Date().toISOString().slice(0,10).replaceAll('-','')}.pdf`);
  };
  rebuildCommonSearch(q('report-city').value, q('report-common').value);
  load();
});
