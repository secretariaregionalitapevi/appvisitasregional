(() => {
  const $=s=>document.querySelector(s), {request,esc,date}=window.MusicEventsDashboard;
  let data=null, controller=null, version=0;
  const statusNames={PRESENTE:'Presente',JUSTIFICOU:'J · Justificou',NAO_JUSTIFICOU:'NJ · Não justificou',SEM_ENCARREGADO:'SE · Sem encarregado',ENFERMO:'EF · Enfermo',NAO_INFORMADO:'Não informado'};
  const n=value=>Number(value||0).toLocaleString('pt-BR');
  const pct=(value,base)=>value==null?(base===0?'Não se aplica':'Sem base SAM'):`${value.toLocaleString('pt-BR',{maximumFractionDigits:1})}%`;
  const panelCities=()=>window.MusicMultiSelect.values($('#events-city'));
  function syncFromPanel(){
    const cities=panelCities(),joint=['COTIA','CAUCAIA DO ALTO','VARGEM GRANDE PAULISTA'];
    const value=cities.length===3&&joint.every(city=>cities.includes(city))?'ADMIN_COTIA':cities.length>1?'PANEL_SELECTION':cities[0]||'';
    if(value&&![...$('#annual-city').options].some(option=>option.value===value))$('#annual-city').add(new Option(value==='PANEL_SELECTION'?'Municípios selecionados no painel':value,value));
    $('#annual-city').value=value;
  }
  function params(city=$('#annual-city').value){
    const query=new URLSearchParams({ano:$('#annual-year').value});
    (city==='PANEL_SELECTION'?panelCities():city==='ADMIN_COTIA'?['COTIA','CAUCAIA DO ALTO','VARGEM GRANDE PAULISTA']:city?[city]:[]).forEach(value=>query.append('municipio',value));
    window.MusicMultiSelect.values($('#events-common')).forEach(value=>query.append('comum',value));
    return query;
  }
  function render(){
    if(!data)return;
    const filter=$('#annual-status').value, rows=data.rows.filter(row=>!filter||row[filter]);
    const groups=[
      {title:'Itapevi e Pirapora do Bom Jesus · Janeiro / Maio / Setembro',cities:['ITAPEVI','PIRAPORA DO BOM JESUS']},
      {title:'Cotia, Caucaia, VGP, Jandira e Santana · Março / Julho / Novembro',cities:['COTIA','CAUCAIA DO ALTO','VARGEM GRANDE PAULISTA','JANDIRA','SANTANA DE PARNAÍBA']}
    ];
    const summary=data.summary;
    $('#annual-metrics').innerHTML=[['Comuns acompanhadas',summary.commons],['Sem registro dos três públicos',summary.no_participation],['Nenhum músico registrado',summary.no_musicians],['Nenhuma organista registrada',summary.no_organists],['Sem registro do encarregado',summary.no_leader]].map(([label,value])=>`<div><small>${label}</small><strong>${n(value)}</strong></div>`).join('');
    $('#annual-city-reports').innerHTML='<span>PDF por município:</span>'+data.selected_cities.map(city=>`<button type="button" class="btn btn-sm btn-white border" data-annual-city="${esc(city)}">${esc(city)}</button>`).join('');
    $('#annual-tables').innerHTML=groups.map(group=>{
      const groupRows=rows.filter(row=>group.cities.includes(row.municipio));
      if(!groupRows.length)return '';
      const dates=[...new Set(groupRows.flatMap(row=>row.cells.map(cell=>cell.date)))].sort();
      const columns=dates.length+3;
      let municipality=null;
      return `<h4 class="px-3 py-3 mb-0 fs-6">${esc(group.title)}</h4><div class="table-responsive annual-table-scroll mb-4"><table class="table events-table annual-table mb-0"><thead><tr><th>Município / comum / encarregado cadastrado</th><th>Cadastro SAM<br>Músicos / Organistas</th>${dates.map(day=>`<th>${date(day)}<br><button type="button" class="btn btn-sm btn-white border" data-annual-date="${day}">PDF deste ensaio</button></th>`).join('')}<th>Participação no ano</th></tr></thead><tbody>`+groupRows.map(row=>{
      const municipalityHeading=municipality!==row.municipio?`<tr class="events-city-group"><th colspan="${columns}">${esc(row.municipio)}</th></tr>`:'';
      municipality=row.municipio;
      const cells=new Map(row.cells.map(cell=>[cell.date,cell]));
      const readings=[];
      const leaderCount=Number(row.leader_sessions||0), loadedCount=Number(row.loaded_sessions||0);
      const leaderBadge=loadedCount?`<strong class="annual-leader-total ${leaderCount===0?'annual-leader-zero':leaderCount===loadedCount?'annual-leader-full':'annual-leader-partial'}">Encarregado local: ${leaderCount}/${loadedCount} presenças</strong>`:'<strong>Encarregado local: sem dados carregados</strong>';
      if(row.no_musicians)readings.push('Nenhum músico');
      if(row.no_organists)readings.push('Nenhuma organista');
      if(row.no_leader)readings.push('Sem registro do encarregado');
      return municipalityHeading+`<tr${row.no_participation?' class="annual-no-participation"':''}><td><small>${esc(row.municipio)}</small><strong>${esc(row.comum)}</strong><small>${esc(row.encarregado_nome)}</small></td><td><div class="annual-base"><span>MÚSICOS <b>${row.cadastro_musicos??'—'}</b></span><span>ORGANISTAS <b>${row.cadastro_organistas??'—'}</b></span></div></td>${dates.map(day=>{
        const cell=cells.get(day);
        if(!cell)return '<td class="annual-outside">Não previsto neste ciclo</td>';
        if(!cell.loaded)return '<td class="annual-outside">Sem dados carregados</td>';
        const status=cell.leader_attendance??(['PRESENTE','JUSTIFICOU','SEM_ENCARREGADO','ENFERMO'].includes(cell.leader_status)?cell.leader_status:'NAO_JUSTIFICOU');
        const onList=status==='PRESENTE',leader={PRESENTE:'PRESENTE',JUSTIFICOU:'JUSTIFICOU',NAO_JUSTIFICOU:'NJ',SEM_ENCARREGADO:'SEM ENCARREGADO',ENFERMO:'ENFERMO'}[status];
        const places=onList?(cell.leader_valid_locations??cell.leader_locations).filter(local=>!['LOCAL A CONFERIR','NÃO INFORMADO'].includes(local.toUpperCase())):[];
        const noLeader=!onList, noThree=cell.musicians===0&&cell.organists===0&&noLeader;
        return `<td${noThree?' class="annual-missing-three"':''}><div class="annual-attendance"><span${cell.musicians===0?' class="annual-missing-category" title="SEM MÚSICO REGISTRADO NESTE ENSAIO"':''}>Músicos <b>${n(cell.musicians)}</b> <small>${pct(cell.musician_percent,row.cadastro_musicos)}</small></span><span${cell.organists===0?' class="annual-missing-category" title="SEM ORGANISTA REGISTRADA NESTE ENSAIO"':''}>Organistas <b>${n(cell.organists)}</b> <small>${pct(cell.organist_percent,row.cadastro_organistas)}</small></span></div><div class="annual-leader conductor-status ${status} ${status==='NAO_JUSTIFICOU'?'annual-missing-category':''}">Encarregado local: ${esc(leader)}</div>${places.length?`<small>LOCAL: ${esc(places.join(' / '))}</small>`:''}${noThree?'<small class="annual-missing-label">SEM REGISTRO DOS TRÊS PÚBLICOS</small>':''}${cell.unresolved?'<small class="text-warning">Conciliação de comuns pendente</small>':''}</td>`;
      }).join('')}<td>${leaderBadge}<small>Com músicos: ${row.musician_sessions} · Com organistas: ${row.organist_sessions} · Com encarregado local: ${row.leader_sessions}</small><small>${esc(row.reading)}</small><small>Cobertura dos dados: ${loadedCount}/${row.expected_sessions??3} ensaios carregados${row.year_complete?'':' · Ano ainda incompleto'}</small>${readings.length?`<small>${readings.map(esc).join(' · ')}</small>`:''}</td></tr>`;
    }).join('')+'</tbody></table></div>';
    }).join('')||'<div class="events-empty">Nenhuma comum para os filtros selecionados.</div>';
    $('#annual-note').textContent=data.note;
  }
  async function load(force=false){
    const current=++version;controller?.abort();controller=new AbortController();
    $('#annual-refresh').disabled=true;$('#annual-pdf').disabled=true;
    $('#annual-message').textContent='Carregando o ano completo…';
    try{
      const query=params();if(force===true)query.set('atualizar','1');
      const result=await request('/musica/eventos/api/anual/?'+query,{signal:controller.signal});
      if(current!==version)return;
      data=result;
      const city=$('#annual-city').value;
      $('#annual-city').innerHTML='<option value="">Todos os municípios</option>'+(['COTIA','CAUCAIA DO ALTO','VARGEM GRANDE PAULISTA'].every(c=>data.cities.includes(c))?'<option value="ADMIN_COTIA">Administração: Cotia / Caucaia / VGP</option>':'')+data.cities.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('');
      $('#annual-city').value=city;
      if(city==='PANEL_SELECTION'){$('#annual-city').add(new Option('Municípios selecionados no painel',city));$('#annual-city').value=city;}
      $('#annual-message').textContent=`Ano ${data.year} · ${data.sessions.filter(s=>s.loaded).length} datas com dados carregados. Acompanhamento separado por ciclo e município. Itapevi / Pirapora: janeiro, maio e setembro. Demais municípios: março, julho e novembro. Encarregado local: PRESENTE, J, NJ, SE ou EF.`;
      render();$('#annual-pdf').disabled=false;
    }catch(error){if(current===version&&error.name!=='AbortError')$('#annual-message').textContent=error.message;}
    finally{if(current===version){$('#annual-refresh').disabled=false;controller=null;}}
  }
  async function download(city,day,button){
    if(!data||button?.disabled)return;
    if(window.AppExport){
      const query=params(city);if(day)query.set('data',day);if($('#annual-status').value)query.set('situacao',$('#annual-status').value);
      const ok=await AppExport.download(button,'/musica/eventos/anual/exportar-pdf/?'+query,{filename:`Ensaios_Regionais_${data.year}.pdf`});
      if(ok)$('#annual-message').textContent='PDF gerado com os filtros de munic?pio e ano selecionados.';
      return;
    }
    const restore=window.MusicEventsDashboard.generating(button);
    const query=params(city);if(day)query.set('data',day);if($('#annual-status').value)query.set('situacao',$('#annual-status').value);
    $('#annual-message').textContent='Gerando o PDF com o acompanhamento e a grade por ensaio…';
    try{
      const response=await fetch('/musica/eventos/anual/exportar-pdf/?'+query,{cache:'no-store'});
      if(!response.ok||response.redirected){let message='Não foi possível gerar o PDF.';try{message=(await response.json()).error||message;}catch{}throw Error(message);}
      const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');
      link.href=url;link.download=window.MusicEventsDashboard.downloadName(response,`Ensaios_Regionais_${data.year}.pdf`);link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      $('#annual-message').textContent='PDF gerado com os filtros de município e ano selecionados.';
    }catch(error){$('#annual-message').textContent=error.message;}finally{restore();}
  }
  document.querySelector('[data-view="annual"]').addEventListener('click',()=>{syncFromPanel();if(!data&&!controller)void load();});
  $('#events-city').addEventListener('change',()=>{syncFromPanel();data=null;if(!document.querySelector('[data-view-panel="annual"]').hidden)void load();});
  $('#events-common').addEventListener('change',()=>{data=null;if(!document.querySelector('[data-view-panel="annual"]').hidden)void load();});
  document.addEventListener('music-events-data',()=>{
    data=null;
    if(!document.querySelector('[data-view-panel="annual"]').hidden&&!controller)void load();
  });
  $('#annual-refresh').onclick=()=>load(true);
  $('#annual-city').onchange=()=>{
    const city=$('#annual-city').value;
    const cities=city==='PANEL_SELECTION'?panelCities():city==='ADMIN_COTIA'?['COTIA','CAUCAIA DO ALTO','VARGEM GRANDE PAULISTA']:city?[city]:[];
    window.MusicMultiSelect.setValues($('#events-city'),cities);window.MusicMultiSelect.refresh($('#events-city'));
    $('#events-city').dispatchEvent(new Event('change',{bubbles:true}));
  };
  $('#annual-year').onchange=load;$('#annual-status').onchange=render;
  $('#events-pdf').addEventListener('click',event=>{
    if(!document.querySelector('[data-view-panel="annual"]').hidden){event.preventDefault();event.stopImmediatePropagation();void download(undefined,undefined,event.currentTarget);}
  },true);
  $('#annual-pdf').onclick=event=>download(undefined,undefined,event.currentTarget);
  $('#annual-city-reports').onclick=event=>{const button=event.target.closest('[data-annual-city]');if(button)void download(button.dataset.annualCity,undefined,button);};
  $('#annual-tables').onclick=event=>{const button=event.target.closest('[data-annual-date]');if(button)void download(undefined,button.dataset.annualDate,button);};
})();
