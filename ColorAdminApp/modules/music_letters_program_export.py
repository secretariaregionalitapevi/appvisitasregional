from .report_identity import printed_by, workbook_identity
"""Relatório documental com a identidade institucional dos relatórios de cartas."""
import io
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from django.utils import timezone
from .music_letters_exports import context, date_br
from .music_letters_domain import MODALITIES
from .music_letters_program import program_summary, LABELS

def make_program_excel(rows, responsible, filters):
    rows = [r for r in rows if r.get('program_assessment')]
    summary = program_summary(rows)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Programa Mínimo'
    headers = ['Nome', 'Município', 'Comum', 'Etapa da carta', 'Data do exame',
               'Situação documental', 'MSA', 'Método', 'Hinário', 'Consulta ao GEM']
    stamp = timezone.localtime().strftime('%d/%m/%Y %H:%M')
    percent = summary['unconfirmed_percent']
    description = ('Sem base avaliada' if percent is None else f'{percent:g}% sem comprovação completa')
    titles = ['CONGREGAÇÃO CRISTÃ NO BRASIL', 'Regional Itapevi - São Paulo · MÚSICA',
              'Cartas de exames · Programa Mínimo (consulta atual ao GEM)',
              f'{context(filters)} · Emissão: {stamp} · Impresso por: {responsible}',
              f'{description} · Base: {summary["assessed"]} alunos/etapas avaliados; {summary["total"]} no recorte. '
              f'{summary["counts"]["pending"]} com requisitos pendentes; {summary["counts"]["review"]} aguardando validação. '
              'Cada aluno conta uma vez por etapa. Sem dados/consulta excluídos do percentual.']
    for number, title in enumerate(titles, 1):
        sheet.merge_cells(start_row=number, start_column=1, end_row=number, end_column=10)
        cell = sheet.cell(number, 1, title)
        cell.data_type = 's'
        cell.font = Font(size=15 if number == 1 else 10, bold=number < 4, color='FFFFFF' if number < 3 else '1E4B7A')
        cell.fill = PatternFill('solid', fgColor='1E4B7A' if number < 3 else 'EAF2F8')
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        sheet.row_dimensions[number].height = 32 if number >= 4 else 24
    for column, title in enumerate(headers, 1):
        cell = sheet.cell(7, column, title)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='1E4B7A')
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
    from .music_letters_activity import activity_report_note
    area_labels = {'ok': 'Documentado', 'missing': 'Requisito pendente', 'review': 'Validação pendente'}
    for number, row in enumerate(rows, 8):
        assessment = row['program_assessment']
        areas = {r['area']: area_labels[r['status']] + '\nExigido: ' + r['required'] + '\nDocumentado: ' + r['current'] for r in assessment['requirements']}
        values = [row.get('nome'), row.get('municipio'), row.get('comum'), MODALITIES.get(row.get('modalidade')),
                  date_br((row.get('event_snapshot') or {}).get('data')), '\n'.join(filter(None, [LABELS[assessment['status']], activity_report_note(row)])),
                  areas.get('MSA', 'Não consultado'), areas.get('Método', 'Não consultado'),
                  areas.get('Hinário', 'Não consultado'), assessment['checked_at']]
        for column, value in enumerate(values, 1):
            cell = sheet.cell(number, column, value)
            cell.data_type = 's'
            cell.alignment = Alignment(vertical='top', wrap_text=True)
            cell.fill = PatternFill('solid', fgColor='FFFFFF' if number % 2 else 'F4F6F8')
            cell.border = Border(bottom=Side(style='thin', color='D8DEE5'))
        sheet.row_dimensions[number].height = 180 if activity_report_note(row) else 126
    for column, width in enumerate([34, 25, 44, 22, 16, 25, 40, 42, 40, 22], 1):
        sheet.column_dimensions[get_column_letter(column)].width = width
    sheet.freeze_panes = 'A8'
    sheet.auto_filter.ref = f'A7:J{max(7, len(rows) + 7)}'
    sheet.sheet_view.showGridLines = False
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = 'landscape'
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.print_title_rows = '1:7'
    sheet.print_options.horizontalCentered = True
    sheet.print_area = f'A1:J{max(7, len(rows) + 7)}'
    sheet.oddFooter.center.text = 'Música · Programa Mínimo · Página &P de &N'
    output = io.BytesIO()
    workbook_identity(workbook, responsible);workbook.save(output)
    return output.getvalue()


def make_program_pdf(rows, responsible, filters):
    """Cabeçalho em três colunas e tabela integral, conforme REPORT_EXPORT_STANDARD."""
    from html import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
    from reportlab.pdfgen import canvas
    rows = [r for r in rows if r.get('program_assessment')]
    summary = program_summary(rows)
    scope = context(filters)
    stamp = timezone.localtime().strftime('%d/%m/%Y %H:%M')
    page_width, page_height = landscape(A4)
    width = page_width - 56
    blue, pale = colors.HexColor('#1e4b7a'), colors.HexColor('#eaf2f8')
    body = ParagraphStyle('program-body', fontName='Helvetica', fontSize=7.5, leading=10, textColor=colors.HexColor('#263238'))
    def para(text, **overrides):
        style = ParagraphStyle('program-cell', parent=body, **overrides) if overrides else body
        return Paragraph(escape(str(text or '')).replace('\n', '<br/>'), style)
    def rich(label, value):
        return Paragraph('<b>' + escape(label) + '</b> ' + escape(str(value or '')).replace('\n', '<br/>'), body)

    class InstitutionalCanvas(canvas.Canvas):
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
                center = [para('CONGREGAÇÃO CRISTÃ NO BRASIL', fontSize=15, leading=18, fontName='Helvetica-Bold', alignment=1),
                          para('Regional Itapevi - São Paulo', fontSize=9, leading=12, alignment=1),
                          para('MÚSICA · CARTAS DE EXAMES', fontSize=11, leading=15, fontName='Helvetica-Bold', textColor=blue, alignment=1),
                          para('Programa Mínimo · Resumo técnico dos músicos', fontSize=9, leading=12, alignment=1)]
                metadata = Paragraph(f'<b>Página:</b> {self._pageNumber} de {total}<br/>'
                    f'<b>Emissão:</b> {stamp}<br/><b>Recorte:</b> {escape(scope)}<br/>'
                    f'<b>Responsável:</b> Secretaria Regional da Música',
                    ParagraphStyle('program-meta', parent=body, fontSize=7, leading=9, alignment=2))
                header = Table([['', center, metadata]], colWidths=[190, width - 380, 190])
                header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
                _, height = header.wrap(width, 82)
                header.drawOn(self, 28, page_height - 16 - height)
                self.setFont('Helvetica', 7)
                self.setFillColor(colors.HexColor('#64748b'))
                self.drawString(28, 18, 'Música · Programa Mínimo · Consulta atual ao GEM')
                printed_by(self, responsible, page_width - 28, 18, f'Página {self._pageNumber} de {total}')
                canvas.Canvas.showPage(self)
            canvas.Canvas.save(self)

    percent = summary['unconfirmed_percent']
    percentage = 'Sem base avaliada' if percent is None else f'{percent:g}% sem comprovação completa'
    counts = summary['counts']
    context_table = Table([[para('Recorte: ' + scope)],
        [para(f'{percentage} · {counts["eligible"]} documentados · {counts["pending"]} com requisitos pendentes · {counts["review"]} aguardando validação', fontName='Helvetica-Bold', textColor=blue)],
        [para(f'Base: {summary["assessed"]} alunos/etapas avaliados, de {summary["total"]} no recorte. '
              f'{counts["no_data"] + counts["unlinked"]} sem histórico/vínculo; {counts["unavailable"]} consultas indisponíveis. '
              'Cada aluno conta uma vez por etapa. Sem dados/consulta excluídos do percentual.')],
        [para('Consulta documental atual ao GEM; não representa a situação histórica na emissão. '
              'Somente músicos em Culto Oficial ou Oficialização. A emissão da carta continua permitida.')]], colWidths=[width])
    context_table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), pale),
        ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
    content = [context_table, Spacer(1, 12)]
    headers = [para(label, fontName='Helvetica-Bold', textColor=colors.white, alignment=1)
               for label in ['ALUNO / CARTA', 'MSA', 'MÉTODO', 'HINÁRIO']]
    table_rows = [headers]
    from .music_letters_activity import activity_report_note
    area_labels = {'ok': 'Documentado', 'missing': 'Requisito pendente', 'review': 'Validação pendente'}
    for row in rows:
        assessment = row['program_assessment']
        identity = [para(row.get('nome'), fontName='Helvetica-Bold', textColor=blue),
                    para(row.get('comum')), para(row.get('municipio')),
                    rich('Etapa:', MODALITIES.get(row.get('modalidade'))),
                    rich('Exame:', date_br((row.get('event_snapshot') or {}).get('data'))),
                    rich('Situação:', LABELS[assessment['status']]), rich('Consulta:', assessment.get('checked_at'))]
        if activity_report_note(row):
            identity.append(para(activity_report_note(row), fontSize=7, leading=9))
        areas = {r['area']: [para(area_labels[r['status']], fontName='Helvetica-Bold', textColor=blue),
                 rich('Exigido:', r['required']), rich('Documentado:', r['current'])] for r in assessment['requirements']}
        table_rows.append([identity] + [areas.get(area, [para(LABELS[assessment['status']])]) for area in ('MSA', 'Método', 'Hinário')])
    if rows:
        table = Table(table_rows, colWidths=[width * fraction for fraction in (.23, .25, .27, .25)], repeatRows=1, splitByRow=1)
        table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), blue),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f4f6f8')]),
            ('GRID', (0, 0), (-1, -1), .4, colors.HexColor('#c8d1da')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 7),
            ('RIGHTPADDING', (0, 0), (-1, -1), 7), ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7)]))
        content.append(table)
    else:
        content.append(para('Nenhuma carta de músico em Culto Oficial ou Oficialização no recorte selecionado.'))
    output = io.BytesIO()
    SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=28, rightMargin=28,
                      topMargin=100, bottomMargin=34).build(content, canvasmaker=InstitutionalCanvas)
    return output.getvalue()
