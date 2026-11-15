const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

async function main() {
  const notices = [];
  const context = {window:{AppFeedback:{show:options=>notices.push(options)}},document:{addEventListener() {}}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('static/js/app-export.js','utf8'), context);
  const attrs = new Map([['tabindex','0']]);
  const button = {tagName:'A',innerHTML:'PDF',disabled:false,
    getAttribute:key=>attrs.get(key)??null,setAttribute:(key,value)=>attrs.set(key,value),removeAttribute:key=>attrs.delete(key)};
  let finish;
  const pending = context.window.AppExport.run(button,()=>new Promise(resolve=>{finish=resolve;}));
  assert.match(button.innerHTML,/fa-spinner/);
  assert.equal(button.disabled,true);
  assert.equal(attrs.get('aria-busy'),'true');
  assert.equal(notices.length,0, 'Generating must not open feedback');
  assert.equal(await context.window.AppExport.run(button,()=>{throw Error('Duplicate click');}),false);
  finish();
  assert.equal(await pending,true);
  assert.deepEqual(notices.map(n=>n.type),['success']);
  assert.equal(button.innerHTML,'PDF');
  assert.equal(button.disabled,false);
  assert.equal(attrs.has('aria-busy'),false);
  assert.equal(attrs.has('aria-disabled'),false);
  assert.equal(attrs.get('tabindex'),'0');
  assert.equal(await context.window.AppExport.run(button,()=>{throw Error('Network failed');}),false);
  assert.equal(notices.at(-1).type,'error');
  assert.equal(button.disabled,false);
  assert.equal(button.innerHTML,'PDF');

  let queries = 0;
  const layers = [];
  const feedbackContext = {window:{setTimeout(){}},document:{querySelector(){queries++;return null;},
    createElement:()=>({setAttribute(){},querySelector:()=>null,remove(){}}),body:{appendChild:layer=>layers.push(layer)}}};
  vm.createContext(feedbackContext);
  vm.runInContext(fs.readFileSync('static/js/app-feedback.js','utf8'),feedbackContext);
  const feedback = feedbackContext.window.AppFeedback;
  for (const options of [{type:'loading',flow:'export'}, {type:'loading',flow:'save',title:'Gerando relatório'},
    {type:'loading',title:'Preparando PDF...'}]) {
    const notice = feedback.show(options);
    notice.close();
    assert.equal(notice.element,null);
  }
  assert.equal(queries,0, 'Export loading must not touch the overlay or an existing modal');
  feedback.show({type:'loading',flow:'save',title:'Salvando cadastro'});
  feedback.show({type:'success',flow:'export',title:'Arquivo pronto'});
  feedback.show({type:'error',flow:'export',title:'Falha na exportação'});
  assert.equal(layers.length,3, 'Save progress and export success/error must remain visible');
  console.log('Export feedback: button-only loading, duplicate protection, restoration, success/error and legacy callers passed.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
