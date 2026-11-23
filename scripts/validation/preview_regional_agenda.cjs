/* Capturas offline do template real, com dados de demonstração apenas neste teste.
 * Não abre localhost e não consulta nem altera o sistema ou o Google Calendar.
 */
const {chromium}=require('../../tmp/agenda-validation/node_modules/playwright-core');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..');
const output=path.join(root,'tmp/agenda-validation');
const browserPath=process.env.AGENDA_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe';
const mime={'.css':'text/css','.js':'text/javascript','.woff2':'font/woff2','.woff':'font/woff','.ttf':'font/ttf','.png':'image/png','.jpg':'image/jpeg','.svg':'image/svg+xml'};
const admins=[{id:'cotia',nome:'Cotia / Caucaia / VGP',municipios:['Cotia','Caucaia do Alto','Vargem Grande Paulista'],configurada:true},{id:'itapevi',nome:'Itapevi',municipios:['Itapevi'],configurada:true},{id:'jandira',nome:'Jandira',municipios:['Jandira'],configurada:true},{id:'santana',nome:'Santana / Pirapora',municipios:['Santana de Parnaíba','Pirapora do Bom Jesus'],configurada:true}];
const calendars=[['cotia','cotia','Cotia'],['caucaia','cotia','Caucaia do Alto'],['vargem_grande','cotia','Vargem Grande Paulista'],['itapevi','itapevi','Itapevi'],['jandira','jandira','Jandira'],['santana','santana','Santana de Parnaíba'],['pirapora','santana','Pirapora do Bom Jesus']].map(([id,administracao_id,nome])=>({id,administracao_id,nome,municipio:nome,calendar_id:id+'@example.com',configurada:true}));
const samples=[['itapevi',23,'Reunião de planejamento','CONFIRMADO',19],['cotia',25,'Reunião técnica','PENDENTE_ADM',19],['jandira',28,'Ensaio regional','CONFIRMADO',17],['santana',29,'Encontro de responsáveis','PENDENTE_REGIONAL',10],['itapevi',27,'Reunião do ministério','CONFIRMADO',19],['cotia',14,'Reunião de coordenação','CONFIRMADO',16],['itapevi',7,'Ensaio regional','CONFIRMADO',17]];
const events=samples.map(([adm,day,title,status,hour],i)=>({id:`12345678-1234-1234-1234-${String(i+1).padStart(12,'0')}`,administracao_id:adm,municipio:admins.find(a=>a.id===adm).municipios[0],titulo:title,categoria:'Encontro regional',local:'Central',inicio:`2026-11-${String(day).padStart(2,'0')}T${hour}:00:00-03:00`,fim:`2026-11-${String(day).padStart(2,'0')}T${hour+2}:00:00-03:00`,status,versao:1,criado_por:'preview',criado_por_nome:'Secretaria Regional',conflitos:[],conflitos_externos:[],detalhes:true}));
events.forEach(e=>{e.agenda_id=calendars.find(c=>c.municipio===e.municipio).id;});
(async()=>{
  const browser=await chromium.launch({executablePath:browserPath,headless:true,args:['--disable-extensions','--no-first-run']});
  try {
    const page=await browser.newPage({viewport:{width:1600,height:1050},deviceScaleFactor:1});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',async route=>{
      const url=new URL(route.request().url());
      if(url.hostname!=='agenda-preview.invalid'||!url.pathname.startsWith('/static/'))return route.abort();
      const file=path.resolve(root,'.'+decodeURIComponent(url.pathname));
      if(!file.startsWith(path.join(root,'static')+path.sep)||!fs.existsSync(file))return route.abort();
      await route.fulfill({body:fs.readFileSync(file),contentType:mime[path.extname(file)]||'application/octet-stream'});
    });
    let html=fs.readFileSync(path.join(output,'preview.html'),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'');
    html=html.replace('<head>','<head><base href="https://agenda-preview.invalid/">');
    await page.setContent(html,{waitUntil:'load'});
    await page.evaluate(({admins,events,calendars})=>{
      const RealDate=Date;window.Date=class extends RealDate{constructor(...args){super(...(args.length?args:['2026-11-23T12:00:00-03:00']));}};
      if(!window.crypto.randomUUID)Object.defineProperty(window.crypto,'randomUUID',{value:()=> '12345678-1234-1234-1234-123456789abc'});
      window.AppFeedback={show:()=>{}};
      window.fetch=async(url,options)=>{
        const id=url.match(/eventos\/([0-9a-f-]{36})\//)?.[1];
        if(url.includes('configuracao'))return {ok:true,json:async()=>({administrations:admins.map(a=>({...a,prazo_horas:48,calendar_id:''})),calendars,responsibles:[],users:[]})};
        const data=id?{event:events.find(e=>e.id===id),conflicts:[],opinions:[],history:[]}:
          {events:window.__previewEmpty?[]:url.includes('pending=1')?events.filter(e=>e.status.startsWith('PENDENTE')):events,
           administrations:admins,calendars,roles:[{papel:'REGIONAL',administracao_id:null}],regional:true,master:true,user_id:'preview',configurada:!window.__previewEmpty};
        return {ok:true,json:async()=>data};
      };
    },{admins,events,calendars});
    await page.addScriptTag({content:fs.readFileSync(path.join(root,'static/js/regional-agenda.js'),'utf8')});
    await page.waitForSelector('.agenda-day');
    await page.evaluate(()=>document.fonts.ready);
    await page.screenshot({path:path.join(output,'agenda-desktop.png'),fullPage:true});
    await page.locator('.agenda-event-pill[data-event]').first().click();
    await page.waitForSelector('#agenda-detail-dialog[open]');
    await page.screenshot({path:path.join(output,'agenda-detail.png'),fullPage:true});
    await page.locator('#agenda-detail-dialog [data-close]').click();
    await page.locator('#agenda-new').click();
    await page.screenshot({path:path.join(output,'agenda-form.png'),fullPage:true});
    await page.locator('#agenda-form-dialog [data-close]').click();
    await page.locator('#agenda-config').click();
    await page.waitForSelector('#agenda-config-dialog[open]');
    assert.equal(await page.locator('.agenda-municipal-form').count(),7);
    assert.equal(await page.locator('.agenda-config-group').count(),4);
    await page.screenshot({path:path.join(output,'agenda-municipal-config.png'),fullPage:true});
    await page.locator('#agenda-config-dialog [data-close]').click();
    await page.evaluate(()=>document.documentElement.setAttribute('data-bs-theme','dark'));
    await page.waitForFunction(()=>getComputedStyle(document.getElementById('agenda-config')).backgroundColor==='rgb(28, 43, 56)');
    await page.screenshot({path:path.join(output,'agenda-dark.png'),fullPage:true});
    await page.evaluate(()=>document.documentElement.removeAttribute('data-bs-theme'));
    await page.waitForFunction(()=>getComputedStyle(document.getElementById('agenda-config')).backgroundColor==='rgb(255, 255, 255)');
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(output,'agenda-mobile.png'),fullPage:true});
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
    assert.equal(overflow,false,'Não deve haver rolagem horizontal no celular');
    await page.locator('button[data-view=pending]').click();
    await page.waitForSelector('#agenda-list:not([hidden])');
    await page.screenshot({path:path.join(output,'agenda-mobile-pending.png'),fullPage:true});
    await page.setViewportSize({width:1880,height:920});
    await page.evaluate(()=>{window.__previewEmpty=true;});
    await page.locator('button[data-view=calendar]').click();
    await page.waitForSelector('#agenda-setup:not([hidden])');
    await page.screenshot({path:path.join(output,'agenda-empty-desktop.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    console.log('Desktop, celular, modo escuro e formulários capturados offline; sem erros de JavaScript ou rolagem horizontal.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
