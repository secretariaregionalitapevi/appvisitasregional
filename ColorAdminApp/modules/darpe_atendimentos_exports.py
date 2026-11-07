"""Relatórios de atendimentos com a composição institucional canônica."""
from datetime import datetime
from io import BytesIO
from math import ceil
from urllib.parse import quote
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import requests
from django.http import HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import darpe_atendimentos as attendance
from .darpe import _actor
from .module_access import MODULE_DARPE, can_access_module

NAVY, PALE = '1E4B7A', 'EAF2F8'
TITLE = 'Atendimentos realizados'
HEADERS = ['Data', 'Horário', 'Setor', 'Município', 'Local atendido', 'Comum responsável',
           'Atendente responsável', 'Equipe musical', 'Hinos / Palavra']


def report_values(row):
    responsible = next((p['nome'] for p in row['equipe'] if p['funcao'] == 'atendente'), '—')
    musicians = {p['cadastro_id'] for p in row['equipe'] if p['funcao'] in {'musico', 'organista'}}
    return [datetime.strptime(row['data'], '%Y-%m-%d').strftime('%d/%m/%Y'),
            row['hora_inicio'][:5] + ' às ' + row['hora_fim'][:5], str(row['setor']), row['municipio'],
            row['local'], row['comum'], responsible, str(len(musicians)) + ' músicos / organistas',
            ', '.join(map(str, row.get('hinos', []))) + (' · ' + row['palavra'] if row.get('palavra') else '')]


def report_scope(params):
    parts = [params.get('ano') or 'Todos os anos',
             ('Mês ' + params['mes']) if params.get('mes') else 'Todos os meses']
    for key, label in [('inicio', 'De'), ('fim', 'Até')]:
        if params.get(key):
            parts.append(label + ' ' + datetime.strptime(params[key], '%Y-%m-%d').strftime('%d/%m/%Y'))
    parts += [', '.join(attendance.selected_filters(params, 'municipio')) or 'Todos os municípios',
              ', '.join(attendance.selected_filters(params, 'comum')) or 'Todas as comuns',
              ('Setor ' + params['setor']) if params.get('setor') else 'Todos os setores']
    if params.get('q'):
        parts.append('Pesquisa: ' + params['q'])
    return ' · '.join(parts)


def build_excel(rows, scope, actor, now):
    book = Workbook()
    sheet = book.active
    sheet.title = 'ATENDIMENTOS DARPE'
    for number, label, size, background, foreground in (
        (1, 'CONGREGAÇÃO CRISTÃ NO BRASIL', 15, NAVY, 'FFFFFF'),
        (2, 'Regional Itapevi - São Paulo', 10, NAVY, 'FFFFFF'),
        (3, 'D.A.R.P.E · ' + TITLE, 12, PALE, NAVY),
    ):
        sheet.merge_cells(start_row=number, start_column=1, end_row=number, end_column=9)
        cell = sheet.cell(number, 1, label)
        cell.font = Font(size=size, bold=number != 2, color=foreground)
        cell.fill = PatternFill('solid', fgColor=background)
        cell.alignment = Alignment(horizontal='center', vertical='center')
        sheet.row_dimensions[number].height = 25 if number == 1 else 21
    sheet.merge_cells('A4:E4')
    sheet['A4'] = 'Recorte: ' + scope
    sheet.merge_cells('F4:I4')
    sheet['F4'] = f'<b>Emissão:</b> {now:%d/%m/%Y %H:%M} · Responsável: {actor}'
    sheet.row_dimensions[4].height = 45
    for cell in (sheet['A4'], sheet['F4']):
        cell.alignment = Alignment(wrap_text=True, vertical='center')
        cell.font = Font(size=9, color='536A7D')
    sheet.merge_cells('A5:I5')
    sheet['A5'] = f'{len(rows)} atendimentos realizados'
    sheet['A5'].font = Font(size=9, bold=True, color=NAVY)
    border = Border(bottom=Side(style='thin', color='CCD5DD'))
    for col, label in enumerate(HEADERS, 1):
        cell = sheet.cell(6, col, label)
        cell.fill = PatternFill('solid', fgColor=NAVY)
        cell.font = Font(size=9, bold=True, color='FFFFFF')
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    sheet.row_dimensions[6].height = 30
    widths = [14, 20, 10, 23, 36, 40, 35, 26, 40]
    for number, row in enumerate(rows, 7):
        values = report_values(row)
        for col, value in enumerate(values, 1):
            cell = sheet.cell(number, col, str(value))
            # Nomes e localidades são dados, inclusive quando começam por '='.
            cell.data_type = 's'
            cell.font = Font(size=9, color='263238')
            cell.alignment = Alignment(vertical='center', wrap_text=True)
            cell.border = border
            if number % 2 == 0:
                cell.fill = PatternFill('solid', fgColor='F4F6F8')
        sheet.row_dimensions[number].height = max(38, 13 * max(ceil(len(str(value)) / (width - 3)) for value, width in zip(values, widths)) + 8)
    for col, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(col)].width = width
    sheet.freeze_panes = 'A7'
    sheet.auto_filter.ref = f'A6:I{max(6, sheet.max_row)}'
    sheet.sheet_view.showGridLines = False
    sheet.page_setup.orientation = 'landscape'
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_title_rows = '1:6'
    sheet.print_area = f'A1:I{sheet.max_row}'
    sheet.oddFooter.center.text = 'D.A.R.P.E · Página &P de &N'
    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def build_pdf(rows, scope, actor, now):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfgen import canvas
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    page_width, page_height = landscape(A4)
    usable = page_width - 56
    normal = ParagraphStyle('normal', fontName='Helvetica', fontSize=7.2, leading=9.4, textColor='#263238')
    header = ParagraphStyle('header', parent=normal, fontName='Helvetica-Bold', textColor=colors.white, alignment=TA_CENTER)
    context = ParagraphStyle('context', parent=normal, fontSize=8, leading=10, textColor='#1e4b7a')
    metadata = ParagraphStyle('metadata', parent=normal, fontSize=7, leading=9, alignment=TA_RIGHT)
    def p(value, style=normal):
        return Paragraph(escape(str(value)), style)

    class NumberedCanvas(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.states = []

        def showPage(self):
            self.states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self.states)
            for state in self.states:
                self.__dict__.update(state)
                self.saveState()
                center = page_width / 2
                self.setFillColor(colors.HexColor('#263238'))
                for y, text, font, size, color in (
                    (page_height - 29, 'CONGREGAÇÃO CRISTÃ NO BRASIL', 'Helvetica-Bold', 15, '#263238'),
                    (page_height - 43, 'Regional Itapevi - São Paulo', 'Helvetica', 9, '#263238'),
                    (page_height - 60, 'D.A.R.P.E', 'Helvetica-Bold', 12, '#1e4b7a'),
                    (page_height - 74, TITLE, 'Helvetica', 9, '#263238'),
                ):
                    self.setFont(font, size)
                    self.setFillColor(colors.HexColor(color))
                    self.drawCentredString(center, y, text)
                details = Paragraph(f'<b>Página {self._pageNumber} de {total}</b><br/>'
                                    f'<b>Emissão:</b> {now:%d/%m/%Y %H:%M}<br/>'
                                    f'<b>Recorte:</b> {escape(scope)}<br/><b>Impresso por:</b> {escape(actor)}', metadata)
                _, height = details.wrap(210, 90)
                details.drawOn(self, page_width - 238, page_height - 16 - height)
                self.setFont('Helvetica', 7)
                self.setFillColor(colors.HexColor('#6b7280'))
                self.drawString(28, 19, f'D.A.R.P.E - {len(rows)} atendimentos realizados')
                self.drawRightString(page_width - 28, 19, f'Página {self._pageNumber} de {total}')
                self.restoreState()
                super().showPage()
            super().save()

    data = [[p(label, header) for label in HEADERS]]
    for row in rows:
        data.append([p(value) for value in report_values(row)])
    widths = [52, 65, 32, 65, 110, 120, 100, 80, usable - 624]
    table = LongTable(data, colWidths=widths, repeatRows=1, splitByRow=1, hAlign='CENTER')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e4b7a')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f4f6f8')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#d8dee5')),
        ('LINEBELOW', (0, 0), (-1, -1), .45, colors.HexColor('#c8d1da')),
        ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    band = Table([[p(f'RECORTE DO RELATÓRIO · {scope} · {len(rows)} ATENDIMENTOS', context)]], colWidths=[usable])
    band.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#eaf2f8')),
                             ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=landscape(A4), leftMargin=28, rightMargin=28,
                            topMargin=100, bottomMargin=34, title=TITLE, author=actor)
    doc.build([band, Spacer(1, 8), table], canvasmaker=NumberedCanvas)
    return stream.getvalue()



@never_cache
@require_GET
def export(request, format):
    if not request.session.get('user_id') or not can_access_module(request, MODULE_DARPE):
        return JsonResponse({'error': 'Acesso DARPE não autorizado.'}, status=403)
    try:
        data = attendance.filtered(attendance.visible_records(request), request.GET)
        if not data:
            return JsonResponse({'error': 'Nenhum atendimento no recorte selecionado.'}, status=400)
        data.sort(key=lambda r: (r['data'], r['hora_inicio']), reverse=True)
        now = datetime.now(ZoneInfo('America/Sao_Paulo'))
        scope = report_scope(request.GET)
        actor = _actor(request)['name']
        builder, mime, extension = ((build_excel, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'xlsx')
                                    if format == 'excel' else (build_pdf, 'application/pdf', 'pdf'))
        response = HttpResponse(builder(data, scope, actor, now), content_type=mime)
        filename = f'Atendimentos_DARPE_{now:%d_%m_%Y_%H_%M}.{extension}'
        response['Content-Disposition'] = "attachment; filename*=UTF-8''" + quote(filename)
        response['X-Content-Type-Options'] = 'nosniff'
        return response
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Confira os filtros do relatório.'}, status=400)
    except requests.RequestException as exc:
        return attendance.database_error(exc)
