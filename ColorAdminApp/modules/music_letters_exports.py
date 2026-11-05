"""Relação por modalidade do modelo recebido, com o cabeçalho institucional do projeto."""
import io
from collections import defaultdict
from html import escape
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, KeepTogether
from reportlab.pdfgen import canvas
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from .music_letters_domain import MODALITIES, RESULTS

BLUE = '#1e4b7a'
PALE = '#eaf2f8'

def date_br(value):
    value = str(value or '')[:10]
    return '/'.join(reversed(value.split('-'))) if len(value) == 10 else '—'

def context(filters):
    return ' · '.join(filter(None, [filters.get('municipio') or 'Todos os municípios', filters.get('comum'), filters.get('ano'),
        filters.get('tipo'), MODALITIES.get(filters.get('modalidade')), RESULTS.get(filters.get('resultado')),
        ('De ' + date_br(filters['inicio'])) if filters.get('inicio') else '',
        ('Até ' + date_br(filters['fim'])) if filters.get('fim') else '',
        ('Mês ' + filters['mes']) if filters.get('mes') else '']))

def sections(rows):
    result = defaultdict(list)
    for row in rows:
        event = row.get('event_snapshot') or {}
        key = (row.get('municipio', ''), event.get('data', ''), event.get('evento', ''), row.get('tipo'), row.get('modalidade'))
        result[key].append(row)
    return [(key, sorted(items, key=lambda x: (x.get('comum', ''), x.get('nome', '')))) for key, items in sorted(result.items())]

def row_values(row, number):
    payload = row.get('payload') or {}
    instrument = ' · '.join(filter(None, [payload.get('instrumento'), payload.get('tonalidade')]))
    notes = [row.get('review_notes') or '']
    if row.get('review_result', 'PENDENTE') != 'PENDENTE':
        notes.insert(0, RESULTS.get(row['review_result'], row['review_result']))
    if row.get('modalidade', '').startswith('troca_'):
        notes.append(payload.get('novo_instrumento') or '')
    return [str(number), row.get('nome', ''), row.get('comum', ''), instrument, ' · '.join(filter(None, notes))]

def heading(key):
    city, date, event, kind, modality = key
    label = {'oficializacao': 'PARA EXAME DE OFICIALIZAÇÃO', 'culto': 'PARA TESTE CULTO OFICIAL', 'rjm': 'PARA TESTE RJM', 'troca_necessidade': 'TROCA DE INSTRUMENTO · NECESSIDADE', 'troca_enfermidade': 'TROCA DE INSTRUMENTO · ENFERMIDADE'}.get(modality, MODALITIES.get(modality, modality))
    return f'{city} · {date_br(date)} · {"Organistas" if kind == "organista" else "Músicos"} · {label}'

def make_pdf(rows, responsible, filters):
    output = io.BytesIO()
    page_width, page_height = landscape(A4)
    width = page_width - 56
    issued = timezone.localtime().strftime('%d/%m/%Y %H:%M')
    scope = context(filters)
    cell_style = ParagraphStyle('cell', fontName='Helvetica', fontSize=8, leading=11, textColor=colors.HexColor('#263238'))
    label_style = ParagraphStyle('label', parent=cell_style, fontName='Helvetica-Bold', textColor=colors.HexColor(BLUE), fontSize=10, leading=13, keepWithNext=True)
    para = lambda text, style=cell_style: Paragraph(escape(str(text or '')).replace('\n', '<br/>'), style)
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
                center = page_width / 2
                self.setFillColor(colors.HexColor(BLUE))
                self.setFont('Helvetica-Bold', 15)
                self.drawCentredString(center, page_height - 29, 'CONGREGAÇÃO CRISTÃ NO BRASIL')
                self.setFont('Helvetica', 9)
                self.drawCentredString(center, page_height - 43, 'Regional Itapevi - São Paulo')
                self.setFont('Helvetica-Bold', 11)
                self.drawCentredString(center, page_height - 59, 'MÚSICA · CARTAS DE EXAMES')
                self.setFont('Helvetica', 9)
                self.drawCentredString(center, page_height - 72, 'Relação de candidatos para exame')
                meta = Paragraph(f'<b>Página:</b> {self._pageNumber} de {total}<br/><b>Emissão:</b> {issued}<br/><b>Impresso por:</b> {escape(responsible)}',
                                 ParagraphStyle('meta', fontSize=7, leading=9, alignment=2))
                _, height = meta.wrap(185, 60)
                meta.drawOn(self, page_width - 213, page_height - 19 - height)
                self.setFont('Helvetica', 7)
                self.setFillColor(colors.HexColor('#64748b'))
                self.drawString(28, 18, f'Cartas de exames · {len(rows)} cartas')
                self.drawRightString(page_width - 28, 18, f'Página {self._pageNumber} de {total}')
                canvas.Canvas.showPage(self)
            canvas.Canvas.save(self)
    content = [Table([[para('Recorte: ' + scope + f' · {len(rows)} cartas')]], colWidths=[width],
                     style=[('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(PALE)), ('PADDING', (0, 0), (-1, -1), 7)]), Spacer(1, 12)]
    for key, items in sections(rows):
        header = [para(label, ParagraphStyle('th', parent=cell_style, textColor=colors.white, fontName='Helvetica-Bold'))
                  for label in ['Nº', 'NOME', 'COMUM', 'INSTRUMENTO', 'OBSERVAÇÃO']]
        body = [header] + [[para(value) for value in row_values(row, number)] for number, row in enumerate(items, 1)]
        table = Table(body, colWidths=[width * n for n in (.035, .28, .33, .18, .175)], repeatRows=1, splitByRow=1)
        table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(BLUE)),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f4f6f8')]),
            ('GRID', (0, 0), (-1, -1), .4, colors.HexColor('#c8d1da')), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
        content.extend([KeepTogether([para(heading(key), label_style), Spacer(1, 5)]), table, Spacer(1, 14)])
    if not rows:
        content.append(para('Nenhuma carta preenchida no recorte selecionado.'))
    content.append(para(f'Total de inscrições: {len(rows)} · Cartas emitidas: {len(rows)} · Aprovações confirmadas: {sum(r.get("review_result") == "APROVADO" for r in rows)}', label_style))
    SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=100, bottomMargin=34).build(content, canvasmaker=NumberedCanvas)
    return output.getvalue()

def make_excel(rows, responsible, filters):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Cartas de exames'
    headers = ['Nº', 'Nome', 'Comum', 'Instrumento', 'Observação', 'Município', 'Exame', 'Data', 'Modalidade', 'Resultado']
    issued = timezone.localtime().strftime('%d/%m/%Y %H:%M')
    for index, text in enumerate(['CONGREGAÇÃO CRISTÃ NO BRASIL', 'Regional Itapevi - São Paulo · MÚSICA',
                                  'Cartas de exames · Relação de candidatos', f'{context(filters)} · Emissão: {issued} · Impresso por: {responsible}'], 1):
        sheet.merge_cells(start_row=index, start_column=1, end_row=index, end_column=10)
        cell = sheet.cell(index, 1, text)
        cell.font = Font(size=15 if index == 1 else 10, bold=index < 4, color='FFFFFF' if index < 3 else '1E4B7A')
        cell.fill = PatternFill('solid', fgColor='1E4B7A' if index < 3 else 'EAF2F8')
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
    for column, label in enumerate(headers, 1):
        cell = sheet.cell(6, column, label)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='1E4B7A')
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
    for number, row in enumerate([r for _, items in sections(rows) for r in items], 1):
        event = row.get('event_snapshot') or {}
        values = row_values(row, number) + [row['municipio'], event.get('evento'), date_br(event.get('data')),
                   MODALITIES.get(row.get('modalidade')), RESULTS.get(row.get('review_result', 'PENDENTE'))]
        for column, value in enumerate(values, 1):
            cell = sheet.cell(number + 6, column, value)
            cell.data_type = 's'  # Nomes/observações nunca viram fórmulas de planilha.
            cell.fill = PatternFill('solid', fgColor='FFFFFF' if number % 2 else 'F4F6F8')
            cell.alignment = Alignment(vertical='top', wrap_text=True)
            cell.border = Border(bottom=Side(style='thin', color='D8DEE5'))
    for i, width in enumerate([7, 38, 48, 25, 35, 25, 45, 14, 30, 25], 1):
        sheet.column_dimensions[get_column_letter(i)].width = width
    sheet.row_dimensions[4].height = 32
    sheet.freeze_panes = 'A7'
    sheet.auto_filter.ref = f'A6:J{max(6, len(rows)+6)}'
    sheet.sheet_view.showGridLines = False
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = 'landscape'
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.print_title_rows = '1:6'
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()
