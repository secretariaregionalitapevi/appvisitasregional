"""Matriz de orientação: preserva a composição original a pedido do usuário."""
import io
from pathlib import Path
from html import escape
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from .darpe_library import instruments


def make_pdf():
    output = io.BytesIO()
    regular, bold = 'Helvetica', 'Helvetica-Bold'
    fonts = Path('C:/Windows/Fonts')
    if (fonts / 'calibri.ttf').exists():
        for name, filename in [('DarpeCalibri', 'calibri.ttf'), ('DarpeCalibriBold', 'calibrib.ttf')]:
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, str(fonts / filename)))
        regular, bold = 'DarpeCalibri', 'DarpeCalibriBold'
    c = canvas.Canvas(output, pagesize=(841.92, 595.32))
    c.setTitle('DARPE - Instrumentos permitidos - quatro setores')
    c.setAuthor('D.A.R.P.E. - Regional Itapevi')
    left, right, top = 35, 807, 569
    edges = [left]
    for width in [16, 110, 130, 82, 70, 148, 216]:
        edges.append(edges[-1] + width)

    def box(x, y, width, height, fill='white'):
        c.setFillColor(colors.toColor(fill));c.setStrokeColor(colors.black);c.setLineWidth(.45)
        c.rect(x,y,width,height,stroke=1,fill=1)

    def text(value,x,y,width,height,size=8,strong=False,color='black',align=0):
        p=Paragraph(escape(value).replace('\n','<br/>'),ParagraphStyle('cell',fontName=bold if strong else regular,fontSize=size,leading=size*1.12,textColor=colors.toColor(color),alignment=align))
        _,h=p.wrap(width-4,height);p.drawOn(c,x+2,y+(height-h)/2)

    box(left,top-42,right-left,42)
    text('DARPE - DEPARTAMENTO DE ASSISTÊNCIA RELIGIOSA PARA EVANGELIZAÇÃO',left,top-21,right-left,21,size=13,strong=True,align=1)
    text('tabela de orientação geral quanto ao uso de instrumentos musicais permitidos',left,top-42,right-left,21,size=12,align=1)
    y=top-42;header_height=54
    box(left,y-header_height,126,header_height)
    text('INSTRUMENTOS\nCONFORME MOO',left,y-header_height,126,header_height,strong=True,align=1)
    descriptions=['Sistemas de Ressocialização e Socioeducativos','Clínicas de Dependentes e Albergues','Forças de Segurança','Hospitais, Instituições para Idosos e Setor Educacional']
    for number in range(4):
        x=edges[number+2];width=edges[number+3]-x
        box(x,y-13,width,13,'#202b34');text(f'SETOR {number+1}',x,y-13,width,13,strong=True,color='white',align=1)
        box(x,y-header_height,width,header_height-13);text(descriptions[number],x,y-header_height,width,header_height-13,align=1)
    box(edges[6],y-header_height,216,header_height)
    text('MOTIVO NÃO SER PERMITIDO',edges[6],y-header_height,216,header_height,strong=True,align=1)
    y-=header_height;rows=instruments();height=12
    groups=[(1,3,'CORDAS','#fff2cc'),(4,15,'MADEIRAS','#deebf7'),(16,24,'METAIS','#fce4d6')]
    family_by_row={i:(label,fill) for start,end,label,fill in groups for i in range(start,end+1)}
    for index,row in enumerate(rows):
        bottom=y-height;fill=family_by_row.get(index,('', 'white'))[1]
        if index==0:
            box(left,bottom,126,height,fill);text('ÓRGÃO/TECLADO (irmãs)',left,bottom,126,height,size=7.6,strong=True)
        else:
            box(edges[1],bottom,110,height,fill);text(row['name'].upper(),edges[1],bottom,110,height,size=7.6,strong=True)
        values=['(Nas unidades femininas)','(Com famílias)','x',''] if index==0 else ['x' if row['s1']=='Permitido' else '', 'x','x','x' if index<=3 else '']
        for j,value in enumerate(values):
            x=edges[j+2];width=edges[j+3]-x;box(x,bottom,width,height,fill);text(value,x,bottom,width,height,size=7.5,strong=index>0,align=1)
        reason=('Setor 1 e 2: conforme indicado' if index==0 else 'Setor 1: cordas fora dos instrumentos se tornam uma arma' if index<=3 else 'Setor 4: instrumento de sopro - risco biológico' if index==4 else 'Setor 1: instrumento de grande porte' if row['name'] in {'Tuba','Saxofone barítono'} else '')
        box(edges[6],bottom,216,height,fill);text(reason,edges[6],bottom,216,height,size=7.3)
        y=bottom
    table_top=top-42-header_height
    for start,end,label,fill in groups:
        bottom=table_top-(end+1)*height;h=(end-start+1)*height;box(left,bottom,16,h,fill)
        c.saveState();c.translate(left+11,bottom+h/2);c.rotate(90);c.setFillColor(colors.black);c.setFont(bold,8);c.drawCentredString(0,0,label);c.restoreState()
    y-=7;c.setFillColor(colors.HexColor('#ffc000'));c.rect(left,y-12,right-left,12,fill=1,stroke=0)
    text('OBSERVAÇÕES GERAIS',left,y-12,right-left,12,strong=True);y-=17
    notes=[
        'Setor 2 e 4 - TODOS os instrumentos devem tocar na altura da escrita, pois frequências altas causam mal-estar em pacientes em tratamento.',
        'Setor 4 - Hospitais e instituições para idosos: onde se toca ao ar livre, podemos utilizar instrumentos de sopro.',
        'Setor 4 - Atendimento educacional (antigo setor 5): não há canto, não há música. Não levar instrumentos externos. O uso por alunos depende da autorização da instituição.',
        'A incorporação do setor educacional ao setor 4 não estende a ele as permissões de hospitais e instituições para idosos.',
    ]
    for value in notes:
        p=Paragraph(escape(value),ParagraphStyle('note',fontName=regular,fontSize=8,leading=9.5))
        _,h=p.wrap(right-left-18,100);p.drawOn(c,left+18,y-h);y-=h+3
    c.setFont(regular,7);c.setFillColor(colors.HexColor('#4b5563'))
    c.drawString(left,19,'Atualização da distribuição: quatro setores. Demais orientações preservadas do documento fornecido.')
    c.drawRightString(right,19,'D.A.R.P.E. - 1/1');c.showPage();c.save()
    return output.getvalue()
