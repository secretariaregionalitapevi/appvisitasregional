(() => {
  const $ = selector => document.querySelector(selector);
  const {load, feedback, request, esc, date} = window.MusicEventsDashboard;
  const state = {importToken:null};
  $('#events-import').onclick=()=>{ $('#import-error').textContent=''; bootstrap.Modal.getOrCreateInstance($('#events-import-modal')).show(); };
  $('#import-type').onchange=()=>{ $('#import-family').disabled=$('#import-type').value==='ENSAIO_REGIONAL'; if($('#import-family').disabled) $('#import-family').value='GERAL'; };
  let previewVersion=0;
  $('#import-file').onchange=async()=>{
    const version=++previewVersion;
    state.importToken=null; $('#import-confirm').disabled=true; $('#import-reviewed').checked=false; $('#import-error').textContent='';
    const file=$('#import-file').files[0]; if(!file) return;
    $('#import-preview').textContent='Conferindo a aba nominal…';
    const form=new FormData();form.append('arquivo',file);
    try {
      const data=await request('/musica/eventos/api/importacao/previa/',{method:'POST',headers:{'X-CSRFToken':$('#events-import-form [name=csrfmiddlewaretoken]').value},body:form});
      if(version!==previewVersion) return;
      state.importToken=data.token; $('#import-date').value=data.suggested_date; $('#import-title').value=`${$('#import-type').value==='ENSAIO_REGIONAL'?'Ensaio Regional':'Reunião Técnica'} · ${date(data.suggested_date)}`;
      $('#import-preview').innerHTML=`<div class="alert alert-success"><strong>${data.count} registros únicos prontos para importar</strong><br>Aba: ${esc(data.sheet)} · Linhas recebidas: ${data.raw_count} · UUIDs repetidos: ${data.duplicates}<br>Possíveis homônimos ou duplicidades com UUID diferente: ${data.possible_duplicates} (preservados para conferência)</div><p><strong>Locais:</strong> ${Object.entries(data.locations).map(([key,value])=>`${esc(key)}: ${value}`).join(' · ')}</p><p><strong>Datas originais:</strong> ${Object.entries(data.dates).map(([key,value])=>`${date(key)}: ${value}`).join(' · ')}</p><p><strong>Classificação proposta:</strong> ${Object.entries(data.categories).map(([key,value])=>`${esc(key)}: ${value}`).join(' · ')}</p><p class="text-muted small">Instrumentistas contam como músicos; órgão e funções de organistas, como organistas. O cargo é preservado separadamente. Nenhum vínculo com pessoa do SAM é presumido.</p>`;
      $('#import-confirm').disabled=false;
    } catch(error) { if(version===previewVersion){$('#import-preview').textContent='Prévia indisponível.';$('#import-error').textContent=error.message;} }
  };
  $('#events-import-form').onsubmit=async event=>{
    event.preventDefault(); if(!state.importToken) return;
    $('#import-confirm').disabled=true; $('#import-error').textContent='';
    try {
      const data=await request('/musica/eventos/api/importacao/confirmar/',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':event.target.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify({token:state.importToken,titulo:$('#import-title').value,data_evento:$('#import-date').value,tipo:$('#import-type').value,familia:$('#import-family').value,conferido:$('#import-reviewed').checked})});
      bootstrap.Modal.getOrCreateInstance($('#events-import-modal')).hide();
      await window.MusicEventsDashboard.selectEvent(data.evento_id); feedback(data.ja_importado?'Este arquivo já estava importado. O evento existente foi preservado.':`${data.quantidade} registros importados. Os indicadores do evento estão disponíveis no painel.`,'success');
    } catch(error) {$('#import-error').textContent=error.message;} finally {$('#import-confirm').disabled=!state.importToken;}
  };
  $('#events-new').onclick=()=>{ $('#events-create-error').textContent=''; bootstrap.Modal.getOrCreateInstance($('#events-create-modal')).show(); };
  $('#event-type').onchange=()=>{ $('#event-family').disabled=$('#event-type').value==='ENSAIO_REGIONAL'; if($('#event-family').disabled) $('#event-family').value='GERAL'; };
  $('#events-create-form').onsubmit=async event=>{
    event.preventDefault(); $('#events-save').disabled=true; $('#events-create-error').textContent='';
    try {
      const payload=Object.fromEntries(new FormData(event.target)); delete payload.csrfmiddlewaretoken;
      await request('/musica/eventos/api/eventos/',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':event.target.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify(payload)});
      bootstrap.Modal.getOrCreateInstance($('#events-create-modal')).hide(); event.target.reset(); $('#event-type').onchange(); await load(); feedback('Rascunho registrado com o responsável da sessão.','success');
    } catch(error) {$('#events-create-error').textContent=error.message;} finally {$('#events-save').disabled=false;}
  };
})();
