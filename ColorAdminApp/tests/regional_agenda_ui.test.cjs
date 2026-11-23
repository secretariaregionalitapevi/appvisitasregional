const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const path=require('node:path');
const {randomUUID}=require('node:crypto');
const {JSDOM}=require(process.env.AGENDA_JSDOM_MODULE||'../../tmp/agenda-validation/node_modules/jsdom');
const template=readFileSync(path.resolve(__dirname,'../../tmp/agenda-validation/page.html'),'utf8');
const script=readFileSync(path.resolve(__dirname,'../../static/js/regional-agenda.js'),'utf8');
const user='00000000-0000-0000-0000-000000000001';
const event={id:'12345678-1234-1234-1234-123456789abc',administracao_id:'cotia',agenda_id:'cotia',municipio:'Cotia',titulo:'Reunião <teste>',categoria:'Reunião Técnica',local:'Central',inicio:'2099-12-01T19:00:00-03:00',fim:'2099-12-01T21:00:00-03:00',status:'PENDENTE_ADM',versao:1,criado_por:'other',criado_por_nome:'Solicitante',conflitos:['original'],conflitos_externos:[],detalhes:true};
const administrations=[{id:'itapevi',nome:'Itapevi',municipios:['Itapevi'],configurada:true},{id:'cotia',nome:'Cotia / Caucaia / VGP',municipios:[],configurada:true},{id:'jandira',nome:'Jandira',municipios:[],configurada:true},{id:'santana',nome:'Santana / Pirapora',municipios:[],configurada:true}];
const calendars=[['cotia','cotia','Cotia'],['caucaia','cotia','Caucaia do Alto'],['vargem_grande','cotia','Vargem Grande Paulista'],['itapevi','itapevi','Itapevi'],['jandira','jandira','Jandira'],['santana','santana','Santana de Parnaíba'],['pirapora','santana','Pirapora do Bom Jesus']].map(([id,administracao_id,nome])=>({id,administracao_id,nome,municipio:nome,calendar_id:id+'@google',configurada:true}));
const flush=async()=>{for(let i=0;i<5;i++)await new Promise(r=>setTimeout(r,0));};
async function setup(options={}){
  const dom=new JSDOM(template,{url:'https://app.example/musica/agenda-regional/'+(options.query||''),runScripts:'outside-only'});
  const w=dom.window,calls=[],messages=[];
  const NativeDate=w.Date;
  w.Date=class extends NativeDate{constructor(...args){super(...(args.length?args:['2099-12-01T12:00:00-03:00']));}};
  Object.defineProperty(w.crypto,'randomUUID',{value:randomUUID});
  w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  w.HTMLDialogElement.prototype.close=function(){this.open=false;};
  w.AppFeedback={show:message=>messages.push(message)};
  const roles=options.regional?[{papel:'REGIONAL',administracao_id:null}]:[{papel:'ENCARREGADO',administracao_id:'itapevi'}];
  const e={...event,...options.event};
  const adminChoices=administrations.map(a=>({...a,municipios:options.allMunicipalities?calendars.filter(c=>c.administracao_id===a.id).map(c=>c.municipio):a.municipios}));
  w.fetch=async(url,request)=>{
    calls.push({url,request});let data;
    if(options.error) return {ok:false,json:async()=>({error:'Serviço indisponível'})};
    if(url.includes('/api/configuracao/'))data={administrations:adminChoices.map(a=>({...a,calendar_id:a.id+'@google',prazo_horas:48})),calendars,responsibles:[],users:[{user_id:user,full_name:'Encarregado Itapevi',municipio:'Itapevi'}]};
    else if(request.method==='POST'){
      const body=JSON.parse(request.body);
      data={event:{...e,status:body.acao==='parecer'?'PENDENTE_REGIONAL':'PRONTO'}};
    }else if(url.includes('/eventos/'+event.id+'/'))data={event:e,conflicts:[{id:'original',administracao_id:'itapevi',titulo:'Compromisso existente',inicio:e.inicio,fim:e.fim,status:'CONFIRMADO'}],opinions:options.opinions||[],history:[]};
    else data={events:[e],administrations:adminChoices,calendars,roles,regional:!!options.regional,master:true,user_id:user,configurada:options.configurada??true,...(options.connection?{connection:options.connection}:{}),...(options.sync?{sync:options.sync}:{})};
    return {ok:true,json:async()=>data};
  };
  w.eval(script);await flush();return {dom,w,doc:w.document,calls,messages};
}
test('UI renders actual monthly template and safely escapes event titles',async()=>{
  const s=await setup();try{
    const cells=s.doc.querySelectorAll('.agenda-day').length;
    assert.ok(cells>=28&&cells<=42);assert.equal(cells%7,0);
    assert.ok(s.doc.getElementById('agenda-list').textContent.includes('Reunião <teste>'));
    assert.equal(s.doc.querySelector('teste'),null);
    assert.equal(s.doc.getElementById('agenda-loading').hidden,true);
  }finally{s.dom.window.close();}
});
test('UI cross-administration pending analysis offers the delegated administration',async()=>{
  const s=await setup();try{
    s.doc.querySelector('[data-view=pending]').click();await flush();
    s.doc.querySelector('#agenda-list [data-event]').click();await flush();
    assert.equal(s.doc.getElementById('agenda-detail-dialog').open,true);
    const f=s.doc.getElementById('agenda-decision');assert.equal(f.hidden,false);
    assert.equal(f.elements.administracao_id.value,'itapevi');
    f.elements.decisao.value='IMPEDIMENTO';f.elements.justificativa.value='Responsável indisponível';
    f.dispatchEvent(new s.w.Event('submit',{bubbles:true,cancelable:true}));await flush();
    const post=s.calls.find(c=>c.request.method==='POST');const data=JSON.parse(post.request.body);
    assert.equal(data.acao,'parecer');assert.equal(data.versao,1);assert.equal(data.administracao_id,'itapevi');
    assert.equal(data.decisao,'IMPEDIMENTO');assert.equal(s.messages.at(-1).title,'Decisão registrada');
  }finally{s.dom.window.close();}
});
test('UI Regional decision shows approval/refusal and requires justification',async()=>{
  const s=await setup({regional:true,event:{status:'PENDENTE_REGIONAL'}});try{
    s.doc.querySelector('#agenda-list [data-event]').click();await flush();
    const f=s.doc.getElementById('agenda-decision');assert.equal(f.hidden,false);
    assert.equal(s.doc.getElementById('agenda-decision-adm-label').hidden,true);
    assert.ok([...f.elements.decisao.options].some(o=>o.value==='RECUSAR'));
    assert.equal(f.elements.justificativa.required,true);
  }finally{s.dom.window.close();}
});
test('UI creation sends Sao Paulo offsets and keeps same request ID on retry',async()=>{
  const s=await setup();try{
    s.doc.getElementById('agenda-new').click();const f=s.doc.getElementById('agenda-form');
    assert.equal(f.elements.administracao_id.options.length,1);assert.equal(f.elements.municipio.value,'Itapevi');
    Object.assign(f.elements.titulo,{value:'Novo evento'});f.elements.local.value='Central';
    f.elements.inicio.value='2099-12-03T19:00';f.elements.fim.value='2099-12-03T21:00';
    const id=f.dataset.id;f.dispatchEvent(new s.w.Event('submit',{bubbles:true,cancelable:true}));await flush();
    const post=s.calls.find(c=>c.request.method==='POST');const body=JSON.parse(post.request.body);
    assert.equal(body.id,id);assert.equal(body.inicio,'2099-12-03T19:00:00-03:00');
    assert.equal(body.administracao_id,'itapevi');assert.equal(body.csrfmiddlewaretoken,undefined);
    assert.equal(post.request.headers['X-CSRFToken'],'test-csrf');
    assert.equal(s.doc.getElementById('agenda-form-dialog').open,false);
  }finally{s.dom.window.close();}
});
test('UI cancel controls use project classes and close icon',async()=>{
  const s=await setup();try{
    for(const b of s.doc.querySelectorAll('button'))if(b.textContent.trim().startsWith('Cancelar')){
      assert.ok(b.classList.contains('btn-danger'));assert.ok(b.classList.contains('app-btn-cancel'));assert.ok(b.querySelector('.fa-xmark'));
    }
  }finally{s.dom.window.close();}
});
test('UI service failure is not shown as an empty or confirmed calendar',async()=>{
  const s=await setup({error:true});try{
    assert.ok(s.doc.getElementById('agenda-loading').textContent.includes('Não foi possível'));
    assert.equal(s.messages[0].type,'error');assert.equal(s.doc.querySelectorAll('.agenda-day').length,0);
  }finally{s.dom.window.close();}
});
test('UI notification link opens the requested event analysis',async()=>{
  const s=await setup({query:'?evento='+event.id});try{assert.equal(s.doc.getElementById('agenda-detail-dialog').open,true);}finally{s.dom.window.close();}
});
test('UI administration controls filter both month and list and can return to all',async()=>{
  const s=await setup();try{
    s.doc.querySelector('button[data-admin=itapevi]').click();
    assert.equal(s.doc.getElementById('agenda-filter').value,'itapevi');
    assert.equal(s.doc.querySelectorAll('.agenda-event-pill').length,0);
    assert.equal(s.doc.querySelector('button[data-admin=itapevi]').getAttribute('aria-pressed'),'true');
    s.doc.getElementById('agenda-all').click();
    assert.equal(s.doc.getElementById('agenda-filter').value,'');
    assert.ok(s.doc.querySelectorAll('.agenda-event-pill').length>0);
  }finally{s.dom.window.close();}
});
test('UI day selection updates summary and pre-fills the event dates',async()=>{
  const s=await setup();try{
    s.doc.querySelector('.agenda-date[data-day="2099-12-03"]').click();
    assert.ok(s.doc.getElementById('agenda-day-title').textContent.includes('3 de dezembro'));
    assert.ok(s.doc.getElementById('agenda-mobile-day-content').textContent.includes('3 de dezembro'));
    s.doc.getElementById('agenda-day-new').click();
    assert.equal(s.doc.getElementById('agenda-form').elements.inicio.value,'2099-12-03T19:00');
    assert.equal(s.doc.getElementById('agenda-form').elements.fim.value,'2099-12-03T21:00');
  }finally{s.dom.window.close();}
});
test('UI keyboard moves between calendar dates with visible selection',async()=>{
  const s=await setup();try{
    const current=s.doc.querySelector('.agenda-date[data-day="2099-12-01"]');
    current.dispatchEvent(new s.w.KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true,cancelable:true}));
    const next=s.doc.querySelector('.agenda-date[data-day="2099-12-02"]');
    assert.equal(next.getAttribute('aria-pressed'),'true');
    assert.equal(s.doc.activeElement,next);
  }finally{s.dom.window.close();}
});
test('UI search is accent-insensitive and works in list view',async()=>{
  const s=await setup();try{
    const search=s.doc.getElementById('agenda-search');search.value='reuniao';
    search.dispatchEvent(new s.w.Event('input',{bubbles:true}));
    assert.ok(s.doc.querySelectorAll('.agenda-event-pill').length>0);
    s.doc.querySelector('button[data-view=list]').click();await flush();
    assert.equal(s.doc.getElementById('agenda-calendar').hidden,true);
    assert.equal(s.doc.getElementById('agenda-list').hidden,false);
    search.value='termo inexistente';search.dispatchEvent(new s.w.Event('input',{bubbles:true}));
    assert.ok(s.doc.getElementById('agenda-list').textContent.includes('Nenhum resultado encontrado'));
  }finally{s.dom.window.close();}
});
test('UI reserves keep their details private and do not offer an event action',async()=>{
  const s=await setup({event:{detalhes:false,titulo:'Horário reservado'}});try{
    assert.equal(s.doc.querySelectorAll('.agenda-event-pill[data-event]').length,0);
    assert.equal(s.doc.querySelectorAll('.agenda-day-entry[data-event]').length,0);
  }finally{s.dom.window.close();}
});
test('UI configures seven municipal IDs inside the four administration groups',async()=>{
  const s=await setup();try{
    s.doc.getElementById('agenda-config').click();await flush();
    assert.equal(s.doc.querySelectorAll('.agenda-config-group').length,4);
    assert.equal(s.doc.querySelectorAll('.agenda-municipal-form').length,7);
    assert.equal(s.doc.querySelectorAll('.agenda-deadline-form').length,4);
    const f=s.doc.querySelector('form[data-calendar=caucaia]');f.elements.calendar_id.value='new-caucaia@google';
    f.dispatchEvent(new s.w.Event('submit',{bubbles:true,cancelable:true}));await flush();
    const data=JSON.parse(s.calls.find(c=>c.request.method==='POST').request.body);
    assert.equal(data.agenda_id,'caucaia');assert.equal(data.calendar_id,'new-caucaia@google');
    assert.equal(data.prazo_horas,undefined);
  }finally{s.dom.window.close();}
});
test('UI municipal filter is independent from its administration and preselects creation',async()=>{
  const s=await setup({allMunicipalities:true});try{
    s.doc.querySelector('button[data-admin=cotia]').click();
    const filter=s.doc.getElementById('agenda-calendar-filter');assert.equal(filter.options.length,4);
    filter.value='caucaia';filter.dispatchEvent(new s.w.Event('change',{bubbles:true}));
    assert.equal(s.doc.querySelectorAll('.agenda-event-pill').length,0);
    s.doc.getElementById('agenda-new').click();const form=s.doc.getElementById('agenda-form');
    assert.equal(form.elements.administracao_id.value,'cotia');assert.equal(form.elements.municipio.value,'Caucaia do Alto');
  }finally{s.dom.window.close();}
});
test('UI explains missing IDs and authentication separately',async()=>{
  const s=await setup({configurada:false,connection:{token_configurado:false,ids_configurados:4,missing_calendars:['Cotia','Vargem Grande Paulista','Pirapora do Bom Jesus']}});try{
    const text=s.doc.getElementById('agenda-setup').textContent;
    assert.ok(text.includes('IDs ainda não salvos: Cotia'));assert.ok(text.includes('AGENDA_N8N_TOKEN'));
  }finally{s.dom.window.close();}
});
test('UI shows existing Google events as read-only even for Regional managers',async()=>{
  const s=await setup({regional:true,event:{somente_leitura:true,origem:'google',status:'GOOGLE',criado_por:null}});try{
    s.doc.querySelector('#agenda-list [data-event]').click();await flush();
    assert.equal(s.doc.getElementById('agenda-cancellation').hidden,true);
    assert.equal(s.doc.getElementById('agenda-decision').hidden,true);
    assert.ok(s.doc.getElementById('agenda-detail').textContent.includes('agenda de origem'));
  }finally{s.dom.window.close();}
});
