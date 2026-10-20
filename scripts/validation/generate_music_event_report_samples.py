"""Gera amostras locais para validar visualmente os dois relatórios operacionais."""
from datetime import datetime
from pathlib import Path

from ColorAdminApp.modules.music_events_conductors import summarize
from ColorAdminApp.modules.music_events_dashboard import aggregate
from ColorAdminApp.modules.music_events_leaders import attach_leaders
from ColorAdminApp.modules.music_events_registry import attach_registry
from ColorAdminApp.modules.music_events_reports import build_pdf


def main(reports=('comuns', 'encarregados')):
    events=[{'id':'e','titulo':'Ensaio Regional - 20/09/2026','data_evento':'2026-09-20',
             'tipo':'ENSAIO_REGIONAL','familia':'GERAL','status':'ABERTO','base_id':None}]
    sites=[{'id':'it','evento_id':'e','nome':'ITAPEVI'},{'id':'pi','evento_id':'e','nome':'PIRAPORA'}]
    catalog=[{'comum':'BR-22-0673 - VILA DOUTOR CARDOSO','cidade':'ITAPEVI'},
             {'comum':'BR-22-0002 - COMUM DE EXEMPLO','cidade':'ITAPEVI'}]
    records=[
        {'evento_id':'e','local_id':'it','nome':'Músico A','comum_informada':catalog[0]['comum'],'municipio_informado':'ITAPEVI','categoria':'MUSICO','situacao':'PRESENTE','familia':'CORDAS','instrumento':'VIOLINO'},
        {'evento_id':'e','local_id':'pi','nome':'Organista A','comum_informada':catalog[0]['comum'],'municipio_informado':'ITAPEVI','categoria':'ORGANISTA','situacao':'PRESENTE','familia':'TECLADO','instrumento':'ÓRGÃO'},
        {'evento_id':'e','local_id':'pi','nome':'Encarregado A','comum_informada':catalog[0]['comum'],'municipio_informado':'ITAPEVI','categoria':'MUSICO','cargo':'MÚSICO','situacao':'PRESENTE','familia':'METAIS','instrumento':'TROMPETE'},
    ]
    frequency=[{'evento_id':'e','comum_codigo':'BR-22-0673','comum':catalog[0]['comum'],'municipio':'ITAPEVI','local_referencia_id':'it','base_validada':False,'musicos_base':0,'organistas_base':0},
               {'evento_id':'e','comum_codigo':'BR-22-0002','comum':catalog[1]['comum'],'municipio':'ITAPEVI','local_referencia_id':'it','base_validada':False,'musicos_base':0,'organistas_base':0}]
    data=aggregate(events,records,sites,frequency,{'evento':'e'},catalog)
    registry=[{'id':str(i),'nome_aluno':'Encarregado A' if i==1 else f'Pessoa {i}','status':'Ativo','nivel':'RJM','instrumento':'ÓRGÃO' if i>8 else 'VIOLINO','comum_congregacao':catalog[0]['comum'],'municipio':'ITAPEVI','cargo_ministerio':'ENCARREGADO LOCAL' if i==1 else 'MÚSICO'} for i in range(1,11)]
    attach_registry(data,registry,catalog);data['conductors']=summarize(events,records,sites,[{'evento_id':'e','comum_chave':'BR-22-0002','comum_nome':catalog[1]['comum'],'municipio':'ITAPEVI','situacao':'JUSTIFICOU','local_id':None,'observacoes':'Motivo informado'}],{'evento':'e'},catalog,frequency,registry)
    attach_leaders(data,registry,catalog)
    data['registry']={'available':True};data['report_identity']={'scope':'Global · Itapevi','common':''}
    out=Path('output/pdf');out.mkdir(parents=True,exist_ok=True);now=datetime(2026,10,19,20,30)
    arquivos = {
        'comuns': 'Validacao_Frequencia_por_Comum.pdf',
        'encarregados': 'Validacao_Encarregados_por_Municipio.pdf',
    }
    for report in reports:
        name = arquivos[report]
        data['report']=report;(out/name).write_bytes(build_pdf(data,'Validação interna',now))


if __name__=='__main__':main()
