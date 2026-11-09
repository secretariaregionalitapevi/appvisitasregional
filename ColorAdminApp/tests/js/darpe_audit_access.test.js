const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'../../..');
test('auditoria mantém DARPE e permite selecionar seus três níveis sem autorizar outras pastas',async()=>{
 const dom=new JSDOM(fs.readFileSync(path.join(root,'ColorAdminApp/templates/pages/auditoria.html'),'utf8'),{url:'http://project.test/administracao/',runScripts:'outside-only'}),w=dom.window;
 w.eval(fs.readFileSync(path.join(root,'static/plugins/jquery/dist/jquery.min.js'),'utf8'));
 w.bootstrap={Modal:{getOrCreateInstance:()=>({show(){}})},Tab:{getOrCreateInstance:()=>({show(){}})}};
 w.fetch=async url=>({ok:true,headers:{get:()=> 'application/json'},json:async()=>String(url).includes('metadados')?{}:{profiles:[{user_id:'darpe-user',full_name:'Pessoa DARPE',sector:'D.A.R.P.E',role_id:3,status:'pending'}],logs:[],sessions:[],module_access:[],access_levels:[]}});
 try{w.eval(fs.readFileSync(path.join(root,'static/js/admin/auditoria.js'),'utf8'));await new Promise(r=>setTimeout(r,100));
 const $=w.$,button=$('<button class="edit-user" data-id="darpe-user" data-approve="true"></button>').appendTo(w.document.body);button.trigger('click');
 assert.equal($('#edit-sector').val(),'D.A.R.P.E');assert($('#module-darpe').prop('checked'));assert(!$('#module-visitas').prop('checked'));assert(!$('#module-musicalizacao').prop('checked'));
 for(const role of ['4','3','2']){$('#edit-role').val(role).trigger('change');assert.equal($('#edit-sector').val(),'D.A.R.P.E');assert($('#module-darpe').prop('checked'));}
 $('#module-musica').prop('checked',true).trigger('change');assert.equal($('#edit-sector').val(),'D.A.R.P.E');
 }finally{w.close();}
});

test('auditoria mantém G.E.M como pasta principal independente',async()=>{
 const dom=new JSDOM(fs.readFileSync(path.join(root,'ColorAdminApp/templates/pages/auditoria.html'),'utf8'),{url:'http://project.test/administracao/',runScripts:'outside-only'}),w=dom.window;
 w.eval(fs.readFileSync(path.join(root,'static/plugins/jquery/dist/jquery.min.js'),'utf8'));
 w.bootstrap={Modal:{getOrCreateInstance:()=>({show(){}})},Tab:{getOrCreateInstance:()=>({show(){}})}};
 w.fetch=async url=>({ok:true,headers:{get:()=> 'application/json'},json:async()=>String(url).includes('metadados')?{}:{profiles:[{user_id:'gem-user',full_name:'Pessoa GEM',sector:'G.E.M',role_id:4,status:'pending'}],logs:[],sessions:[],module_access:[],access_levels:[]}});
 try{w.eval(fs.readFileSync(path.join(root,'static/js/admin/auditoria.js'),'utf8'));await new Promise(r=>setTimeout(r,100));
 const $=w.$,button=$('<button class="edit-user" data-id="gem-user" data-approve="true"></button>').appendTo(w.document.body);button.trigger('click');
 assert.equal($('#edit-sector').val(),'G.E.M');assert($('#module-gem').prop('checked'));assert(!$('#module-visitas').prop('checked'));assert(!$('#module-musicalizacao').prop('checked'));
 }finally{w.close();}
});
