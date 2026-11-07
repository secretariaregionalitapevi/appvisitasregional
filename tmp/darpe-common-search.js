(() => {
 'use strict';
 const norm=value=>String(value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim().toUpperCase();
 document.querySelectorAll('select[name="comum"],select#mobile-common').forEach(select=>{
  const wrap=document.createElement('div');wrap.className='darpe-common-picker';
  const toggle=document.createElement('button');toggle.type='button';toggle.className='darpe-common-toggle';toggle.setAttribute('aria-haspopup','listbox');toggle.setAttribute('aria-expanded','false');
  const panel=document.createElement('div');panel.className='darpe-common-panel';panel.hidden=true;
  const search=document.createElement('input');search.type='search';search.className='darpe-common-search';search.placeholder='Digite o nome ou código BR';search.setAttribute('aria-label','Pesquisar comum por nome ou código BR');search.autocomplete='off';
  const list=document.createElement('div');list.className='darpe-common-options';list.id=(select.id||select.name)+'-search-options';list.setAttribute('role','listbox');list.setAttribute('aria-label','Comuns disponíveis');toggle.setAttribute('aria-controls',list.id);
  const close=()=>{panel.hidden=true;toggle.setAttribute('aria-expanded','false');};
  const render=()=>{list.replaceChildren();const terms=norm(search.value).split(/\s+/).filter(Boolean),available=[...select.options].filter(o=>!o.disabled&&terms.every(t=>norm(o.textContent).includes(t)));for(const option of available){const button=document.createElement('button');button.type='button';button.className='darpe-common-option';button.setAttribute('role','option');button.setAttribute('aria-selected',String(option.selected));button.textContent=option.textContent;button.onclick=()=>{select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));sync();close();toggle.focus();};button.onkeydown=e=>{const buttons=[...list.querySelectorAll('button')],index=buttons.indexOf(button);if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();buttons[(index+(e.key==='ArrowDown'?1:buttons.length-1))%buttons.length]?.focus();}if(e.key==='Escape'){close();toggle.focus();}};list.append(button);}if(!available.length){const empty=document.createElement('p');empty.className='darpe-common-empty';empty.textContent='Nenhuma comum encontrada neste município.';list.append(empty);}};
  const sync=()=>{toggle.textContent=select.selectedOptions[0]?.textContent||'Selecione a comum';toggle.disabled=select.disabled;toggle.title=toggle.textContent;if(select.disabled)close();render();};
  const open=()=>{if(select.disabled)return;panel.hidden=false;toggle.setAttribute('aria-expanded','true');search.value='';render();search.focus();};
  toggle.onclick=()=>panel.hidden?open():close();toggle.onkeydown=e=>{if(e.key==='ArrowDown'){e.preventDefault();open();}};
  search.oninput=render;search.onkeydown=e=>{if(e.key==='ArrowDown'){e.preventDefault();list.querySelector('button')?.focus();}if(e.key==='Escape'){close();toggle.focus();}if(e.key==='Enter')e.preventDefault();};
  select.classList.add('darpe-common-native');select.tabIndex=-1;select.insertAdjacentElement('afterend',wrap);panel.append(search,list);wrap.append(toggle,panel);select.addEventListener('change',sync);select.addEventListener('invalid',event=>{event.preventDefault();open();});select.form?.addEventListener('reset',()=>queueMicrotask(sync));new MutationObserver(sync).observe(select,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled','selected']});document.addEventListener('click',event=>{if(!wrap.contains(event.target))close();});sync();
 });
})();
