"""Institutional individual exam history report."""
import io
from html import escape
from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from .report_identity import printed_by, RESPONSIBLE_HTML


def history_pdf(request, rows):
    from .music_exams import actor, export_context, result_label
    now = timezone.localtime()
    stream = io.BytesIO()
    width, height = landscape(A4)
    usable = width - 56
    style = ParagraphStyle('cell', fontName='Helvetica', fontSize=7, leading=9)
    def p(value):
        return Paragraph(escape(str(value or '—')), style)
    context = export_context(request)
    def page(canvas, doc):
        center = width / 2
        canvas.setFillColor(colors.HexColor('#1e4b7a'))
        for y, text, size, font in [(height-28, 'CONGREGAÇÃO CRISTÃ NO BRASIL', 15, 'Helvetica-Bold'),
                                     (height-42, 'Regional Itapevi - São Paulo', 9, 'Helvetica'),
                                     (height-59, 'MÚSICA', 12, 'Helvetica-Bold'),
                                     (height-73, 'Histórico individual de Exames e Testes', 9, 'Helvetica')]:
            canvas.setFont(font, size)
            canvas.drawCentredString(center, y, text)
        meta = Paragraph(f'Página {doc.page}<br/>Emissão: {now:%d/%m/%Y %H:%M}<br/>Recorte: Histórico individual<br/>{RESPONSIBLE_HTML}',
                         ParagraphStyle('meta', fontName='Helvetica', fontSize=7, leading=10, alignment=2))
        meta.wrap(190, 70)
        meta.drawOn(canvas, width-218, height-92)
        canvas.setFont('Helvetica', 7)
        canvas.drawString(28, 17, 'Música · Histórico individual')
        printed_by(canvas, actor(request), width-28, page=f'Página {doc.page}')
    headers = ['Aluno(a)', 'Município / comum', 'Instrumento', 'Exame', 'Data', 'Resultado', 'Evento da agenda']
    heading_style = ParagraphStyle('head', parent=style, textColor=colors.white, fontName='Helvetica-Bold', alignment=1)
    data = [[Paragraph(escape(x), heading_style) for x in headers]]
    for r in rows:
        raw_date = r.get('data_exame')
        from datetime import datetime
        date = datetime.strptime(raw_date[:10], '%Y-%m-%d').strftime('%d/%m/%Y') if raw_date else '—'
        data.append([p(r.get('nome_aluno')), p(' / '.join(filter(None, [r.get('municipio'), r.get('comum')]))),
                     p(r.get('instrumento')), p(r.get('tipo_exame')), p(date), p(result_label(r)),
                     p(r.get('agenda_evento_titulo') or 'Registro histórico')])
    if not rows:
        data.append([p('Nenhum exame no recorte.')] + [p('') for _ in headers[1:]])
    table = Table(data, colWidths=[usable*.19, usable*.23, usable*.10, usable*.12, usable*.075, usable*.11, usable*.175], repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND', (0,0),(-1,0), colors.HexColor('#1e4b7a')),
                               ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f4f6f8')]),
                               ('GRID',(0,0),(-1,-1),.4,colors.HexColor('#c8d1da')),
                               ('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),
                               ('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    context_table = Table([[p(f'{len(rows)} registros · {context}')]], colWidths=[usable])
    context_table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#eaf2f8')),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
    SimpleDocTemplate(stream, pagesize=(width,height), leftMargin=28,rightMargin=28,topMargin=100,bottomMargin=34).build([context_table,table], onFirstPage=page,onLaterPages=page)
    response = HttpResponse(stream.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Historico_Exames_{now:%d_%m_%Y_%H_%M}.pdf"'
    return response
