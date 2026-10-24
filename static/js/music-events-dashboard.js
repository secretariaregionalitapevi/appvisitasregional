(() => {
  const $=s=>document.querySelector(s), multi=window.MusicMultiSelect;
  multi.setupAll($('.music-events'));
  const category=$('.music-events').dataset.eventCategory;
  const state={items:[],data:null,page:0,version:0};
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const date=v=>v?String(v).slice(0,10).split('-').reverse().join('/'):'—';
  function downloadName(response,fallback){const header=response.headers.get('Content-Disposition')||'',utf8=header.match(/filename\*=UTF-8''([^;]+)/i);if(utf8){try{return decodeURIComponent(utf8[1]);}catch{}}return header.match(/filename="([^"]+)"/)?.[1]||fallback;}
  const number=v=>Number(v||0).toLocaleString('pt-BR');
  const kind=e=>e.tipo==='ENSAIO_REGIONAL'?'Ensaio Regional':e.familia==='GERAL'?'RT Geral':`RT · ${e.familia.charAt(0)+e.familia.slice(1).toLocaleLowerCase('pt-BR')}`;
  function eventLabel(e){const day=date(e.data_evento);let title=String(e.titulo||kind(e)).replace(/\bensaio regional\b/gi,'Ensaio Regional');title=title.split(day).join('').split(String(e.data_evento).slice(0,10)).join('').replace(/^[\s·|–—:-]+|[\s·|–—:-]+$/g,'').trim();return `${title||kind(e)} · ${day}`;}
  const feedback=(message,tone='danger')=>{$('#events-feedback').innerHTML=message?`<div class="alert alert-${tone}">${esc(message)}</div>`:'';};
  async function request(url,options){const r=await fetch(url+(url.includes('?')?'&':'?')+'categoria='+encodeURIComponent(category),{cache:'no-store',...options});if(r.redirected)throw Error('Sua sessão expirou. Entre novamente.');const d=await r.json();if(!r.ok)throw Error(d.error||'Não foi possível concluir a operação.');return d;}
  const map={evento:'#events-event',ano:'#events-year',mes:'#events-month',inicio:'#events-start',fim:'#events-end',tipo:'#events-type',local:'#events-local',origem:'#events-origin',busca:'#events-search',status:'#events-status'};
  function query(){const q=new URLSearchParams({categoria:category});for(const [k,s]of Object.entries(map))if($(s).value)q.set(k,$(s).value);multi.values($('#events-city')).forEach(v=>q.append('municipio',v));multi.values($('#events-common')).forEach(v=>q.append('comum',v));return q;}
  function options(select,rows,placeholder){const value=select.value;select.innerHTML=`<option value="">${placeholder}</option>`+rows.map(([v,l])=>`<option value="${esc(v)}">${esc(l)}</option>`).join('');if([...select.options].some(o=>o.value===value))select.value=value;}
  function chart(target,rows,tone){const max=Math.max(1,...rows.map(x=>x[1]));$(target).innerHTML=rows.length?rows.map(([label,value])=>`<div class="events-bar-row"><div><span>${esc(label)}</span><strong>${number(value)}</strong></div><div class="events-bar-track"><span style="width:${value/max*100}%;background:${tone}"></span></div></div>`).join(''):'<div class="events-empty">Sem presenças neste recorte.</div>';}
  const percent=v=>`${Number(v).toLocaleString('pt-BR',{maximumFractionDigits:1})}%`;
  const change=v=>v==null?'Sem comparação':`${v>0?'+':''}${percent(v)}`;
  function spark(points,field,large=false){
    if(!points.length)return '<div class="events-no-history">Sem série comparável neste recorte.</div>';
    const w=320,h=large?110:55,pad=10,values=points.map(p=>Number(p[field]||0)),max=Math.max(1,...values),min=Math.min(0,...values);
    const times=points.map(p=>Date.parse(p.date)),span=Math.max(...times)-Math.min(...times);
    const coords=values.map((v,i)=>[points.length===1?w/2:span?(times[i]-Math.min(...times))/span*(w-pad*2)+pad:pad+i*(w-pad*2)/(points.length-1),h-pad-(v-min)/(max-min||1)*(h-pad*2)]);
    const segments=coords.slice(1).map((p,i)=>`<line x1="${coords[i][0]}" y1="${coords[i][1]}" x2="${p[0]}" y2="${p[1]}" stroke="${values[i+1]<values[i]?'#ce3852':'#0ca6ac'}" stroke-width="2.5"/>`).join('');
    const peak=values.indexOf(Math.max(...values)),last=coords.length-1;
    const dots=coords.map((p,i)=>`<circle cx="${p[0]}" cy="${p[1]}" r="${i===last?4:2.4}" fill="${i===last&&i>0&&values[i]<values[i-1]?'#ce3852':'#0ca6ac'}"><title>${date(points[i].date)}: ${number(values[i])}</title></circle>`).join('');
    return `<svg class="events-spark" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(points.map((p,i)=>date(p.date)+': '+values[i]).join('; '))}"><line x1="10" y1="${h-10}" x2="310" y2="${h-10}" stroke="#e4edf3"/>${points.length>1?`<polygon points="${coords[0][0]},${h-10} ${coords.map(p=>p.join(',')).join(' ')} ${coords[last][0]},${h-10}" fill="#0ca6ac" opacity=".07"/>`:''}${large&&last>peak?`<line x1="${coords[peak][0]}" y1="${coords[peak][1]}" x2="${coords[last][0]}" y2="${coords[last][1]}" stroke="#ce3852" stroke-dasharray="4 4" opacity=".55"/>`:''}${segments}${dots}</svg>`;
  }
  function visuals(data){
    const m=data.totals.MUSICO||0,o=data.totals.ORGANISTA||0,total=m+o,share=total?m/total*100:0;
    $('#events-participation-chart').innerHTML=`<div class="events-music-split"><div class="events-donut" style="background:${total?`conic-gradient(#2f8de4 0 ${share}%,#d85a8a ${share}% 100%)`:'#edf3f8'}"><div><strong>${number(total)}</strong><span>total musical</span></div></div><div class="events-split-values"><div><span><i style="background:#2f8de4"></i>Músicos</span><strong>${number(m)}</strong><small>${total?percent(share):'—'} do total musical</small></div><div><span><i style="background:#d85a8a"></i>Organistas</span><strong>${number(o)}</strong><small>${total?percent(100-share):'—'} do total musical</small></div></div></div><div class="events-visual-foot">Outros participantes: <strong>${number((data.totals.total||0)-total)}</strong> · Ministério, apoio e irmandade</div>`;
    const families=data.musician_families||{},max=Math.max(1,...['CORDAS','MADEIRAS','METAIS'].map(x=>families[x]||0));
    $('#events-family-chart').innerHTML=`<div class="events-columns">${[['CORDAS','Cordas','#2f8de4'],['MADEIRAS','Madeiras','#14aaa0'],['METAIS','Metais','#e7a329']].map(([key,label,tone])=>`<div class="events-column"><strong>${number(families[key])}</strong><small>${m?percent((families[key]||0)/m*100):'—'}</small><div class="events-column-space"><span style="height:${(families[key]||0)/max*100}%;background:${tone}"></span></div><b>${label}</b></div>`).join('')}</div><div class="events-visual-foot">Base: <strong>${number(m)} músicos</strong> · Outros instrumentos / não classificados: <strong>${number(m-['CORDAS','MADEIRAS','METAIS'].reduce((s,x)=>s+(families[x]||0),0))}</strong></div>`;
    const history=data.evolution||{series:[]};

  }
  function table(){const data=state.data;if(!data)return;const rows=data.rows.slice(state.page*20,(state.page+1)*20);let city=null,html='';
    for(const r of rows){if(city!==r.municipio){city=r.municipio;html+=`<tr class="events-city-group"><td colspan="6">${esc(city)}</td></tr>`;}const m=r.musicos_base??r.cadastro_musicos,o=r.organistas_base??r.cadastro_organistas,status=r.encarregado_status||(['PRESENTE','JUSTIFICOU','SEM_ENCARREGADO','ENFERMO'].includes(r.encarregado_situacao)?r.encarregado_situacao:'NAO_JUSTIFICOU'),label={PRESENTE:'PRESENTE',JUSTIFICOU:'JUSTIFICOU',NAO_JUSTIFICOU:'NJ',SEM_ENCARREGADO:'SEM ENCARREGADO',ENFERMO:'ENFERMO'}[status];html+=`<tr><td><strong>${esc(r.comum)}</strong></td><td>${number(r.MUSICO)}</td><td>${number(r.ORGANISTA)}</td><td><b>${number(r.MUSICO+r.ORGANISTA)}</b></td><td class="events-registered-leader"><strong>${esc(r.encarregado_nome||'Não localizado no cadastro')}</strong><small><span class="conductor-status ${esc(status)}">${esc(label)}</span>${r.encarregado_local?` <span>${esc(r.encarregado_local)}</span>`:''}</small>${r.encarregado_nomes?.length>1?'<small class="text-warning">Mais de um encarregado cadastrado · conferir</small>':''}</td><td>${m==null?'—':number(m)} / ${o==null?'—':number(o)}</td></tr>`;}
    $('#events-frequency-body').innerHTML=html||'<tr><td colspan="6" class="events-empty">Sem comuns neste recorte.</td></tr>';
    const t=data.totals;$('#events-base-musicians').textContent=data.base_complete?'Base histórica':'Cadastro atual';$('#events-frequency-foot').innerHTML=`<tr><td>Total · ${number(t.comuns)} comuns</td><td>${number(t.MUSICO)}</td><td>${number(t.ORGANISTA)}</td><td>${number((t.MUSICO||0)+(t.ORGANISTA||0))}</td><td colspan="2">${data.base_complete?'Referência histórica':'Referência cadastral atual'}</td></tr>`;
    $('#events-commons-count').textContent=`${number(t.comuns)} comuns`;
    $('#events-page-reading').textContent=data.rows.length?`${state.page*20+1}–${Math.min((state.page+1)*20,data.rows.length)} de ${data.rows.length}`:'0 comuns';$('#events-page-prev').disabled=state.page===0;$('#events-page-next').disabled=(state.page+1)*20>=data.rows.length;
  }
  function render(data){state.data=data;state.page=0;const t=data.totals;
    const regions=data.regional_overview||[],musical=(t.MUSICO||0)+(t.ORGANISTA||0),pct=v=>musical?(v/musical*100).toLocaleString('pt-BR',{maximumFractionDigits:1})+'%':'—';
    $('#events-metrics').innerHTML=[['Músicos',t.MUSICO,'MUSICO','fa-music','#2f8de4',pct(t.MUSICO||0)+' do total musical'],['Organistas',t.ORGANISTA,'ORGANISTA','fa-keyboard','#d85a8a',pct(t.ORGANISTA||0)+' do total musical'],['Comuns representadas',t.comuns,'comuns','fa-location-dot','#7764d8',number(t.municipios)+' municípios com registros'],['Encarregados locais',t.encarregados,'encarregados','fa-user-check','#e7a329','Presenças nominais no recorte']].map(([label,value,field,icon,tone,context])=>{const max=Math.max(1,...regions.map(r=>r[field]||0));return `<article class="events-metric" style="--tone:${tone}"><div class="events-metric-top"><small>${label}</small><i class="fa ${icon}"></i></div><div class="events-kpi-value"><strong>${number(value)}</strong></div><p class="events-kpi-context">${esc(context)}</p><div class="events-kpi-distribution" role="img" aria-label="${esc(regions.map(r=>r.municipio+': '+(r[field]||0)).join('; '))}">${regions.map(r=>{const label={'CAUCAIA DO ALTO':'Caucaia','COTIA':'Cotia','ITAPEVI':'Itapevi','JANDIRA':'Jandira','PIRAPORA DO BOM JESUS':'Pirapora','SANTANA DE PARNAÍBA':'Fazendinha','VARGEM GRANDE PAULISTA':'VGP'}[r.municipio]||r.municipio;return `<div class="events-kpi-column"><b>${number(r[field])}</b><div><i style="height:${(r[field]||0)/max*100}%"></i></div><span data-short="${esc(label.slice(0,3).toUpperCase())}">${esc(label)}</span></div>`;}).join('')}</div><div class="events-kpi-caption">Quantidade por município de origem</div></article>`;}).join('');
    $('#events-management-note').innerHTML=`<span><b>${number(t.eventos)}</b> evento(s) · <b>${number(t.comuns)}</b> comuns · <b>${number(t.total)}</b> presenças gerais</span><span>${data.filters.origem==='regional'?'Sete municípios da Regional':data.filters.origem==='visitantes'?'Visitantes':'Regional e visitantes'}</span>`;
    $('#events-scope-reading').textContent=`${data.events.length===1?kind(data.events[0])+' · '+date(data.events[0].data_evento):number(t.eventos)+' eventos'} · ${multi.labels($('#events-city'),'Todos os municípios')} · ${$('#events-local').selectedOptions[0]?.textContent||'Todos os locais'}`;
    chart('#events-city-chart',data.municipalities.map(x=>[x.municipio,x.total]),'#2f8de4');
    visuals(data);
    chart('#events-location-chart',data.locations.map(x=>[x.nome,x.total]),'#7764d8');
    $('#events-body').innerHTML=data.events.map(e=>`<tr><td>${date(e.data_evento)}</td><td><strong>${esc(e.titulo)}</strong></td><td>${esc(kind(e))}</td><td><span class="events-status ${esc(e.status)}">${esc(e.status)}</span></td><td>${esc(e.created_by_name)}</td><td><button class="btn btn-sm btn-outline-primary" data-event-id="${esc(e.id)}" type="button">Selecionar</button></td></tr>`).join('')||'<tr><td colspan="6" class="events-empty">Sem eventos neste recorte.</td></tr>';
    $('#events-count').textContent=`${number(t.eventos)} eventos`;table();document.dispatchEvent(new CustomEvent('music-events-data',{detail:data}));
  }
  let dashboardController, historyController;
  async function loadHistory(params,version){
    historyController=new AbortController();
    try{const history=await request('/musica/eventos/api/historico/?'+params,{signal:historyController.signal});
      if(version!==state.version)return;
      state.data.evolution=history.evolution;
      document.dispatchEvent(new CustomEvent('music-events-history',{detail:history}));
    }catch(error){if(version===state.version&&error.name!=='AbortError')document.dispatchEvent(new CustomEvent('music-events-history',{detail:{error:error.message}}));}
  }
  async function load(preloaded){const version=++state.version;dashboardController?.abort();historyController?.abort();dashboardController=new AbortController();const params=query();$('#events-refresh').disabled=true;$('#events-excel').disabled=$('#events-pdf').disabled=true;
    try{const d=preloaded?.totals?preloaded:await request('/musica/eventos/api/painel/?'+params,{signal:dashboardController.signal});if(version!==state.version)return;
      multi.setOptions($('#events-city'),d.options.cities,'Todos os municípios');
      const selected=multi.values($('#events-common'));const cities=multi.normalizedValues($('#events-city'));
      const commons=d.options.commons.filter(x=>!cities.length||cities.includes(multi.normalize(x.city)));
      const c=$('#events-common');c.innerHTML='';commons.forEach(x=>c.add(new Option(x.label,x.value)));multi.setValues(c,selected);multi.refresh(c);
      options($('#events-local'),d.options.locations.map(x=>[x.id,x.nome]),'Todos os locais');
      render(d);feedback('');$('#events-excel').disabled=$('#events-pdf').disabled=false;
      void loadHistory(params,version);
    }catch(error){if(version===state.version){feedback(error.message);$('#events-management-note').textContent='Não foi possível atualizar o recorte. Use Atualizar para tentar novamente.';}}
    finally{if(version===state.version)$('#events-refresh').disabled=false;}
  }
  async function initialize(selectedId){try{const initialParams=query();initialParams.delete('evento');initialParams.set('inicial','1');if(typeof selectedId==='string')initialParams.set('evento',selectedId);
    const [data,initialDashboard]=await Promise.all([request('/musica/eventos/api/eventos/'),request('/musica/eventos/api/painel/?'+initialParams)]);state.items=data.items;
    options($('#events-event'),data.items.map(e=>[e.id,eventLabel(e)]),'Todos os eventos');
    options($('#events-year'),[...new Set(data.items.map(e=>e.data_evento.slice(0,4)))].sort().reverse().map(x=>[x,x]),'Todos');
    if(data.items.length)$('#events-event').value=initialDashboard.filters.evento;
    const bases=data.bases.filter(x=>x.homologada);$('#events-new').classList.toggle('d-none',!data.can_manage);$('#events-new').disabled=!bases.length;$('#events-import').classList.toggle('d-none',!data.can_manage);
    options($('#event-base'),bases.map(x=>[x.id,`${date(x.referencia)} · ${x.origem}`]),'Selecione a base');
    $('#events-base-state').textContent='O painel abre nos sete municípios da Regional. Visitantes ficam na visão complementar. O percentual considera somente presenças vinculadas ao público elegível do SAM. Cargos são dimensões sobrepostas e não devem ser somados novamente ao total.';
    await load(initialDashboard);
  }catch(error){feedback(error.message);}}
  options($('#events-month'),['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'].map((x,i)=>[String(i+1).padStart(2,'0'),x]),'Todos');
  Object.values(map).filter(x=>x!=='#events-search').forEach(s=>$(s).addEventListener('change',()=>{if(['#events-year','#events-month','#events-start','#events-end','#events-type'].includes(s)){$('#events-event').value='';$('#events-local').value='';}if(s==='#events-event')$('#events-local').value='';load();}));
  $('#events-city').addEventListener('change',()=>{multi.clear($('#events-common'));load();});$('#events-common').addEventListener('change',load);
  let timer;$('#events-search').oninput=()=>{clearTimeout(timer);timer=setTimeout(load,350);};
  $('#events-refresh').onclick=load;$('#events-clear').onclick=()=>{Object.values(map).forEach(s=>$(s).value='');$('#events-origin').value='regional';multi.clear($('#events-city'));multi.clear($('#events-common'));load();};
  $('#events-body').onclick=e=>{const b=e.target.closest('[data-event-id]');if(b){$('#events-event').value=b.dataset.eventId;$('#events-local').value='';load();$('.events-control').scrollIntoView({behavior:'smooth'});}};
  $('#events-page-prev').onclick=()=>{state.page--;table();};$('#events-page-next').onclick=()=>{state.page++;table();};
  function generating(button){
    if(!button)return ()=>{};
    const original=button.innerHTML,disabled=button.disabled;
    button.disabled=true;button.setAttribute('aria-busy','true');
    button.innerHTML='<i class="fa fa-spinner fa-spin me-1"></i>Gerando';
    return ()=>{button.innerHTML=original;button.disabled=disabled;button.removeAttribute('aria-busy');};
  }
  async function download(format,report,extra={},button){if(button?.disabled)return;const restore=generating(button);try{const q=query();if(report)q.set('relatorio',report);for(const [key,value] of Object.entries(extra)){q.delete(key);if(value)q.append(key,value);}const response=await fetch(`/musica/eventos/exportar-${format}/?${q}`,{cache:'no-store'});if(!response.ok||response.redirected)throw Error('Não foi possível exportar. Confira sua sessão e tente novamente.');const blob=await response.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=downloadName(response,`Ensaios_RTs.${format==='excel'?'xlsx':'pdf'}`);a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){feedback(error.message);}finally{restore();}}
  $('#events-excel').onclick=e=>download('excel',undefined,{},e.currentTarget);$('#events-pdf').onclick=e=>download('pdf','comuns',{},e.currentTarget);$('#events-commons-pdf').onclick=e=>download('pdf','comuns',{},e.currentTarget);
  async function selectEvent(id){Object.values(map).forEach(s=>$(s).value='');$('#events-origin').value='regional';multi.clear($('#events-city'));multi.clear($('#events-common'));await initialize(id);}
  window.MusicEventsDashboard={generating,downloadName,load:initialize,refresh:load,download,selectEvent,feedback,request,esc,date};
  $('#events-metrics').innerHTML=['Músicos presentes','Organistas presentes','Presenças totais','Comuns representadas'].map(label=>`<article class="events-metric events-loading"><small>${label}</small><strong>—</strong><p>Carregando indicadores…</p></article>`).join('');
  initialize();
})();
