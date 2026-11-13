"""Institutional individual exam history report."""
import io
from datetime import datetime
from html import escape
from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from .report_identity import printed_by, RESPONSIBLE_HTML


def report_year(request, rows):
    selected = str(request.GET.get('ano') or '')
    years = {str(row.get('data_exame') or '')[:4] for row in rows} - {''}
    return selected if len(selected) == 4 and selected.isdigit() else (
        next(iter(years)) if len(years) == 1 else str(timezone.localdate().year))


def history_pdf(request, rows):
    from .music_exams import actor, export_context, result_label
    now = timezone.localtime()
    stream = io.BytesIO()
    width, height = landscape(A4)
    usable = width - 56
    style = ParagraphStyle('cell', fontName='Helvetica', fontSize=7, leading=9)
    widths = [usable-590, 86, 245, 56, 80, 58, 65]
    # Fit text to its cell so each exam occupies one line, without clipping names.
    def p(value, width=None, approved=False):
        text = ' '.join(str(value or '—').split())
        font = 'Helvetica-Bold' if approved else 'Helvetica'
        size = min(7, 7*(width-12)/max(stringWidth(text, font, 7), 1)) if width else 7
        cell_style = ParagraphStyle('value', parent=style, fontName=font,
                                    fontSize=size, alignment=1 if approved else 0,
                                    textColor='#087a58' if approved else '#263238')
        return Paragraph(escape(text), cell_style)
    context = export_context(request)
    year = report_year(request, rows)
    def page(canvas, doc):
        center = []
        for text, size, font, leading in [
            ('CONGREGAÇÃO CRISTÃ NO BRASIL', 15, 'Helvetica-Bold', 18),
            ('Regional Itapevi - São Paulo', 9, 'Helvetica', 12),
            ('MÚSICA', 12, 'Helvetica-Bold', 16),
            ('Histórico individual de Exames e Testes', 9, 'Helvetica', 12)]:
            center.append(Paragraph(text, ParagraphStyle('title', fontName=font,
                          fontSize=size, leading=leading, alignment=1, textColor='#1e4b7a')))
        meta = Paragraph(f'Página {doc.page}<br/>Emissão: {now:%d/%m/%Y %H:%M}<br/>Recorte: Histórico individual<br/>{RESPONSIBLE_HTML}',
                         ParagraphStyle('meta', fontName='Helvetica', fontSize=7, leading=10, alignment=2))
        header = Table([['', center, meta]], colWidths=[190, usable-380, 190])
        header.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),
                                    ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),
                                    ('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
        _, header_height = header.wrap(usable, 80)
        header.drawOn(canvas, 28, height-16-header_height)
        canvas.setFillColor(colors.HexColor('#1e4b7a'))
        canvas.setFont('Helvetica', 7)
        canvas.drawString(28, 17, f'Exames - Regional Itapevi - {year}')
        printed_by(canvas, actor(request), width-28, page=f'Página {doc.page}')
    headers = ['Aluno(a)', 'Município', 'Comum', 'Instrumento', 'Exame', 'Data', 'Resultado']
    heading_style = ParagraphStyle('head', parent=style, textColor=colors.white, fontName='Helvetica-Bold', alignment=1)
    data = [[Paragraph(escape(x), heading_style) for x in headers]]
    for r in rows:
        raw_date = r.get('data_exame')
        date = datetime.strptime(raw_date[:10], '%Y-%m-%d').strftime('%d/%m/%Y') if raw_date else '—'
        values = [r.get('nome_aluno'), r.get('municipio'), r.get('comum'),
                  r.get('instrumento'), r.get('tipo_exame'), date, result_label(r)]
        data.append([p(value, widths[column], column == 6 and value in {'APROVADO','APROVADA'})
                     for column, value in enumerate(values)])
    if not rows:
        data.append([p('Nenhum exame no recorte.')] + [p('') for _ in headers[1:]])
    table = Table(data, colWidths=widths, repeatRows=1, splitByRow=1)
    table.setStyle(TableStyle([('BACKGROUND', (0,0),(-1,0), colors.HexColor('#1e4b7a')),
                               ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f4f6f8')]),
                               ('GRID',(0,0),(-1,-1),.4,colors.HexColor('#c8d1da')),
                               ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),4),
                               ('BOTTOMPADDING',(0,0),(-1,-1),4)]))
    context_table = Table([[p(f'{len(rows)} registros · {context}')]], colWidths=[usable])
    context_table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#eaf2f8')),
                                      ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
    SimpleDocTemplate(stream, pagesize=(width,height), leftMargin=28,rightMargin=28,topMargin=84,bottomMargin=34).build([context_table,table], onFirstPage=page,onLaterPages=page)
    response = HttpResponse(stream.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Historico_Exames_{now:%d_%m_%Y_%H_%M}.pdf"'
    return response
