(() => {
  'use strict';
  const script=document.currentScript;
  const loggedUser=script?.dataset.user||'';
  const responsible='Secretaria Regional da Música';
  const plain=node=>node==null?'':typeof node==='string'||typeof node==='number'?String(node):Array.isArray(node)?node.map(plain).join(''):plain(node.text);
  function prepare(definition){
    const originalHeader=definition.header,originalFooter=definition.footer;
    let inferredUser='';
    function headerNode(node){
      if(!node||typeof node!=='object')return node;
      if(Array.isArray(node))return node.map(headerNode);
      const value=plain(node.text),match=value.match(/(?:impresso por|respons[aá]vel)\s*:\s*(.*)/i);
      if(match){
        inferredUser=inferredUser||match[1].trim();
        const prefix=value.slice(0,match.index);
        return {...node,bold:false,text:[...(prefix?[{text:prefix,bold:false}]:[]),{text:'Responsável: ',bold:true},{text:responsible,bold:false}]};
      }
      const result={...node};
      for(const key of ['columns','stack','text'])if(result[key]&&typeof result[key]==='object')result[key]=headerNode(result[key]);
      return result;
    }
    definition.header=(page,pages,pageSize)=>{
      let node=headerNode(typeof originalHeader==='function'?originalHeader(page,pages,pageSize):originalHeader);
      if(!JSON.stringify(node).includes(responsible)){
        const line={text:[{text:'Responsável: ',bold:true},{text:responsible}],fontSize:7,alignment:'right'};
        if(node?.columns?.length){const last=node.columns.at(-1);if(last.stack)last.stack.push(line);else node.columns[node.columns.length-1]={stack:[last,line],width:last.width};}
        else node={margin:[28,16,28,0],stack:[node||'',line]};
      }
      return node;
    };
    // Discover legacy metadata before pdfmake requests the first footer.
    if(originalHeader)definition.header(1,1,{width:842,height:595});
    definition.footer=(page,pages,pageSize)=>{
      const actor=(loggedUser&&loggedUser!=='Usuário'?loggedUser:inferredUser||loggedUser)||'Usuário';
      const old=typeof originalFooter==='function'?originalFooter(page,pages,pageSize):originalFooter;
      const result=old&&typeof old==='object'&&!Array.isArray(old)?{...old}:{margin:[28,5,28,0],columns:[old||'']};
      const right={text:[{text:'Impresso por: ',bold:true},{text:actor,bold:false},{text:` - Página ${page} de ${pages}`,bold:false}],alignment:'right',fontSize:7,width:'auto',noWrap:true,color:'#6b7280'};
      if(result.columns){result.columns=[...result.columns];if(result.columns.length>1)result.columns[result.columns.length-1]=right;else result.columns.push(right);}
      else return {margin:[28,5,28,0],columns:[result,right]};
      return result;
    };
    return definition;
  }
  function jsPdfHeader(doc,x,y){
    const label='Responsável: ',value=responsible;
    doc.setFont('helvetica','bold');const labelWidth=doc.getTextWidth(label);
    doc.setFont('helvetica','normal');const valueWidth=doc.getTextWidth(value),start=x-labelWidth-valueWidth;
    doc.setFont('helvetica','bold');doc.text(label,start,y);
    doc.setFont('helvetica','normal');doc.text(value,start+labelWidth,y);
  }
  function jsPdfFooter(doc,user){
    const pages=doc.getNumberOfPages();
    for(let page=1;page<=pages;page++){
      doc.setPage(page);const w=doc.internal.pageSize.getWidth(),h=doc.internal.pageSize.getHeight();
      doc.setFillColor(255,255,255);doc.rect(w/2,h-15,w/2-10,13,'F');
      doc.setTextColor(82,99,113);doc.setFontSize(7);
      const label='Impresso por: ',tail=`${loggedUser||user||'Usuário'} - Página ${page} de ${pages}`;
      doc.setFont('helvetica','bold');const labelWidth=doc.getTextWidth(label);
      doc.setFont('helvetica','normal');const tailWidth=doc.getTextWidth(tail),x=w-14-labelWidth-tailWidth;
      doc.setFont('helvetica','bold');doc.text(label,x,h-8);
      doc.setFont('helvetica','normal');doc.text(tail,x+labelWidth,h-8);
    }
  }
  window.AppReportIdentity={prepare,jsPdfHeader,jsPdfFooter};
})();
