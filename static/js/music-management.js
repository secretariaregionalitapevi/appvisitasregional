(() => {
 'use strict';
 const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const short=['Itapevi','Jandira','Cotia/VGP','Sant./Pir.'];
 window.MusicManagement={cards(cards,groups){return cards.map(card=>{
  const values=groups.map((g,i)=>({label:g.grupo,short:short[i]||g.grupo,value:Number(card.valueFor(g,i)||0)}));const max=Math.max(1,...values.map(v=>v.value));
  return `<article class="management-metric" style="--metric-color:${escape(card.color)}"><div class="management-metric-head"><span>${escape(card.label)}</span><i class="fa ${escape(card.icon)}" aria-hidden="true"></i></div><strong>${Number(card.value||0).toLocaleString('pt-BR')}</strong><div class="management-metric-note">${escape(card.note||'No recorte selecionado')}</div><div class="management-metric-chart" role="img" aria-label="${escape(values.map(v=>v.label+': '+v.value).join('; '))}">${values.map(v=>`<div title="${escape(v.label)}"><b>${v.value.toLocaleString('pt-BR')}</b><span class="management-bar-track"><i style="--bar-height:${v.value/max*100}%"></i></span><small>${escape(v.short)}</small></div>`).join('')}</div><p class="management-metric-footer">${escape(card.footer||'Quantidade por administração')}</p></article>`;
 }).join('');}};
 document.addEventListener('click',event=>{document.querySelectorAll('.management-more[open]').forEach(menu=>{if(!menu.contains(event.target))menu.open=false;});});
 document.addEventListener('keydown',event=>{if(event.key==='Escape')document.querySelectorAll('.management-more[open]').forEach(menu=>menu.open=false);});
})();
