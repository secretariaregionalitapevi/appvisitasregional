(() => {
 'use strict';
 const root=document.querySelector('#darpe-attendance');if(!root)return;
 if(window.requireAuth&&!window.requireAuth())return;
 const $=id=>document.getElementById(id),form=$('da-form'),base=root.dataset.api;
 const roles={atendente:'Atendente responsável',oracao:'Oração',musico:'Músico',organista:'Organista',colaborador:'Colaborador',palavra:'Irmão da palavra'};
 const prayers={enfermidades:'Enfermidade(s)',acidentados:'Acidentado(s)',tribulacoes:'Tribulação(ões)',familias:'Família(s)',causas:'Causa(s)',testemunhados:'Testemunhado(s)',viagens:'Viagem(ns)'};
 let editing=false,context,team=[],submissionId,busy=false,records=[],searchVersion=0,timer;
 function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
 function feedback(type,title,message){return window.AppFeedback.show({type,title,message,toast:true});}
 const detailModal=$('da-detail');
 document.body.append(detailModal);
 let selectedDetail=null,detailTrigger=null;
 async function printPapeleta(item,button){
  if(!item)return;
  await window.AppExport.run(button,async()=>{
   const response=await fetch(base+'papeleta/'+encodeURIComponent(item.id)+'/imprimir/',{credentials:'same-origin',cache:'no-store'});
   const type=response.headers.get('Content-Type')||'';
   if(response.redirected)throw Error('Sua sessão expirou. Entre novamente.');
   if(!response.ok||!type.includes('text/html')||response.headers.get('X-Papeleta-Print')!=='1'){
    let message='Não foi possível preparar a papeleta para impressão.';
    if(type.includes('application/json'))message=(await response.json()).error||message;
    throw Error(message);
   }
   const blob=await response.blob();if(!blob.size)throw Error('A papeleta retornada está vazia.');
   const url=URL.createObjectURL(blob),frame=document.createElement('iframe');
   frame.title='Impressão da papeleta';frame.className='da-print-frame';frame.setAttribute('aria-hidden','true');frame.tabIndex=-1;
   const cleanup=()=>{frame.remove();URL.revokeObjectURL(url);};
   await new Promise((resolve,reject)=>{
    let printing=false;
    const timeout=setTimeout(()=>{cleanup();reject(Error('A impressão não respondeu. Baixe o PDF e use a opção Imprimir do leitor.'));},15000);
    frame.onload=()=>{
     if(printing)return;printing=true;
     setTimeout(()=>{
      try{
       frame.contentWindow.addEventListener?.('afterprint',()=>{button.focus();setTimeout(cleanup,0);},{once:true});
       frame.contentWindow.focus();frame.contentWindow.print();button.focus();
       clearTimeout(timeout);setTimeout(cleanup,120000);resolve();
      }
      catch{clearTimeout(timeout);cleanup();reject(Error('Não foi possível abrir a impressão. Baixe o PDF e imprima pelo leitor.'));}
     },350);
    };
    frame.src=url;document.body.append(frame);
   });
  },{success:'Janela de impressão aberta. Confirme a impressora e as páginas no navegador.'});
  if(button.isConnected)button.focus();
 }
 root.addEventListener('darpe:print',event=>printPapeleta(event.detail.record,event.detail.button));
 $('da-detail-print').onclick=()=>printPapeleta(selectedDetail,$('da-detail-print'));
 detailModal.addEventListener('hidden.bs.modal',()=>{
  const trigger=detailTrigger;
  setTimeout(()=>{if(trigger?.isConnected)trigger.focus();else document.querySelector('.daa-row-actions button, .da-record')?.focus();},0);
 });
 function detail(item){
  selectedDetail=item;detailTrigger=document.activeElement;
  $('da-detail-title').textContent=item.local;
  $('da-detail-subtitle').textContent=sectorName(item.setor);
  $('da-detail-pdf').href=base+'papeleta/'+encodeURIComponent(item.id)+'/pdf/';
  const target=$('da-detail-content');target.replaceChildren();
  const icon=name=>{const n=node('i',undefined,'fa '+name);n.setAttribute('aria-hidden','true');return n;};
  const field=(label,value)=>{const box=node('div',undefined,'da-detail-field');box.append(node('dt',label),node('dd',value||'Não informado'));return box;};
  const section=(title,symbol)=>{const box=node('section',undefined,'da-detail-section'),heading=node('h3');heading.append(icon(symbol),document.createTextNode(title));box.append(heading);return box;};
  const overview=node('div',undefined,'da-detail-overview');
  for(const [label,value,symbol] of [['Data',dateLabel(item.data),'fa-calendar-days'],['Horário',item.hora_inicio.slice(0,5)+' às '+item.hora_fim.slice(0,5),'fa-clock'],['Município',item.municipio,'fa-location-dot'],['Setor','Setor '+item.setor,'fa-layer-group']]){
   const box=node('div'),copy=node('div');copy.append(node('small',label),node('strong',value));box.append(icon(symbol),copy);overview.append(box);
  }
  target.append(overview);
  const location=section('Local e contatos','fa-map-location-dot'),locationFields=node('dl',undefined,'da-detail-fields');
  locationFields.append(field('Local atendido',item.local),field('Comum do responsável',item.comum));
  for(const [label,value,type]of [['WhatsApp',item.whatsapp,'whatsapp'],['Outro telefone',item.telefone,'tel']]){
   const box=field(label,value);if(value){const digits=value.replace(/\D/g,''),link=node('a',value);link.href=type==='tel'?'tel:+'+(digits.startsWith('55')?digits:'55'+digits):'https://wa.me/'+(digits.startsWith('55')?digits:'55'+digits);if(type==='whatsapp'){link.target='_blank';link.rel='noopener';}box.lastChild.replaceChildren(link);}locationFields.append(box);
  }
  location.append(locationFields);target.append(location);
  const teamSection=section('Equipe do atendimento','fa-users'),teamGrid=node('div',undefined,'da-detail-team');
  const symbols={atendente:'fa-user-tie',oracao:'fa-hands',musico:'fa-music',organista:'fa-keyboard',colaborador:'fa-user-group',palavra:'fa-comment-dots'};
  for(const [role,label]of Object.entries(roles)){
   const box=node('div',undefined,'da-detail-person'),head=node('h4');head.append(icon(symbols[role]),document.createTextNode(label));box.append(head);
   const people=(item.equipe||[]).filter(p=>p.funcao===role);
   if(people.length){const list=node('ul');for(const person of people)list.append(node('li',person.nome));box.append(list);}else box.append(node('p','Não informado','da-detail-empty'));
   teamGrid.append(box);
  }
  teamSection.append(teamGrid);target.append(teamSection);
  const service=section('Culto de evangelização','fa-music'),serviceFields=node('dl',undefined,'da-detail-fields');
  const hymns=field('Hinos',''),tags=node('div',undefined,'da-detail-hymns');for(const number of item.hinos||[])tags.append(node('span',String(number)));hymns.lastChild.replaceChildren((item.hinos||[]).length?tags:document.createTextNode('Não informado'));
  serviceFields.append(hymns,field('Palavra',item.palavra),field('Participação',item.participacao),field('Observações',item.observacoes));service.append(serviceFields);target.append(service);
  const prayersSection=section('Pedidos de oração','fa-hands'),prayerGrid=node('dl',undefined,'da-detail-prayers');
  for(const [key,label]of Object.entries(prayers)){const value=(item.pedidos_oracao||{})[key]??0;prayerGrid.append(field(label,value==='todas'?'Todas':String(value)));}
  prayersSection.append(prayerGrid);target.append(prayersSection);
  const audit=node('div',undefined,'da-detail-audit'),created=new Date(item.created_at);
  audit.append(icon('fa-circle-info'),node('span','Registrado por '+(item.created_by_name||'Não informado')+(Number.isNaN(created.getTime())?'':' · '+created.toLocaleString('pt-BR',{timeZone:'America/Sao_Paulo',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}).replace(',',''))));target.append(audit);
  bootstrap.Modal.getOrCreateInstance(detailModal).show();
 }
 async function api(action,options={}){const headers=new Headers(options.headers||{});if(options.body){headers.set('Content-Type','application/json');const csrf=form.querySelector('[name=csrfmiddlewaretoken]');if(csrf)headers.set('X-CSRFToken',csrf.value);}const response=await (window.authFetch||fetch)(base+action,{cache:'no-store',...options,headers});let data;try{data=await response.json();}catch{throw Error('Não foi possível ler a resposta do servidor.');}if(!response.ok)throw Error(data.error||'Não foi possível concluir a operação.');return data;}
 function sectorName(id){return context?.setores?.find(s=>s.id===Number(id))?.nome||'Setor '+id;}
 function dateLabel(value){const [y,m,d]=value.split('-');return `${d}/${m}/${y}`;}
 function show(view){$('da-editor').hidden=view!=='editor';root.querySelector('.da-list').hidden=view!=='list';$('da-new').hidden=view!=='list';root.dispatchEvent(new CustomEvent('darpe:view',{detail:{view},bubbles:true}));}
 function drawTeam(){const target=$('da-team');target.replaceChildren();for(const entry of team){const item=node('div',undefined,'da-member'),label=node('span',entry.nome+' · '+roles[entry.funcao]),remove=node('button','×');remove.type='button';remove.setAttribute('aria-label','Remover '+entry.nome+' da função '+roles[entry.funcao]);remove.onclick=()=>{team=team.filter(x=>x!==entry);drawTeam();};item.append(label,remove);target.append(item);}}
 function invalidateSearch(){searchVersion++;clearTimeout(timer);$('da-person-results').replaceChildren();$('da-search-status').textContent='';}
 function saveLabel(text){const button=$('da-save');for(const child of [...button.childNodes])if(child.nodeType===3)child.remove();button.append(document.createTextNode(' '+text));}
 function fresh(){editing=false;saveLabel('Registrar atendimento');$('da-editor-title').textContent='Novo atendimento';form.reset();form.querySelectorAll('input,select,textarea').forEach(x=>x.disabled=false);team=[];submissionId=crypto.randomUUID();const scope=context.escopo;form.elements.municipio.value=scope.municipio||'';form.elements.comum.value=scope.comum||'';form.elements.municipio.readOnly=['municipal','local'].includes(scope.level)||Boolean(scope.comum&&scope.municipio);form.elements.comum.readOnly=Boolean(scope.comum)||scope.level==='local';drawTeam();invalidateSearch();show('editor');form.elements.data.focus();}
 function edit(item){fresh();editing=true;submissionId=item.id;for(const key of ['data','hora_inicio','hora_fim','setor','local','whatsapp','telefone','municipio','comum','palavra','participacao','observacoes'])form.elements[key].value=item[key]??'';form.elements.hinos.value=item.hinos.join(', ');team=item.equipe.map(p=>({...p}));for(const key of Object.keys(prayers))form.elements['pedido_'+key].value=item.pedidos_oracao[key]==='todas'?0:(item.pedidos_oracao[key]??0);$('da-all-families').checked=item.pedidos_oracao.familias==='todas';$('da-all-families').onchange();$('da-editor-title').textContent='Editar atendimento';saveLabel('Salvar alterações');drawTeam();}
 async function remove(item){if(busy)return;const confirmed=await AppFeedback.confirm({title:'Excluir atendimento?',message:dateLabel(item.data)+' · '+item.local,detail:'A papeleta será removida permanentemente.',confirmText:'Excluir atendimento'});if(!confirmed)return false;busy=true;const notice=feedback('loading','Excluindo atendimento','Aguarde a confirmação do sistema.');try{await api('atendimentos/',{method:'DELETE',body:JSON.stringify({id:item.id})});show('list');await load();notice.close();feedback('success','Atendimento excluído','A papeleta foi removida.');return true;}catch(error){notice.close();feedback('error','Não foi possível excluir',error.message);}finally{busy=false;}}
 async function search(){const version=++searchVersion,query=$('da-person-query').value.trim(),role=$('da-role').value;const target=$('da-person-results');target.replaceChildren();if(query.length<2){$('da-search-status').textContent='Digite pelo menos 2 letras.';return;}$('da-search-status').textContent='Pesquisando no cadastro DARPE…';try{const data=await api('pessoas/?'+new URLSearchParams({q:query,funcao:role}));if(version!==searchVersion)return;$('da-search-status').textContent=data.items.length?'Selecione uma pessoa.':'Nenhuma pessoa ativa encontrada para esta função.';for(const person of data.items){const button=node('button',undefined,'da-person');button.type='button';button.append(node('strong',person.nome),node('small',[person.comum,person.municipio,person.instrumento].filter(Boolean).join(' · ')));button.onclick=()=>{if(team.some(x=>x.cadastro_id===person.id&&x.funcao===role))return;if(['atendente','palavra'].includes(role)&&team.some(x=>x.funcao===role)){feedback('warning','Confira a equipe','Remova a pessoa já selecionada nesta função para substituí-la.');return;}team.push({cadastro_id:person.id,funcao:role,nome:person.nome});drawTeam();$('da-person-query').value='';invalidateSearch();};target.append(button);}}catch(error){if(version===searchVersion)$('da-search-status').textContent=error.message;}}
 async function load(){const status=$('da-list-status');status.textContent='Carregando atendimentos…';$('da-refresh').disabled=true;try{const params=new URLSearchParams();if($('da-date').value)params.set('data',$('da-date').value);if($('da-sector-filter').value)params.set('setor',$('da-sector-filter').value);records=(await api('atendimentos/?'+params)).items;const target=$('da-records');target.replaceChildren();for(const item of records){const b=node('button',undefined,'da-record');b.type='button';const responsible=item.equipe.find(p=>p.funcao==='atendente');b.append(node('strong',dateLabel(item.data)+' · '+item.local),node('small','Setor '+item.setor+' · '+item.municipio+' · '+(responsible?.nome||'')));b.onclick=()=>detail(item);target.append(b);}status.textContent=records.length?records.length+' atendimento(s) no recorte.':'Nenhum atendimento no recorte. Use Novo atendimento para registrar uma papeleta.';return true;}catch(error){status.textContent=error.message;return false;}finally{$('da-refresh').disabled=false;}}
 for(const [key,label]of Object.entries(prayers)){const wrap=node('label',label),input=node('input');input.type='number';input.min=0;input.max=99999;input.step=1;input.value='0';input.name='pedido_'+key;input.className='form-control';wrap.append(input);$('da-prayers').append(wrap);}
 $('da-all-families').onchange=()=>{form.elements.pedido_familias.disabled=$('da-all-families').checked;};
 $('da-person-query').oninput=()=>{invalidateSearch();timer=setTimeout(search,300);};$('da-role').onchange=()=>{invalidateSearch();search();};
 $('da-new').onclick=fresh;$('da-back').onclick=()=>{if(!busy){invalidateSearch();show('list');}};$('da-refresh').onclick=load;$('da-date').onchange=load;$('da-sector-filter').onchange=load;
 root.addEventListener('darpe:open',event=>{if(event.detail?.record){if(event.detail.mode==='edit')edit(event.detail.record);else if(event.detail.mode==='delete')remove(event.detail.record);else detail(event.detail.record);}else if(context)fresh();});
 form.onsubmit=async event=>{event.preventDefault();if(busy)return;const data=Object.fromEntries(new FormData(form));const hymnParts=String(data.hinos||'').split(/[,;\s]+/).filter(Boolean);if(hymnParts.some(x=>!/^\d+$/.test(x))){feedback('error','Confira os hinos','Separe os números dos hinos por vírgulas ou espaços.');return;}const payload={...data,id:submissionId,setor:Number(data.setor),hinos:hymnParts.map(Number),equipe:team.map(({cadastro_id,funcao})=>({cadastro_id,funcao})),pedidos_oracao:{}};for(const key of Object.keys(prayers))payload.pedidos_oracao[key]=key==='familias'&&$('da-all-families').checked?'todas':Number(data['pedido_'+key]||0);delete payload.csrfmiddlewaretoken;busy=true;$('da-save').disabled=true;$('da-back').disabled=true;$('da-save').querySelector('.da-spinner').hidden=false;form.setAttribute('aria-busy','true');const notice=feedback('loading',editing?'Salvando alterações':'Registrando atendimento','Aguarde a confirmação do sistema regional.');try{await api('atendimentos/',{method:editing?'PATCH':'POST',body:JSON.stringify(payload)});show('list');const refreshed=await load();notice.close();feedback(refreshed?'success':'warning',editing?'Atendimento atualizado':'Atendimento registrado',refreshed?'A papeleta está disponível no sistema regional.':'O registro foi salvo. Atualize a lista para consultá-lo.');}catch(error){notice.close();feedback('error','Não foi possível confirmar o registro',error.message);}finally{busy=false;$('da-save').disabled=false;$('da-back').disabled=false;$('da-save').querySelector('.da-spinner').hidden=true;form.removeAttribute('aria-busy');}};
 (async()=>{try{context=await api('contexto/');for(const sector of context.setores){for(const id of ['da-sector','da-sector-filter']){const option=node('option','Setor '+sector.id+' · '+sector.nome);option.value=sector.id;$(id).append(option);}}$('da-scope').textContent='Escopo: '+[context.escopo.level,context.escopo.municipio,context.escopo.comum].filter(Boolean).join(' · ');await load();}catch(error){$('da-new').disabled=true;$('da-list-status').textContent=error.message;}})();
})();
