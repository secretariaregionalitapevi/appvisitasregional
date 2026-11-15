"""Reproduz a presença nominal usando a aba Dados do arquivo fornecido."""
from collections import Counter
from datetime import datetime
from pathlib import Path

import pymupdf
from openpyxl import load_workbook

from ColorAdminApp.modules.music_events_conductors import summarize, attach_common_attendance
from ColorAdminApp.modules.music_events_dashboard import aggregate, code
from ColorAdminApp.modules.music_events_import import parse_workbook
from ColorAdminApp.modules.music_events_reports import build_pdf, build_excel


def main():
    path=Path.home()/'OneDrive/REGIONAL ITAPEVI/DB_CONTAGEM/DB_EnR_15.11.2026.xlsx'
    source=parse_workbook(path.read_bytes())
    records=[dict(row,evento_id='validation',local_id=row['local'],situacao='PRESENTE') for row in source['records']]
    catalog=[dict(comum=common,cidade=city) for common,city in
             sorted({(r['comum_informada'],r['municipio_informado']) for r in records if r['comum_informada'].startswith('BR-')})]
    sites=[dict(id=local,nome=local,evento_id='validation') for local in source['locations']]
    events=[dict(id='validation',titulo='Ensaio Regional · 15/11/2026',data_evento='2026-11-15',
                 tipo='ENSAIO_REGIONAL',familia='GERAL',status='ABERTO',base_id=None)]
    data=aggregate(events,records,sites,[],{},catalog)
    data['conductors']=summarize(events,records,sites,[],{},catalog)
    attach_common_attendance(data)
    expected={entry['comum_chave'] for entry in data['conductors']['rows'] if entry['consta_lista']}
    by_common={code(row['comum']):row for row in data['rows']}
    for key in expected:
        assert by_common[key]['encarregado_situacao']=='PRESENTE', key
    amarildo=next(row for row in data['conductors']['rows'] if row['comum_chave']=='BR-22-0423'
                  and row['encarregado_nome'].startswith('AMARILDO'))
    assert amarildo['registro']=='PRESENTE'
    assert by_common['BR-22-0423']['encarregado_situacao']=='PRESENTE'
    assert not any(not row['encarregado_nome'] and row['fonte']=='Não conferido'
                   and row['comum_chave'] in expected for row in data['conductors']['rows'])
    data['report']='comuns'
    out=Path('tmp/conductor-source-audit');out.mkdir(parents=True,exist_ok=True)
    now=datetime(2026,11,15,16,0)
    pdf=out/'presenca_nominal_validacao.pdf'
    pdf.write_bytes(build_pdf(data,'Validação nominal',now))
    xlsx=out/'presenca_nominal_validacao.xlsx'
    xlsx.write_bytes(build_excel(data,'Validação nominal',now))
    book=load_workbook(xlsx,rich_text=True)
    sheet=book.active
    for row in sheet.iter_rows(min_row=10,values_only=True):
        if row[1] in {by_common[key]['comum'] for key in expected}:
            assert row[2]=='PRESENTE', row[:3]
    assert 'Secretaria Regional da Música' in str(sheet['A5'].value)
    with pymupdf.open(pdf) as document:
        central_page=None
        from ColorAdminApp.modules.music_events_annual_reports import model_widths, common_name
        name_counts=Counter(common_name(row['comum']).upper() for row in data['rows'])
        present_cells=0
        red_nj=0
        bands=set()
        vgp_rendered=False
        for page in document:
            vgp_on_page=False
            assert 'NÃO INFORMADO' not in page.get_text()
            red_nj+=sum(span['text'].strip()=='NJ' and span['color']==0xE00000
                        for block in page.get_text('dict')['blocks'] if 'lines' in block
                        for line in block['lines'] for span in line['spans'])
            legend=[page.search_for(label) for label in ['J - JUSTIFICOU','NJ - NÃO JUSTIFICOU','SE - SEM ENCARREGADO','EF - ENFERMO']]
            if all(legend):
                assert max(items[0].y0 for items in legend)-min(items[0].y0 for items in legend)<1
            for drawing in page.get_drawings():
                fill=drawing.get('fill')
                if fill:
                    for name,hexvalue in [('CAUCAIA DO ALTO','FFE699'),('COTIA','BDD7EE'),('VARGEM GRANDE PAULISTA','D9E6AE')]:
                        rgb=tuple(int(hexvalue[i:i+2],16)/255 for i in (0,2,4))
                        if all(abs(a-b)<.001 for a,b in zip(fill,rgb)):
                            bands.add(name)
                            if name=='VARGEM GRANDE PAULISTA':
                                vgp_on_page=True
            words=page.get_text('words')
            # Inspect the actual conductor cell, not the word PRESENTES in the heading.
            bounds=model_widths();left=28+bounds[0];right=left+bounds[1]
            heads=page.search_for('ENCARREGADO LOCAL')
            legends=page.search_for('LEGENDA')
            if heads and legends:
                top=heads[0].y1;bottom=legends[0].y0
                present_cells+=sum(word[4]=='PRESENTE' and right<=word[0]<right+bounds[2]
                                   and top<word[1]<bottom for word in words)
            rows=[r for r in data['rows'] if code(r['comum']) in expected]
            for row in rows:
                name=common_name(row['comum']).upper()
                if name_counts[name]!=1:
                    continue
                for match in page.search_for(name):
                    if match.x0 < left-2 or match.x1 > right+2:
                        continue
                    full_name=page.get_textbox(pymupdf.Rect(left,match.y0-3,right,match.y1+3))
                    if ' '.join(full_name.split())!=' '.join(name.split()):
                        continue
                    cell=page.get_textbox(pymupdf.Rect(right,match.y0-3,right+bounds[2],match.y1+3))
                    assert 'PRESENTE' in cell, (name,cell)
            if page.search_for('CENTRAL - CAUCAIA DO ALTO'):
                central_page=page.number+1
                page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).save(out/'central_caucaia.png')
            if not vgp_rendered and vgp_on_page and page.search_for('LEGENDA'):
                page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).save(out/'vgp.png')
                vgp_rendered=True
        assert central_page is not None
        assert present_cells==len(expected),(present_cells,len(expected))
        assert red_nj>0
        assert bands=={'CAUCAIA DO ALTO','COTIA','VARGEM GRANDE PAULISTA'}
        print('NJ em vermelho; municípios somente na coluna lateral colorida; legenda em uma linha.')
        print(f'PDF: {len(document)} páginas; Central de Caucaia conferida na página {central_page}.')
    print('Fonte nominal:',source['count'],'registros. Encarregados presentes:',data['conductors']['totals'].get('PRESENTE',0))
    print('Comuns com presença nominal confirmada:',len(expected),'; todas conferidas como PRESENTE no painel, PDF e Excel.')
    print('Amarildo:',amarildo['encarregado_nome'],amarildo['registro'])


if __name__=='__main__':
    main()
