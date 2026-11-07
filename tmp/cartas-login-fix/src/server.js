'use strict';
const http=require('node:http'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'..');for(const name of ['.env.local','.env']){const file=path.join(root,name);if(fs.existsSync(file))process.loadEnvFile(file);}
const {Store,headers}=require('./store'),{getAgenda}=require('./agenda');
const {administrations,administration,modalities,examEvents,eligibleEvent,validate,duplicateKey,norm,commonMatches,findCommonInAdministration}=require('./domain');
const {makePdf,availableModalities,letterFilename}=require('./pdf');
const store=new Store();
const adminHandler=require('./admin-router').createAdminHandler(store);
const {consultation}=require('./program');
const {studentActivity,activityReview}=require('./student-activity');
const {visitorSession}=require('./session');
const {legacyPayload}=require('./legacy-payload');
function json(res,status,data){res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(data));}
async function body(req){let text='';for await(const chunk of req){text+=chunk;if(Buffer.byteLength(text)>20000)throw Object.assign(Error('Dados excedem o tamanho permitido.'),{status:413});}try{return JSON.parse(text||'{}');}catch{throw Object.assign(Error('Dados inválidos.'),{status:400});}}
async function handler(req,res){
  res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Referrer-Policy','same-origin');res.setHeader('X-Frame-Options','DENY');
  res.setHeader('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'");
  try{
    const url=new URL(req.url,'http://app.invalid'),route=url.pathname;
    if(route.startsWith('/api/admin/'))return adminHandler(req,res,url);
    if(route==='/api/health')return json(res,200,{ok:true,configured:!!(store.url&&store.key),templates:availableModalities});
    if(route==='/api/login'&&req.method==='POST'){
      const p=await body(req);if(!store.url)return json(res,503,{error:'Configure o Supabase no servidor.'});
      const r=await fetch(store.url+'/auth/v1/token?grant_type=password',{method:'POST',headers:{...headers(process.env.SUPABASE_PUBLISHABLE_KEY||process.env.SUPABASE_ANON_KEY||''),'Content-Type':'application/json'},body:JSON.stringify({email:p.email,password:p.password}),signal:AbortSignal.timeout(12000)});
      const data=await r.json();if(!r.ok)return json(res,401,{error:'Não foi possível entrar. Confira e-mail e senha.'});
      res.setHeader('Set-Cookie',`cartas_session=${data.access_token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=${data.expires_in}${process.env.NODE_ENV==='production'?'; Secure':''}`);
      return json(res,200,{ok:true});
    }
    if(route==='/api/logout'&&req.method==='POST'){res.setHeader('Set-Cookie','cartas_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0');return json(res,200,{ok:true});}
    if(route.startsWith('/api/')){
      if(!store.url||!store.key)throw Object.assign(Error('Configure o Supabase no servidor para continuar.'),{status:503});
      const token=req.headers.cookie?.match(/(?:^|;\s*)cartas_session=([^;]+)/)?.[1];
      const authenticated=token?await store.user(token):null;
      const user=authenticated||{id:visitorSession(req,res,store.key),email:'Solicitante da carta',guest:true};
      if(route==='/api/bootstrap'&&req.method==='GET'){const commons=await store.commons();return json(res,200,{administrations,modalities,available:availableModalities,commons:commons.map(c=>({...c,administracao:administration(c.municipio)})),user:user.email});}
      if(route==='/api/events'&&req.method==='GET'){const agenda=await getAgenda();return json(res,200,{events:examEvents(agenda.events,url.searchParams.get('municipio')),source:agenda.source});}
      if(route==='/api/people'&&req.method==='GET'){const query=(url.searchParams.get('q')||'').trim().slice(0,120);if(query.length<2)return json(res,200,{people:[]});return json(res,200,{people:await store.people(url.searchParams.get('comum'),url.searchParams.get('tipo'),query)});}
      if(route==='/api/program-assessment'&&req.method==='GET'){
        const type=url.searchParams.get('tipo'),target=url.searchParams.get('modalidade');
        if(type!=='musico'||!['culto','oficializacao'].includes(target))return json(res,200,{assessment:null});
        const id=url.searchParams.get('pessoa_id');
        if(!/^[a-f0-9-]{36}$/i.test(id||''))return json(res,400,{error:'Selecione o candidato no cadastro.'});
        const [person]=await store.people(url.searchParams.get('comum'),type,'',id);
        if(!person)return json(res,404,{error:'Candidato não encontrado nesta comum.'});
        return json(res,200,{assessment:await consultation(store,person,type,target)});
      }
      if(route==='/api/student-activity'&&req.method==='GET'){
        const type=url.searchParams.get('tipo'),id=url.searchParams.get('pessoa_id');
        if(type!=='musico')return json(res,200,{activity:null});
        if(!/^[a-f0-9-]{36}$/i.test(id||''))return json(res,400,{error:'Selecione o candidato no cadastro.'});
        const [person]=await store.people(url.searchParams.get('comum'),type,'',id);
        if(!person)return json(res,404,{error:'Candidato não encontrado nesta comum.'});
        return json(res,200,{activity:await studentActivity(store,person,type)});
      }
      if(route==='/api/ministry'&&req.method==='GET')return json(res,200,{ministry:await store.ministry(url.searchParams.get('comum'),url.searchParams.get('municipio'))});
      if(route==='/api/letters'&&req.method==='GET'){const rows=await store.rows('cartas_emissoes',{owner_session:`eq.${user.id}`,deleted_at:'is.null',select:'id,nome,comum,tipo,modalidade,status,created_at,event_snapshot',order:'created_at.desc'});return json(res,200,{letters:rows});}
      const download=route.match(/^\/api\/letters\/([a-f0-9-]{36})\/pdf$/);
      if(download&&req.method==='GET'){const [record]=await store.rows('cartas_emissoes',{id:`eq.${download[1]}`,owner_session:`eq.${user.id}`,deleted_at:'is.null'});if(!record||record.status!=='ready')return json(res,404,{error:'PDF não disponível.'});return json(res,200,{url:`/api/letters/${record.id}/document`});}
      const documentRoute=route.match(/^\/api\/letters\/([a-f0-9-]{36})\/document$/);
      if(documentRoute&&req.method==='GET'){
        const [record]=await store.rows('cartas_emissoes',{id:`eq.${documentRoute[1]}`,owner_session:`eq.${user.id}`,deleted_at:'is.null'});
        if(!record||record.status!=='ready'||!record.pdf_path)return json(res,404,{error:'PDF não disponível.'});
        const pdf=await store.document(record.pdf_path),filename=letterFilename(record);
        res.writeHead(200,{'Content-Type':'application/pdf','Cache-Control':'private, no-store','Content-Disposition':`inline; filename="Carta_Exame.pdf"; filename*=UTF-8''${encodeURIComponent(filename).replace(/'/g,'%27')}`});return res.end(pdf);
      }
      if(route==='/api/letters'&&req.method==='POST'){
        const raw=await body(req),p=validate(raw);if(raw.consentimento!==true)throw Object.assign(Error('Confirme a autorização para uso dos dados na carta.'),{status:400});
        if(!availableModalities[p.tipo]?.includes(p.modalidade))throw Object.assign(Error('O modelo original desta modalidade ainda não foi disponibilizado.'),{status:422});
        const commons=await store.commons(),canonical=findCommonInAdministration(commons,p.comum,p.municipio);if(!canonical)throw Object.assign(Error('A comum selecionada não pertence à administração informada.'),{status:400});
        p.comum=canonical.comum;p.municipio=canonical.municipio;
        const [person]=await store.people(p.comum,p.tipo,'',String(raw.pessoa_id||''));
        if(!raw.pessoa_id||!person)throw Object.assign(Error('Selecione o músico ou organista no cadastro desta comum.'),{status:400});
        p.pessoa_id=person.id;p.nome=person.nome;p.instrumento=person.instrumento||p.instrumento;p.tonalidade=person.tonalidade||p.tonalidade;

        if(p.tipo==='organista'&&!commons.some(c=>commonMatches(c.comum,p.comum_instrutora)))throw Object.assign(Error('Selecione a comum da instrutora no cadastro.'),{status:400});
        const agenda=await getAgenda(),event=examEvents(agenda.events,p.municipio).find(e=>e.id===p.evento_id);
        if(!event||!eligibleEvent(event,p.tipo,p.modalidade))throw Object.assign(Error('O exame mudou ou não está mais disponível. Selecione novamente.'),{status:409});
        const ministry=await store.ministry(p.comum,p.municipio);
        const chosen={};for(const role of ['anciao','cooperador','encarregado','regional']){
          const match=ministry.find(m=>m.id===raw[role]);
          const roleText=norm(match?.ministerio);const valid={anciao:/ANCIAO/,cooperador:/COOPERADOR.*(OFICIO|OFICIAL)/,encarregado:/ENCARREGADO.*LOCAL/,regional:/ENCARREGADO.*REGIONAL/}[role];
          if(!raw[role])throw Object.assign(Error('O ministério responsável deve estar completo antes da emissão. Confira a relação de assinaturas.'),{status:400});
          if(!match||!valid.test(roleText))throw Object.assign(Error('Selecione os responsáveis conforme o cadastro ministerial.'),{status:400});chosen[role]=match;
        }
        chosen.secretario=ministry.find(m=>m.ministerio==='SECRETÁRIO DA MÚSICA')||null;
        const [program_assessment,student_activity]=await Promise.all([consultation(store,person,p.tipo,p.modalidade),studentActivity(store,person,p.tipo)]);
        const activity_review=activityReview(student_activity,p,event,chosen);
        const record=await store.reserve({duplicate_key:duplicateKey(p,event),nome:p.nome,comum:p.comum,municipio:p.municipio,tipo:p.tipo,modalidade:p.modalidade,event_id:event.id,event_snapshot:event,ministry_snapshot:chosen,payload:{...p,program_assessment,student_activity,activity_review,consentimento:true,n8n:legacyPayload(p,event,chosen)},created_by:user.guest?null:user.id,owner_session:user.id,status:'processing'});
        try{const pdf=await makePdf(record,user.email);const pdfPath=`${user.id}/${record.id}.pdf`;await store.upload(pdfPath,pdf);await store.update(record.id,{status:'ready',pdf_path:pdfPath,pdf_sha256:crypto.createHash('sha256').update(pdf).digest('hex')});return json(res,201,{id:record.id,status:'ready',activity_pending:student_activity?.pending===true});}
        catch(e){await store.update(record.id,{status:'failed'}).catch(()=>{});throw e;}
      }
      return json(res,404,{error:'Recurso não encontrado.'});
    }
    if(!['GET','HEAD'].includes(req.method))return json(res,405,{error:'Método não permitido.'});
    const file=path.join(root,'public',route==='/'?'index.html':(route==='/admin'||route==='/admin/')?'admin.html':route);
    if(!file.startsWith(path.join(root,'public')+path.sep))return json(res,404,{error:'Não encontrado.'});
    if(!fs.existsSync(file)||!fs.statSync(file).isFile())return json(res,404,{error:'Não encontrado.'});
    const mime={'.html':'text/html; charset=utf-8','.js':'application/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.png':'image/png','.svg':'image/svg+xml','.woff2':'font/woff2','.ttf':'font/ttf'};
    res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream','Cache-Control':'no-cache'});if(req.method==='HEAD')res.end();else fs.createReadStream(file).pipe(res);
  }catch(e){json(res,e.status||500,{error:e.status?e.message:'Não foi possível concluir. Tente novamente.',...(e.duplicate?{duplicate:e.duplicate}:{})});}
}
if(require.main===module)http.createServer(handler).listen(Number(process.env.PORT||3010),'127.0.0.1',()=>console.log('Cartas disponível na porta '+(process.env.PORT||3010)));
module.exports=handler;
