"""Exportações do mesmo recorte autorizado do painel de justificativas.

Composição reutilizada das referências institucionais de music_ministry_reports
e gem_sync_admin.export_report, conforme docs/REPORT_EXPORT_STANDARD.md.
"""
from datetime import datetime
from html import escape
from io import BytesIO
from math import ceil
from zoneinfo import ZoneInfo

import requests
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import music_justification_portal as portal
from .music_events_filenames import download_header
from .report_identity import RESPONSIBLE_HTML, printed_by, workbook_identity

HEADERS = ['Evento / Data', 'Município / Comum', 'Nome Completo / Cargo', 'Motivo', 'Registro', 'Contabilização']
NAVY, PALE = '1E4B7A', 'EAF2F8'
WIDTH, HEIGHT = landscape(A4)
USEFUL = WIDTH - 56
STYLE = ParagraphStyle('justification-body', fontName='Helvetica', fontSize=7.5, leading=10,
                       textColor=colors.HexColor('#263238'))


def day(value):
    return '/'.join(str(value)[:10].split('-')[::-1])


def report_rows(items):
    rows = []
    for r in items:
        received = datetime.fromisoformat(r['created_at'].replace('Z', '+00:00')).astimezone(ZoneInfo('America/Sao_Paulo'))
        rows.append([f"{r['evento_titulo']}\n{day(r['data_evento'])} {r['hora']} · {r['familia']}",
                     f"{r['municipio']}\n{r['comum']}", f"{r['nome']}\n{r.get('cargo') or 'Cargo a Conferir'}", r['motivo'],
                     received.strftime('%d/%m/%Y %H:%M'), 'Justificou - vinculado' if r.get('destino') else 'Aguardando vínculo'])
    return rows


def scope(filters):
    pieces = [filters.get('municipio') or 'Todos os municípios']
    if filters.get('comum'):
        pieces.append(filters['comum'])
    return ' · '.join(pieces)


def p(value, style=STYLE):
    return Paragraph(escape(str(value)).replace('\n', '<br/>'), style)


def build_pdf(data, filters, actor, now):
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=100, bottomMargin=34)
    def header(canvas, document):
        canvas.saveState()
        centered = ParagraphStyle('center', parent=STYLE, fontSize=9, leading=12, alignment=1)
        entity = ParagraphStyle('entity', parent=centered, fontName='Helvetica-Bold', fontSize=15, leading=18, textColor=colors.black)
        module = ParagraphStyle('module', parent=centered, fontName='Helvetica-Bold', fontSize=11, leading=13, textColor=colors.HexColor('#1E4B7A'))
        meta = ParagraphStyle('meta', parent=STYLE, alignment=2, fontSize=7, leading=10)
        title = [p('CONGREGAÇÃO CRISTÃ NO BRASIL', entity), p('Regional Itapevi - São Paulo', centered),
                 p('Música', module), p('Justificativas dos eventos musicais', centered)]
        metadata = Paragraph(f'<b>Página:</b> {document.page}<br/><b>Emissão:</b> {now:%d/%m/%Y %H:%M}<br/>'
                             f'<b>Recorte:</b> {escape(filters.get("municipio") or "Regional Itapevi")}<br/>{RESPONSIBLE_HTML}', meta)
        table = Table([['', title, metadata]], colWidths=[190, USEFUL-380, 190])
        table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]))
        _, height = table.wrap(USEFUL, 90)
        table.drawOn(canvas, 28, HEIGHT-16-height)
        canvas.setFillColor(colors.HexColor('#526371')); canvas.setFont('Helvetica', 7)
        canvas.drawString(28, 18, 'Música · Justificativas · Regional Itapevi')
        printed_by(canvas, actor, WIDTH-28, 18, f'Página {document.page}')
        canvas.restoreState()
    context = f'<b>Recorte:</b> {escape(scope(filters))}<br/><b>Justificativas:</b> {len(data["items"])} · <b>Aguardando vínculo:</b> {data["metrics"]["pendentes"]}'
    selected = next((e['titulo'] for e in data['options']['events'] if e['id'] == filters.get('evento')), None)
    if selected:
        context += '<br/><b>Evento:</b> ' + escape(selected)
    band = Table([[Paragraph(context, STYLE)]], colWidths=[USEFUL])
    band.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#EAF2F8')),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    heading = ParagraphStyle('heading', parent=STYLE, fontName='Helvetica-Bold', textColor=colors.white, alignment=1)
    body = [[p(h, heading) for h in HEADERS]]
    body += [[p(v) for v in row] for row in report_rows(data['items'])]
    if len(body) == 1:
        body.append([p('Nenhuma justificativa neste recorte.')] + ['']*5)
    table = Table(body, colWidths=[132,132,112,USEFUL-562,86,100], repeatRows=1, splitByRow=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#1E4B7A')),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F4F6F8')]),
        ('GRID',(0,0),(-1,-1),.35,colors.HexColor('#C8D1DA')),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    doc.build([band,Spacer(1,12),table], onFirstPage=header, onLaterPages=header)
    return stream.getvalue()


def build_excel(data, filters, actor, now):
    workbook = Workbook(); sheet = workbook.active; sheet.title = 'Justificativas'
    selected = next((e['titulo'] for e in data['options']['events'] if e['id'] == filters.get('evento')), 'Todos os eventos')
    titles = ['CONGREGAÇÃO CRISTÃ NO BRASIL','Regional Itapevi - São Paulo · Música',
              'Justificativas dos eventos musicais', scope(filters) + ' · ' + selected,
              f'Emissão: {now:%d/%m/%Y %H:%M} · Responsável: Secretaria Regional da Música',
              f"{len(data['items'])} justificativas · {data['metrics']['pendentes']} aguardando vínculo ao painel"]
    for row, title in enumerate(titles,1):
        sheet.merge_cells(start_row=row,start_column=1,end_row=row,end_column=6)
        cell = sheet.cell(row,1,title); cell.data_type = 's'
        cell.font = Font(size=15 if row == 1 else 10,bold=row <= 3,color='FFFFFF' if row <= 2 else NAVY)
        cell.fill = PatternFill('solid',fgColor=NAVY if row <= 2 else PALE)
        cell.alignment = Alignment(horizontal='center',vertical='center',wrap_text=True)
        sheet.row_dimensions[row].height = 36 if row == 4 else 26
    sheet.append(HEADERS)
    for cell in sheet[7]:
        cell.fill = PatternFill('solid',fgColor=NAVY); cell.font = Font(bold=True,color='FFFFFF',size=10)
        cell.alignment = Alignment(horizontal='center',vertical='center',wrap_text=True)
    sheet.row_dimensions[7].height = 30
    widths = [38,32,27,40,20,23]
    for index, row in enumerate(report_rows(data['items']),8):
        line_count = 1
        for column,value in enumerate(row,1):
            cell = sheet.cell(index,column,value); cell.data_type = 's'
            cell.font = Font(size=10); cell.alignment = Alignment(vertical='top',wrap_text=True)
            cell.border = Border(bottom=Side(style='thin',color='D8DEE5'))
            if index % 2 == 0: cell.fill = PatternFill('solid',fgColor='F4F6F8')
            line_count = max(line_count,sum(max(1,ceil(len(line)/(widths[column-1]-3))) for line in value.split('\n')))
        sheet.row_dimensions[index].height = max(30,(line_count+1)*13)
    for index,width in enumerate(widths,1): sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = 'A8'; sheet.auto_filter.ref = f'A7:F{max(7,sheet.max_row)}'
    sheet.sheet_view.showGridLines = False; sheet.print_area = f'A1:F{sheet.max_row}'; sheet.print_title_rows = '1:7'
    sheet.page_setup.orientation = 'landscape'; sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth,sheet.page_setup.fitToHeight = 1,0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.oddFooter.center.text = 'Regional Itapevi · Página &P de &N'
    workbook_identity(workbook,actor)
    stream = BytesIO(); workbook.save(stream); return stream.getvalue()


@require_GET
def export(request, file_format):
    if not portal.events._allowed(request):
        return JsonResponse({'error':'Acesso não autorizado.'},status=403)
    if file_format not in {'pdf','excel'}:
        return JsonResponse({'error':'Formato inválido.'},status=404)
    try:
        data = portal.dashboard_data(request)
        profile = request.session.get('user_profile') or {}
        actor = profile.get('full_name') or profile.get('nome') or profile.get('name') or profile.get('email') or 'Usuário'
        now = datetime.now(ZoneInfo('America/Sao_Paulo'))
        content = build_pdf(data,request.GET,actor,now) if file_format == 'pdf' else build_excel(data,request.GET,actor,now)
        extension = 'pdf' if file_format == 'pdf' else 'xlsx'
        response = HttpResponse(content,content_type='application/pdf' if extension == 'pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = download_header(f'[RELATÓRIO] JUSTIFICATIVAS_{now:%d_%m_%Y_%H_%M}.{extension}')
        return response
    except (ValueError,TypeError,KeyError) as exc:
        return JsonResponse({'error':str(exc)},status=400)
    except requests.RequestException:
        return JsonResponse({'error':'Não foi possível exportar. Confira a conexão e a migração 062.'},status=502)
