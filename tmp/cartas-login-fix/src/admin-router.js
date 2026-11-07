'use strict';
const {AdminAuth,sameOrigin,assertCSRF}=require('./admin-auth');
const {AdminManagement}=require('./admin-management');
const {letterFilename}=require('./pdf');
function createAdminHandler(store,env=process.env,{auth=new AdminAuth(store,env),management=new AdminManagement(store,env)}={}){
 const json=(res,status,data)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(data));};
 async function body(req){let text='';for await(const chunk of req){text+=chunk;if(Buffer.byteLength(text)>12000)throw Object.assign(Error('Dados excedem o tamanho permitido.'),{status:413});}try{return JSON.parse(text||'{}');}catch{throw Object.assign(Error('Dados inválidos.'),{status:400});}}
 return async(req,res,url)=>{
  res.setHeader('Cache-Control','no-store');
  try{
   const route=url.pathname.replace(/\/+$/,'');
   if(route==='/api/admin/config'&&req.method==='GET'){
    const portal=env.REGIONAL_PORTAL_URL||(env.NODE_ENV==='production'||env.VERCEL_ENV?'https://appvisitasregional.vercel.app':'http://127.0.0.1:8000');
    let registrationUrl=null;try{const target=new URL('/user/cadastro',portal);if(['http:','https:'].includes(target.protocol)){target.searchParams.set('origem','cartas');registrationUrl=target.href;}}catch{}
    return json(res,200,{registration_url:registrationUrl,export_formats:['pdf','excel'],api_version:'cartas-admin-exports-v2'});
   }
   if(route==='/api/admin/login'&&req.method==='POST'){const {identity,session}=await auth.login(req,res,await body(req));return json(res,200,{user:identity,csrf:session.csrf});}
   if(route==='/api/admin/logout'&&req.method==='POST'){await auth.logout(req,res);return json(res,200,{ok:true});}
   const {identity,session}=await auth.require(req,res);
   if(req.method!=='GET'){sameOrigin(req);assertCSRF(req,session);}
   if(route==='/api/admin/session'&&req.method==='GET')return json(res,200,{user:identity,csrf:session.csrf});
   if(route==='/api/admin/events'&&req.method==='GET'){const state=await management.state(identity);return json(res,200,{events:state.events,agenda_unavailable:state.agenda_unavailable});}
   if(route==='/api/admin/letters'&&req.method==='GET')return json(res,200,await management.list(identity,url.searchParams));
   if(route==='/api/admin/export'&&req.method==='GET'){
    const format=url.searchParams.get('formato');if(!['pdf','excel'].includes(format))return json(res,400,{error:'Escolha PDF ou Excel.'});
    const report=await management.list(identity,url.searchParams,true),exports=require('./admin-exports');
    const buffer=format==='pdf'?await exports.makePdf(report,identity):exports.makeExcel(report,identity),extension=format==='pdf'?'pdf':'xlsx';
    const filename='Relacao_Candidatos_'+identity.municipio.replace(/[^a-z0-9]+/ig,'_')+'_'+report.event.data.split('-').reverse().join('_')+'.'+extension;
    res.writeHead(200,{'Content-Type':format==='pdf'?'application/pdf':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','Content-Disposition':`attachment; filename="${filename}"`,'Cache-Control':'private, no-store'});return res.end(buffer);
   }
   if(route==='/api/admin/receipt'&&req.method==='POST')return json(res,200,await management.receipt(identity,await body(req)));
   const document=route.match(/^\/api\/admin\/letters\/([a-f0-9-]{36})\/document$/i);
   if(document&&req.method==='GET'){const {row,pdf}=await management.document(identity,document[1]);res.writeHead(200,{'Content-Type':'application/pdf','Cache-Control':'private, no-store','Content-Disposition':`inline; filename="Carta_Exame.pdf"; filename*=UTF-8''${encodeURIComponent(letterFilename(row)).replace(/'/g,'%27')}`});return res.end(pdf);}
   return json(res,404,{error:'Recurso administrativo não encontrado.'});
  }catch(e){return json(res,e.status||500,{error:e.status?e.message:'Não foi possível concluir. Tente novamente.'});}
 };
}
module.exports={createAdminHandler};
