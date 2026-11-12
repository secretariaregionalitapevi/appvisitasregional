
    let currentData = [];
    let trendChart = null;
    let mixChart = null;
    let dashboardGroupContext = 'ALL';
    let dashboardRequestSequence = 0;
    const dashboardAccessLevel = 'null';
    const dashboardDefaultCommon = 'null';
    const dashboardDefaultCity = 'null';
    const dashboardCommons = JSON.parse(document.getElementById('dashboard-commons-data').textContent);
    const resetDashboardPeriodToCurrent = () => {
        const now = new Date();
        const currentYear = String(now.getFullYear());
        const currentMonth = String(now.getMonth() + 1);
        if (!$(`#filter-ano option[value="${currentYear}"]`).length) {
            $('#filter-ano').prepend(new Option(currentYear, currentYear));
        }
        $('#filter-ano').val(currentYear);
        $('#filter-mes').val(currentMonth);
    };

    const dashboardPeriodStorageKey = 'visitas-dashboard-period-v1';
    const rememberDashboardPeriod = () => {
        try {
            localStorage.setItem(dashboardPeriodStorageKey, JSON.stringify({
                year: $('#filter-ano').val(), month: $('#filter-mes').val()
            }));
        } catch (error) { /* O painel continua funcionando se o armazenamento estiver indisponivel. */ }
    };
    const restoreDashboardPeriod = () => {
        resetDashboardPeriodToCurrent();
        try {
            const saved = JSON.parse(localStorage.getItem(dashboardPeriodStorageKey));
            if (!saved || !/^\d{4}$/.test(saved.year) || !/^(all|[1-9]|1[0-2])$/.test(saved.month)) return;
            if (!$(`#filter-ano option[value="${saved.year}"]`).length) {
                $('#filter-ano').prepend(new Option(saved.year, saved.year));
            }
            $('#filter-ano').val(saved.year);
            $('#filter-mes').val(saved.month);
        } catch (error) { /* Sem preferencia valida, usar o mes vigente. */ }
    };

    const formatNum = (v) => new Intl.NumberFormat('pt-BR').format(v || 0);
    const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
    const formatDisplayText = value => {
        const rawText = String(value || '').trim();
        const regionalGroup = rawText.match(/^grupo\s+(rf|re|[a-z])$/i);
        if (regionalGroup) return `Grupo ${regionalGroup[1].toLocaleUpperCase('pt-BR')}`;
        const connectors = new Set(['a','as','da','das','de','do','dos','e','em','na','nas','no','nos']);
        return rawText.toLocaleLowerCase('pt-BR').split(/\s+/).map((word, index) => {
            if (/^[a-z]{2}-\d/i.test(word)) return word.toLocaleUpperCase('pt-BR');
            if (/^(?=[ivxlcdm]+$)m{0,4}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$/i.test(word)) return word.toLocaleUpperCase('pt-BR');
            if (index > 0 && connectors.has(word)) return word;
            return word.charAt(0).toLocaleUpperCase('pt-BR') + word.slice(1);
        }).join(' ');
    };
    const categoryPresentation = value => {
        const normalized = String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleUpperCase('pt-BR').trim();
        if (normalized === 'GVI' || normalized.includes('GRUPO DE VISITAS') || normalized.includes('MINISTERIO')) return {label:'GVI - Irmandade', css:'category-gvi'};
        if (normalized === 'GVM' || normalized.includes('MOCIDADE')) return {label:'GVM - Mocidade', css:'category-gvm'};
        if (normalized === 'GVE' || normalized === 'GVMU' || normalized.includes('ENCARREGADO') || normalized.includes('MUSICO') || normalized.includes('ORGANISTA')) return {label:'GVE - Músicos', css:'category-gve'};
        if (normalized === 'RF' || normalized.includes('REUNIAO FAMILIAR')) return {label:'RF - Reunião Familiar', css:'category-rf'};
        if (normalized === 'RE' || normalized.includes('EVANGELIZACAO')) return {label:'RE - Evangelização', css:'category-re'};
        return {label:formatDisplayText(value || 'Não informada'), css:'category-other'};
    };
    const agendaTeamType = item => {
        const explicit = String(item.equipe_tipo || '').toUpperCase();
        if (explicit === 'LOCAL' || explicit === 'REGIONAL') return explicit;
        const teamName = String(item.equipe_responsavel || '').trim();
        if (!teamName) return 'LOCAL';
        return /^Grupo\s+[A-Z]$/i.test(teamName) ? 'REGIONAL' : 'LOCAL';
    };
    const normalizedStatus = item => String(item.status || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    const saoPauloDayStart = date => `${date}T00:00:00-03:00`;
    const saoPauloNextDayStart = date => `${moment(date, 'YYYY-MM-DD', true).add(1, 'day').format('YYYY-MM-DD')}T00:00:00-03:00`;
    const sourceBadgeClass = status => {
        if (status === 'Agenda') return 'source-agenda';
        if (status === 'Mensal') return 'source-monthly';
        if (status === 'Mensal + Agenda') return 'source-combined';
        return 'source-default';
    };
    const contextDescriptions = {
        ALL: 'Visitas realizadas da agenda local e regional.',
        LOCAL: 'Visitas realizadas locais, incluindo registros sem equipe.',
        REGIONAL: 'Visitas realizadas pelos grupos regionais.'
    };
    const syncGroupContextWithCommon = commonSelection => {
        const hasSpecificCommon = Boolean(commonSelection && commonSelection !== '__all__');
        if (hasSpecificCommon) {
            dashboardGroupContext = 'LOCAL';
            $('[data-group-context]').removeClass('active').attr('aria-pressed', 'false');
            $('[data-group-context="LOCAL"]').addClass('active').attr('aria-pressed', 'true');
        }
        $('#context-description').text(contextDescriptions[dashboardGroupContext]);
    };

    const renderDashboards = (data, agendaData = []) => {
        if (!Array.isArray(data)) {
            console.error('Dados inválidos recebidos:', data);
            return;
        }
        
        const selectedCommon = $('#filter-comum').val();
        const scopedAgenda = agendaData.filter(item => !selectedCommon || selectedCommon === '__all__'
            || String(item.comum || '').trim() === selectedCommon);
        const contextualAgenda = dashboardGroupContext === 'ALL'
            ? scopedAgenda
            : scopedAgenda.filter(item => agendaTeamType(item) === dashboardGroupContext);
        const commonIdentity = comum => {
            const value = String(comum || '').trim().toUpperCase();
            const code = value.match(/BR-\d{2}-\d{4}/);
            return code ? code[0] : value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/\s+/g, ' ');
        };
        const getKey = (mes, ano, comum) => `${parseInt(mes, 10)}-${parseInt(ano, 10)}-${commonIdentity(comum)}`;
        const categoryKey = value => {
            const cat = String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().trim();
            if (cat === 'GVM' || cat.includes('MOCIDADE')) return 'gvm';
            if (cat === 'GVE' || cat === 'GVMU' || /MUSICO|ORGANISTA|ENCARREGADO/.test(cat)) return 'gve';
            if (cat === 'RF' || cat.includes('REUNIAO FAMILIAR')) return 'rf';
            if (cat === 'RE' || cat.includes('EVANGELIZACAO')) return 're';
            return 'gvi';
        };
        const realizedAgenda = contextualAgenda.filter(item => normalizedStatus(item).trim() === 'realizada');
        const agendaForTotals = realizedAgenda.filter(item => {
            if (!moment(item.data_inicio).isValid()) return false;
            return !selectedCommon || selectedCommon === '__all__'
                || commonIdentity(item.comum) === commonIdentity(selectedCommon);
        });
        let agendaGVI = 0, agendaGVM = 0, agendaGVE = 0, agendaRF = 0, agendaRE = 0;
        agendaForTotals.forEach(item => {
            const category = categoryKey(item.categoria);
            if (category === 'gvi') agendaGVI++;
            else if (category === 'gvm') agendaGVM++;
            else if (category === 'gve') agendaGVE++;
            else if (category === 'rf') agendaRF++;
            else if (category === 're') agendaRE++;
        });

        const totals = {
            gvi: agendaGVI, gvm: agendaGVM, gve: agendaGVE, rf: agendaRF, re: agendaRE
        };
        totals.visitas = totals.gvi + totals.gvm + totals.gve + totals.rf + totals.re;

        // Update KPIs
        $('#kpi-total').text(formatNum(totals.visitas));
        $('#kpi-gvi').text(formatNum(totals.gvi));
        $('#kpi-gvm').text(formatNum(totals.gvm));
        $('#kpi-gve').text(formatNum(totals.gve));
        $('#kpi-rf').text(formatNum(totals.rf));
        $('#kpi-re').text(formatNum(totals.re));

        const statusCount = status => contextualAgenda.filter(item => normalizedStatus(item).trim() === status).length;
        const realized = statusCount('realizada');
        const notRealized = statusCount('nao realizada');
        const cancelled = statusCount('cancelada');
        const durations = agendaForTotals.map(item => Number(item.duracao_minutos)).filter(value => Number.isFinite(value) && value > 0);
        const completionBase = realized + notRealized + cancelled;
        $('#ops-realizadas').text(formatNum(realized));
        $('#ops-nao-realizadas').text(formatNum(notRealized));
        $('#ops-canceladas').text(formatNum(cancelled));
        $('#ops-taxa').text(completionBase ? `${Math.round((realized / completionBase) * 100)}%` : '\u2014');
        const averageDuration = durations.length ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length) : null;
        const canSeeDurationAlert = dashboardAccessLevel === 'global' || dashboardAccessLevel === 'regional';
        $('#ops-duracao')
            .text(averageDuration !== null ? `${averageDuration} min` : '\u2014')
            .toggleClass('duration-alert', canSeeDurationAlert && averageDuration > 30);

        const contextLabel = dashboardGroupContext === 'LOCAL' ? 'Projeto local' : (dashboardGroupContext === 'REGIONAL' ? 'Projeto regional' : 'Geral');
        $('#exec-text').html(`<b>${contextLabel}: ${formatNum(totals.visitas)} visitas realizadas.</b> Somente registros da agenda com status Realizada, dentro da localidade e do per\u00edodo selecionados.`);

        // Agrupar somente as realizadas por comum e mes para a tabela.
        const tableMap = {};
        
        agendaForTotals.forEach(item => {
            const dt = moment(item.data_inicio);
            const mes = dt.month() + 1;
            const ano = dt.year();
            
            const comum = String(item.comum || '').trim();
            if (!comum || comum === 'null') return;
            
            const k = getKey(mes, ano, comum);

            if (!tableMap[k]) {
                tableMap[k] = { referencia_mes: mes, referencia_ano: ano, comum: comum, gvi: 0, gvm: 0, gve: 0, rf: 0, re: 0, status: 'Agenda' };
            }
            
            tableMap[k][categoryKey(item.categoria)]++;
            
            tableMap[k].total_visitas = tableMap[k].gvi + tableMap[k].gvm + tableMap[k].gve + tableMap[k].rf + tableMap[k].re;
        });

        const combinedTableData = Object.values(tableMap).sort((a, b) => {
            if (a.referencia_ano !== b.referencia_ano) return a.referencia_ano - b.referencia_ano;
            if (a.referencia_mes !== b.referencia_mes) return a.referencia_mes - b.referencia_mes;
            return a.comum.localeCompare(b.comum);
        });

        renderTrendChart(agendaForTotals, combinedTableData);
        renderMixChart(totals);
        renderRankingList(combinedTableData, agendaForTotals);
        renderTable(combinedTableData);
    };

    const renderTrendChart = (agendaData, combinedTableData = []) => {
        const mesFiltro = $('#filter-mes').val();
        const dataDe = $('#peridodo-de').val();
        const dataAte = $('#peridodo-ate').val();
        
        // Se filtramos por um mês específico ou período, agrupamos por Dia. Senão, por Mês.
        const agruparPorDia = (mesFiltro !== 'all') || (dataDe && dataAte);

        const seriesData = {};
        const emptyPoint = () => ({ gvi: 0, gvm: 0, gve: 0, rf: 0, re: 0 });
        const categoryKey = value => {
            const normalized = String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
            if (normalized === 'GVM' || normalized.includes('MOCIDADE')) return 'gvm';
            if (normalized === 'GVE' || normalized === 'GVMU' || normalized.includes('ENCARREGADO') || normalized.includes('MUSICO') || normalized.includes('ORGANISTA')) return 'gve';
            if (normalized === 'RF' || normalized.includes('REUNIAO FAMILIAR')) return 'rf';
            if (normalized === 'RE' || normalized.includes('EVANGELIZACAO')) return 're';
            return 'gvi';
        };
        
        if (agruparPorDia) {
            // Relatórios mensais não têm dia exato, então no gráfico diário plotamos apenas a Agenda.
            agendaData.forEach(d => {
                const key = moment(d.data_inicio).format('DD/MM');
                seriesData[key] ||= emptyPoint();
                seriesData[key][categoryKey(d.categoria)]++;
            });
        } else {
            // Gráfico Mensal: Plotamos a tabela combinada (Relatórios + Agenda)
            combinedTableData.forEach(d => {
                const mesStr = d.referencia_mes.toString().padStart(2, '0');
                const key = `${mesStr}/${d.referencia_ano}`;
                seriesData[key] ||= emptyPoint();
                ['gvi', 'gvm', 'gve', 'rf', 're'].forEach(category => seriesData[key][category] += Number(d[category] || 0));
            });
        }
        
        const cats = Object.keys(seriesData).sort((a, b) => {
            const formatStr = agruparPorDia ? 'DD/MM' : 'MM/YYYY';
            return moment(a, formatStr) - moment(b, formatStr);
        });
        const categorySeries = [
            { name: 'GVI', key: 'gvi' }, { name: 'GVM', key: 'gvm' },
            { name: 'Músicos (GVE)', key: 'gve' }, { name: 'RF', key: 'rf' }, { name: 'RE', key: 're' }
        ].map(item => ({ name: item.name, type: 'column', data: cats.map(cat => seriesData[cat][item.key]) }));
        const totals = cats.map(cat => Object.values(seriesData[cat]).reduce((sum, value) => sum + value, 0));

        // Se houver apenas 1 ponto de dados, um gráfico de área fica invisível (apenas um ponto). Mudamos para barra.
        const chartType = 'line';

        if (trendChart) trendChart.destroy();
        trendChart = new ApexCharts(document.querySelector("#chart-evolution"), {
            series: [...categorySeries, { name: 'Total', type: 'line', data: totals }],
            chart: { type: chartType, height: 320, stacked: true, stackOnlyBar: true, toolbar: { show: true, tools: { download: true, selection: false, zoom: false, zoomin: false, zoomout: false, pan: false, reset: false } } },
            colors: ['#348fe2', '#00acac', '#EE5622', '#5D2A42', '#B80C09', '#2d353c'],
            stroke: { curve: 'smooth', width: [0, 0, 0, 0, 0, 3] },
            markers: { size: [0, 0, 0, 0, 0, 4] },
            plotOptions: { bar: { columnWidth: '58%', borderRadius: 3 } },
            xaxis: { categories: cats, axisBorder: { show: false }, axisTicks: { show: false } },
            yaxis: { min: 0, forceNiceScale: true, labels: { formatter: value => Math.round(value) } },
            grid: { borderColor: '#eef1f4', strokeDashArray: 4 },
            legend: { position: 'top', horizontalAlign: 'left' },
            dataLabels: { enabled: false },
            tooltip: { shared: true, intersect: false, theme: 'light' },
            noData: { text: 'Sem dados para o contexto selecionado.' }
        });
        trendChart.render();
    };

    const renderMixChart = (totals) => {
        if (mixChart) mixChart.destroy();
        mixChart = new ApexCharts(document.querySelector("#chart-mix"), {
            series: [totals.gvi, totals.gvm, totals.gve, totals.rf, totals.re],
            chart: { type: 'donut', height: 300 },
            labels: ['Irmandade (GVI)', 'Mocidade (GVM)', 'Músicos (GVE)', 'Família (RF)', 'Evangelização (RE)'],
            colors: ['#348fe2', '#00acac', '#EE5622', '#5D2A42', '#B80C09'],
            legend: { position: 'bottom' },
            plotOptions: { pie: { donut: { size: '68%', labels: { show: true, name: { show: true }, value: { show: true, formatter: value => formatNum(value) }, total: { show: true, label: 'Total', formatter: () => formatNum(totals.visitas) } } } } },
            dataLabels: { enabled: true, formatter: value => `${Math.round(value)}%` },
            tooltip: {
                custom: function({series, seriesIndex, dataPointIndex, w}) {
                    return '<div style="background-color: #222 !important; color: #fff !important; padding: 6px 12px; border-radius: 4px; font-weight: bold; border: 1px solid #444; font-size: 13px; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">' +
                           w.config.labels[seriesIndex] + ': ' + series[seriesIndex] +
                           '</div>';
                }
            }
        });
        mixChart.render();
    };

    const renderRankingList = (data, agendaData = []) => {
        const ranking = {};
        data.forEach(item => {
            const common = formatDisplayText(item.comum || 'Localidade nao informada');
            ranking[common] = (ranking[common] || 0) + Number(item.total_visitas || 0);
        });
        const rows = Object.entries(ranking).sort((a, b) => b[1] - a[1]).slice(0, 10);
        const total = Object.values(ranking).reduce((sum, value) => sum + value, 0);
        const maximum = rows[0]?.[1] || 1;
        const container = $('#locality-ranking').empty();
        if (!rows.length) {
            container.html('<div class="ranking-empty"><i class="fa fa-info-circle me-1"></i>Sem localidades para o contexto selecionado.</div>');
            return;
        }
        if (rows.length === 1) {
            const [name, value] = rows[0];
            const daily = {};
            const activeTeams = new Set();
            agendaData.forEach(item => {
                const date = String(item.data_inicio || '').slice(0, 10);
                if (date) daily[date] = (daily[date] || 0) + 1;
                const rawTeam = String(item.equipe_responsavel || '').trim();
                const numberedTeam = rawTeam.match(/^Equipe(?:\s+de\s+visitas?)?\s+0*(\d+)$/i);
                const namedGroup = rawTeam.match(/^Grupo\s+(RF|RE|[A-Z])$/i);
                const canonicalTeam = numberedTeam
                    ? `Equipe ${Number(numberedTeam[1])}`
                    : (namedGroup ? `Grupo ${namedGroup[1].toUpperCase()}` : '');
                // Nomes avulsos de responsáveis não são novas equipes.
                // Sem um vínculo explícito, a visita permanece no total,
                // mas não infla o indicador de equipes atuantes.
                if (canonicalTeam) activeTeams.add(canonicalTeam);
            });
            const activeDays = Object.keys(daily).length;
            const dailyAverage = activeDays ? agendaData.length / activeDays : 0;
            const peak = Object.entries(daily).sort((a,b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0];
            const peakLabel = peak ? `${peak[0].split('-').reverse().slice(0,2).join('/')} · ${formatNum(peak[1])}` : '—';
            container.html(`<div class="locality-single">
                <div class="locality-single-main"><span class="ranking-position">1&ordm;</span><div class="locality-single-name"><strong>${escapeHtml(name)}</strong><span>Resultado da localidade no recorte selecionado</span></div><div class="locality-single-total"><strong>${formatNum(value)}</strong><span>Total de visitas</span></div></div>
                <div class="locality-category-grid">
                    <div class="locality-category" style="--category-color:#348fe2"><strong>${formatNum(activeDays)}</strong><span>Dias com visitas</span></div>
                    <div class="locality-category" style="--category-color:#00acac"><strong>${activeDays ? dailyAverage.toLocaleString('pt-BR',{maximumFractionDigits:1}) : '—'}</strong><span>Média por dia ativo</span></div>
                    <div class="locality-category" style="--category-color:#f59c1a"><strong>${peakLabel}</strong><span>Pico diário (data · visitas)</span></div>
                    <div class="locality-category" style="--category-color:#6c5ce7"><strong>${formatNum(activeTeams.size)}</strong><span>Equipes atuantes</span></div>
                </div>
            </div>`);
            return;
        }
        const grid = $('<div class="ranking-grid"></div>');
        const leftColumn = $('<div class="ranking-column"></div>');
        const rightColumn = $('<div class="ranking-column"></div>');
        rows.forEach(([name, value], index) => {
            const share = total ? (value / total) * 100 : 0;
            const item = $(`
                <div class="ranking-item">
                    <span class="ranking-position">${index + 1}&ordm;</span>
                    <div class="ranking-main">
                        <div class="ranking-name">${escapeHtml(name)}</div>
                        <div class="ranking-track" aria-hidden="true"><div class="ranking-fill" style="width:${Math.max(3, (value / maximum) * 100)}%"></div></div>
                    </div>
                    <div class="ranking-value"><span class="ranking-count">${formatNum(value)}</span><span class="ranking-share">${share.toLocaleString('pt-BR', {maximumFractionDigits: 1})}%</span></div>
                </div>`);
            (index < 5 ? leftColumn : rightColumn).append(item);
        });
        grid.append(leftColumn, rightColumn);
        container.append(grid);
    };

    const renderTable = (data) => {
        const existingTable = $.fn.DataTable.isDataTable('#table-visitas')
            ? $('#table-visitas').DataTable()
            : null;
        if (existingTable) existingTable.clear();
        const body = $('#table-visitas tbody').empty();

        const mesesAbreviados = ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'];

        data.forEach(item => {
            const mesStr = mesesAbreviados[parseInt(item.referencia_mes) - 1] || item.referencia_mes;
            const chronologicalKey = `${String(item.referencia_ano).padStart(4, '0')}${String(item.referencia_mes).padStart(2, '0')}`;
            body.append(`
                    <tr>
                        <td class="fw-bold text-nowrap" data-order="${chronologicalKey}">${mesStr}/${item.referencia_ano}</td>
                        <td>${item.comum}</td>
                        <td class="text-center">${item.gvi}</td>
                        <td class="text-center">${item.gvm}</td>
                        <td class="text-center">${item.gve || 0}</td>
                        <td class="text-center">${item.rf}</td>
                        <td class="text-center">${item.re}</td>
                        <td class="text-center fw-bold text-primary">${item.total_visitas}</td>
                        <td class="text-center">
                            <span class="source-badge ${sourceBadgeClass(item.status)}">${escapeHtml(item.status || '')}</span>
                        </td>
                    </tr>
                `);
        });
        if (existingTable) {
            const rows = body.children().detach();
            existingTable.rows.add(rows).draw();
            existingTable.responsive.recalc();
            return;
        }

        $('#table-visitas').DataTable({ 
            responsive: true,
            order: [[0, 'asc'], [1, 'asc']],
            language: { 
                url: 'https://cdn.datatables.net/plug-ins/1.13.4/i18n/pt-BR.json',
                paginate: { first: "«", previous: "‹", next: "›", last: "»" }
            }
        });
    };

    const applyFilters = async () => {
        const requestSequence = ++dashboardRequestSequence;
        let ano = $('#filter-ano').val();
        let mes = $('#filter-mes').val();
        const commonSelection = $('#filter-comum').val() || '';
        const comum = commonSelection === '__all__' ? '' : commonSelection;
        const municipio = $('#filter-municipio').val() || '';
        const dataDe = $('#peridodo-de').val();
        const dataAte = $('#peridodo-ate').val();

        if (ano === 'undefined' || !ano) ano = new Date().getFullYear();
        if (mes === 'undefined' || !mes) mes = 'all';

        try {
            currentData = [];

            const agendaParams = new URLSearchParams();
            if (dataDe) agendaParams.set('start_date', saoPauloDayStart(dataDe));
            if (dataAte) agendaParams.set('end_date', saoPauloNextDayStart(dataAte));

            if (!dataDe && !dataAte) {
                if (mes !== 'all') {
                    const startOfMonth = moment(`${ano}-${mes}-01`, 'YYYY-M-DD').startOf('month').format('YYYY-MM-DD');
                    const startOfNextMonth = moment(`${ano}-${mes}-01`, 'YYYY-M-DD').add(1, 'month').startOf('month').format('YYYY-MM-DD');
                    agendaParams.set('start_date', saoPauloDayStart(startOfMonth));
                    agendaParams.set('end_date', saoPauloDayStart(startOfNextMonth));
                } else {
                    agendaParams.set('start_date', saoPauloDayStart(`${ano}-01-01`));
                    agendaParams.set('end_date', saoPauloDayStart(`${Number(ano) + 1}-01-01`));
                }
            }
            if (municipio) agendaParams.set('municipio', municipio);
            if (comum) agendaParams.set('comum', comum);
            const agendaUrl = `/visitas/api/agenda/?${agendaParams.toString()}`;
            
            const resAgenda = await fetch(agendaUrl);
            const dataAgenda = await resAgenda.json();
            if (requestSequence !== dashboardRequestSequence) return;
            let filteredAgenda = [];
            if (!resAgenda.ok || dataAgenda.error) throw new Error(dataAgenda.error || 'Falha ao consultar a agenda.');
            if (Array.isArray(dataAgenda)) {
                // Production metrics include only visits with a final outcome.
                const finalStatuses = new Set(['realizada', 'nao realizada', 'cancelada']);
                filteredAgenda = dataAgenda.filter(item => finalStatuses.has(normalizedStatus(item).trim())
                    && (!comum || String(item.comum || '').trim() === comum)
                    && (!municipio || String(item.municipio || '').trim() === municipio));
                
                window.globalAgendaVisitas = filteredAgenda;
                window.dashboardAgendaData = filteredAgenda;
                const contextualFinalAgenda = dashboardGroupContext === 'ALL'
                    ? filteredAgenda
                    : filteredAgenda.filter(item => agendaTeamType(item) === dashboardGroupContext);
                renderRealizedVisits(contextualFinalAgenda.filter(item => normalizedStatus(item) === 'realizada'));
            }

            renderDashboards(currentData, filteredAgenda);

        } catch (err) {
            if (requestSequence !== dashboardRequestSequence) return;
            console.error('Erro de Sincronização:', err);
            Swal.fire({
                icon: 'error',
                title: 'Erro de Sincronização',
                text: err.message,
                confirmButtonColor: '#2c3e50',
                timer: 3000
            });
            renderDashboards([]);
            renderRealizedVisits([]);
        }
    };

    const renderRealizedVisits = (data) => {
        if ($.fn.DataTable.isDataTable('#table-visitas-realizadas')) $('#table-visitas-realizadas').DataTable().destroy();
        const body = $('#table-visitas-realizadas tbody').empty();

        data.forEach(item => {
            const visitDateValue = new Date(item.data_inicio);
            const visitDate = visitDateValue.toLocaleDateString('pt-BR', { timeZone: 'America/Sao_Paulo' });
            const scheduledTime = visitDateValue.toLocaleTimeString('pt-BR', { timeZone: 'America/Sao_Paulo', hour: '2-digit', minute: '2-digit' });
            const visitStartTime = item.horario_inicio || scheduledTime;
            const category = categoryPresentation(item.categoria);
            let statusBadge = '';
            if (item.status === 'Cancelada') {
                statusBadge = '<span class="badge bg-danger ms-2">Cancelada</span>';
            } else if (item.status === 'Não realizada') {
                statusBadge = '<span class="badge bg-warning text-dark ms-2">Não Realizada</span>';
            }
            const note = String(item.observacoes || '').trim();
            const duration = Number(item.duracao_minutos);
            const hasDuration = item.duracao_minutos !== null && item.duracao_minutos !== undefined
                && Number.isFinite(duration) && duration >= 0;
            const durationDisplay = hasDuration
                ? `<div class="visit-duration-line"><i class="fa fa-hourglass-half" aria-hidden="true"></i><span>Dura&ccedil;&atilde;o: ${duration} min</span></div>`
                : '';
            const observationDisplay = note
                ? escapeHtml(note)
                : '<span class="visit-note-empty">Sem observa&ccedil;&otilde;es</span>';
            body.append(`
                    <tr>
                        <td data-order="${visitDateValue.getTime()}">
                            <div class="visit-when">
                                <div class="visit-date"><i class="fa fa-calendar-o text-muted me-1" aria-hidden="true"></i>${visitDate}</div>
                                <div class="visit-time-line"><i class="fa fa-clock-o" aria-hidden="true"></i><span>${escapeHtml(visitStartTime)}</span></div>
                                ${durationDisplay}
                            </div>
                        </td>
                        <td>${escapeHtml(formatDisplayText(item.titulo) || '-')}</td>
                        <td>${escapeHtml(formatDisplayText(item.comum || item.endereco_visitado) || '-')}</td>
                        <td class="text-center"><span class="category-badge ${category.css}">${escapeHtml(category.label)}</span>${statusBadge}</td>
                        <td class="text-center">${escapeHtml(formatDisplayText(item.equipe_responsavel) || '-')}</td>
                        <td>${observationDisplay}</td>
                        <td class="text-center" style="white-space: nowrap;">
                            <button onclick="viewVisita('${item.id}')" class="btn btn-xs fw-bold text-white me-1 shadow-sm px-2" style="background-color: #00acac;"><i class="fa fa-eye me-1"></i> VER</button>
                            <button onclick="editVisita('${item.id}')" class="btn btn-xs fw-bold text-white me-1 shadow-sm px-2" style="background-color: #f5b041;"><i class="fa fa-edit me-1"></i> EDITAR</button>
                            <button class="btn btn-xs fw-bold text-white shadow-sm px-2" style="background-color: #ff5b57;" onclick="deleteAgendaEvent('${item.id}')"><i class="fa fa-trash me-1"></i> APAGAR</button>
                        </td>
                    </tr>
                `);
        });
        $('#table-visitas-realizadas').DataTable({ 
            responsive: true, 
            order: [[0, 'desc']],
            language: { 
                url: 'https://cdn.datatables.net/plug-ins/1.13.4/i18n/pt-BR.json',
                emptyTable: "Nenhuma visita realizada encontrada para o período e filtros selecionados.",
                paginate: { first: "«", previous: "‹", next: "›", last: "»" }
            }
        });
    };

    window.deleteAgendaEvent = async (id) => {
        const confirmed = await AppFeedback.confirm({title:'Excluir agendamento?',message:'O agendamento será removido definitivamente.',confirmText:'Sim, excluir'});
        if (!confirmed) return;
        const notice = AppFeedback.show({type:'loading',flow:'delete',title:'Excluindo agendamento',message:'Aguarde, o registro está sendo removido.'});
        try {
            const res = await fetch(`/visitas/api/agenda/?id=${id}`, {method:'DELETE',headers:{'X-CSRFToken':'null'}});
            if (!res.ok) { const body=await res.json(); throw new Error(body.error||'Não foi possível excluir o agendamento.'); }
            notice.close(); await applyFilters();
            AppFeedback.show({type:'success',title:'Agendamento excluído',message:'O registro foi removido e o painel foi atualizado.'});
        } catch (error) { notice.close(); AppFeedback.show({type:'error',title:'Não foi possível excluir',message:error.message}); }
    };

    window.viewVisita = (id) => openVisitaModal(id, false);
    window.editVisita = (id) => openVisitaModal(id, true);

    const openVisitaModal = (id, isEdit) => {
        const item = (window.globalAgendaVisitas || []).find(v => v.id == id);
        if (!item) return;

        $('#det-id').val(item.id);
        $('#det-data').val(item.data_inicio ? item.data_inicio.slice(0, 16) : '');
        $('#det-status').val(item.status || 'Agendada');
        $('#det-titulo').val(item.titulo || '');
        $('#det-categoria').val(item.categoria || 'GVI');
        $('#det-comum').val(item.comum || '');
        $('#det-equipe').val(item.equipe_responsavel || '');
        $('#det-endereco').val(item.endereco_visitado || '');
        $('#det-obs').val(item.observacoes || '');
        $('#det-justificativa').val(item.motivo_cancelamento || '');
        
        // Trigger status change para exibir justificativa se necessário
        setTimeout(() => $('#det-status').trigger('change'), 100);

        const inputs = $('#form-detalhes-visita input, #form-detalhes-visita select, #form-detalhes-visita textarea');
        if (isEdit) {
            inputs.prop('disabled', false);
            $('#btn-save-detalhes').removeClass('d-none');
            $('#detalhes-modal-title').html('<i class="fa fa-edit me-2"></i> Editar Visita');
            $('#modal-detalhes-visita .modal-header').removeClass('bg-teal').addClass('bg-warning');
        } else {
            inputs.prop('disabled', true);
            $('#btn-save-detalhes').addClass('d-none');
            $('#detalhes-modal-title').html('<i class="fa fa-info-circle me-2"></i> Detalhes da Visita');
            $('#modal-detalhes-visita .modal-header').removeClass('bg-warning').addClass('bg-teal');
        }
        $('#modal-detalhes-visita').modal('show');
    };

    window.updateDetalhesVisita = async (e) => {
        if (e) e.preventDefault();
        const id = $('#det-id').val();
        const data = {data_inicio:$('#det-data').val()?moment($('#det-data').val()).format('YYYY-MM-DDTHH:mm:ss-03:00'):null,status:$('#det-status').val(),titulo:$('#det-titulo').val(),categoria:$('#det-categoria').val(),equipe_responsavel:$('#det-equipe').val(),endereco_visitado:$('#det-endereco').val(),observacoes:$('#det-obs').val(),motivo_cancelamento:$('#det-justificativa').val()};
        const btn=$('#btn-save-detalhes'),notice=AppFeedback.show({type:'loading',flow:'update',title:'Atualizando visita',message:'Aguarde, as alterações estão sendo salvas.'});
        btn.prop('disabled',true).html('<i class="fa fa-spinner fa-spin"></i> Salvando...');
        try { const res=await fetch(`/visitas/api/agenda/?id=${id}`,{method:'PATCH',headers:{'Content-Type':'application/json','X-CSRFToken':'null'},body:JSON.stringify(data)}); if(!res.ok){let body={};try{body=await res.json()}catch(e){}throw new Error(body.error||body.message||'Erro ao salvar no servidor')} notice.close();$('#modal-detalhes-visita').modal('hide');await applyFilters();AppFeedback.show({type:'success',title:'Visita atualizada',message:'As alterações foram salvas e o painel foi atualizado.'}); }
        catch(error){notice.close();AppFeedback.show({type:'error',title:'Não foi possível atualizar',message:error.message})}
        finally{btn.prop('disabled',false).html('Salvar Alterações')}
    };

    const saveVisit = async () => {
        const formData={referencia_ano:parseInt($('#fv-ano').val()),referencia_mes:parseInt($('#fv-mes').val()),municipio:'null',cidade:'null',comum:$('#fv-comum').val(),gvi:parseInt($('#fv-gvi').val()||0),gvm:parseInt($('#fv-gvm').val()||0),gve:parseInt($('#fv-gve').val()||0),rf:parseInt($('#fv-rf').val()||0),re:parseInt($('#fv-re').val()||0),observacoes:$('#fv-obs').val(),status:'Lançado'};
        const btn=$('#btn-save'),notice=AppFeedback.show({type:'loading',flow:'save',title:'Salvando fechamento',message:'Aguarde, o relatório está sendo validado e gravado.'});
        btn.prop('disabled',true).html('<i class="fa fa-spinner fa-spin"></i> Salvando...');
        try {const res=await fetch('/visitas/api/dashboard/',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':'null'},body:JSON.stringify(formData)}),body=await res.json();if(!res.ok)throw new Error(body.error||body.details||'Erro ao salvar');notice.close();$('#modal-nova-visita').modal('hide');await applyFilters();AppFeedback.show({type:'success',title:body.operation==='updated'?'Fechamento atualizado':'Fechamento registrado',message:body.operation==='updated'?'O fechamento existente foi atualizado sem criar duplicidade.':'O relatório foi gravado e o painel foi atualizado.'});}
        catch(error){notice.close();AppFeedback.show({type:'error',title:'Não foi possível salvar',message:error.message})}
        finally{btn.prop('disabled',false).text('Salvar Lançamento')}
    };

    const exportPDF = () => {
        try {
            const { jsPDF } = window.jspdf;
            const doc = new jsPDF('landscape');

            const pageWidth = doc.internal.pageSize.getWidth();
            const userName = 'null';
            const start = $('#peridodo-de').val(), end = $('#peridodo-ate').val();
            const period = start || end ? `${start ? moment(start).format('DD/MM/YYYY') : 'início'} a ${end ? moment(end).format('DD/MM/YYYY') : 'hoje'}` : 'Todos os lançamentos';
            const drawHeader = pageNumber => {
                doc.setTextColor(0,0,0); doc.setFont('helvetica','bold'); doc.setFontSize(16);
                doc.text('CONGREGAÇÃO CRISTÃ NO BRASIL', pageWidth / 2, 15, {align:'center'});
                doc.setFont('helvetica','normal'); doc.setFontSize(10); doc.text('Regional Itapevi - São Paulo', pageWidth / 2, 21, {align:'center'});
                doc.setTextColor(30,75,122); doc.setFont('helvetica','bold'); doc.setFontSize(12); doc.text('CONTROLE REGIONAL DE VISITAS', pageWidth / 2, 29, {align:'center'});
                doc.setTextColor(70,70,70); doc.setFont('helvetica','normal'); doc.setFontSize(10); doc.text('Relatório Consolidado de Visitas', pageWidth / 2, 34, {align:'center'});
                doc.setTextColor(0,0,0); doc.setFontSize(8); doc.text(`Página ${pageNumber}`, pageWidth - 14, 8, {align:'right'});
                doc.text(`Emissão: ${moment().format('DD/MM/YYYY')}`, pageWidth - 14, 15, {align:'right'}); doc.text(`Período: ${period}`, pageWidth - 14, 20, {align:'right'}); window.AppReportIdentity.jsPdfHeader(doc,pageWidth-14,25);
                doc.setTextColor(100,100,100); doc.setFontSize(7); doc.text(`${moment().format('DD/MM/YYYY')} às ${moment().format('HH:mm')}`, pageWidth - 14, 29, {align:'right'});
            };

            doc.autoTable({
                html: '#table-visitas',
                startY: 42,
                margin: { top: 42 },
                theme: 'grid',
                styles: { fontSize: 8 },
                headStyles: { fillColor: [30, 75, 122], textColor: 255 },
                alternateRowStyles: { fillColor: [245, 245, 245] },
                didDrawPage: data => drawHeader(data.pageNumber)
            });

            window.AppReportIdentity.jsPdfFooter(doc,userName);doc.save(`Relatorio_Visitas_${moment().format('YYYYMMDD')}.pdf`);
        } catch (err) {
            console.error('Erro ao gerar PDF:', err);
            Swal.fire('Erro', 'Ocorreu um erro ao gerar o PDF.', 'error');
        }
    };

    const exportExcel = () => {
        try {
            const table = document.getElementById('table-visitas');
            const wb = XLSX.utils.table_to_book(table, { sheet: "Visitas" });
            XLSX.writeFile(wb, `Relatorio_Visitas_${moment().format('YYYYMMDD')}.xlsx`);
        } catch (err) {
            console.error('Erro ao gerar Excel:', err);
            Swal.fire('Erro', 'Ocorreu um erro ao gerar o Excel.', 'error');
        }
    };

    $(document).ready(function () {
        restoreDashboardPeriod();
        const rebuildDashboardCommons = (municipio, selected = '') => {
            const select = $('#filter-comum');
            if (select.hasClass('select2-hidden-accessible')) select.select2('destroy');
            select.empty();
            if (dashboardAccessLevel !== 'local') select.append(new Option('Todas as comuns', '__all__'));
            dashboardCommons.filter(item => !municipio || item.cidade === municipio).forEach(item => select.append(new Option(item.comum, item.comum)));
            select.val(selected || (dashboardAccessLevel === 'local' ? dashboardDefaultCommon : '__all__'));
            select.prop('disabled', dashboardAccessLevel === 'local').select2({
                width: '100%', language: 'pt-BR',
                placeholder: 'Pesquise pelo código ou nome da comum...',
                allowClear: dashboardAccessLevel !== 'local',
                dropdownParent: $('.dashboard-common-filter')
            });
        };
        const municipalitySelect = $('#filter-municipio');
        const hasDefaultCity = municipalitySelect.find('option').toArray().some(option => option.value === dashboardDefaultCity);
        if (dashboardDefaultCity && hasDefaultCity) municipalitySelect.val(dashboardDefaultCity);
        rebuildDashboardCommons(municipalitySelect.val() || dashboardDefaultCity, dashboardDefaultCommon);
        syncGroupContextWithCommon($('#filter-comum').val() || '');
        $('#filter-municipio').on('change', function () {
            rebuildDashboardCommons($(this).val(), '');
            applyFilters();
        });
        $('#filter-comum').on('change', function () {
            syncGroupContextWithCommon($(this).val() || '');
            applyFilters();
        });

        $('[data-group-context]').on('click', function () {
            if ($(this).prop('disabled')) return;
            dashboardGroupContext = $(this).data('group-context');
            $('[data-group-context]').removeClass('active').attr('aria-pressed', 'false');
            $(this).addClass('active').attr('aria-pressed', 'true');
            $('#context-description').text(contextDescriptions[dashboardGroupContext]);
            const agenda = window.dashboardAgendaData || [];
            const contextualAgenda = dashboardGroupContext === 'ALL' ? agenda : agenda.filter(item => agendaTeamType(item) === dashboardGroupContext);
            renderDashboards(currentData, agenda);
            renderRealizedVisits(contextualAgenda.filter(item => normalizedStatus(item) === 'realizada'));
        });

        $('#filter-ano, #filter-mes').on('change', rememberDashboardPeriod);

        // Auto-update on filter change
        $('#filter-ano, #filter-mes, #peridodo-de, #peridodo-ate').on('change', applyFilters);

        $('#btn-refresh').click(() => {
            applyFilters().then(() => {
                Swal.fire({
                    icon: 'info',
                    title: 'Painel Atualizado',
                    text: `Sincronização concluída: ${(window.dashboardAgendaData || []).filter(item => normalizedStatus(item).trim() === 'realizada').length} visitas realizadas processadas.`,
                    confirmButtonColor: '#2c3e50',
                    timer: 3000
                });
            });
        });

        $('#btn-clear').click(() => {
            resetDashboardPeriodToCurrent();
            rememberDashboardPeriod();
            if (dashboardAccessLevel === 'regional' || dashboardAccessLevel === 'global') $('#filter-municipio').val(dashboardDefaultCity);
            rebuildDashboardCommons(
                $('#filter-municipio').val() || dashboardDefaultCity,
                dashboardDefaultCommon
            );
            syncGroupContextWithCommon($('#filter-comum').val() || '');
            $('#peridodo-de, #peridodo-ate').val('');
            applyFilters();
        });

        $('#btn-pdf').click(exportPDF);
        $('#btn-excel').click(exportExcel);

        $('#form-visita').on('submit', (e) => { e.preventDefault(); saveVisit(); });

        $('#det-status').on('change', function() {
            const status = $(this).val();
            if (status === 'Cancelada' || status === 'Não realizada') {
                $('#div-det-justificativa').removeClass('d-none');
            } else {
                $('#div-det-justificativa').addClass('d-none');
            }
        });

        // Initial load with small delay to ensure DOM is ready
        setTimeout(applyFilters, 100);
    });
