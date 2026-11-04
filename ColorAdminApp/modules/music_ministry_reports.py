"""PDF e Excel institucionais; o mesmo recorte da consulta individual."""
from datetime import datetime
from html import escape
from io import BytesIO
from zoneinfo import ZoneInfo

from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak

from .music_events_filenames import report_scope
from .music_ministry_domain import TITLE, ROLES, KINDS, STATES

NAVY, PALE = '1E4B7A', 'EAF2F8'
WIDTH, HEIGHT = landscape(A4)
USEFUL = WIDTH - 56
STYLE = ParagraphStyle('ministry-body', fontName='Helvetica', fontSize=8, leading=11, textColor=colors.HexColor('#263238'))


def status_colors(value):
    if value in ('Presente', 'Justificou'):
        return '167853', 'E5F4EC'
    if value in (STATES['SEM_REGISTRO'], 'NJ'):
        return 'B4233D', 'FCE8EC'
    return None


def p(text, style=STYLE):
    return Paragraph(escape('' if text is None else str(text).replace('Encarregado local', 'Encarregado Local')).replace('\n', '<br/>'), style)


def scope_text(data):
    cities = data.get('filters', {}).get('municipios') or data['selected_cities']
    from .music_events_dashboard import regional_city
    cities = sorted({regional_city(c) for c in cities})
    short = report_scope(cities)
    return short, 'Toda a Regional' if short == 'REGIONAL ITAPEVI' else ' / '.join(cities)


def context(data):
    filters = data.get('filters', {})
    parts = [f'Ano: {data["year"]}', scope_text(data)[1], ROLES.get(filters.get('cargo'), 'Todos os cargos'),
             KINDS.get(filters.get('tipo'), 'Todos os tipos de evento')]
    if filters.get('comuns'):
        parts.append('Comuns: ' + ', '.join(filters['comuns']))
    if filters.get('busca'):
        parts.append('Busca: ' + filters['busca'])
    event = selected_event(data)
    if event:
        parts.append(event['titulo'] + ' - ' + '/'.join(str(event['date'])[:10].split('-')[::-1]))
    if filters.get('situacao'):
        parts.append(STATES[filters['situacao']])
    return ' · '.join(parts)


def selected_event(data):
    key = data.get('filters', {}).get('evento')
    return next((event for event in data.get('event_options', []) if event['id'] == key), None)


def event_rows(data):
    return [[row['municipio'], row['nome'], ' / '.join(ROLES.get(role, role) for role in cell['roles']),
             cell['comum'], STATES[cell['situacao']]] for row in data['rows'] for cell in row['cells']]


def summary_rows(data):
    return [[r['municipio'], r['nome'], ' / '.join(ROLES.get(role, role) for role in r['roles']), r['comum'],
             f'{r["present"]}/{r["verified"]}' if r['verified'] else 'Sem conferência',
             r['states'].get('JUSTIFICOU', 0), r['states'].get('SEM_REGISTRO', 0),
             r['states'].get('CONFERIR', 0), r['states'].get('SEM_DADOS', 0)] for r in data['rows']]


def detail_rows(data):
    return [[r['municipio'], r['nome'], str(c['date'])[:10][8:10] + '/' + str(c['date'])[5:7] + '/' + str(c['date'])[:4],
             c['titulo'], KINDS[c['tipo']], c['local'], c['modalidade'].title(), STATES[c['situacao']],
             c.get('observacoes', '')] for r in data['rows'] for c in r['cells']]


SUMMARY = ['Município', 'Nome', 'Cargo', 'Comum', 'Presenças / conferidos', 'Justificou', 'Sem presença', 'Pendentes', 'Sem dados']
DETAIL = ['Município', 'Nome', 'Data', 'Evento', 'Tipo', 'Local', 'Modalidade', 'Situação', 'Observações']
EVENT = ['Município', 'Nome', 'Cargo', 'Comum de origem', 'Situação']


def build_pdf(data, actor, now):
    by_event = bool(data.get('filters', {}).get('evento'))
    report_title = 'Lista de presentes' if data.get('filters', {}).get('situacao') == 'PRESENTE' else 'Participação no encontro'
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=100, bottomMargin=34)
    heading = ParagraphStyle('heading', parent=STYLE, textColor=colors.white, fontName='Helvetica-Bold', alignment=1)
    bold = ParagraphStyle('bold', parent=STYLE, fontName='Helvetica-Bold', textColor=colors.HexColor('#1E4B7A'))
    def header(canvas, document):
        canvas.saveState()
        entity = ParagraphStyle('entity', parent=bold, fontSize=15, leading=18, alignment=1, textColor=colors.black)
        centered = ParagraphStyle('centered', parent=STYLE, fontSize=9, leading=12, alignment=1)
        module = ParagraphStyle('module', parent=bold, fontSize=11, leading=13, alignment=1)
        meta = ParagraphStyle('meta', parent=STYLE, alignment=2, fontSize=7, leading=10)
        title = [p('CONGREGAÇÃO CRISTÃ NO BRASIL', entity), p('Regional Itapevi - São Paulo', centered),
                 p('Relatório de Presença', module), p(report_title if by_event else 'Histórico anual de participação', centered)]
        metadata = Paragraph(f'<b>Página:</b> {document.page}<br/><b>Emissão:</b> {now:%d/%m/%Y %H:%M}<br/><b>Recorte:</b> {escape(scope_text(data)[0])}<br/><b>Impresso por:</b> {escape(actor)}', meta)

        table = Table([['', title, metadata]], colWidths=[190, USEFUL - 380, 190])
        table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                   ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        _, height = table.wrap(USEFUL, 90)
        table.drawOn(canvas, 28, HEIGHT - 16 - height)
        canvas.setFillColor(colors.HexColor('#526371'))
        canvas.setFont('Helvetica', 7)
        canvas.drawString(28, 18, f'Ministério da Música · {data["year"]} · {scope_text(data)[0]}')
        canvas.drawRightString(WIDTH - 28, 18, f'Regional Itapevi · Página {document.page}')
        canvas.restoreState()
    def table(labels, rows, widths):
        body = [[p(label, heading) for label in labels]]
        absent = ParagraphStyle('absence', parent=STYLE, textColor=colors.HexColor('#B4233D'), fontName='Helvetica-Bold')
        status_col = 4 if labels == EVENT else 7 if labels == DETAIL else -1
        body += [[p(value, ParagraphStyle('status', parent=STYLE, fontName='Helvetica-Bold', textColor=colors.HexColor('#' + status_colors(value)[0])) if col == status_col and status_colors(value) else absent if labels == SUMMARY and col == 4 and str(value).startswith('0/') else STYLE)
                  for col, value in enumerate(row)] for row in rows]
        if not rows:
            body.append([p('Nenhum registro para o recorte.')] + [''] * (len(labels) - 1))
        result = Table(body, colWidths=widths, repeatRows=1, splitByRow=1)
        result.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E4B7A')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F4F6F8')]),
            ('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#C8D1DA')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
        return result
    event = selected_event(data)
    event_title = event['titulo'] if event else 'Todos os eventos do ano'
    event_date = '/'.join(str(event['date'])[:10].split('-')[::-1]) if event else str(data['year'])
    selected_common_count = len({(r['municipio'], r['comum'].split(' - ')[0]) for r in data['rows']})
    band_text = (f'<b>Evento:</b> {escape(event_title)}<br/>'
                 f'<b>Data / período:</b> {event_date} &nbsp; | &nbsp; <b>Municípios:</b> {escape(scope_text(data)[1])}<br/>'
                 f'<b>Cargo:</b> {escape(ROLES.get(data.get("filters", {}).get("cargo"), "Todos os cargos").replace("Encarregado local", "Encarregado Local"))} &nbsp; | &nbsp; '
                 f'<b>Situação:</b> {escape(STATES.get(data.get("filters", {}).get("situacao"), "Todas as situações"))}<br/>'
                 f'<b>Pessoas na lista:</b> {len(data["rows"])} &nbsp; | &nbsp; <b>Comuns na lista:</b> {selected_common_count}')
    band = Table([[Paragraph(band_text, STYLE)]], colWidths=[USEFUL])
    band.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#EAF2F8')),
                             ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    if by_event:
        story = [band, Spacer(1, 12), p(f'{report_title} · {len(data["rows"])} pessoas', bold), Spacer(1, 8),
                 table(EVENT, event_rows(data), [100, 195, 115, USEFUL - 505, 95])]
        doc.build(story, onFirstPage=header, onLaterPages=header)
        return stream.getvalue()
    story = [band, Spacer(1, 10), p('Resumo individual', bold), Spacer(1, 6),
             p('Presenças / conferidos considera somente encontros com presença, justificativa ou ausência conferida. '
               'Pendências, eventos sem dados e não aplicáveis ficam fora do denominador. '
               'O cadastro atual não comprova convocação histórica.'), Spacer(1, 8)]
    story.append(table(SUMMARY, summary_rows(data), [76, 110, 75, USEFUL - 559, 72, 58, 56, 56, 56]))
    story.extend([PageBreak(), p('Histórico por pessoa e evento', bold), Spacer(1, 8),
                  table(DETAIL, detail_rows(data), [65, 106, 54, 115, 80, 65, 57, 76, USEFUL - 618])])
    doc.build(story, onFirstPage=header, onLaterPages=header)
    return stream.getvalue()


def build_excel(data, actor, now):
    workbook = Workbook()
    sheets = [
        ('Resumo', SUMMARY, summary_rows(data), [25, 35, 26, 44, 23, 15, 18, 15, 15]),
        ('Histórico', DETAIL, detail_rows(data), [25, 35, 15, 40, 28, 25, 18, 28, 55])]
    if data.get('filters', {}).get('evento'):
        sheets = [('Presenças', EVENT, event_rows(data), [28, 42, 30, 55, 28])]
    for index, (name, headers, rows, widths) in enumerate(sheets):
        sheet = workbook.active if index == 0 else workbook.create_sheet(name)
        sheet.title = name
        last = get_column_letter(len(headers))
        for row_no, value in [(1, 'CONGREGAÇÃO CRISTÃ NO BRASIL'), (2, 'Regional Itapevi - São Paulo'),
                              (3, TITLE), (4, context(data)), (5, f'Emissão: {now:%d/%m/%Y %H:%M} · Impresso por: {actor}')]:
            sheet.merge_cells(f'A{row_no}:{last}{row_no}')
            cell = sheet.cell(row_no, 1, value)
            cell.font = Font(size=15 if row_no == 1 else 10, bold=row_no <= 3, color='FFFFFF' if row_no <= 2 else NAVY)
            cell.fill = PatternFill('solid', fgColor=NAVY if row_no <= 2 else PALE)
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            sheet.row_dimensions[row_no].height = 30 if row_no == 4 else 24
        sheet.append([f'Lista do encontro · {len(rows)} registros' if headers == EVENT else
                      'Presenças / conferidos exclui pendências e eventos sem dados. Cadastro atual não comprova convocação histórica.'])
        sheet.merge_cells(f'A6:{last}6')
        sheet.cell(6, 1).alignment = Alignment(wrap_text=True)
        sheet.row_dimensions[6].height = 28
        sheet.append(headers)
        for cell in sheet[7]:
            cell.fill = PatternFill('solid', fgColor=NAVY)
            cell.font = Font(color='FFFFFF', bold=True)
            cell.alignment = Alignment(horizontal='center', wrap_text=True)
        for row_index, row in enumerate(rows, 8):
            for col, value in enumerate(row, 1):
                cell = sheet.cell(row_index, col, value)
                if isinstance(value, str):
                    cell.data_type = 's'
                cell.alignment = Alignment(vertical='top', wrap_text=True)
                cell.border = Border(bottom=Side(style='thin', color='D8DEE5'))
                if row_index % 2 == 0:
                    cell.fill = PatternFill('solid', fgColor='F4F6F8')
                if headers == SUMMARY and col == 5 and str(value).startswith('0/'):
                    cell.fill = PatternFill('solid', fgColor='FCE8EC')
                    cell.font = Font(bold=True, color='B4233D')
            sheet.row_dimensions[row_index].height = 42 if index == 0 else 60
        for col, width in enumerate(widths, 1):
            sheet.column_dimensions[get_column_letter(col)].width = width
        sheet.freeze_panes = 'A8'
        sheet.auto_filter.ref = f'A7:{last}{max(7, sheet.max_row)}'
        sheet.sheet_view.showGridLines = False
        sheet.page_setup.orientation = 'landscape'
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
        sheet.page_setup.fitToWidth, sheet.page_setup.fitToHeight = 1, 0
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.print_title_rows = '1:7'
        sheet.print_options.horizontalCentered = True
        sheet.print_area = f'A1:{last}{sheet.max_row}'
        sheet.oddFooter.center.text = 'Regional Itapevi · Página &P de &N'
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def export_response(data, request, file_format):
    profile = request.session.get('user_profile') or {}
    actor = profile.get('full_name') or profile.get('nome') or profile.get('name') or 'Usuário'
    now = datetime.now(ZoneInfo('America/Sao_Paulo'))
    content = build_pdf(data, actor, now) if file_format == 'pdf' else build_excel(data, actor, now)
    extension = 'pdf' if file_format == 'pdf' else 'xlsx'
    scope = report_scope(data.get('filters', {}).get('municipios') or data['selected_cities'], filename=True)
    response = HttpResponse(content, content_type='application/pdf' if extension == 'pdf' else
                            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    event = selected_event(data)
    from .music_events_filenames import download_header
    if event:
        labels = {'REUNIAO_MINISTERIO': 'REUNIÃO_MUSICAL', 'ENSAIO_REGIONAL': 'ENSAIO_REGIONAL',
                  'ENSAIO_MUNICIPAL': 'ENSAIO_MUNICIPAL', 'REUNIAO_TECNICA': 'REUNIÃO_TÉCNICA', 'CAPACITACAO': 'CAPACITAÇÃO'}
        label = labels.get(event.get('tipo'), 'PRESENÇA')
        if str(event.get('local', '')).upper() in ('BRÁS', 'BRAS'):
            label += '_BRÁS'
        stamp = '_'.join(str(event['date'])[:10].split('-')[::-1])
        filename = f'[RELATÓRIO] {label}_{stamp}.{extension}'
    else:
        filename = f'[RELATÓRIO] PRESENÇA_{scope.upper()}_{data["year"]}.{extension}'
    response['Content-Disposition'] = download_header(filename)
    response['Cache-Control'] = 'private, no-store'
    return response
