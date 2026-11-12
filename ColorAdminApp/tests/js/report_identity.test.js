const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.resolve(__dirname,'../../..');
const context={document:{currentScript:{dataset:{user:'Operador Teste'}}}};
context.window=context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(root,'static/js/app-report-identity.js'),'utf8'),context);
const original={pageSize:'A4',pageOrientation:'landscape',pageMargins:[28,100,28,34],
 header:page=>({margin:[28,16,28,0],columns:[{width:190,text:''},
  {width:'*',stack:[{text:'CONGREGAÇÃO CRISTÃ NO BRASIL',bold:true,fontSize:15,alignment:'center'},
   {text:'Regional Itapevi - São Paulo',alignment:'center',fontSize:9},
   {text:'Relatório de validação',alignment:'center',fontSize:11}]},
  {width:190,alignment:'right',fontSize:7,stack:[{text:'Emissão: 12/11/2026 14:30'},
   {text:[{text:'Impresso por: ',bold:true},{text:'Nome antigo'}]}]}]}),
 footer:page=>({margin:[28,5,28,0],columns:[{text:'Regional Itapevi',fontSize:7},{text:`Página ${page}`,fontSize:7}]}),
 content:[{text:'Dados de exemplo preservados.'}]};
const formatted=context.AppReportIdentity.prepare(original);
const header=formatted.header(1,2,{}),footer=formatted.footer(1,2,{});
const metadata=header.columns[2].stack.at(-1);
assert.equal(metadata.text[0].text,'Responsável: ');
assert.equal(metadata.text[0].bold,true);
assert.equal(metadata.text[1].text,'Secretaria Regional da Música');
assert.equal(metadata.text[1].bold,false);
assert.equal(footer.columns[1].text[0].text,'Impresso por: ');
assert.equal(footer.columns[1].text[0].bold,true);
assert.equal(footer.columns[1].text[1].text,'Operador Teste');
assert.equal(footer.columns[1].text[2].text,' - Página 1 de 2');
assert.ok(!JSON.stringify(header).includes('Nome antigo'));
assert.ok(!JSON.stringify(header).includes('Operador Teste'));
const constant=context.AppReportIdentity.prepare({header:{columns:[{text:'Relatório'},{stack:[]}]},footer:{text:'Legenda'},content:[]});
assert.ok(JSON.stringify(constant.header(1,1,{})).includes('Secretaria Regional da Música'));
assert.ok(JSON.stringify(constant.footer(1,1,{})).includes('Operador Teste'));
console.log('Report metadata: header, authenticated printer, bold labels and existing content verified');
if(process.argv.includes('--render')){
 const pdfmake=require(path.join(root,'static/plugins/pdfmake/build/pdfmake.min.js'));
 const fonts=require(path.join(root,'static/plugins/pdfmake/build/vfs_fonts.js'));
 if(pdfmake.addVirtualFileSystem)pdfmake.addVirtualFileSystem(fonts.pdfMake?.vfs||fonts);
 else pdfmake.vfs=fonts.pdfMake?.vfs||fonts;
 fs.mkdirSync(path.join(root,'tmp/report-identity'),{recursive:true});
 pdfmake.createPdf(formatted).getBuffer(buffer=>fs.writeFileSync(path.join(root,'tmp/report-identity/browser.pdf'),buffer));
}
