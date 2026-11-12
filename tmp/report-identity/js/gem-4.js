
['gem-excel','gem-pdf'].forEach(id=>{
  const button=document.getElementById(id);
  if(!button)return;
  const handler=button.onclick;
  if(!handler)return;
  button.onclick=async event=>{
    window.gemExportHadError=false;
    const notice=AppFeedback.show({type:'loading',flow:'export',title:'Gerando relatório',message:'Aguarde enquanto o arquivo é preparado.'});
    try{
      await handler.call(button,event);
      if(!window.gemExportHadError)AppFeedback.show({type:'success',title:'Relatório gerado',message:'O download do arquivo foi iniciado.'});
    }catch(error){
      window.gemExportHadError=true;
      AppFeedback.show({type:'error',title:'Falha na exportação',message:error.message});
    }finally{
      notice.close();
    }
  };
});
