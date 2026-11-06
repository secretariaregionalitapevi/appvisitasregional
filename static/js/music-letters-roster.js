(() => {
'use strict';
const $=s=>document.querySelector(s);if(!$('#letters-delivery-section'))return;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const day=v=>v?String(v).slice(0,10).split('-').reverse().join('/'):'Não informado';
const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/Sao_Paulo'}).format(new Date());
let data=null,token=null,receipt=null,page=0,busy=false,refreshTimer,deadlineDirty=false,receiptSaving=false;
const size=25,base='/musica/cartas-exames/api/relacao/';
async function api(url,options={}){const response=await fetch(url,{credentials:'same-origin',cache:'no-store',...options});if(response.redirected)throw Error('Sua sessão expirou. Entre novamente.');const payload=await response.json();if(!response.ok)throw Error(payload.error||'Não foi possível concluir a operação.');return payload;}
const post=(path,body)=>api(base+path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':$('[name=csrfmiddlewaretoken]').value},body:JSON.stringify(body)});
function feedback(text,tone='danger'){ $('#roster-feedback').innerHTML=text?`<div class="alert alert-${tone}">${esc(text)}</div>`:''; }
function options(id,entries,first){const select=$(id),value=select.value;select.innerHTML=`<option value="">${esc(first)}</option>`+entries.map(([key,label])=>`<option value="${esc(key)}">${esc(label)}</option>`).join('');select.value=value;}
function eventLabel(e){return day(e.data)+' - '+(e.evento||'Exame');}
function rows(){return (data?.items||[]).filter(r=>(!$('#roster-event').value||r.event_id===$('#roster-event').value)&&(!$('#roster-kind').value||r.tipo===$('#roster-kind').value)&&(!$('#roster-delivery-filter').value||r.delivery_status===$('#roster-delivery-filter').value));}
function suggestDate(){
 const value=$('#roster-pre-date').value;if(!value)return;
 const [year,month,day]=value.split('-').map(Number),lastDay=new Date(Date.UTC(year,month-1,0)).getUTCDate(),d=new Date(Date.UTC(year,month-2,Math.min(day,lastDay)));
 d.setUTCDate(d.getUTCDate()-(d.getUTCDay()+2)%7);$('#roster-deadline').value=d.toISOString().slice(0,10);
}
function deadlineFields(){
 const event=data.events.find(e=>e.id===$('#roster-event').value),saved=data.deadlines[event?.id],form=$('#roster-deadline-form');
 form.hidden=!event;if(!event)return;
 if(deadlineDirty&&form.dataset.event===event.id)return;
 form.dataset.event=event.id;
 const refs=data.pre_options?.[event.id]||[];
 options('#roster-pre-event',refs.map(e=>[e.id,eventLabel(e)]),'Selecione uma pr\u00e9-avalia\u00e7\u00e3o oficial');
 $('#roster-pre-event').value=saved?.pre_event_id||refs.find(e=>e.data===saved?.pre_date)?.id||'';
 $('#roster-pre-date').value=saved?.pre_date||'';
 $('#roster-deadline').value=saved?.deadline||'';
 $('#roster-deadline-note').textContent=saved?.source==='automatic'?'Prazo autom\u00e1tico: sexta-feira em ou antes de um m\u00eas da pr\u00e9-avalia\u00e7\u00e3o. Voc\u00ea pode escolher outra pr\u00e9-avalia\u00e7\u00e3o oficial ou ajustar o limite de entrega e salvar.':saved?'Prazo escolhido para este evento. A data da pr\u00e9-avalia\u00e7\u00e3o vem do calend\u00e1rio oficial; o limite de entrega pode ser ajustado.':'Pr\u00e9-avalia\u00e7\u00e3o n\u00e3o localizada no calend\u00e1rio oficial. N\u00e3o ser\u00e1 usada uma data estimada.';
 for(const id of ['#roster-pre-event','#roster-pre-date','#roster-deadline','#roster-suggest','#roster-save-deadline'])$(id).disabled=!data.can_deadline||!data.enabled;
 for(const id of ['#roster-deadline','#roster-suggest','#roster-save-deadline'])$(id).disabled=!data.can_deadline||!data.enabled||!refs.length;
}

function render(){if(!data)return;const list=rows(),all=(data.items||[]).filter(r=>(!$('#roster-event').value||r.event_id===$('#roster-event').value)&&(!$('#roster-kind').value||r.tipo===$('#roster-kind').value));
 const count=status=>all.filter(r=>r.delivery_status===status).length,received=all.filter(r=>r.delivery?.received).length;
 $('#roster-stats').innerHTML=[['Inscrições',all.length,''],['Cartas entregues',received,'received'],['Cartas faltantes',all.length-received,'missing'],['Entregues no prazo',count('on_time'),'received'],['Entregues em atraso',count('late'),'late']].map(([label,n,style])=>`<div class="roster-stat ${style}"><strong>${n}</strong><span>${label}</span></div>`).join('');
 page=Math.min(page,Math.max(0,Math.ceil(list.length/size)-1));$('#roster-count').textContent=list.length+' candidato(s) · '+count('overdue')+' não entregue(s) com prazo vencido · '+count('unknown_date')+' entrega(s) sem data';
 $('#roster-body').innerHTML=list.slice(page*size,(page+1)*size).map(r=>`<tr><td><strong>${esc(r.nome)}</strong><small>${esc(r.comum)}</small><small>${esc([r.instrumento,r.tonalidade].filter(Boolean).join(' - '))}${r.issued?'':' · Carta ainda não emitida'}</small></td><td>${r.tipo==='organista'?'Organista':'Músico'}<small>${esc(data.modalities[r.modalidade]||r.modalidade)}</small></td><td>${day(r.event_snapshot.data)}<small>${esc(r.event_snapshot.evento)}</small></td><td>${data.deadlines[r.event_id]?day(data.deadlines[r.event_id].deadline)+`<small>${data.deadlines[r.event_id].source==='automatic'?'Autom\u00e1tico':'Escolhido'} \u00b7 Pr\u00e9-avalia\u00e7\u00e3o: ${day(data.deadlines[r.event_id].pre_date)}</small>`:'Pr\u00e9-avalia\u00e7\u00e3o n\u00e3o localizada'}${data.can_deadline&&data.enabled?`<button type="button" class="roster-edit-deadline" data-deadline-event="${esc(r.event_id)}">${data.deadlines[r.event_id]?'Alterar':'Escolher prazo'}</button>`:''}</td><td><span class="roster-state ${esc(r.delivery_status)}">${esc(r.delivery_label)}</span>${r.delivery?.received_on?`<small>${day(r.delivery.received_on)}</small>`:''}${r.delivery?.recorded_by?`<small>${esc(r.delivery.recorded_by)}</small>`:''}</td><td class="text-center"><input type="checkbox" data-receipt="${esc(r.key)}" ${r.delivery?.received?'checked':''} ${data.can_manage&&data.enabled?'':'disabled'} aria-label="Registrar entrega da carta de ${esc(r.nome)}" title="Registrar ou corrigir o recebimento"></td></tr>`).join('')||'<tr><td colspan="6" class="text-center p-4">Nenhum candidato no recorte. Use Exportar / importar para incluir a relação manual.</td></tr>';
 $('#roster-page').textContent=`Página ${page+1} de ${Math.max(1,Math.ceil(list.length/size))}`;$('#roster-prev').disabled=page===0;$('#roster-next').disabled=(page+1)*size>=list.length;
}
async function load(){if(busy)return;busy=true;$('#roster-refresh').disabled=true;try{data=await api(base);options('#roster-event',data.events.map(e=>[e.id,eventLabel(e)]),'Todos os eventos');options('#roster-export-event',data.events.map(e=>[e.id,eventLabel(e)]),'Todos os eventos');options('#roster-export-mode',Object.entries(data.modalities),'Todas as modalidades');$('#roster-import-section').hidden=!data.can_manage;deadlineFields();render();feedback(!data.enabled?'O controle de entrega aguarda a aplicação da migração 044 no Supabase. As cartas emitidas continuam disponíveis.':data.agenda_unavailable?'A agenda está indisponível. Eventos das cartas e relações existentes continuam disponíveis.':'',!data.enabled?'warning':'info');}catch(e){feedback(e.message);}finally{busy=false;$('#roster-refresh').disabled=false;}}
function exportLinks(){const params=new URLSearchParams();for(const [key,id]of [['roster_event','event'],['roster_type','kind'],['roster_mode','mode'],['delivery_status','delivery']])params.set(key,$('#roster-export-'+id).value);for(const [key,id]of [['list_city','letters-list-city'],['list_common','letters-list-common']])params.set(key,$('#'+id).value);$('#roster-export-context').textContent='Recorte: '+($('#letters-list-city').value||'Todos os municípios')+' · '+($('#letters-list-common').value||'Todas as comuns')+'. PDF separado por modalidade, com a marcação de carta entregue na última coluna.';$('#roster-export-pdf').href='/musica/cartas-exames/relacao/pdf/?'+params;$('#roster-export-xlsx').href='/musica/cartas-exames/relacao/excel/?'+params;token=null;$('#roster-import-preview-area').hidden=true;}
$('#roster-export-delivery').innerHTML=$('#roster-delivery-filter').innerHTML;
$('#letters-roster-open').addEventListener('click',async()=>{if(!data)await load();if(!data)return;$('#roster-export-event').value=$('#roster-event').value||$('#letters-event').value;$('#roster-export-kind').value=$('#roster-kind').value;$('#roster-export-delivery').value=$('#roster-delivery-filter').value;exportLinks();$('#roster-panel').showModal();});
$('#roster-panel-close').addEventListener('click',()=>$('#roster-panel').close());
for(const id of ['event','kind','mode','delivery'])$('#roster-export-'+id).addEventListener('change',exportLinks);
for(const id of ['#roster-event','#roster-kind','#roster-delivery-filter'])$(id).addEventListener('change',()=>{page=0;if(id==='#roster-event'){deadlineDirty=false;deadlineFields();}render();});
$('#roster-prev').addEventListener('click',()=>{page--;render();});$('#roster-next').addEventListener('click',()=>{page++;render();});$('#roster-refresh').addEventListener('click',load);
$('#roster-pre-event').addEventListener('change',()=>{
 const ref=data.pre_options?.[$('#roster-event').value]?.find(e=>e.id===$('#roster-pre-event').value);
 $('#roster-pre-date').value=ref?.data||'';if(ref)suggestDate();else $('#roster-deadline').value='';for(const id of ['#roster-deadline','#roster-suggest','#roster-save-deadline'])$(id).disabled=!ref||!data.can_deadline||!data.enabled;deadlineDirty=true;
});
$('#roster-pre-date').readOnly=true;
$('#roster-deadline').addEventListener('change',()=>{deadlineDirty=true;});
$('#roster-suggest').addEventListener('click',()=>{if(!$('#roster-pre-date').value){$('#roster-pre-date').reportValidity();return;}suggestDate();deadlineDirty=true;});
$('#roster-deadline-form').addEventListener('submit',async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{await post('prazo/',{event_id:$('#roster-event').value,pre_event_id:$('#roster-pre-event').value,pre_date:$('#roster-pre-date').value,deadline:$('#roster-deadline').value,version:data.deadlines[$('#roster-event').value]?.version||0});deadlineDirty=false;await load();feedback('Prazo de entrega salvo.','success');}catch(err){feedback(err.message);}finally{b.disabled=false;}});
$('#roster-body').addEventListener('click',e=>{const edit=e.target.closest('[data-deadline-event]');if(edit){$('#roster-event').value=edit.dataset.deadlineEvent;deadlineDirty=false;deadlineFields();page=0;render();$('#roster-deadline-form').scrollIntoView({behavior:'smooth',block:'center'});$('#roster-pre-event').focus({preventScroll:true});return;}const box=e.target.closest('[data-receipt]');if(!box)return;e.preventDefault();receipt=data.items.find(r=>r.key===box.dataset.receipt);if(!receipt)return;$('#roster-receipt-person').textContent=receipt.nome+' - '+receipt.comum;$('#roster-received').checked=true;$('#roster-received-on').value=receipt.delivery?.received_on||today();$('#roster-received-on').max=today();$('#roster-received-on').required=$('#roster-received').checked;$('#roster-received-on').disabled=!$('#roster-received').checked;$('#roster-receipt-error').textContent='';$('#roster-receipt-help').textContent=receipt.delivery?.received?'Para desfazer o recebimento, desmarque Carta entregue e salve a altera\u00e7\u00e3o.':'Marque Carta entregue e informe a data efetiva de recebimento.';$('#roster-receipt-form button[type=submit]').textContent='Salvar recebimento';$('#roster-receipt-dialog').showModal();});
$('#roster-received').addEventListener('change',()=>{$('#roster-received-on').required=$('#roster-received').checked;$('#roster-received-on').disabled=!$('#roster-received').checked;$('#roster-receipt-form button[type=submit]').textContent=$('#roster-received').checked?'Salvar recebimento':'Salvar como n\u00e3o entregue';});
$('#roster-receipt-cancel').addEventListener('click',()=>$('#roster-receipt-dialog').close());
$('#roster-receipt-form').addEventListener('submit',async e=>{
 e.preventDefault();if(receiptSaving||!receipt)return;receiptSaving=true;
 const button=e.submitter,original=button.innerHTML,selected=receipt,received=$('#roster-received').checked;
 const payload={key:selected.key,version:selected.version,received,received_on:received?$('#roster-received-on').value:null};
 button.disabled=true;button.setAttribute('aria-busy','true');button.innerHTML='<i class="fa fa-spinner fa-spin me-1" aria-hidden="true"></i>Salvando...';
 const notify=(type,title,message,detail)=>window.AppFeedback?.show({type,title,message,detail,flow:'save',toast:true});
 notify('loading','Salvando recebimento',received?'Registrando a entrega da carta.':'Desmarcando a entrega da carta.');
 try{
  const result=await post('entrega/',payload);
  const delivery=result.result?.data?.delivery||{received,received_on:payload.received_on};
  selected.delivery=delivery;selected.version=result.result?.version||selected.version+1;
  const limit=data.deadlines[selected.event_id]?.deadline;
  selected.delivery_status=received?(!delivery.received_on?'unknown_date':!limit?'received':delivery.received_on<=limit?'on_time':'late'):!limit?'no_deadline':today()>limit?'overdue':'pending';
  selected.delivery_label=$('#roster-delivery-filter').querySelector(`option[value="${selected.delivery_status}"]`)?.textContent||'';
  render();$('#roster-receipt-dialog').close();await load();
  notify('success',received?'Recebimento salvo':'Entrega desmarcada',received?'A entrega da carta foi registrada.':'A carta voltou a constar como n\u00e3o entregue.','Altera\u00e7\u00e3o salva no hist\u00f3rico de recebimentos.');
 }catch(err){
  $('#roster-receipt-error').textContent=err.message;
  notify('error','N\u00e3o foi poss\u00edvel salvar',err.message,'O recebimento anterior foi preservado. Tente novamente.');
 }finally{button.disabled=false;button.innerHTML=original;button.removeAttribute('aria-busy');receiptSaving=false;}
});
$('#roster-import-form').addEventListener('submit',async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;token=null;$('#roster-import-preview-area').hidden=true;$('#roster-import-feedback').textContent='Consultando cadastro e histórico do GEM...';try{if(!data.enabled)throw Error('Aplique a migração 044 antes de importar.');if(!$('#roster-export-event').value||!$('#roster-export-kind').value||!$('#roster-export-mode').value)throw Error('Selecione evento, tipo e modalidade antes de importar.');const body=new FormData();body.append('arquivo',$('#roster-file').files[0]);body.append('event_id',$('#roster-export-event').value);body.append('tipo',$('#roster-export-kind').value);body.append('modalidade',$('#roster-export-mode').value);const preview=await api(base+'importar/previa/',{method:'POST',headers:{'X-CSRFToken':$('[name=csrfmiddlewaretoken]').value},body});token=preview.token;$('#roster-import-summary').textContent=preview.new+' candidato(s) novo(s) · '+preview.existing+' existente(s), preservados';$('#roster-import-body').innerHTML=preview.items.map(r=>`<tr><td><strong>${esc(r.nome)}</strong><small>${esc(r.comum)}</small></td><td>${esc(r.match_label)}<small>${esc(r.program_assessment?.label||'Consulta documental não se aplica a esta modalidade')}</small></td><td>${r.delivery.received?'Entregue':'Não entregue'}<small>${r.delivery.received_on?day(r.delivery.received_on):r.delivery.received?'Data não informada':''}</small></td><td>${r.exists?'Preservar existente':'Incluir na relação'}</td></tr>`).join('');$('#roster-import-preview-area').hidden=false;$('#roster-import-confirm').disabled=!preview.new;$('#roster-import-feedback').textContent='Confira a prévia. A importação não emite cartas nem aprova candidatos.';}catch(err){$('#roster-import-feedback').textContent=err.message;}finally{b.disabled=false;}});
$('#roster-file').addEventListener('change',()=>{token=null;$('#roster-import-preview-area').hidden=true;});
$('#roster-import-confirm').addEventListener('click',async e=>{if(!token)return;const b=e.currentTarget;b.disabled=true;try{const result=await post('importar/confirmar/',{token});token=null;$('#roster-import-preview-area').hidden=true;$('#roster-import-feedback').textContent=(result.result?.inserted||0)+' candidato(s) importado(s).';await load();}catch(err){$('#roster-import-feedback').textContent=err.message;}finally{b.disabled=false;}});
window.addEventListener('letters-updated',()=>{clearTimeout(refreshTimer);refreshTimer=setTimeout(()=>{if(!document.querySelector('dialog[open]'))load();},300);});load();
})();
