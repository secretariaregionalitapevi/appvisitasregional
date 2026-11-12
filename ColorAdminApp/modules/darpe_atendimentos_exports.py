from .report_identity import printed_by, workbook_identity
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
    workbook_identity(book, actor);book.save(stream)
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
                                    f'<b>Recorte:</b> {escape(scope)}<br/><b>Responsável:</b> Secretaria Regional da Música', metadata)
                _, height = details.wrap(210, 90)
                details.drawOn(self, page_width - 238, page_height - 16 - height)
                self.setFont('Helvetica', 7)
                self.setFillColor(colors.HexColor('#6b7280'))
                self.drawString(28, 19, f'D.A.R.P.E - {len(rows)} atendimentos realizados')
                printed_by(self, actor, page_width - 28, 19, f'Página {self._pageNumber} de {total}')
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


def build_papeleta_pdf(record, actor, now):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfgen import canvas
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    page_width, page_height = A4
    usable = page_width - 56
    label_style = ParagraphStyle(
        'PapeletaLabel', fontName='Helvetica-Bold', fontSize=8, leading=10,
        textColor='#1e4b7a',
    )
    value_style = ParagraphStyle(
        'PapeletaValue', fontName='Helvetica', fontSize=8, leading=10,
        textColor='#263238',
    )
    header_style = ParagraphStyle(
        'PapeletaTableHeader', fontName='Helvetica-Bold', fontSize=8,
        leading=10, textColor=colors.white, alignment=TA_CENTER,
    )
    metadata_style = ParagraphStyle(
        'PapeletaMetadata', fontName='Helvetica', fontSize=6.5, leading=8,
        alignment=TA_RIGHT, textColor='#263238',
    )

    def paragraph(value, style=value_style):
        return Paragraph(escape(str(value or '—')).replace('\n', '<br/>'), style)

    def field(label, value):
        return [paragraph(label, label_style), paragraph(value)]

    class PapeletaCanvas(canvas.Canvas):
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
                for y, text, font, size, color in (
                    (page_height - 29, 'CONGREGAÇÃO CRISTÃ NO BRASIL',
                     'Helvetica-Bold', 15, '#263238'),
                    (page_height - 43, 'Regional Itapevi - São Paulo',
                     'Helvetica', 9, '#263238'),
                    (page_height - 60, 'D.A.R.P.E', 'Helvetica-Bold', 12, '#1e4b7a'),
                    (page_height - 74, 'Papeleta de atendimento',
                     'Helvetica', 9, '#263238'),
                ):
                    self.setFont(font, size)
                    self.setFillColor(colors.HexColor(color))
                    self.drawCentredString(center, y, text)
                details = Paragraph(
                    f'<b>Página:</b> {self._pageNumber} de {total}<br/>'
                    f'<b>Emissão:</b> {now:%d/%m/%Y %H:%M}<br/>'
                    f'<b>Data:</b> {datetime.strptime(row_data, "%Y-%m-%d"):%d/%m/%Y}<br/>'
                    f'<b>Responsável:</b> Secretaria Regional da Música',
                    metadata_style,
                )
                _, metadata_height = details.wrap(165, 80)
                details.drawOn(self, page_width - 28 - 165,
                               page_height - 16 - metadata_height)
                self.setFont('Helvetica', 7)
                self.setFillColor(colors.HexColor('#6b7280'))
                self.drawString(28, 19, 'D.A.R.P.E · Papeleta de atendimento')
                printed_by(self, actor, page_width - 28, 19, f'Página {self._pageNumber} de {total}')
                self.restoreState()
                super().showPage()
            super().save()

    row_data = record['data']
    content = [[paragraph('ATENDIMENTO D.A.R.P.E.', header_style),
                paragraph(datetime.strptime(row_data, '%Y-%m-%d').strftime('%d/%m/%Y'),
                          ParagraphStyle(
                              'PapeletaDate', fontName='Helvetica-Bold', fontSize=9,
                              leading=12, textColor=colors.white, alignment=TA_RIGHT,
                          ))]]
    banner = Table(content, colWidths=[usable - 90, 90])
    banner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1e4b7a')),
        ('BOX', (0, 0), (-1, -1), .6, colors.HexColor('#1e4b7a')),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    def people_for(*roles):
        return ', '.join(
            person.get('nome', '') for person in record.get('equipe', [])
            if person.get('funcao') in roles and person.get('nome')
        ) or '—'

    fields = [
        field('Horário', record['hora_inicio'][:5] + ' às ' + record['hora_fim'][:5]),
        field('Setor', f"Setor {record['setor']}"),
        field('Local', record['local']),
        field('Município', record['municipio']),
        field('Comum do responsável', record['comum']),
        field('Atendente', people_for('atendente')),
        field('Orações', people_for('oracao')),
        field('Músicos', people_for('musico', 'organista')),
        field('Colaboradores', people_for('colaborador')),
        field('Hinos', ', '.join(map(str, record.get('hinos', []))) or '—'),
    ]
    for label, key in (('WhatsApp', 'whatsapp'), ('Outro telefone', 'telefone')):
        if record.get(key):
            fields.append(field(label, record[key]))
    fields.extend([
        field('Palavra', record.get('palavra')),
        field('Irmão da palavra', people_for('palavra')),
        field('Participação', record.get('participacao')),
        field('Obs.', record.get('observacoes')),
    ])

    prayer_labels = [
        ('enfermidades', 'Enfermidade(s)'), ('acidentados', 'Acidentado(s)'),
        ('tribulacoes', 'Tribulação(ões)'), ('familias', 'Família(s)'),
        ('causas', 'Causa(s)'), ('testemunhados', 'Testemunhado(s)'),
        ('viagens', 'Viagem(ns)'),
    ]
    prayers = [[
        paragraph('PEDIDOS DE ORAÇÃO', header_style), '', '', '',
    ]]
    prayer_values = record.get('pedidos_oracao') or {}
    for index in range(0, len(prayer_labels), 2):
        cells = []
        for key, label in prayer_labels[index:index + 2]:
            value = prayer_values.get(key, 0)
            cells.extend([paragraph(label, label_style),
                          paragraph('Todas' if value == 'todas' else value)])
        if len(cells) == 2:
            cells.extend([paragraph(''), paragraph('')])
        prayers.append(cells)

    def detail_table(data, widths, header_rows=0):
        table = Table(data, colWidths=widths, repeatRows=header_rows, hAlign='LEFT')
        styles = [
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LINEBELOW', (0, 0), (-1, -1), .6, colors.HexColor('#8b9aaa')),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]
        if header_rows:
            styles.extend([
                ('SPAN', (0, 0), (-1, 0)),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e4b7a')),
                ('BOX', (0, 0), (-1, 0), .6, colors.HexColor('#1e4b7a')),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('TOPPADDING', (0, 0), (-1, 0), 6),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#eaf2f8')),
                ('BOX', (0, 1), (-1, -1), .5, colors.HexColor('#c8d1da')),
                ('INNERGRID', (0, 1), (-1, -1), .4, colors.HexColor('#c8d1da')),
                ('ALIGN', (1, 1), (1, -1), 'CENTER'),
                ('ALIGN', (3, 1), (3, -1), 'CENTER'),
            ])
        else:
            styles.append(('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#eaf2f8')))
        table.setStyle(TableStyle(styles))
        return table

    stream = BytesIO()
    doc = SimpleDocTemplate(
        stream, pagesize=A4, leftMargin=28, rightMargin=28,
        topMargin=94, bottomMargin=34, title='Papeleta de atendimento',
        author=actor,
    )
    doc.build([
        banner, Spacer(1, 5),
        detail_table(fields, [112, usable - 112]), Spacer(1, 8),
        detail_table(prayers, [usable * .36, usable * .14,
                               usable * .36, usable * .14], header_rows=1),
    ], canvasmaker=PapeletaCanvas)
    return stream.getvalue()


def export_papeleta_pdf(request, record_id):
    if not request.session.get('user_id') or not can_access_module(request, MODULE_DARPE):
        return JsonResponse({'error': 'Acesso DARPE não autorizado.'}, status=403)
    try:
        rows = attendance.rows(attendance.TABLE, {'id': 'eq.' + str(record_id)})
        if not rows or not attendance.in_scope(attendance.user_scope(request), rows[0]):
            return JsonResponse({'error': 'Atendimento não encontrado no seu escopo.'}, status=404)
        now = datetime.now(ZoneInfo('America/Sao_Paulo'))
        response = HttpResponse(
            build_papeleta_pdf(rows[0], _actor(request)['name'], now),
            content_type='application/pdf',
        )
        filename = f"Papeleta_DARPE_{datetime.strptime(rows[0]['data'], '%Y-%m-%d').strftime('%d_%m_%Y')}.pdf"
        response['Content-Disposition'] = "attachment; filename*=UTF-8''" + quote(filename)
        response['Cache-Control'] = 'no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
    except requests.RequestException as exc:
        return attendance.database_error(exc)


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
