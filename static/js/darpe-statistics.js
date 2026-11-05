(() => {
 'use strict';
 const root = document.querySelector('#darpe-statistics');
 if (!root) return;
 const $ = id => document.getElementById(id), format = n => Number(n).toLocaleString('pt-BR');
 const labels = {unidades:'Unidades constituídas',batismos:'Batismos desde 2010',pessoas_batizadas:'Pessoas batizadas',colaboradores:'Ministério e colaboradores',atendimentos:'Atendimentos formalizados'};
 const icons = ['fa-map-location-dot','fa-droplet','fa-users','fa-handshake','fa-clipboard-check'];
 const colors = ['#238be6','#0b9d8f','#7b61d1','#d49216','#d25e8a'];
 let items = [], versions = [], currentId = '';
 const month = value => new Date(value.slice(0,7)+'-01T12:00:00').toLocaleDateString('pt-BR',{month:'long',year:'numeric'});
 const stamp = value => {const d=new Date(value);return d.toLocaleDateString('pt-BR')+' '+d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});};
 function el(tag, cls, text) {const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node;}
 function status(text, error=false) {$('stats-status').textContent=text;$('stats-status').className=error?'text-danger':'';}
 function selected() {return versions.find(row=>row.id===currentId)||items.at(-1);}
 function render() {
  const row=selected(); if(!row) {status('Nenhuma competência publicada. Registre a primeira atualização.');return;}
  currentId=row.id;
  $('stats-period').value=row.competencia;
  const latest=items.find(x=>x.competencia===row.competencia), history=versions.filter(x=>x.competencia===row.competencia);
  $('stats-version').textContent=(row.id===latest?.id?'Versão vigente':'Versão histórica')+' · '+history.length+' publicação(ões)';
  const previous=items.filter(x=>x.competencia<row.competencia).at(-1);
  const cards=$('stats-cards'); cards.replaceChildren();
  Object.entries(labels).forEach(([key,label],index)=>{
   const card=el('article','statistics-card');card.style.setProperty('--indicator-color',colors[index]);
   const head=el('div','statistics-card-head'),icon=el('i','fa '+icons[index]);icon.setAttribute('aria-hidden','true');head.append(el('span','',label),icon);
   const badge=el('span','statistics-change');
   if(previous){const delta=row[key]-previous[key],percent=previous[key]?Math.abs(delta/previous[key]*100).toLocaleString('pt-BR',{maximumFractionDigits:1})+'%':'';badge.textContent=(delta>0?'+':'')+format(delta)+(percent?' ('+percent+')':'');badge.classList.add(delta>0?'increase':delta<0?'decrease':'stable');}
   else {badge.textContent='Base inicial';badge.classList.add('stable');}
   card.append(head,el('strong','',format(row[key])),badge,el('small','',previous?'Comparado a '+month(previous.competencia):'Primeira competência disponível'));cards.append(card);
  });
  $('stats-geography').textContent=row.distribuicao||'Distribuição não informada nesta publicação.';
  $('stats-source').textContent=row.fonte;
  $('stats-observations').textContent=row.observacoes;
  $('stats-author').textContent='Publicado em '+stamp(row.created_at)+' · '+row.responsavel;
  drawChart(); renderHistory();
 }
 function svgNode(tag,attrs,text) {const node=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))node.setAttribute(k,v);if(text!==undefined)node.textContent=text;return node;}
 function drawChart() {
  const row=selected(),key=$('stats-metric').value,points=items.filter(x=>x.competencia<=row.competencia).map(x=>x.competencia===row.competencia?row:x),target=$('stats-chart');target.replaceChildren();
  const chartWidth=Math.max(260,Math.min(760,target.clientWidth||760)),left=62,right=chartWidth-20;
  const svg=svgNode('svg',{viewBox:`0 0 ${chartWidth} 245`,role:'img','aria-label':labels[key]+' por competência. '+points.map(x=>month(x.competencia)+': '+format(x[key])).join('; ')});
  const max=Math.max(...points.map(x=>x[key]),1)*1.15;
  for(let i=0;i<=4;i++){const y=185-i*40;svg.append(svgNode('line',{x1:left,x2:right,y1:y,y2:y,stroke:'#e4ecf2','stroke-dasharray':'4 4'}),svgNode('text',{x:left-10,y:y+4,'text-anchor':'end',fill:'#667f92','font-size':11},format(Math.round(max*i/4))));}
  const positions=points.map((x,i)=>[points.length===1?(left+right)/2:left+10+i*(right-left-20)/(points.length-1),185-x[key]/max*160]);
  if(positions.length>1){svg.append(svgNode('polygon',{points:positions.map(p=>p.join(',')).join(' ')+` ${positions.at(-1)[0]},185 ${positions[0][0]},185`,fill:'#eaf4fb'}),svgNode('polyline',{points:positions.map(p=>p.join(',')).join(' '),fill:'none',stroke:'#238be6','stroke-width':3,'stroke-linejoin':'round'}));}
  positions.forEach(([x,y],i)=>{const dot=svgNode('circle',{cx:x,cy:y,r:5,fill:'#238be6',stroke:'#fff','stroke-width':2});dot.append(svgNode('title',{},month(points[i].competencia)+': '+format(points[i][key])));svg.append(dot);if(points.length<10||i===0||i===points.length-1)svg.append(svgNode('text',{x,y:210,'text-anchor':'middle',fill:'#617c90','font-size':11},points[i].competencia.slice(5,7)+'/'+points[i].competencia.slice(0,4)));if(points.length<7)svg.append(svgNode('text',{x,y:y-13,'text-anchor':'middle',fill:'#1e4b7a','font-size':12,'font-weight':700},format(points[i][key])));});
  target.append(svg);
  $('stats-chart-note').textContent=points.length===1?'Uma competência registrada. A evolução será exibida após a próxima publicação.':'Valores acumulados de '+month(points[0].competencia)+' a '+month(row.competencia)+'.';
 }
 function renderHistory() {
  $('stats-history-count').textContent=versions.length;
  const body=$('stats-history');body.replaceChildren();
  [...versions].reverse().forEach(row=>{const tr=el('tr'),cell=el('td'),button=el('button','btn btn-sm btn-outline-primary',row.id===currentId?'Em análise':'Ver publicação');button.type='button';button.onclick=()=>{currentId=row.id;render();};cell.append(button);tr.append(el('td','',month(row.competencia)),el('td','',stamp(row.created_at)),el('td','',row.responsavel),el('td','',items.some(x=>x.id===row.id)?'Vigente na competência':'Histórica'),cell);body.append(tr);});
 }
 async function load(preferred) {
  status('Carregando histórico…');
  try {const response=await fetch('/darpe/biblioteca/estatisticas/',{cache:'no-store'}),body=await response.json();if(!response.ok)throw Error(body.error||'Falha ao consultar estatísticas.');items=body.items||[];versions=body.versions||[];$('stats-period').replaceChildren(...[...items].reverse().map(row=>{const option=el('option','',month(row.competencia));option.value=row.competencia;return option;}));$('stats-period').disabled=!items.length;currentId=(preferred?items.find(x=>x.competencia.startsWith(preferred)):null)?.id||items.at(-1)?.id;status('');render();}
  catch(error){status(error.message,true);}
 }
 $('stats-period').onchange=()=>{currentId=items.find(x=>x.competencia===$('stats-period').value)?.id;render();};
 $('stats-metric').onchange=()=>{if(selected())drawChart();};
 $('stats-copy')?.addEventListener('click',()=>{const row=selected(),form=$('stats-form');if(!row)return;for(const key of [...Object.keys(labels),'fonte','distribuicao','observacoes'])form.elements[key].value=row[key]??'';form.elements.competencia.value=new Date().toISOString().slice(0,7);});
 $('stats-form')?.addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget,data=new FormData(form),payload=Object.fromEntries(data.entries()),button=$('stats-save'),feedback=$('stats-save-status');
  delete payload.csrfmiddlewaretoken;
  for(const key of Object.keys(labels)){if(!/^\d+$/.test(payload[key])){feedback.textContent='Informe números inteiros não negativos.';return;}payload[key]=Number(payload[key]);}
  button.disabled=true;feedback.textContent='Publicando atualização…';
  try{const response=await fetch('/darpe/biblioteca/estatisticas/',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':data.get('csrfmiddlewaretoken')},body:JSON.stringify(payload)}),body=await response.json();if(!response.ok)throw Error(body.error||'Falha ao publicar.');await load(payload.competencia);feedback.textContent=body.message;feedback.className='text-success';}
  catch(error){feedback.textContent=error.message;feedback.className='text-danger';}finally{button.disabled=false;}
 });
 let lastWidth=0;if(window.ResizeObserver)new ResizeObserver(entries=>{const width=Math.round(entries[0].contentRect.width);if(width!==lastWidth){lastWidth=width;if(selected())drawChart();}}).observe($('stats-chart'));
 load();
})();
