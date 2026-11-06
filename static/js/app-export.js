(() => {
'use strict';
const busy = new WeakSet();
function toast(type,title,message,detail){return window.AppFeedback?.show({type,title,message,detail,flow:'export',toast:true});}
function filename(response,fallback){
 const header=response.headers.get('Content-Disposition')||'';
 let name=header.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
 if(name){try{name=decodeURIComponent(name);}catch{name='';}}
 name=name||header.match(/filename="([^"]+)"/i)?.[1]||header.match(/filename=([^;]+)/i)?.[1]||fallback;
 return String(name).replace(/[\\/<>:"|?*\x00-\x1f]/g,'_').trim()||fallback;
}
async function run(button,produce,options={}){
 if(button&&(busy.has(button)||button.disabled||button.getAttribute('aria-disabled')==='true'))return false;
 const original=button?{html:button.innerHTML,disabled:button.disabled,busy:button.getAttribute('aria-busy'),aria:button.getAttribute('aria-disabled'),tab:button.getAttribute('tabindex')}:null;
 if(button){busy.add(button);button.disabled=true;button.setAttribute('aria-busy','true');button.setAttribute('aria-disabled','true');if(button.tagName==='A')button.setAttribute('tabindex','-1');button.innerHTML='<i class="fa fa-spinner fa-spin me-1" aria-hidden="true"></i>Gerando...';}
 toast('loading',options.title||'Gerando arquivo',options.message||'Preparando o arquivo com o recorte selecionado.');
 try{
  await produce();
  toast('success','Arquivo pronto',options.success||'Arquivo gerado. O download foi iniciado.','Confira os downloads do navegador.');
  return true;
 }catch(error){
  toast('error','Não foi possível gerar o arquivo',error.message||'Tente novamente.','Confira sua sessão e tente novamente.');
  return false;
 }finally{
  if(button){button.innerHTML=original.html;button.disabled=original.disabled;for(const [attr,value]of [['aria-busy',original.busy],['aria-disabled',original.aria],['tabindex',original.tab]]){if(value===null)button.removeAttribute(attr);else button.setAttribute(attr,value);}busy.delete(button);}
 }
}
async function download(button,url,options={}){
 return run(button,async()=>{
  const response=await fetch(url,{credentials:'same-origin',cache:'no-store',headers:{'X-Requested-With':'XMLHttpRequest'}});
  if(response.redirected)throw Error('Sua sessão pode ter expirado. Entre novamente e tente exportar.');
  const type=(response.headers.get('Content-Type')||'').toLowerCase();
  if(!response.ok||type.includes('application/json')||type.includes('text/html')){
   let message=response.ok?'O servidor não retornou um arquivo válido.':'Não foi possível gerar o arquivo. Tente novamente.';
   if(type.includes('application/json')){try{const payload=await response.json();message=payload.error||payload.message||message;}catch{}}
   throw Error(message);
  }
  const blob=await response.blob();if(!blob.size)throw Error('O arquivo retornado está vazio. Tente novamente.');
  const objectURL=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=objectURL;link.download=filename(response,options.filename||(/pdf/i.test(type)?'Relatorio.pdf':/csv/i.test(type)?'Relatorio.csv':'Relatorio.xlsx'));
  document.body.appendChild(link);
  try{link.click();}finally{link.remove();window.setTimeout(()=>URL.revokeObjectURL(objectURL),30000);}
 },options);
}
window.AppExport={download,run};
// Shared server-generated exports, including links inside Bootstrap/native modals.
document.addEventListener('click',event=>{
 if(event.defaultPrevented||event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
 const link=event.target.closest('a[href]');if(!link||link.hasAttribute('data-export-custom'))return;
 const href=link.getAttribute('href');if(!href||href.startsWith('#'))return;
 let url;try{url=new URL(href,location.href);}catch{return;}
 if(url.origin!==location.origin||!/^https?:$/.test(url.protocol))return;
 const identified=link.hasAttribute('data-app-export')||/\/(?:exportar[^/]*|export[^/]*|relacao\/(?:pdf|excel)|programa-minimo\/(?:pdf|excel))(?:\/|$)/i.test(url.pathname)||(/gerar|exportar|baixar modelo/i.test(link.textContent)&&!link.querySelector('[data-bs-toggle]'));
 if(!identified)return;
 event.preventDefault();void download(link,url.href);
});
})();
