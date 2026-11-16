from pathlib import Path
p=Path('static/js/music-events-justifications.js')
t=p.read_text(encoding='utf-8')
old='''<div class="table-responsive"><table class="table events-table"><thead><tr><th><input id="just-select-all" type="checkbox" aria-label="Selecionar todas as justificativas visíveis"></th><th>Nome / comum / município</th><th>Motivo</th><th>Lote / origem</th><th class="justification-actions-cell">Ações</th></tr></thead><tbody id="just-saved"></tbody></table></div>'''
new='''<label class="justification-select-all"><input id="just-select-all" type="checkbox"> Selecionar todas as justificativas deste evento e lote</label><div id="just-saved" class="justification-city-groups"></div>'''
assert t.count(old)==1
t=t.replace(old,new)
start=t.index("    $('saved').innerHTML = visibleRows().map(r => ")
end=t.index('\n    selectionState();',start)
old_render=t[start:end]
row_start=old_render.index('`<tr>')
row_end=old_render.index("`).join('')")
row_template=old_render[row_start:row_end+1]
replacement='''    const groups = new Map();
    visibleRows().forEach(row => {
      const city = String(row.municipio || 'Município não informado').trim().toLocaleUpperCase('pt-BR');
      if (!groups.has(city)) groups.set(city, []);
      groups.get(city).push(row);
    });
    const renderRow = r => ROW_TEMPLATE;
    $('saved').innerHTML = [...groups].sort(([a],[b]) => a.localeCompare(b,'pt-BR')).map(([city,rows]) => {
      rows.sort((a,b) => String(a.comum_nome||'').replace(/^BR-\\d+-\\d+\\s*-\\s*/i,'').localeCompare(String(b.comum_nome||'').replace(/^BR-\\d+-\\d+\\s*-\\s*/i,''),'pt-BR') || String(a.nome||'').localeCompare(String(b.nome||''),'pt-BR'));
      return `<details class="justification-city" data-just-city="${esc(city)}" ${expandedMunicipalities.has(city)?'open':''}>
        <summary><span class="justification-city-label"><i class="fa fa-location-dot" aria-hidden="true"></i><strong>${esc(city)}</strong></span><span class="justification-city-count">${rows.length} ${rows.length===1?'justificativa':'justificativas'}</span><i class="fa fa-chevron-down justification-city-chevron" aria-hidden="true"></i></summary>
        <div class="table-responsive"><table class="table events-table mb-0"><thead><tr><th aria-label="Seleção"></th><th>Nome / comum</th><th>Motivo</th><th>Lote / origem</th><th class="justification-actions-cell">Ações</th></tr></thead><tbody>${rows.map(renderRow).join('')}</tbody></table></div>
      </details>`;
    }).join('') || '<p class="justification-empty">Nenhuma justificativa neste evento e lote.</p>';'''
replacement=replacement.replace('ROW_TEMPLATE',row_template)
t=t[:start]+replacement+t[end:]
marker="  const visibleRows = () => saved.filter"
i=t.index(marker)
t=t[:i]+'''  const expandedMunicipalities = new Set();
  $('saved').addEventListener('toggle', event => {
    const city = event.target.dataset?.justCity;
    if (!city) return;
    if (event.target.open) expandedMunicipalities.add(city); else expandedMunicipalities.delete(city);
  }, true);
'''+t[i:]
t=t.replace("if (listedEvent !== event) { $('lot')", "if (listedEvent !== event) { expandedMunicipalities.clear(); $('lot')")
p.write_bytes(t.replace('\r\n','\n').replace('\n','\r\n').encode('utf-8'))
template=Path('ColorAdminApp/templates/pages/music_events.html')
b=template.read_bytes().replace(b'20261116-reason-summary-1',b'20261116-justifications-cities-1').replace(b'20261115-detail-cards-1',b'20261116-justifications-cities-1')
template.write_bytes(b)
