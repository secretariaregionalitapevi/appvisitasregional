const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'../../..');
test('edição preenche papeleta, usa PATCH e exclusão exige confirmação',async()=>{
 const dom=new JSDOM(fs.readFileSync(path.join(root,'ColorAdminApp/templates/partial/darpe-atendimentos.html'),'utf8'),{url:'http://project.test/',runScripts:'outside-only'}),w=dom.window,calls=[];
 const item={id:'123',data:'2026-01-01',hora_inicio:'09:00',hora_fim:'10:00',setor:2,local:'Unidade',whatsapp:'(11) 99999-1234',telefone:'(11) 4141-1234',municipio:'ITAPEVI',comum:'CENTRAL',equipe:[{cadastro_id:'p1',funcao:'atendente',nome:'Pessoa'}],hinos:[7,374],palavra:'Atos 3',participacao:'40',observacoes:'Observação',pedidos_oracao:{familias:'todas',viagens:2}};
 w.crypto.randomUUID=require('node:crypto').randomUUID;
 let confirmed=false;w.AppFeedback={show:()=>({close(){}}),confirm:async()=>confirmed};
 w.fetch=async(url,options={})=>{calls.push({url,options});return new Response(JSON.stringify(url.includes('contexto')?{setores:[{id:2,nome:'Setor 2'}],escopo:{level:'global'}}:options.method?{item}:{items:[item]}));};
 try{w.eval(fs.readFileSync(path.join(root,'static/js/darpe-atendimentos.js'),'utf8'));await new Promise(r=>setTimeout(r,30));const doc=w.document,host=doc.getElementById('darpe-attendance'),form=doc.getElementById('da-form');
 const open=mode=>host.dispatchEvent(new w.CustomEvent('darpe:open',{detail:{record:item,mode}}));open('edit');
 assert.equal(form.elements.local.value,'Unidade');assert.equal(form.elements.whatsapp.value,item.whatsapp);assert.equal(form.elements.telefone.value,item.telefone);assert.equal(form.elements.hinos.value,'7, 374');assert.equal(form.elements.pedido_viagens.value,'2');assert(doc.getElementById('da-all-families').checked);assert.match(doc.getElementById('da-save').textContent,/Salvar alterações/);
 form.elements.local.value='Unidade corrigida';await form.onsubmit({preventDefault(){}});const patch=calls.find(c=>c.options.method==='PATCH');assert(patch);assert.equal(JSON.parse(patch.options.body).local,'Unidade corrigida');assert.equal(JSON.parse(patch.options.body).whatsapp,item.whatsapp);assert.equal(JSON.parse(patch.options.body).telefone,item.telefone);assert.equal(JSON.parse(patch.options.body).id,item.id);
 open('delete');await new Promise(r=>setTimeout(r,10));assert(!calls.some(c=>c.options.method==='DELETE'));
 confirmed=true;open('delete');await new Promise(r=>setTimeout(r,20));assert.equal(JSON.parse(calls.find(c=>c.options.method==='DELETE').options.body).id,item.id);
 }finally{w.close();}
});
