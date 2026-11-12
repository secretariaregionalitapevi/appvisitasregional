"""PDF e Excel institucionais; o mesmo recorte da consulta individual."""
from datetime import datetime
from html import escape
from io import BytesIO
import re
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
from .music_ministry_domain import TITLE, ROLES, KINDS, STATES, code, regional_city

NAVY, PALE = '1E4B7A', 'EAF2F8'
WIDTH, HEIGHT = landscape(A4)
USEFUL = WIDTH - 56
STYLE = ParagraphStyle('ministry-body', fontName='Helvetica', fontSize=8, leading=11, textColor=colors.HexColor('#263238'))


def status_colors(value):
    if value in ('Presente', 'Justificou'):
        return '167853', 'E5F4EC'
    if value in (STATES['SEM_REGISTRO'], 'Não justificou', 'NJ'):
        return 'B4233D', 'FCE8EC'
    if value in (STATES['CONFERIR'], 'Sem encarregado'):
        return '8A5B00', 'FFF3CD'
    if value in (STATES['SEM_DADOS'], STATES['NAO_APLICA'], 'Não informado', 'Enfermo'):
        return '637381', 'F0F2F4'
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
    filters = data.get('filters', {})
    selected_event = filters.get('evento') or ''
    if not selected_event.startswith('legado:') or filters.get('cargo') not in ('', 'ENCARREGADO_LOCAL'):
        return [[row['municipio'], row['nome'].upper(), ' / '.join(ROLES.get(role, role) for role in cell['roles']),
                 cell['comum'], STATES[cell['situacao']]] for row in data['rows'] for cell in row['cells']]

    raw_event_id = selected_event.removeprefix('legado:')
    city_filter = {regional_city(city).casefold() for city in filters.get('municipios', [])}
    common_filter = set(filters.get('comuns', []))
    search = str(filters.get('busca') or '').casefold()
    conductor_labels = {
        'PRESENTE': 'Presente', 'JUSTIFICOU': 'Justificou', 'NAO_JUSTIFICOU': 'Não justificou',
        'NAO_INFORMADO': 'Não informado', 'SEM_ENCARREGADO': 'Sem encarregado', 'ENFERMO': 'Enfermo',
    }
    candidates_by_common = {}
    for row in data['rows']:
        for cell in row['cells']:
            roles = cell.get('roles', row.get('roles', []))
            if cell.get('event_id') == selected_event and 'ENCARREGADO_LOCAL' in roles:
                common = code(cell.get('comum') or row.get('comum'))
                candidates_by_common.setdefault(common, []).append((row, cell))

    conductor_rows, replaced_commons = [], set()
    statuses = sorted((status for status in data.get('legacy_conductor_statuses', [])
                       if status.get('event_id') == raw_event_id),
                      key=lambda status: (status.get('municipio', ''), status.get('comum', '')))
    for status in statuses:
        common_code = code(status.get('comum_codigo') or status.get('comum'))
        label = conductor_labels.get(status.get('situacao'))
        municipality = regional_city(status.get('municipio') or '')
        if (not label or city_filter and municipality.casefold() not in city_filter
                or common_filter and common_code not in common_filter
                or filters.get('situacao') and filters['situacao'] != status.get('situacao')):
            continue
        candidates = candidates_by_common.get(common_code, [])
        if any(cell.get('situacao') == 'PRESENTE' for _, cell in candidates):
            continue
        names = [] if status.get('situacao') == 'SEM_ENCARREGADO' else sorted(
            {row['nome'] for row, _ in candidates}, key=str.casefold)
        name = ' / '.join(names) or '—'
        if search and search not in ' '.join((name, municipality, status.get('comum', ''))).casefold():
            continue
        conductor_rows.append([municipality, name.upper(), 'Conferência por comum',
                               status.get('comum') or common_code, label])
        replaced_commons.add(common_code)

    rows = [[row['municipio'], row['nome'].upper(), ' / '.join(ROLES.get(role, role) for role in cell['roles']),
             cell['comum'], STATES[cell['situacao']]]
            for row in data['rows'] for cell in row['cells']
            if not (code(cell.get('comum') or row.get('comum')) in replaced_commons
                    and 'ENCARREGADO_LOCAL' in cell.get('roles', row.get('roles', [])))]
    return rows + conductor_rows


def summary_rows(data):
    return [[r['municipio'], r['nome'], ' / '.join(ROLES.get(role, role) for role in r['roles']), r['comum'],
             f'{r["present"]}/{r["verified"]}' if r['verified'] else 'Sem conferência',
             r['states'].get('JUSTIFICOU', 0), r['states'].get('SEM_REGISTRO', 0),
             r['states'].get('CONFERIR', 0), r['states'].get('SEM_DADOS', 0)] for r in data['rows']]


def detail_rows(data):
    return [[r['municipio'], r['nome'], str(c['date'])[:10][8:10] + '/' + str(c['date'])[5:7] + '/' + str(c['date'])[:4],
             c['titulo'], KINDS[c['tipo']], c['local'], c['modalidade'].title(), STATES[c['situacao']],
             c.get('observacoes', '')] for r in data['rows'] for c in r['cells']]


def matrix_events(data):
    used = {cell['event_id'] for row in data['rows'] for cell in row['cells']}
    return [event for event in data.get('event_options', []) if event['id'] in used]


def matrix_table(data, events):
    headers = ['Município', 'Nome', 'Comum', 'Ministério / cargo'] + [
        event_heading(event) for event in events]
    rows = []
    for row in data['rows']:
        cells = {cell['event_id']: cell for cell in row['cells']}
        rows.append([row['municipio'], row['nome'], row['comum'],
                     ' / '.join(ROLES.get(role, role) for role in row['roles'])] + [
            STATES['SEM_REGISTRO'] if event['id'] not in cells
            else STATES[cells[event['id']]['situacao']]
            for event in events])
    return headers, rows


def event_heading(event):
    day = '/'.join(str(event['date'])[:10].split('-')[::-1])
    title = re.sub(r'\s*[·-]?\s*' + re.escape(day), '', event['titulo']).strip(' ·-')
    return title + '\n' + day


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
                 p('Relatório de Presença', module), p(report_title if by_event else 'Acompanhamento anual por pessoa', centered)]
        metadata = Paragraph(f'<b>Página:</b> {document.page}<br/><b>Emissão:</b> {now:%d/%m/%Y %H:%M}<br/><b>Recorte:</b> {escape(scope_text(data)[0])}<br/><b>Responsável:</b> Secretaria Regional da Música', meta)

        table = Table([['', title, metadata]], colWidths=[190, USEFUL - 380, 190])
        table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                   ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        _, height = table.wrap(USEFUL, 90)
        table.drawOn(canvas, 28, HEIGHT - 16 - height)
        canvas.setFillColor(colors.HexColor('#526371'))
        canvas.setFont('Helvetica', 7)
        footer_left = f'Regional Itapevi - {data["year"]} - {scope_text(data)[1].title()} - SP'
        footer_right = f'Impresso por: {actor} - Página {document.page}'
        # Keep both sides on the same baseline, even with longer names or scopes.
        from reportlab.pdfbase.pdfmetrics import stringWidth
        total_width = stringWidth(footer_left, 'Helvetica', 7) + stringWidth(footer_right, 'Helvetica', 7)
        canvas.setFont('Helvetica', min(7, 7 * (USEFUL - 20) / max(total_width, 1)))
        canvas.drawString(28, 18, footer_left)
        from .report_identity import printed_by
        printed_by(canvas, actor, WIDTH - 28, 18, f'Página {document.page}')
        canvas.restoreState()
    def table(labels, rows, widths, matrix=False):
        body = [[p(label, heading) for label in labels]]
        absent = ParagraphStyle('absence', parent=STYLE, textColor=colors.HexColor('#B4233D'), fontName='Helvetica-Bold')
        status_col = 4 if labels == EVENT else 7 if labels == DETAIL else -1
        body += [[p(value, ParagraphStyle('status', parent=STYLE, alignment=1 if matrix or labels in (EVENT, DETAIL) and col == status_col else 0, fontName='Helvetica-Bold', textColor=colors.HexColor('#' + status_colors(value)[0])) if (col == status_col or matrix and col >= 4) and status_colors(value) else ParagraphStyle('matrix-cell', parent=STYLE, alignment=1) if matrix and col >= 4 else absent if labels == SUMMARY and col == 4 and str(value).startswith('0/') else STYLE)
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
    events = matrix_events(data)
    story = [band, Spacer(1, 10), p('Uma linha por pessoa; cada coluna representa um encontro. '
             'Pendências e eventos sem dados não são ausências.'), Spacer(1, 8)]
    # Keep event columns readable even when the annual selection grows.
    blocks = [events[start:start + 5] for start in range(0, len(events), 5)] or [[]]
    for index, block in enumerate(blocks):
        if index:
            story.extend([PageBreak(), p(f'Continuação dos eventos · bloco {index + 1} de {len(blocks)}', bold), Spacer(1, 8)])
        labels, rows = matrix_table(data, block)
        fixed = [60, 130, 145, 65]
        widths = fixed + [(USEFUL - sum(fixed)) / len(block)] * len(block) if block else [80, 200, USEFUL - 400, 120]
        story.append(table(labels, rows, widths, matrix=True))
    doc.build(story, onFirstPage=header, onLaterPages=header)
    return stream.getvalue()


def build_excel(data, actor, now):
    workbook = Workbook()
    events = matrix_events(data)
    headers, rows = matrix_table(data, events)
    sheets = [('Acompanhamento', headers, rows, [22, 38, 48, 28] + [25] * len(events))]
    if data.get('filters', {}).get('evento'):
        title = 'Presenças' if data.get('filters', {}).get('situacao') == 'PRESENTE' else 'Participação'
        sheets = [(title, EVENT, event_rows(data), [28, 42, 30, 55, 28])]
    for index, (name, headers, rows, widths) in enumerate(sheets):
        sheet = workbook.active if index == 0 else workbook.create_sheet(name)
        sheet.title = name
        last = get_column_letter(len(headers))
        for row_no, value in [(1, 'CONGREGAÇÃO CRISTÃ NO BRASIL'), (2, 'Regional Itapevi - São Paulo'),
                              (3, TITLE), (4, context(data)), (5, f'Emissão: {now:%d/%m/%Y %H:%M} · Secretaria Regional da Música')]:
            sheet.merge_cells(f'A{row_no}:{last}{row_no}')
            cell = sheet.cell(row_no, 1, value)
            cell.font = Font(size=15 if row_no == 1 else 10, bold=row_no <= 3, color='FFFFFF' if row_no <= 2 else NAVY)
            cell.fill = PatternFill('solid', fgColor=NAVY if row_no <= 2 else PALE)
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            sheet.row_dimensions[row_no].height = 30 if row_no == 4 else 24
        sheet.append([f'Lista do encontro · {len(rows)} registros' if headers == EVENT else
                      'Uma linha por pessoa e uma coluna por encontro. Pendências e eventos sem dados não são ausências.'])
        sheet.merge_cells(f'A6:{last}6')
        sheet.cell(6, 1).alignment = Alignment(wrap_text=True)
        sheet.row_dimensions[6].height = 28
        sheet.append(headers)
        for cell in sheet[7]:
            cell.fill = PatternFill('solid', fgColor=NAVY)
            cell.font = Font(color='FFFFFF', bold=True)
            cell.alignment = Alignment(horizontal='center', wrap_text=True)
        sheet.row_dimensions[7].height = 60 if not data.get('filters', {}).get('evento') else 30
        for row_index, row in enumerate(rows, 8):
            for col, value in enumerate(row, 1):
                cell = sheet.cell(row_index, col, value)
                if isinstance(value, str):
                    cell.data_type = 's'
                cell.alignment = Alignment(vertical='top', wrap_text=True)
                cell.border = Border(bottom=Side(style='thin', color='D8DEE5'))
                if row_index % 2 == 0:
                    cell.fill = PatternFill('solid', fgColor='F4F6F8')
                if (name == 'Acompanhamento' and col >= 5) or (headers == EVENT and col == 5):
                    cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
                    palette = status_colors(value)
                    if palette:
                        cell.font = Font(bold=True, color=palette[0])
                        cell.fill = PatternFill('solid', fgColor=palette[1])
                if headers == SUMMARY and col == 5 and str(value).startswith('0/'):
                    cell.fill = PatternFill('solid', fgColor='FCE8EC')
                    cell.font = Font(bold=True, color='B4233D')
            sheet.row_dimensions[row_index].height = 42 if index == 0 else 60
        for col, width in enumerate(widths, 1):
            sheet.column_dimensions[get_column_letter(col)].width = width
        sheet.freeze_panes = 'E8' if name == 'Acompanhamento' else 'A8'
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
        sheet.oddFooter.right.text = 'Impresso por: ' + actor.replace('&', '&&')
    stream = BytesIO()
    from .report_identity import workbook_identity
    workbook_identity(workbook, actor)
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
