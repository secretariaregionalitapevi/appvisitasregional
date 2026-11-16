(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const number = value => Number(value || 0).toLocaleString('pt-BR');
  const percent = value => value == null ? 'Sem base' : `${Number(value).toLocaleString('pt-BR', {maximumFractionDigits:2})}%`;
  const date = value => value.split('-').reverse().join('/');
  const tones = {MUSICO:'#128879', ORGANISTA:'#bf3976', CORDAS:'#337dc1', MADEIRAS:'#7959b6', METAIS:'#a76c0b', OUTROS:'#61788a'};
  const icons = {MUSICO:'fa-music', ORGANISTA:'fa-keyboard', CORDAS:'fa-music', MADEIRAS:'fa-music', METAIS:'fa-music', OUTROS:'fa-music'};
  const choices = new Map();
  let current, target;
  const metric = (row, candidates) => candidates ? {base:row.candidate_base, present:row.candidate_present, rate:row.candidate_percent} : {base:row.registered, present:row.present, rate:row.percent};
  const width = rate => Math.min(100, Math.max(0, Number(rate) || 0));
  const track = rate => `<span class="sam-meter" aria-hidden="true"><span style="width:${width(rate)}%"></span></span>`;
  function counts(m) {
    return `<span class="sam-counts"><span><span class="sam-count-label">Cadastrados</span><span class="sam-count-value">${number(m.base)}</span></span><span><span class="sam-count-label">Presentes</span><span class="sam-count-value">${number(m.present)}</span></span></span>`;
  }
  function comparisonTable(rows, candidates, groups, cities) {
    return `<div class="sam-matrix-caption">${candidates?'Candidatos e candidatas':'Orquestra'} · Participação e presentes / cadastrados em cada categoria.</div><div class="table-responsive"><table class="table events-table sam-matrix mb-0"><thead><tr><th scope="col">Município de origem</th>${groups.map(group=>`<th scope="col"><span style="--sam-tone:${tones[group.group]}"><i class="fa ${icons[group.group]}" aria-hidden="true"></i>${esc(group.label)}</span></th>`).join('')}</tr></thead><tbody>${cities.map(city=>`<tr><th scope="row">${esc(city)}</th>${groups.map(group=>{
      const row=rows.find(row=>row.city===city&&row.group===group.group);
      if(!row)return '<td>—</td>';
      const m=metric(row,candidates);
      return `<td style="--sam-tone:${tones[row.group]}"><strong class="${m.present>m.base?'sam-divergent':''}">${percent(m.rate)}</strong><span><b>${number(m.present)}</b> / ${number(m.base)}</span>${m.present>m.base?'<small class="sam-matrix-warning">Conferir cadastro e presenças</small>':''}</td>`;
    }).join('')}</tr>`).join('')}</tbody></table></div>`;
  }
  function cityPanels(rows, cities, state, total, groups) {
    return `<div class="sam-municipality-grid ${groups.length===1?'sam-one-category':''}">${cities.map(city=>{
      const cityRows=rows.filter(row=>row.city===city);
      const focus=cityRows.find(row=>row.group===state.group);
      const rate=focus?metric(focus,state.candidates).rate:null;
      const delta=rate!=null&&total.rate!=null?Math.round((rate-total.rate)*100)/100:null;
      const comparison=delta==null?'Sem base para comparação':delta===0?'Mesma participação do recorte':`${Math.abs(delta).toLocaleString('pt-BR',{maximumFractionDigits:2})} p.p. ${delta>0?'acima':'abaixo'} do recorte`;
      return `<article class="sam-city-panel"><header class="sam-city-panel-heading"><h5><i class="fa fa-location-dot" aria-hidden="true"></i>${esc(city)}</h5><span class="sam-city-comparison ${delta>0?'is-above':''}">${esc(focus?.label||'Categoria em destaque')} · ${comparison}</span></header><div class="sam-city-kpis" style="--sam-kpi-columns:${Math.max(1,cityRows.length)}">${cityRows.map(row=>{
        const m=metric(row,state.candidates);
        return `<section class="sam-local-kpi ${row.group===state.group?'is-focused':''}" style="--sam-tone:${tones[row.group]}" aria-label="${esc(row.label)} de ${esc(city)}"><div class="sam-local-title"><i class="fa ${icons[row.group]}" aria-hidden="true"></i><h6>${esc(row.label)}</h6>${row.group===state.group?'<i class="fa fa-check" aria-hidden="true"></i>':''}</div><strong class="sam-local-rate ${m.present>m.base?'sam-divergent':''}">${percent(m.rate)}</strong><span class="sam-local-caption">de participação</span>${track(m.rate)}${counts(m)}${m.present>m.base?'<p class="sam-city-warning">Conferir cadastro e presenças</p>':''}</section>`;
      }).join('')}</div></article>`;
    }).join('')}</div>`;
  }
  function eventPanel(id) {
    const summaries = current.summaries.filter(row => row.event_id === id && row.group !== 'OUTROS');
    const state = choices.get(id) || {group:summaries[0].group, candidates:false, view:'cards', sort:'city'};
    if (!summaries.some(row => row.group === state.group)) state.group = summaries[0].group;
    choices.set(id, state);
    const selected = summaries.find(row => row.group === state.group);
    const total = metric(selected, state.candidates);
    const allRows = current.rows.filter(row => row.event_id === id && row.group !== 'OUTROS');
    const rows = allRows.filter(row => row.group === state.group).sort((a,b) => state.sort === 'rate' ?
      (metric(b,state.candidates).rate ?? -1) - (metric(a,state.candidates).rate ?? -1) || a.city.localeCompare(b.city,'pt-BR') : a.city.localeCompare(b.city,'pt-BR'));
    const cities=[...new Set(allRows.map(row=>row.city))].sort((a,b)=>{
      if(state.sort==='rate'){
        const first=rows.find(row=>row.city===a),second=rows.find(row=>row.city===b);
        const difference=(second?metric(second,state.candidates).rate??-1:-1)-(first?metric(first,state.candidates).rate??-1:-1);
        if(difference)return difference;
      }
      return a.localeCompare(b,'pt-BR');
    });
    const withPresence = rows.filter(row => row.city!=='LOCALIDADE A CONFERIR' && metric(row,state.candidates).present > 0).length;
    const ranked = rows.filter(row => metric(row,state.candidates).rate != null && metric(row,state.candidates).present > 0 && metric(row,state.candidates).present <= metric(row,state.candidates).base)
      .sort((a,b) => metric(b,state.candidates).rate - metric(a,state.candidates).rate);
    const best = ranked[0];
    const candidate = metric(selected, true);
    return `<section class="sam-event-panel" data-sam-event="${esc(id)}" style="--sam-tone:${tones[state.group]}">
      <div class="sam-event-title"><div><span class="sam-event-date"><i class="fa fa-calendar-days" aria-hidden="true"></i>${esc(date(selected.date))}</span><h3>${esc(selected.event)}</h3></div><div class="sam-segment" role="group" aria-label="Público da comparação"><button type="button" data-sam-mode="all" aria-pressed="${!state.candidates}">Orquestra</button><button type="button" data-sam-mode="candidates" aria-pressed="${state.candidates}">Candidatos(as)</button></div></div>
      <div class="sam-category-cards" style="--sam-category-count:${summaries.length}" role="group" aria-label="Selecionar categoria">${summaries.map(row => {
        const m = metric(row, state.candidates);
        return `<button type="button" class="sam-category-card" style="--sam-tone:${tones[row.group]}" data-sam-category="${row.group}" aria-pressed="${row.group===state.group}" aria-label="${esc(row.label)}: ${percent(m.rate)} de participação. Destacar nos indicadores municipais."><span class="sam-category-title"><span class="sam-category-icon"><i class="fa ${icons[row.group]}" aria-hidden="true"></i></span><span>${esc(row.label)}</span><i class="fa fa-check sam-selected-mark" aria-hidden="true"></i></span><span class="sam-category-rate ${m.present>m.base?'sam-divergent':''}">${percent(m.rate)}</span><span class="sam-rate-caption">de participação</span>${track(m.rate)}${counts(m)}</button>`;
      }).join('')}</div>
      <div class="sam-insight-grid" aria-label="Indicadores do recorte">
        <article class="sam-insight-card" style="--sam-tone:#1e4b7a"><div class="sam-insight-title"><span>Participação do recorte</span><i class="fa fa-chart-simple" aria-hidden="true"></i></div><strong class="${total.present>total.base?'sam-divergent':''}">${percent(total.rate)}</strong><p><b>${number(total.present)}</b> presentes de <b>${number(total.base)}</b> cadastrados</p>${track(total.rate)}</article>
        <article class="sam-insight-card" style="--sam-tone:#128879"><div class="sam-insight-title"><span>Alcance municipal</span><i class="fa fa-map-location-dot" aria-hidden="true"></i></div><strong>${withPresence}<small> / ${current.scope_city_count ?? cities.length}</small></strong><p>municípios com presença em ${esc(selected.label).toLocaleLowerCase('pt-BR')}</p><span class="sam-insight-foot">${state.candidates?'Candidatos e candidatas':'Orquestra'}</span></article>
        <article class="sam-insight-card" style="--sam-tone:#337dc1"><div class="sam-insight-title"><span>Maior participação municipal</span><i class="fa fa-arrow-trend-up" aria-hidden="true"></i></div><strong>${best?percent(metric(best,state.candidates).rate):'Sem comparação'}</strong><p>${best?esc(best.city):'Não há presença com base válida para comparar.'}</p><span class="sam-insight-foot">${esc(selected.label)} no recorte</span></article>
        <article class="sam-insight-card" style="--sam-tone:#7959b6"><div class="sam-insight-title"><span>Candidatos(as)</span><i class="fa fa-user-graduate" aria-hidden="true"></i></div><div class="sam-insight-pair"><strong>${number(candidate.present)}</strong><span>${percent(candidate.rate)}</span></div><p>presentes de <b>${number(candidate.base)}</b> cadastrados</p><span class="sam-insight-foot">Fora da contagem da orquestra</span></article>
      </div>
      <div class="sam-explore-heading"><div><h4>Indicadores por município</h4><p>${state.candidates?'Candidatos e candidatas':'Orquestra'} · Destaque: <strong>${esc(selected.label)}</strong> · ${cities.length} ${cities.length===1?'município':'municípios'}</p></div><div class="sam-explore-tools"><label class="sam-sort"><span>Ordenar</span><select data-sam-sort aria-label="Ordenar municípios pela categoria em destaque"><option value="city" ${state.sort==='city'?'selected':''}>Município</option><option value="rate" ${state.sort==='rate'?'selected':''}>Maior participação</option></select></label><div class="sam-segment sam-view-switch" role="group" aria-label="Visualização dos indicadores"><button type="button" data-sam-view="cards" aria-pressed="${state.view==='cards'}"><i class="fa fa-grip" aria-hidden="true"></i><span>KPIs</span></button><button type="button" data-sam-view="table" aria-pressed="${state.view==='table'}"><i class="fa fa-table-columns" aria-hidden="true"></i><span>Comparativo</span></button></div></div></div>
      <p class="sam-category-context"><i class="fa fa-circle-info" aria-hidden="true"></i>Cordas, Madeiras e Metais detalham os músicos. Os naipes não devem ser somados novamente ao total.</p>
      <div class="sam-municipal-content">${cities.length?(state.view==='table'?comparisonTable(allRows,state.candidates,summaries,cities):cityPanels(allRows,cities,state,total,summaries)):'<p class="sam-empty">Sem registros neste recorte.</p>'}</div></section>`;
  }
  function render() {
    const ids = [...new Set(current.summaries.map(row => row.event_id))];
    const diagnostics = [
      current.unresolved_registry ? `${number(current.unresolved_registry)} cadastro(s) com comum não reconhecida.` : '',
      current.undefined_instrument ? `${number(current.undefined_instrument)} cadastro(s) sem instrumento definido; cargos musicais permanecem na base, sem naipe definido.` : '',
      current.unresolved_present ? `${number(current.unresolved_present)} presença(s) sem comum reconhecida, mantidas somente quando o município de origem está identificado.` : ''
    ].filter(Boolean).join(' ');
    target.innerHTML = `<div class="sam-dashboard"><header class="sam-dashboard-heading"><div><span class="sam-source-label"><span></span>Referência atual do SAM</span><h2>Participação musical</h2><p>Do cadastro à presença. Explore o alcance de cada categoria na Regional.</p></div><div class="sam-export-actions"><button type="button" class="btn btn-sm btn-white border" data-sam-export="excel" title="Exportar todas as categorias e níveis do recorte"><i class="fa fa-file-excel text-success" aria-hidden="true"></i>Excel</button><button type="button" class="btn btn-sm btn-white border" data-sam-export="pdf" title="Exportar todas as categorias e níveis do recorte"><i class="fa fa-file-pdf text-danger" aria-hidden="true"></i>PDF</button></div></header>
      <details class="sam-method"><summary><span><i class="fa fa-circle-info" aria-hidden="true"></i>Critérios da consulta</span>${diagnostics?'<span class="sam-review-badge">Há registros para conferência</span>':''}<i class="fa fa-chevron-down" aria-hidden="true"></i></summary><div><p>${esc(current.criterion)}</p><p>Filtros de município e comum recortam a base e as presenças. O filtro de local recorta apenas os presentes. Cada evento é calculado separadamente. Os naipes compõem o total de músicos. Candidatos(as) são medidos separadamente e não integram a orquestra.</p>${diagnostics?`<p class="sam-diagnostic">${esc(diagnostics)}</p>`:''}</div></details>
      ${!current.available?'<div class="sam-no-base"><i class="fa fa-circle-info" aria-hidden="true"></i>Não há cadastro musical reconhecido neste recorte. Percentuais sem base ficam indisponíveis.</div>':''}
      ${ids.map(eventPanel).join('') || '<p class="sam-empty">Selecione um evento e um recorte da Regional para consultar a participação.</p>'}</div>`;
    target.querySelectorAll('[data-sam-export]').forEach(button => {
      button.disabled = !ids.length;
      button.onclick = () => window.MusicEventsDashboard.download(button.dataset.samExport, 'participacao', {}, button);
    });
  }
  document.addEventListener('music-events-data', event => {
    target = document.getElementById('events-sam-participation');
    if (!target) return;
    current = event.detail.sam_participation;
    if (!current) { target.innerHTML = '<p class="sam-empty">Referência SAM indisponível.</p>'; return; }
    render();
    target.onclick = event => {
      const button = event.target.closest('[data-sam-category], [data-sam-mode], [data-sam-view]');
      if (!button) return;
      const id = button.closest('[data-sam-event]').dataset.samEvent;
      const state = choices.get(id);
      if (button.dataset.samCategory) state.group = button.dataset.samCategory;
      if (button.dataset.samMode) state.candidates = button.dataset.samMode === 'candidates';
      if (button.dataset.samView) state.view = button.dataset.samView;
      const key = button.dataset.samCategory ? 'data-sam-category' : button.dataset.samMode ? 'data-sam-mode' : 'data-sam-view';
      const value = button.getAttribute(key);
      render();
      const section = [...target.querySelectorAll('[data-sam-event]')].find(item => item.dataset.samEvent === id);
      section?.querySelector(`[${key}="${value}"]`)?.focus({preventScroll:true});
    };
    target.onchange = event => {
      if (!event.target.matches('[data-sam-sort]')) return;
      const id = event.target.closest('[data-sam-event]').dataset.samEvent;
      choices.get(id).sort = event.target.value;
      render();
      const section = [...target.querySelectorAll('[data-sam-event]')].find(item => item.dataset.samEvent === id);
      section?.querySelector('[data-sam-sort]')?.focus({preventScroll:true});
    };
  });
})();
